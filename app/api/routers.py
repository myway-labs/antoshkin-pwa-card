# app/api/routers.py

"""
API routers for the loyalty card application.

Defines all HTTP endpoints for:
- User registration and verification
- SMS code sending and validation
- Session management (login, logout, me)
- Card display
- Admin panel and data export
"""

import csv
import hashlib
import io
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_async_db
from app.models import Session, User
from app.schemas import (
    SMSRequest,
    SMSResponse,
    UserCreate,
    UserOut,
    UserVerify,
    VerifyResponse,
)
from app.services.auth_dispatcher import send_verification_code
from app.services.check_call_service import initiate_check_call, simulate_incoming_call
from app.services.crud import create_user, get_user_by_phone
from app.services.session_service import create_session, delete_session
from app.services.sms_service import verify_sms_code

logger = logging.getLogger(__name__)

# Create router instance
router = APIRouter()

# Cookie configuration
COOKIE_NAME = "session_token"
COOKIE_MAX_AGE = 2592000  # 30 days in seconds
COOKIE_PATH = "/"

# ============== Page Routes (GET) ==============


@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """
    Root endpoint - serves the main registration page.

    Args:
        request: FastAPI request object (required for templates)

    Returns:
        Rendered HTML template for the registration page
    """
    return request.state.templates.TemplateResponse("index.html", {
        "request": request,
        "auth_method": settings.AUTH_METHOD
    })


@router.get("/splash", response_class=HTMLResponse)
async def splash_page(request: Request):
    """
    Splash screen for PWA - displayed when app is launched from home screen.

    Args:
        request: FastAPI request object (required for templates)

    Returns:
        Rendered splash screen HTML template
    """
    return request.state.templates.TemplateResponse("splash.html", {"request": request})


@router.get("/verify", response_class=HTMLResponse)
async def verify_page(request: Request):
    """
    Verification page - SMS code input.

    Args:
        request: FastAPI request object (required for templates)

    Returns:
        Rendered HTML template for the verification page
    """
    return request.state.templates.TemplateResponse(
        "verify.html",
        {
            "request": request,
            "auth_method": settings.AUTH_METHOD,
            "sms_test_mode": settings.SMS_TEST_MODE,
            # Номер телефона для звонка будет получен из localStorage (сохранён после /api/auth/initiate)
            "call_phone": None,
        },
    )


@router.get("/admin", response_class=HTMLResponse)
async def admin_panel(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    search: str | None = None,
    page: int = 1,
    per_page: int = 50,
):
    """
    Admin panel - displays list of all users with pagination and search.

    Args:
        request: FastAPI request object
        db: AsyncSession database session
        search: Optional phone number search query (filters entire database)
        page: Page number for pagination (default: 1)
        per_page: Number of users per page (default: 50)

    Returns:
        Rendered admin panel HTML template
    """
    # Ensure page is at least 1
    page = max(1, page)

    # Build base query with search filter
    stmt = select(User)
    if search:
        stmt = stmt.where(User.phone.ilike(f"%{search}%"))

    # Get total count (before pagination)
    count_stmt = select(func.count()).select_from(User)
    if search:
        count_stmt = count_stmt.where(User.phone.ilike(f"%{search}%"))

    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar() or 0

    # Calculate offset and total pages
    offset = (page - 1) * per_page
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1

    # Get users for current page (ordered by created_at desc)
    stmt = stmt.order_by(User.created_at.desc()).offset(offset).limit(per_page)
    result = await db.execute(stmt)
    users = result.scalars().all()

    # Get verified count (from entire database, not just filtered)
    verified_stmt = select(func.count()).select_from(User).where(User.is_verified == True)
    verified_result = await db.execute(verified_stmt)
    verified_count = verified_result.scalar() or 0

    return request.state.templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "users": users,
            "total": total,
            "verified_count": verified_count,
            "search": search or "",
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "offset": offset,
        },
    )


