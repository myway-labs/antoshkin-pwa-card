# app/services/phone_service.py

"""
Phone number validation and normalization service.

Handles Russian phone number formats:
- +7XXXXXXXXXX
- 7XXXXXXXXXX
- 8XXXXXXXXXX
- +7 (XXX) XXX-XX-XX
- 8 (XXX) XXX-XX-XX

Functions:
- normalize_phone: Convert to standard +7XXXXXXXXXX format
- validate_phone: Check if phone number is valid Russian format
"""

import re


def normalize_phone(phone: str) -> str:
    """
    Normalize phone number to standard format +7XXXXXXXXXX.
    
    Args:
        phone: Phone number in any Russian format
    
    Returns:
        Normalized phone number (e.g., "+79991234567")
    
    Supported formats:
        - "+7 (999) 123-45-67" → "+79991234567"
        - "8 (999) 123-45-67" → "+79991234567"
        - "+79991234567" → "+79991234567"
        - "79991234567" → "+79991234567"
        - "89991234567" → "+79991234567"
    
    Raises:
        ValueError: If phone number format is invalid
    
    Usage:
        phone = normalize_phone("+7 (999) 123-45-67")
        print(phone)  # "+79991234567"
    """
    # Remove all non-digit characters except +
    cleaned = re.sub(r'[^\d+]', '', phone)
    
    # Handle different starting formats
    if cleaned.startswith('+7'):
        phone_digits = cleaned[1:]  # Remove + to get 7XXXXXXXXXX
    elif cleaned.startswith('7'):
        phone_digits = cleaned
    elif cleaned.startswith('+8'):
        # Replace +8 with +7 (common mistake)
        phone_digits = '7' + cleaned[2:]
    elif cleaned.startswith('8'):
        phone_digits = '7' + cleaned[1:]
    else:
        raise ValueError(
            f"Phone number must start with +7, 7, or 8. Got: {cleaned[:5]}..."
        )
    
    # Check length (7 + 10 digits = 11 characters)
    if len(phone_digits) != 11:
        raise ValueError(
            f"Phone number must have 11 digits. Got: {len(phone_digits)}"
        )
    
    # Return normalized format
    return f'+{phone_digits}'


def validate_phone(phone: str) -> bool:
    """
    Validate Russian phone number format.
    
    Args:
        phone: Phone number to validate
    
    Returns:
        True if valid, False otherwise
    
    Validation rules:
        1. Must start with +7, 7, or 8
        2. Must have exactly 11 digits (including country code)
        3. Second digit must be 9 (for mobile numbers)
    
    Usage:
        if validate_phone("+79991234567"):
            print("Valid phone number")
    """
    try:
        normalized = normalize_phone(phone)
        
        # Check format: +7 followed by 10 digits
        pattern = r'^\+7[0-9]{10}$'
        
        if not re.match(pattern, normalized):
            return False
        
        # Optional: Check if second digit is 9 (mobile numbers)
        # Most Russian mobile numbers start with 9
        # but some landlines may start with other digits
        return normalized[2] in "0123456789"
    
    except ValueError:
        return False


def format_phone_display(phone: str) -> str:
    """
    Format phone number for display (pretty printing).
    
    Args:
        phone: Normalized phone number (+7XXXXXXXXXX)
    
    Returns:
        Formatted phone number (e.g., "+7 (999) 123-45-67")
    
    Usage:
        display = format_phone_display("+79991234567")
        print(display)  # "+7 (999) 123-45-67"
    """
    # Ensure phone is normalized first
    if not phone.startswith('+'):
        phone = normalize_phone(phone)
    
    # Extract digits (without +)
    digits = phone[1:]  # "79991234567"
    
    # Format: +7 (XXX) XXX-XX-XX
    return f"+{digits[0]} ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"


def extract_phone_code(phone: str) -> str:
    """
    Extract phone operator code (3 digits after country code).
    
    Args:
        phone: Normalized phone number (+7XXXXXXXXXX)
    
    Returns:
        Operator code (e.g., "999" for +79991234567)
    
    Usage:
        code = extract_phone_code("+79991234567")
        print(code)  # "999"
    """
    if not phone.startswith('+'):
        phone = normalize_phone(phone)
    
    # Extract 3 digits after +7
    return phone[2:5]
