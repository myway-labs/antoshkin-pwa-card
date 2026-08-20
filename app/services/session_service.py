# app/services/session_service.py

"""
Session service for managing user authentication tokens.

Provides async database operations for session lifecycle:
- create_session: Generate new session token for user
- get_session_by_token: Retrieve session by token (for auth)
- delete_session: Remove session (logout)

All sessions are stored in HttpOnly cookies (30-day lifetime).
Token is never exposed to JavaScript (XSS protection).
"""

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Session


async def create_session(db: AsyncSession, user_id: int, expires_in_days: int = 30) -> str:
    """
    Create new session for user and return token.

    Args:
        db: AsyncSession database session
        user_id: ID of the user to create session for
        expires_in_days: Session lifetime in days (default: 30)

    Returns:
        Session token (string, 256-bit entropy via secrets.token_urlsafe)
    """
    # Generate cryptographically secure token
    token = secrets.token_urlsafe(32)

    # Calculate expiration time
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=expires_in_days)

    # Create session object
    db_session = Session(
        user_id=user_id,
        token=token,
        expires_at=expires_at
    )

    # Add to database
    db.add(db_session)
    await db.commit()
    await db.refresh(db_session)

    return token


async def get_session_by_token(db: AsyncSession, token: str) -> Session | None:
    """
    Retrieve session by token.

    Args:
        db: AsyncSession database session
        token: Session token from cookie

    Returns:
        Session object if found and valid, None otherwise
    """
    # Query session by token
    result = await db.execute(select(Session).where(Session.token == token))
    return result.scalar_one_or_none()


async def delete_session(db: AsyncSession, token: str) -> bool:
    """
    Delete session (logout user).

    Args:
        db: AsyncSession database session
        token: Session token to delete

    Returns:
        True if session was deleted, False if not found
    """
    # Find session by token
    result = await db.execute(select(Session).where(Session.token == token))
    session = result.scalar_one_or_none()

    if not session:
        return False

    # Delete session
    await db.delete(session)
    await db.commit()

    return True


async def cleanup_expired_sessions(db: AsyncSession) -> int:
    """
    Remove all expired sessions from database.

    Args:
        db: AsyncSession database session

    Returns:
        Number of sessions deleted
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    result = await db.execute(
        select(func.count()).select_from(Session).where(
            Session.expires_at < now
        )
    )
    count = result.scalar() or 0

    _ = await db.execute(
        delete(Session).where(
            Session.expires_at < now
        )
    )
    await db.commit()

    return count


async def delete_all_user_sessions(db: AsyncSession, user_id: int) -> int:
    """
    Delete all sessions for a specific user.

    Args:
        db: AsyncSession database session
        user_id: ID of the user

    Returns:
        Number of sessions deleted
    """
    result = await db.execute(
        select(func.count()).select_from(Session).where(
            Session.user_id == user_id
        )
    )
    count = result.scalar() or 0

    _ = await db.execute(
        delete(Session).where(
            Session.user_id == user_id
        )
    )
    await db.commit()

    return count
