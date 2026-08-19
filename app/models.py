# app/models.py

"""
SQLAlchemy database models.

Defines the structure of database tables as Python classes.
Each class represents a table, each attribute represents a column.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, override

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    """
    User model for storing customer loyalty card data.

    Table: users

    Attributes:
        id (int): Primary key, auto-increment
        full_name (str): Customer's full name (max 100 characters)
        phone (str): Normalized phone number (+7XXXXXXXXXX format, unique)
        is_verified (bool): SMS verification status (default: False)
        sms_code (str | None): 4-digit verification code (temporary, nullable)
        sms_code_expires_at (datetime | None): Code expiration time (nullable)
        sms_check_id (str | None): Check Call verification ID from SMS.ru (nullable)
        is_privacy_accepted (bool): Privacy policy acceptance status (default: False)
        is_subscribed (bool): Subscription status (default: False)
        created_at (datetime): Registration timestamp (auto-generated)
        sessions (list[Session]): Relationship to Session objects (auto-delete on user delete)
    """

    __tablename__: str = "users"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)

    # Customer information
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)

    # Verification status
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # SMS verification code (temporary storage)
    sms_code: Mapped[str | None] = mapped_column(String(4), nullable=True)
    sms_code_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Check Call verification ID from SMS.ru
    sms_check_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Privacy and subscription flags
    is_privacy_accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_subscribed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False
    )

    # Relationship to Session objects
    # cascade="all, delete-orphan" ensures sessions are deleted when user is deleted
    sessions: Mapped[list["Session"]] = relationship(
        "Session", back_populates="user", cascade="all, delete-orphan"
    )

    @override
    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<User(id={self.id}, phone='{self.phone}', verified={self.is_verified})>"


class Session(Base):
    """
    Session model for storing user authentication tokens.

    Table: sessions

    Attributes:
        id (int): Primary key, auto-increment
        user_id (int): Foreign key to users.id (indexed for fast lookups)
        token (str): Unique session token (UUID / secrets.token_urlsafe, indexed for fast lookups)
        expires_at (datetime): Session expiration time (30 days from creation)
        created_at (datetime): Session creation timestamp (auto-generated)
        user (User): Relationship to User object

    Usage:
        # Create session for user
        session = Session(user_id=1)
        db.add(session)
        db.commit()

        # Find session by token
        session = db.query(Session).filter(Session.token == token).first()

        # Check if session is expired
        if session.expires_at < datetime.utcnow():
            # Session expired
    """

    __tablename__: str = "sessions"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)

    # Foreign key to users table
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Session token (generated with secrets.token_urlsafe(32))
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)

    # Session expiration (30 days from creation)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False
    )

    # Relationship to User object
    user: Mapped["User"] = relationship("User", back_populates="sessions")

    def __init__(self, **kwargs: object) -> None:
        """
        Initialize session with auto-generated token and expiration.

        Args:
            **kwargs: Keyword arguments (user_id required)
        """
        super().__init__(**kwargs)
        # Generate unique token if not provided
        if not getattr(self, "token", None):
            self.token = secrets.token_urlsafe(32)
        # Set expiration to 30 days from now if not provided
        if not getattr(self, "expires_at", None):
            self.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)

    def is_valid(self) -> bool:
        """
        Check if session is still valid (not expired).

        Returns:
            True if session is valid, False if expired
        """
        return datetime.now(timezone.utc).replace(tzinfo=None) < self.expires_at

    @override
    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<Session(id={self.id}, user_id={self.user_id}, token='{self.token[:8]}...', expires_at={self.expires_at})>"