@router.get("/admin/export")
async def export_users(_request: Request, db: AsyncSession = Depends(get_async_db)):
    """
    Export all users to CSV file.

    Args:
        _request: FastAPI request object
        db: AsyncSession database session

    Returns:
        CSV file with user data for download
    """
    stmt = select(User).order_by(User.created_at.desc())
    result = await db.execute(stmt)
    users = result.scalars().all()

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow(["id", "full_name", "phone", "is_verified", "created_at"])

    # Write user data
    for user in users:
        writer.writerow([
            user.id,
            user.full_name,
            user.phone,
            user.is_verified,
            user.created_at.isoformat(),
        ])

    # Create response with CSV file
    csv_content = output.getvalue()
    output.close()

    return StreamingResponse(
        io.BytesIO(csv_content.encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=users.csv"},
    )


@router.get("/card/{phone}", response_class=HTMLResponse)
async def card_page(request: Request, phone: str, db: AsyncSession = Depends(get_async_db)):
    """
    Display user's loyalty card with QR code.

    Args:
        request: FastAPI request object
        phone: Normalized phone number
        db: AsyncSession database session

    Returns:
        Rendered card HTML template (only for verified users)
    """
    user = await get_user_by_phone(db, phone)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.is_verified:
        # Redirect to verification page if not verified
        return request.state.templates.TemplateResponse(
            "verify.html",
            {
                "request": request,
                "phone": phone,
                "auth_method": settings.AUTH_METHOD,
                "sms_test_mode": settings.SMS_TEST_MODE,
                "call_phone": None,
            },
        )

    return request.state.templates.TemplateResponse(
        "card.html",
        {"request": request, "user": user},
    )


# ============== API Routes (POST) ==============


@router.post("/api/register", response_model=UserOut)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_async_db)):
    """
    Register new user or return existing user data.

    Args:
        user_data: User registration data (full_name, phone)
        db: AsyncSession database session

    Returns:
        User data (existing or newly created)

    Raises:
        HTTPException: If phone number format is invalid
    """
    # Check if user already exists
    existing_user = await get_user_by_phone(db, user_data.phone)

    if existing_user:
        # Return existing user data
        return existing_user

    # Create new user with race condition handling
    try:
        new_user = await create_user(db, user_data.full_name, user_data.phone)
        return new_user
    except IntegrityError:
        # Race condition: another request created the user
        await db.rollback()
        # Fetch and return the existing user
        existing_user = await get_user_by_phone(db, user_data.phone)
        if existing_user:
            return existing_user
        # Should not happen, but raise if user still not found
        raise HTTPException(status_code=500, detail="Failed to create user")


@router.post("/api/auth/initiate", response_model=SMSResponse)
async def initiate_auth_endpoint(
    sms_data: SMSRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Универсальный эндпоинт для инициации любой авторизации (SMS, Flash Call, Check Call).

    Автоматически выбирает метод на основе AUTH_METHOD в конфиге.

    Args:
        sms_data: Phone number for verification
        request: FastAPI request object (for IP extraction)
        db: AsyncSession database session

    Returns:
        {
            "sent": true,
            "call_phone": str (только для check_call)
        }

    Raises:
        HTTPException: If user not found or initiation failed

    Note:
        - Для check_call: делает запрос к SMS.ru, сохраняет check_id, НЕ верифицирует
        - Для SMS/Flash Call: отправляет код пользователю
        - В тестовом режиме check_call НЕ делает автосимуляцию - это делается через /api/auth/simulate-call
    """
    user = await get_user_by_phone(db, sms_data.phone)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Handle Check Call mode
    if settings.AUTH_METHOD == "check_call":
        success, check_id, message, call_phone = await initiate_check_call(db, user, user.phone)

        if not success:
            raise HTTPException(status_code=500, detail=message)

        # ВАЖНО: В тестовом режиме НЕ делаем автосимуляцию!
        # Симуляция вызывается отдельно через /api/auth/simulate-call когда пользователь нажмёт "Позвонить"
        logger.info(f"[API] Check call initiated for {user.phone}, check_id: {check_id}")
        await db.commit()

        # Возвращаем call_phone для фронтенда
        return SMSResponse(sent=True, call_phone=call_phone)

    # SMS/Flash Call mode: use dispatcher service
    success, code, message = await send_verification_code(user.phone, request)

    if not success:
        raise HTTPException(status_code=500, detail=message)

    # Save verification data to database
    user.sms_code = code
    user.sms_code_expires_at = datetime.utcnow() + timedelta(minutes=5)

    await db.commit()

    return SMSResponse(sent=True)


# Оставляем старый путь для обратной совместимости (redirect)
@router.post("/api/send-sms", response_model=SMSResponse, deprecated=True)
async def send_sms_endpoint_deprecated(
    sms_data: SMSRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Deprecated: используйте /api/auth/initiate вместо этого."""
    return await initiate_auth_endpoint(sms_data, request, db)


@router.post("/api/verify", response_model=VerifyResponse)
async def verify_code(
    verify_data: UserVerify,
    db: AsyncSession = Depends(get_async_db),
    response: Response | None = None,
):
    """
    Verify SMS code and activate user account.

    Args:
        verify_data: Phone number and verification code
        db: AsyncSession database session
        response: FastAPI response object (for setting cookie)

    Returns:
        {"verified": true} if code is valid

    Raises:
        HTTPException: If user not found, code invalid, or expired

    Note:
        All users must enter SMS code for verification, including previously verified users.
        This ensures security when logging in after logout.
    """
    user = await get_user_by_phone(db, verify_data.phone)

    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Verify SMS code using service function
    result = await verify_sms_code(db, user, verify_data.code)

    # Unpack result (supports both (success, msg, user_id) and (success, msg))
    if len(result) == 3:
        success, message, user_id = result[0], result[1], result[2]
    else:
        success, message = result[0], result[1]
        user_id = user.id

    if not success:
        raise HTTPException(status_code=400, detail=message)

    # Create session and set cookie using saved user_id
    token = await create_session(db, user_id)

    # Set HttpOnly cookie
    if response:
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            max_age=COOKIE_MAX_AGE,
            path=COOKIE_PATH,
            httponly=True,
            secure=True,
            samesite="lax",
        )

    return VerifyResponse(verified=True)


