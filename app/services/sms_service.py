# app/services/sms_service.py

"""
SMS verification service.

Handles SMS code generation, sending, and verification.
Integrates with SMS gateway API (e.g., SMS.ru).

Functions:
- generate_sms_code: Create 4-digit verification code
- send_sms: Send SMS via gateway API (async)
- verify_sms_code: Validate code and mark user as verified (async)
- set_user_sms_code: Generate and save SMS code (async)
- resend_sms_code: Resend SMS code (async)
"""

import logging
import random
from datetime import datetime, timedelta, timezone
from typing import cast

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import User

# Configure logging
logger = logging.getLogger(__name__)

# Test code for development mode
TEST_CODE = "0000"  # Universal code for testing


def generate_sms_code() -> str:
    """
    Generate 4-digit SMS verification code.

    Returns:
        In SMS_TEST_MODE: always returns "0000"
        In production: random 4-digit code (0000-9999)

    Note:
        Code is zero-padded to ensure exactly 4 digits.

    Usage:
        code = generate_sms_code()
        print(f"Your code: {code}")  # "Your code: 0000" (test mode)
    """
    if settings.SMS_TEST_MODE:
        return TEST_CODE

    return f"{random.randint(0, 9999):04d}"


async def send_sms(phone: str, code: str) -> tuple[bool, str]:
    """
    Send SMS with verification code via SMS gateway.

    Args:
        phone: Normalized phone number (+7XXXXXXXXXX)
        code: 4-digit verification code

    Returns:
        Tuple of (success: bool, message: str)
        - (True, "SMS sent") if successful
        - (False, "Error message") if failed

    Note:
        In test mode (SMS_TEST_MODE=True), returns stub response.
        In production, sends SMS via SMS.ru API using httpx.AsyncClient.

    SMS.ru API:
        GET https://sms.ru/sms/send
        Params: api_key, to, msg, json

    Usage:
        success, message = await send_sms("+79991234567", "1234")
        if success:
            print("SMS sent successfully")
    """
    # Test mode: return stub without sending
    if settings.SMS_TEST_MODE:
        logger.info(f"[SMS] Code {code} to {phone}")
        print(f"[SMS STUB] Code {code} sent to {phone}")
        return True, "SMS sent (test mode)"

    # Production mode: send via SMS.ru API using httpx
    url = "https://sms.ru/sms/send"
    params = {
        "api_id": settings.SMS_API_KEY,
        "to": phone,
        "msg": f"Ваш код верификации: {code}",
        "json": 1
    }

    # Add sender name if configured
    if settings.SMS_SENDER_NAME:
        params["from"] = settings.SMS_SENDER_NAME

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10.0)
            _ = response.raise_for_status()
            data = cast(dict[str, object], response.json())

            # Log full API response for debugging
            logger.debug(f"[SMS] SMS.ru response for {phone}: {data}")
            print(f"[SMS] SMS.ru response: {data}")

            if str(data.get("status")) == "OK":
                logger.info("[SMS] Sent to %s, code: %s", phone, code)
                return True, "SMS sent"
            else:
                error_msg = str(data.get("status_message", "Unknown error"))
                status_code = str(data.get("status_code", "N/A"))
                logger.error(
                    "[SMS] SMS.ru error for %s: %s (code: %s)",
                    phone,
                    error_msg,
                    status_code,
                )
                return False, f"SMS.ru error: {error_msg}"

    except httpx.TimeoutException:
        error_msg = "Request timeout"
        logger.error(f"[SMS] Timeout for {phone}: {error_msg}")
        return False, f"Network error: {error_msg}"

    except httpx.RequestError as e:
        error_msg = str(e)
        logger.error(f"[SMS] Request error for {phone}: {error_msg}")
        return False, f"Network error: {error_msg}"

    except ValueError as e:
        error_msg = "JSON parse error"
        logger.error(f"[SMS] JSON parse error for {phone}: {e!s}")
        return False, f"Response error: {error_msg}"


async def verify_sms_code(
    db: AsyncSession, user: User, code: str
) -> tuple[bool, str, int | None]:
    """
    Verify SMS code and activate user account (async version).

    Args:
        db: AsyncSession database session
        user: User object to verify
        code: 4-digit code entered by user

    Returns:
        Tuple of (success: bool, message: str)
        - (True, "Verified") if code is valid
        - (False, "Error message") if invalid or expired

    Verification logic:
        1. Check if SMS code exists
        2. Check if code has not expired (5 minutes)
        3. Compare entered code with stored code
        4. If valid: mark as verified, clear code

    Note:
        Previously verified users must also enter a valid code when logging in
        after logout. The is_verified flag is ignored during code verification
        to ensure security.

    Usage:
        user = await get_user_by_phone(db, "+79991234567")
        success, message = await verify_sms_code(db, user, "1234")
        if success:
            print("User verified successfully")
    """
    # Check if code exists
    if not user.sms_code:
        return False, "Код не был отправлен", None

    # Check if code has expired
    if user.sms_code_expires_at is None:
        return False, "Ошибка SMS кода", None

    if datetime.now(timezone.utc).replace(tzinfo=None) > user.sms_code_expires_at:
        return False, "Срок действия кода истёк", None

    # Compare codes (constant-time comparison for security)
    if user.sms_code != code:
        return False, "Неверный код", None

    # Code is valid - mark user as verified
    # IMPORTANT: Save user.id BEFORE commit to avoid lazy-loading issues
    user_id = user.id

    user.is_verified = True
    user.sms_code = None
    user.sms_code_expires_at = None
    await db.commit()

    # Return user_id so caller doesn't need to access expired object
    return True, "Verified", user_id


async def set_user_sms_code(db: AsyncSession, user: User) -> tuple[bool, str, str]:
    """
    Generate and set SMS code for user (async version).

    Args:
        db: AsyncSession database session
        user: User object

    Returns:
        Tuple of (success: bool, code: str, message: str)
        - Code is returned for sending via SMS
        - Code is NOT stored in plain text in production (use hash)

    Note:
        Code expires in 5 minutes.
        For production: hash the code before storing in database.

    Usage:
        user = await get_user_by_phone(db, "+79991234567")
        success, code, message = await set_user_sms_code(db, user)
        if success:
            await send_sms(user.phone, code)
    """
    # Generate new code
    code = generate_sms_code()

    # Set expiration time (5 minutes from now)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5)

    # Save to database
    user.sms_code = code
    user.sms_code_expires_at = expires_at
    await db.commit()

    return True, code, "Code generated"


async def resend_sms_code(db: AsyncSession, user: User) -> tuple[bool, str, str]:
    """
    Resend SMS code to user (if previous code expired or not received) (async version).

    Args:
        db: AsyncSession database session
        user: User object

    Returns:
        Tuple of (success: bool, code: str, message: str)

    Note:
        Generates new code and resets expiration time.
        Implement rate limiting in production (e.g., max 3 requests per hour).

    Usage:
        user = await get_user_by_phone(db, "+79991234567")
        success, code, message = await resend_sms_code(db, user)
        await send_sms(user.phone, code)
    """
    # Check if already verified
    if user.is_verified:
        return False, "", "User already verified"

    # Generate and set new code
    return await set_user_sms_code(db, user)