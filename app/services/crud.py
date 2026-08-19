# app/services/crud.py

"""
CRUD (Create, Read, Update, Delete) service for User model.

Provides async database operations for user management:
- get_user_by_phone: Retrieve user by phone number
- create_user: Create new user
- update_user: Update user fields
- get_all_users: Get paginated user list
- delete_user: Remove user from database
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def get_user_by_phone(db: AsyncSession, phone: str) -> User | None:
    """
    Get user by phone number.

    Args:
        db: AsyncSession database session
        phone: Normalized phone number (+7XXXXXXXXXX)

    Returns:
        User object if found, None otherwise

    Usage:
        user = await get_user_by_phone(db, "+79991234567")
        if user:
            print(f"Found: {user.full_name}")
    """
    result = await db.execute(select(User).where(User.phone == phone))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    """
    Get user by ID.

    Args:
        db: AsyncSession database session
        user_id: User's primary key

    Returns:
        User object if found, None otherwise
    """
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, full_name: str, phone: str) -> User:
    """
    Create new user in database.

    Args:
        db: AsyncSession database session
        full_name: Customer's full name
        phone: Normalized phone number (+7XXXXXXXXXX)

    Returns:
        Created User object (with id and created_at populated)

    Usage:
        user = await create_user(db, "Иван Иванов", "+79991234567")
        print(f"Created user with ID: {user.id}")
    """
    db_user = User(
        full_name=full_name,
        phone=phone,
        is_verified=False,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None)
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user


async def update_user(
    db: AsyncSession, user: User, update_data: dict[str, object]
) -> User:
    """
    Update user fields.

    Args:
        db: AsyncSession database session
        user: User object to update
        update_data: Dictionary with fields to update
            e.g., {"full_name": "Новое имя", "is_verified": True}

    Returns:
        Updated User object

    Usage:
        user = await get_user_by_phone(db, "+79991234567")
        updated = await update_user(db, user, {"is_verified": True})
    """
    for key, value in update_data.items():
        if hasattr(user, key):
            setattr(user, key, value)

    await db.commit()
    await db.refresh(user)
    return user


async def get_all_users(
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0
) -> list[User]:
    """
    Get paginated list of all users.

    Args:
        db: AsyncSession database session
        limit: Maximum number of users to return (default: 50)
        offset: Number of users to skip (default: 0)

    Returns:
        List of User objects ordered by created_at (newest first)

    Usage:
        users = await get_all_users(db, limit=10, offset=0)
        for user in users:
            print(f"{user.full_name}: {user.phone}")
    """
    result = await db.execute(
        select(User)
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


async def count_users(db: AsyncSession) -> int:
    """
    Get total count of users in database.

    Args:
        db: AsyncSession database session

    Returns:
        Total number of users

    Usage:
        total = await count_users(db)
        print(f"Total users: {total}")
    """
    result = await db.execute(select(func.count()).select_from(User))
    return int(result.scalar() or 0)


async def delete_user(db: AsyncSession, user: User) -> bool:
    """
    Delete user from database.

    Args:
        db: AsyncSession database session
        user: User object to delete

    Returns:
        True if deleted successfully

    Usage:
        user = await get_user_by_phone(db, "+79991234567")
        await delete_user(db, user)
    """
    await db.delete(user)
    await db.commit()
    return True


async def set_sms_code(
    db: AsyncSession,
    user: User,
    code: str,
    expires_at: datetime
) -> User:
    """
    Set SMS verification code for user.

    Args:
        db: AsyncSession database session
        user: User object
        code: 4-digit verification code
        expires_at: Code expiration timestamp

    Returns:
        Updated User object
    """
    user.sms_code = code
    user.sms_code_expires_at = expires_at
    await db.commit()
    await db.refresh(user)
    return user


async def clear_sms_code(db: AsyncSession, user: User) -> User:
    """
    Clear SMS verification code after successful verification.

    Args:
        db: AsyncSession database session
        user: User object

    Returns:
        Updated User object
    """
    user.sms_code = None
    user.sms_code_expires_at = None
    await db.commit()
    await db.refresh(user)
    return user


async def verify_user(db: AsyncSession, user: User) -> User:
    """
    Mark user as verified and clear SMS code.

    Args:
        db: AsyncSession database session
        user: User object to verify

    Returns:
        Updated User object with is_verified=True

    Usage:
        user = await get_user_by_phone(db, "+79991234567")
        verified_user = await verify_user(db, user)
    """
    user.is_verified = True
    user.sms_code = None
    user.sms_code_expires_at = None
    await db.commit()
    await db.refresh(user)
    return user

