# app/services/auth_dispatcher.py

"""
Authorization dispatcher.

Selects the appropriate authorization method (SMS, Flash Call, or Check Call)
based on the AUTH_METHOD configuration setting.

Functions:
- send_verification_code: Send code via selected method (async)
- get_client_ip: Extract client IP from request (helper)
"""

import logging

from fastapi import Request

from app.config import settings
from app.services.call_service import send_flash_call
from app.services.sms_service import generate_sms_code, send_sms

# Configure logging
logger = logging.getLogger(__name__)


def get_client_ip(request: Request) -> str:
    """
    Extract client IP address from request.

    Handles X-Forwarded-For header for proxied requests.

    Args:
        request: FastAPI request object

    Returns:
        Client IP address string, or "-1" if unavailable

    Note:
        Returns "-1" for local/manual sends as per SMS.ru documentation.
    """
    # Check for X-Forwarded-For header (proxied requests)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP in the chain (original client)
        return forwarded_for.split(",")[0].strip()

    # Direct connection
    if request.client and request.client.host:
        return request.client.host

    # Fallback for local/manual sends
    return "-1"


async def send_verification_code(
    phone: str, request: Request | None = None
) -> tuple[bool, str, str]:
    """
    Send verification code using the configured method (SMS, Flash Call, or Check Call).

    Args:
        phone: Normalized phone number (+7XXXXXXXXXX)
        request: FastAPI request object (for IP extraction)

    Returns:
        Tuple of (success: bool, code: str, message: str)
        - For SMS/Flash Call: code is returned for storage in database
        - For Check Call: code is empty string, check_id is stored separately
        - Message contains status or error description

    Logic:
        - If AUTH_METHOD = "sms": generate code locally, send via SMS
        - If AUTH_METHOD = "call": API generates code, returns it in response
        - If AUTH_METHOD = "check_call": API returns check_id and call_phone

    Note:
        This function is used ONLY for SMS and Flash Call methods.
        Check Call uses a dedicated endpoint /api/auth/check-call/initiate.

    Usage:
        success, code, message = await send_verification_code(
            "+79991234567", request
        )
        if success:
            # Save code to database (for SMS/Flash Call)
            user.sms_code = code
    """
    # Get client IP for anti-fraud protection
    ip = get_client_ip(request) if request else "-1"

    if settings.AUTH_METHOD == "call":
        # Flash Call mode: API generates and returns the code
        logger.info(f"[DISPATCHER] Using Flash Call for {phone}")
        return await send_flash_call(phone, ip)
    elif settings.AUTH_METHOD == "check_call":
        # Check Call mode: should use dedicated endpoint, not this dispatcher
        # Return error to indicate incorrect usage
        logger.error(
            "[DISPATCHER] Check Call should use /api/auth/check-call/initiate, not send_verification_code"
        )
        return False, "", "Check Call requires dedicated endpoint"
    else:
        # SMS mode (default): generate code locally and send via SMS
        logger.info(f"[DISPATCHER] Using SMS for {phone}")
        code = generate_sms_code()
        success, message = await send_sms(phone, code)
        return success, code, message