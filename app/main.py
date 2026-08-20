# app/main.py

"""
FastAPI application entry point.

Initializes the FastAPI app, configures middleware,
and includes API routers.
"""

import os
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routers import router
from app.config import settings
from app.database import Base, sync_engine
from app.middleware.auth import SessionAuthMiddleware

# Initialize database tables
# Creates all tables defined in models.py if they don't exist
Base.metadata.create_all(bind=sync_engine)

# Initialize FastAPI application
app = FastAPI(
    title="Antoshkin Loyalty Card",
    description="PWA for loyalty card management with SMS verification",
    version="0.1.0",
    debug=settings.DEBUG,
)

# Add authentication middleware
# Runs on every request, injects current_user into request.state
app.add_middleware(SessionAuthMiddleware)

# Configure static files (CSS, JS, images, manifest)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Base and static directories resolution
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "favicon.ico"))


@app.get("/apple-touch-icon.png", include_in_schema=False)
async def apple_touch() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "apple-touch-icon.png"))


@app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
async def apple_touch_precomposed() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "apple-touch-icon-precomposed.png"))


@app.get("/robots.txt", include_in_schema=False)
async def robots() -> FileResponse:
    return FileResponse(os.path.join(BASE_DIR, "robots.txt"))


# Configure Jinja2 templates
templates = Jinja2Templates(directory="templates")


@app.middleware("http")
async def add_templates_to_request(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """
    Middleware to add templates to request state.

    Makes templates available in endpoints via request.state.templates
    """
    request.state.templates = templates
    response = await call_next(request)
    return response


# Include API router
app.include_router(router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """
    Health check endpoint for monitoring.

    Returns:
        Simple status response
    """
    return {"status": "ok"}