# ============== Session API Routes ==============


@router.post("/api/login")
async def login(
    sms_data: SMSRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    _response: Response | None = None,
):
    """
    Login by phone number.

    Logic:
    - Check if phone exists in database
    - If found (any status): send SMS code, return 200 OK (redirect to verify)
    - If not found: return 404 Not Found (frontend should trigger registration)

    Args:
        sms_data: Phone number for login
        request: FastAPI request object (for IP extraction)
        db: AsyncSession database session
        _response: Optional FastAPI response object

    Returns:
        {"sent": true} if SMS was sent successfully

    Raises:
        HTTPException: 404 if user not found (trigger registration)

    Usage (Frontend):
        # Try to login
        const response = await fetch('/api/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({phone: '+79991234567'})
        });

        if (response.status === 404) {
            // User not found - start registration flow
        } else if (response.ok) {
            // SMS sent - redirect to verification page
        }
    """
    # Find user by phone
    user = await get_user_by_phone(db, sms_data.phone)

    if not user:
        # User not found - frontend should trigger registration
        raise HTTPException(status_code=404, detail="User not found")

    # Используем универсальный эндпоинт /api/auth/initiate для всех методов
    # Для check_call это инициирует звонок, для SMS/Flash Call - отправит код
    return await initiate_auth_endpoint(sms_data, request, db)


# ============== Check Call Webhook ==============


@router.post("/api/auth/webhook/sms-ru")
async def sms_ru_webhook(request: Request, db: AsyncSession = Depends(get_async_db)):
    """
    Webhook endpoint for SMS.ru Check Call notifications.

    Receives automatic notifications from SMS.ru when a user completes a check call.
    Updates user verification status based on webhook data.

    Expected POST data from SMS.ru (form-data):
        - data[N]: Multi-line text entries
          Line 1: Event type (callcheck_status)
          Line 2: check_id
          Line 3: status (401 = verified)
          Line 4: unix timestamp
        - hash: SHA256 hash for validation

    Response format from SMS.ru:
        Check call status sent as form data in data[1], data[2], ... data[100].

    Args:
        request: FastAPI request object (for form data)
        db: AsyncSession database session

    Returns:
        Plain text "100" to confirm successful processing (SMS.ru requirement)

    Note:
        SMS.ru sends this webhook when user completes the check call.
        Server marks user as verified and clears sms_check_id.
        IMPORTANT: Must return "100" as plain text, not JSON!
    """
    try:
        # Parse form data from SMS.ru
        form_data = await request.form()

        logger.info(f"[WEBHOOK] Full SMS.ru data: {dict(form_data)}")
        # SMS.ru sends data in data[1], data[2], ... data[100] format
        # Each entry is multi-line text: type\ncheck_id\nstatus\ntimestamp
        api_id = settings.SMS_API_KEY  # Your SMS_API_KEY from SMS.ru

        # Collect all data entries for hash validation
        data_entries = []
        for key, value in form_data.items():
            if key.startswith("data["):
                data_entries.append(str(value))

        # Validate hash if present
        if "hash" in form_data and data_entries:
            # Hash is computed from api_id + concatenation of ALL data entries
            hash_string = api_id + "".join(data_entries)
            expected_hash = hashlib.sha256(hash_string.encode()).hexdigest()

            if form_data["hash"] != expected_hash:
                logger.warning(
                    f"[WEBHOOK] Hash validation failed. Expected: {expected_hash}, Got: {form_data['hash']}"
                )

        # Process each data entry
        for key, value in form_data.items():
            if key.startswith("data["):
                # Split into lines
                lines = str(value).split("\n")

                if len(lines) >= 3:
                    event_type = lines[0].strip()
                    check_id = lines[1].strip()
                    status = lines[2].strip()

                    # Handle callcheck_status events
                    if event_type == "callcheck_status" and status == "401":
                        # Find user by check_id
                        stmt = select(User).where(User.sms_check_id == check_id)
                        result = await db.execute(stmt)
                        user = result.scalar_one_or_none()

                        if user:
                            # Mark user as verified
                            user.is_verified = True
                            user.sms_check_id = None  # Clear check_id after successful verification
                            user.sms_code = None
                            user.sms_code_expires_at = None
                            await db.commit()

        # Always return 100 to confirm receipt (SMS.ru requirement)
        return PlainTextResponse(content="100")

    except Exception:
        return PlainTextResponse(content="100")


