# app/middleware/auth.py

"""
Authentication middleware for session validation.

This middleware runs on every request and:
1. Extracts session_token from cookies
2. Validates session in database
3. Injects current_user into request.state

Important:
- Does NOT block requests (returns 401 in routes, not middleware)
- Stateless: only injects user, doesn't modify database
- Safe for public routes (/, /admin, static files)
"""

from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from starlette.middleware.base import BaseHTTPMiddleware

from app.database import AsyncSessionLocal
from app.models import Session, User


class SessionAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware for automatic session authentication.

    Usage:
        # In main.py
        from app.middleware.auth import SessionAuthMiddleware
        app.add_middleware(SessionAuthMiddleware)

        # In routes
        @app.get("/protected")
        async def protected_route(request: Request):
            user = request.state.current_user
            if not user:
                raise HTTPException(status_code=401)
            return {"user": user}

    How it works:
        1. Extract "session_token" cookie from request
        2. Query session from database by token
        3. Check if session is valid (not expired)
        4. Set request.state.current_user = session.user (or None)
        5. Continue request processing

    Note:
        - current_user is None if:
          * No cookie present
          * Session not found in database
          * Session expired
        - Middleware does NOT return 401 (routes handle this)
        - Session is NOT deleted on expiration (routes handle this)
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """
        Process request and inject current_user.

        Args:
            request: FastAPI request object
            call_next: Next middleware/route handler

        Returns:
            Response from route handler
        """
        # Initialize current_user as None (unauthenticated)
        request.state.current_user = None
        request.state.is_authenticated = False

        # Extract session token from cookies
        token = request.cookies.get("session_token")

        if not token:
            # No cookie - continue as anonymous
            return await call_next(request)

        # Create async database session
        async with AsyncSessionLocal() as db:
            # Find session by token with eager-loaded user (async)
            result = await db.execute(
                select(Session)
                .options(selectinload(Session.user))
                .where(Session.token == token)
            )
            session = result.scalar_one_or_none()

            if not session:
                # Session not found in database - continue as anonymous
                return await call_next(request)

            # Check if session is valid (not expired)
            if not session.is_valid():
                # Session expired - continue as anonymous
                # Note: Not deleting session here (let routes handle cleanup)
                return await call_next(request)

            # Session is valid - inject user (already loaded via selectinload)
            request.state.current_user = session.user
            request.state.is_authenticated = True

        # Continue request processing with injected user
        return await call_next(request)


# Convenience function for dependency injection
async def get_current_user_optional(request: Request) -> User | None:
    """
    Dependency for optional authentication.

    Returns current_user if authenticated, None otherwise.
    Does NOT raise HTTPException (use for public routes).

    Usage:
        @app.get("/public")
        async def public_route(
            user = Depends(get_current_user_optional)
        ):
            if user:
                return {"greeting": f"Hello, {user.full_name}"}
            return {"greeting": "Hello, guest"}
    """
    user: User | None = getattr(request.state, "current_user", None)
    return user


async def get_current_user_required(request: Request) -> User:
    """
    Dependency for required authentication.

    Returns current_user if authenticated.
    Raises HTTPException(401) if not authenticated.

    Usage:
        @app.get("/protected")
        async def protected_route(
            user = Depends(get_current_user_required)
        ):
            return {"user": user}

    Raises:
        HTTPException: 401 Unauthorized if not authenticated
    """
    user: User | None = getattr(request.state, "current_user", None)

    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    return user
