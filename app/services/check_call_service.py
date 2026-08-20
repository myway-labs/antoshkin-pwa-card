# app/services/check_call_service.py

"""
Check Call verification service.

Handles Check Call authorization flow via SMS.ru API.
In Check Call mode, the user makes a call to a specified number for verification.

Functions:
- initiate_check_call: Request a check call from SMS.ru (async)
- verify_check_call_status: Check verification status via API (async, optional polling)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import cast

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import User

# Configure logging
logger = logging.getLogger(__name__)


async def initiate_check_call(
    _db: AsyncSession, user: User, phone: str
) -> tuple[bool, str, str, str | None]:
    """
    Initiate Check Call verification via SMS.ru API.

    Args:
        db: AsyncSession database session
        user: User object to update
        phone: Normalized phone number (+7XXXXXXXXXX)

    Returns:
        Tuple of (success: bool, check_id: str, message: str, call_phone: Optional[str])
        - check_id: Verification ID (or TEST stub in test mode)
        - call_phone: Phone number to call (only in production mode)
        - message: Status or error description

    Note:
        In test mode (SMS_TEST_MODE=True):
        - Makes real request to SMS.ru to get actual check_id
        - Saves check_id to user.sms_check_id (does NOT commit)
        - Does NOT auto-verify — webhook simulation handled separately via /api/auth/simulate-check-call
        - Caller must commit the session

        In production:
        - Makes request to SMS.ru /callcheck/add endpoint
        - Saves check_id to user.sms_check_id for webhook verification
        - Does NOT commit — caller must commit the session

    SMS.ru API:
        GET https://sms.ru/callcheck/add
        Params: api_id, phone, json

    Response format:
        {
            "status": "OK",
            "status_code": 100,
            "check_id": "201737-542",
            "call_phone": "78005008275",
            "call_phone_pretty": "+7 (800) 500-8275",
            "call_phone_html": "<a href=\"callto:78005008275\">+7 (800) 500-8275</a>"
        }

    Usage:
        success, check_id, message, call_phone = await initiate_check_call(db, user, "+79991234567")
        if success:
            user.sms_check_id = check_id
            await db.commit()
    """
    # Test mode: make REAL request to SMS.ru to get actual check_id
    # Does NOT auto-verify — simulation is done via separate endpoint
    if settings.SMS_TEST_MODE:
        logger.info(f"[CHECK_CALL] Initiated for {phone} (test mode with real API)")

        # Make real request to get actual check_id
        url = "https://sms.ru/callcheck/add"
        params = {
            "api_id": settings.SMS_API_KEY,
            "phone": phone.lstrip('+'),
            "json": 1
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=10.0)
                _ = response.raise_for_status()
                data = cast(dict[str, object], response.json())

                if str(data.get("status")) == "OK":
                    real_check_id = str(data.get("check_id", ""))
                    call_phone = cast(str | None, data.get("call_phone"))
                    logger.info(
                        "[CHECK_CALL] Got real check_id %s in test mode", real_check_id
                    )
                    print(f"[CHECK_CALL] SMS.ru response (test mode): {data}")

                    # Save real check_id and expiration (DO NOT commit here)
                    # Do NOT auto-verify — wait for simulate_check_call endpoint
                    user.sms_check_id = real_check_id
                    user.sms_code_expires_at = datetime.now(timezone.utc).replace(
                        tzinfo=None
                    ) + timedelta(minutes=5)
                    # is_verified remains False until simulate_check_call is invoked

                    logger.info(
                        "[CHECK_CALL] Test mode: check_id saved for %s, waiting for call simulation",
                        user.phone,
                    )
                    return (
                        True,
                        real_check_id,
                        "Check call initiated (test mode)",
                        call_phone,
                    )
                else:
                    error_msg = str(data.get("status_text", "Unknown error"))
                    logger.error("[CHECK_CALL] SMS.ru error in test mode: %s", error_msg)
                    return False, "", f"SMS.ru error: {error_msg}", None
        except Exception as e:
            logger.error(f"[CHECK_CALL] Request error in test mode: {e!s}")
            return False, "", f"Network error: {e!s}", None

    # Production mode: request check call via SMS.ru API using httpx
    url = "https://sms.ru/callcheck/add"
    params = {
        "api_id": settings.SMS_API_KEY,
        "phone": phone.lstrip('+'),  # Remove + prefix for API
        "json": 1
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10.0)
            _ = response.raise_for_status()
            data = cast(dict[str, object], response.json())

            # Log full API response for debugging
            logger.debug("[CHECK_CALL] SMS.ru response for %s: %s", phone, data)
            print(f"[CHECK_CALL] SMS.ru response: {data}")

            if str(data.get("status")) == "OK":
                check_id = str(data.get("check_id", ""))
                call_phone = cast(str | None, data.get("call_phone"))
                call_phone_pretty = str(data.get("call_phone_pretty", call_phone))

                # Update user with check_id for webhook verification (DO NOT commit here)
                user.sms_check_id = check_id
                user.sms_code_expires_at = datetime.now(timezone.utc).replace(
                    tzinfo=None
                ) + timedelta(minutes=5)

                logger.info(
                    "[CHECK_CALL] Initiated for %s, check_id: %s, call_phone: %s",
                    phone,
                    check_id,
                    call_phone_pretty,
                )
                return True, check_id, "Check call initiated", call_phone
            else:
                error_msg = str(data.get("status_text", "Unknown error"))
                status_code = str(data.get("status_code", "N/A"))
                logger.error(
                    "[CHECK_CALL] SMS.ru error for %s: %s (code: %s)",
                    phone,
                    error_msg,
                    status_code,
                )
                return False, "", f"SMS.ru error: {error_msg}", None

    except httpx.TimeoutException:
        error_msg = "Request timeout"
        logger.error(f"[CHECK_CALL] Timeout for {phone}: {error_msg}")
        return False, "", f"Network error: {error_msg}", None

    except httpx.RequestError as e:
        error_msg = str(e)
        logger.error(f"[CHECK_CALL] Request error for {phone}: {error_msg}")
        return False, "", f"Network error: {error_msg}", None

    except ValueError as e:
        error_msg = "JSON parse error"
        logger.error(f"[CHECK_CALL] JSON parse error for {phone}: {e!s}")
        return False, "", f"Response error: {error_msg}", None


async def verify_check_call_status(check_id: str) -> tuple[bool, str, str]:
    """
    Verify Check Call status via SMS.ru API (optional polling method).

    This is an alternative to webhook-based verification.
    Can be used for manual status checks or fallback polling.

    Args:
        check_id: Verification ID from initiate_check_call

    Returns:
        Tuple of (success: bool, status: str, message: str)
        - status: "401" (verified), "400" (pending), "402" (expired/invalid)
        - message: Text description of status

    SMS.ru API:
        GET https://sms.ru/callcheck/status
        Params: api_id, check_id, json

    Response format:
        {
            "status": "OK",
            "status_code": 100,
            "check_status": "401",
            "check_status_text": "Авторизация по звонку: номер подтвержден"
        }

    Status codes:
        - 100: Request successful, waiting for call
        - 400: Not verified yet (no call received)
        - 401: Verified (call received)
        - 402: Expired or invalid check_id

    Usage:
        success, status, message = await verify_check_call_status("201737-542")
        if success and status == "401":
            # User is verified
    """
    # Test mode: return stub
    if settings.SMS_TEST_MODE:
        logger.info(f"[CHECK_CALL] Status check for {check_id} (test mode)")
        # Simulate verified status for test IDs
        if check_id.startswith("TEST-"):
            return True, "401", "Авторизация по звонку: номер подтвержден (test)"
        return True, "400", "Ожидание звонка (test)"

    # Production mode: check status via SMS.ru API
    url = "https://sms.ru/callcheck/status"
    params = {
        "api_id": settings.SMS_API_KEY,
        "check_id": check_id,
        "json": 1
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10.0)
            _ = response.raise_for_status()
            data = cast(dict[str, object], response.json())

            # Log full API response for debugging
            logger.debug("[CHECK_CALL] Status response for %s: %s", check_id, data)
            print(f"[CHECK_CALL] Status response: {data}")

            if str(data.get("status")) == "OK":
                check_status = str(data.get("check_status", ""))
                check_status_text = str(data.get("check_status_text", "Unknown status"))

                logger.info(
                    "[CHECK_CALL] Status for %s: %s - %s",
                    check_id,
                    check_status,
                    check_status_text,
                )
                return True, check_status, check_status_text
            else:
                error_msg = str(data.get("status_text", "Unknown error"))
                status_code = str(data.get("status_code", "N/A"))
                logger.error(
                    "[CHECK_CALL] SMS.ru status error for %s: %s (code: %s)",
                    check_id,
                    error_msg,
                    status_code,
                )
                return False, "", f"SMS.ru error: {error_msg}"

    except httpx.TimeoutException:
        error_msg = "Request timeout"
        logger.error(f"[CHECK_CALL] Timeout for {check_id}: {error_msg}")
        return False, "", f"Network error: {error_msg}"

    except httpx.RequestError as e:
        error_msg = str(e)
        logger.error(f"[CHECK_CALL] Request error for {check_id}: {error_msg}")
        return False, "", f"Network error: {error_msg}"

    except ValueError as e:
        error_msg = "JSON parse error"
        logger.error(f"[CHECK_CALL] JSON parse error for {check_id}: {e!s}")
        return False, "", f"Response error: {error_msg}"


async def simulate_incoming_call(
    _db: AsyncSession, user: User, phone: str
) -> tuple[bool, str]:
    """
    Simulate incoming check call webhook in test mode.

    This function emulates what SMS.ru webhook does when user completes a check call.
    Should be called ONLY in test mode (SMS_TEST_MODE=True) after user clicks "Позвонить".

    Args:
        db: AsyncSession database session
        user: User object to update
        phone: Phone number for logging (passed explicitly to avoid lazy loading)

    Returns:
        Tuple of (success: bool, message: str)

    Logic:
        - Checks if user has sms_check_id set
        - Marks user as verified (is_verified=True)
        - Clears sms_check_id and expiration
        - Does NOT commit — caller must commit the session

    Usage:
        success, message = await simulate_incoming_call(db, user, phone)
        if success:
            await db.commit()
    """
    if not settings.SMS_TEST_MODE:
        logger.error("[SIMULATE] Cannot simulate call in production mode")
        return False, "Simulation only available in test mode"

    if not user.sms_check_id:
        logger.warning(f"[SIMULATE] No sms_check_id found for {phone}")
        return False, "No active check call found"

    # Emulate webhook: mark user as verified
    logger.info(f"[SIMULATE] Simulating incoming call for {phone}, check_id: {user.sms_check_id}")

    user.is_verified = True
    user.sms_check_id = None
    user.sms_code_expires_at = None

    logger.info(f"[SIMULATE] User {phone} verified successfully (simulated)")
    return True, "Call simulated successfully"