@router.post("/api/auth/simulate-call")
async def simulate_call_endpoint(
    sms_data: SMSRequest,
    db: AsyncSession = Depends(get_async_db),
    response: Response | None = None,
):
    """
    Симуляция входящего звонка в тестовом режиме (SMS_TEST_MODE=True).

    Этот эндпоинт вызывается когда пользователь нажимает кнопку "Позвонить" на фронтенде.
    Он эмулирует webhook от SMS.ru: находит пользователя по sms_check_id и верифицирует его.

    Args:
        sms_data: Phone number
        db: AsyncSession database session
        response: FastAPI response object (for setting cookie)

    Returns:
        {"success": true, "message": "OK", "verified": true, "redirect": "/card/{phone}"} если симуляция успешна

    Raises:
        HTTPException: 400 если не тестовый режим или нет активного check_id
    """
    if not settings.SMS_TEST_MODE:
        raise HTTPException(status_code=400, detail="Simulation only available in test mode")

    user = await get_user_by_phone(db, sms_data.phone)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.sms_check_id:
        raise HTTPException(status_code=400, detail="No active check session. Please initiate call first.")

    # Используем сервисный метод для симуляции (передаём phone явно, чтобы избежать lazy loading)
    success, message = await simulate_incoming_call(db, user, sms_data.phone)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    # Сохраняем user.id ДО коммита, чтобы избежать lazy loading после commit
    user_id = user.id

    await db.commit()

    # Create session and set cookie
    token = await create_session(db, user_id)
    if response:
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            max_age=COOKIE_MAX_AGE,
            path=COOKIE_PATH,
            httponly=True,
            secure=True,
            samesite="lax",
        )

    return {
        "success": True,
        "message": "OK",
        "verified": True,
        "redirect": f"/card/{sms_data.phone}",
    }


@router.get("/api/auth/check-call-status")
async def check_call_status(
    phone: str,
    db: AsyncSession = Depends(get_async_db),
    response: Response | None = None,
):
    """
    Check verification status for Check Call method (polling endpoint).

    Frontend polls this endpoint every 2-3 seconds to detect when
    the webhook has updated the user's verification status.

    If user is verified and no session exists, creates a new session and sets cookie.

    IMPORTANT: This endpoint ONLY checks the status of the active sms_check_id.
    It does NOT check user.is_verified flag to prevent bypassing the call verification.
    Even if user.is_verified=True from a previous session, we must wait for the
    webhook to confirm the NEW call before creating a session.

    Args:
        phone: Normalized phone number (+7XXXXXXXXXX)
        db: AsyncSession database session
        response: FastAPI response object (for setting cookie)

    Returns:
        {
            "verified": bool,
            "status": str,  # "pending", "verified", "expired"
            "redirect": str  # "/card/{phone}" if verified
        }

    Usage (Frontend):
        const response = await fetch('/api/auth/check-call-status?phone=+79991234567');
        const data = await response.json();
        if (data.verified) {
            // Redirect to card page
        }
    """
    user = await get_user_by_phone(db, phone)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Explicitly load phone to avoid lazy loading issues in async context
    user_phone = user.phone

    # CRITICAL: Do NOT check user.is_verified here!
    # We must only verify based on the current sms_check_id status.
    # The webhook is the only source of truth for call verification.
    # This prevents bypassing the call by having is_verified=True from a previous session.

    # Check if user was verified by webhook (is_verified=True AND sms_check_id was cleared)
    # The webhook flow is:
    # 1. User initiates call -> sms_check_id is set
    # 2. User calls -> SMS.ru sends webhook with status=401
    # 3. Webhook handler sets is_verified=True AND clears sms_check_id
    # 4. Polling detects is_verified=True with no sms_check_id -> success

    # IMPORTANT: Check this FIRST before checking if sms_check_id exists!
    # If webhook has already confirmed (is_verified=True and sms_check_id=None), we should succeed
    if user.is_verified and not user.sms_check_id:
        # Delete any existing sessions to ensure clean state
        stmt = select(Session).where(Session.user_id == user.id)
        result = await db.execute(stmt)
        existing_sessions = result.scalars().all()

        for old_session in existing_sessions:
            await db.delete(old_session)

        # Create fresh session
        token = await create_session(db, user.id)
        await db.commit()

        # Set cookie when verified
        if response:
            response.set_cookie(
                key=COOKIE_NAME,
                value=token,
                max_age=COOKIE_MAX_AGE,
                path=COOKIE_PATH,
                httponly=True,
                secure=True,
                samesite="lax",
            )

        return {"verified": True, "status": "verified", "redirect": f"/card/{phone}"}

    # Check if there's an active sms_check_id
    if not user.sms_check_id:
        # No active check call session (and not verified by webhook)
        return {"verified": False, "status": "none"}

    # Check if check_id is expired
    if user.sms_code_expires_at and datetime.utcnow() > user.sms_code_expires_at:
        return {"verified": False, "status": "expired"}

    # Still waiting for webhook confirmation (sms_check_id exists, is_verified may be old value)
    return {"verified": False, "status": "pending"}


