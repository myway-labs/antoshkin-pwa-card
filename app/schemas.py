# app/schemas.py

"""
Pydantic schemas for request/response validation.

Defines data contracts for API endpoints:
- UserCreate: validation for user registration
- UserVerify: validation for SMS code verification
- UserOut: response schema for user data
- UserListOut: response schema for admin user list
"""

import re
from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserBase(BaseModel):
    """
    Base schema with common user attributes.

    Used as parent class for other user schemas.
    """

    full_name: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., min_length=10, max_length=20)


class UserCreate(UserBase):
    """
    Schema for user registration request.

    Validates incoming data when a new user registers.
    Phone number is validated for Russian format.
    """

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """
        Validate phone number format.

        Accepts: +7XXXXXXXXXX, 7XXXXXXXXXX, 8XXXXXXXXXX, +7 (XXX) XXX-XX-XX
        Returns: Normalized format +7XXXXXXXXXX

        Raises:
            ValueError: If phone number is invalid
        """
        # Remove all non-digit characters except +
        cleaned = re.sub(r"[^\d+]", "", v)

        # Handle different formats
        if cleaned.startswith("+7"):
            phone_digits = cleaned[1:]  # Remove +
        elif cleaned.startswith("7"):
            phone_digits = cleaned
        elif cleaned.startswith("8"):
            phone_digits = "7" + cleaned[1:]
        else:
            raise ValueError("Phone number must start with +7, 7, or 8")

        # Check length (7 + 10 digits = 11 characters)
        if len(phone_digits) != 11:
            raise ValueError("Phone number must have 11 digits (e.g., +7XXXXXXXXXX)")

        # Return normalized format
        return f"+{phone_digits}"

    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={
            "example": {
                "full_name": "Иван Иванов",
                "phone": "+79991234567",
            }
        }
    )


class UserVerify(BaseModel):
    """
    Schema for SMS verification request.

    Validates phone number and 4-digit verification code.
    """

    phone: str
    code: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Normalize phone number (same as UserCreate)."""
        cleaned = re.sub(r"[^\d+]", "", v)

        if cleaned.startswith("+7"):
            phone_digits = cleaned[1:]
        elif cleaned.startswith("7"):
            phone_digits = cleaned
        elif cleaned.startswith("8"):
            phone_digits = "7" + cleaned[1:]
        else:
            raise ValueError("Phone number must start with +7, 7, or 8")

        if len(phone_digits) != 11:
            raise ValueError("Phone number must have 11 digits")

        return f"+{phone_digits}"

    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={
            "example": {
                "phone": "+79991234567",
                "code": "1234",
            }
        }
    )


class UserOut(BaseModel):
    """
    Schema for user data response.

    Returns user information after successful registration
    or verification. Excludes sensitive data (sms_code).
    """

    id: int
    full_name: str
    phone: str
    is_verified: bool
    created_at: datetime

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)


class UserListOut(BaseModel):
    """
    Schema for admin user list response.

    Returns paginated list of users with total count.
    """

    users: list[UserOut]
    total: int
    limit: int
    offset: int

    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={
            "example": {
                "users": [
                    {
                        "id": 1,
                        "full_name": "Иван Иванов",
                        "phone": "+79991234567",
                        "is_verified": True,
                        "created_at": "2025-02-25T10:00:00",
                    }
                ],
                "total": 1,
                "limit": 50,
                "offset": 0,
            }
        }
    )


class SMSRequest(BaseModel):
    """
    Schema for SMS sending request.

    Validates phone number for SMS code delivery.
    """

    phone: str

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Normalize phone number (same as UserCreate)."""
        cleaned = re.sub(r"[^\d+]", "", v)

        if cleaned.startswith("+7"):
            phone_digits = cleaned[1:]
        elif cleaned.startswith("7"):
            phone_digits = cleaned
        elif cleaned.startswith("8"):
            phone_digits = "7" + cleaned[1:]
        else:
            raise ValueError("Phone number must start with +7, 7, or 8")

        if len(phone_digits) != 11:
            raise ValueError("Phone number must have 11 digits")

        return f"+{phone_digits}"

    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={
            "example": {
                "phone": "+79991234567",
            }
        }
    )


class VerifyResponse(BaseModel):
    """
    Schema for verification response.

    Simple boolean response for verification status.
    """

    verified: bool


class SMSResponse(BaseModel):
    """
    Schema for SMS sending response.

    Indicates if SMS was sent successfully.
    For check_call method, also includes the phone number to call.
    """

    sent: bool
    call_phone: str | None = None