@router.post("/api/auth/simulate-check-call")
async def simulate_check_call(
    phone: str,
    db: AsyncSession = Depends(get_async_db),
    response: Response | None = None,
):
    """
    Simulate incoming check call in test mode (emulates SMS.ru webhook).

    This endpoint is called by frontend when user clicks "Позвонить" button.
    Only works in test mode (SMS_TEST_MODE=True).

    Args:
        phone: Normalized phone number (+7XXXXXXXXXX)
        db: AsyncSession database session
        response: FastAPI response object (for setting cookie)

    Returns:
        {
            "success": bool,
            "message": str,
            "verified": bool,
            "redirect": str (if verified)
        }

    Logic:
        - Checks if test mode is enabled
        - Finds user by phone
        - Calls simulate_incoming_call service function
        - Commits changes to database
        - Creates session and sets cookie if verified
    """
    if not settings.SMS_TEST_MODE:
        raise HTTPException(status_code=403, detail="Simulation only available in test mode")

    user = await get_user_by_phone(db, phone)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Simulate incoming call (emulates webhook)
    success, message = await simulate_incoming_call(db, user, phone)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    # Commit the verification
    await db.commit()

    # Create session and set cookie
    token = await create_session(db, user.id)
    if response:
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            max_age=COOKIE_MAX_AGE,
            path=COOKIE_PATH,
            httponly=True,
            secure=True,
            samesite="lax",
        )

    return {
        "success": True,
        "message": message,
        "verified": True,
        "redirect": f"/card/{phone}",
    }


# ============== Session API Routes ==============


@router.post("/api/logout")
async def logout(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Logout user (delete session).

    Logic:
    - Get session token from cookie
    - Delete session from database
    - Clear cookie in browser

    Args:
        request: FastAPI request object (for cookie access)
        db: AsyncSession database session

    Returns:
        {"success": true} if logged out successfully
    """
    # Get token from cookie
    token = request.cookies.get(COOKIE_NAME)

    if token:
        # Delete session from database
        await delete_session(db, token)

    # Create response with cookie cleared
    response = Response(content='{"success": true}')
    response.delete_cookie(
        key=COOKIE_NAME,
        path=COOKIE_PATH,
        httponly=True,
        secure=True,
        samesite="lax",
    )

    return response


@router.get("/api/me", response_model=UserOut)
async def get_current_user(
    request: Request,
    _db: AsyncSession = Depends(get_async_db),
):
    """
    Get current authenticated user.

    Logic:
    - Middleware already validated session and set request.state.current_user
    - Just return the user if authenticated

    Args:
        request: FastAPI request object (for cookie access)
        _db: AsyncSession database session

    Returns:
        User data if authenticated

    Raises:
        HTTPException: 401 Unauthorized if not authenticated

    Usage (Frontend):
        # Check if user is authenticated
        const response = await fetch('/api/me', {
            credentials: 'include'  // Send cookies automatically
        });

        if (response.ok) {
            const user = await response.json();
            // User is authenticated
        } else if (response.status === 401) {
            // Not authenticated - show login form
        }
    """
    # Get user from request.state (injected by middleware)
    user = request.state.current_user

    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Return user data
    return user
