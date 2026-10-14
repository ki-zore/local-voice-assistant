"""Voice Assistant FastAPI Application Main Entrypoint."""

from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.config import get_settings
from backend.app.db import close_db_connection, ensure_indexes, get_db
from backend.app.models.common import ErrorResponse
from backend.app.routes import (
    availability_router,
    bookings_router,
    businesses_router,
    calls_router,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("voice_assistant.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager to connect database, ensure indexes, and clean up."""
    logger.info("Initializing Voice Assistant Backend...")
    db = get_db()
    try:
        await ensure_indexes(db)
        logger.info("Database connected and indexes verified.")
    except Exception as exc:
        logger.error("Failed to initialize database indexes: %s", exc)

    yield

    logger.info("Shutting down Voice Assistant Backend...")
    close_db_connection()


app = FastAPI(
    title="Voice Assistant Backend API",
    description="Multi-tenant backend for local AI Voice Receptionist managing cafe bookings, FAQs, and calls.",
    version="1.0.0",
    lifespan=lifespan,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)

# CORS configuration
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Standardized error handlers: {"error": "<code>", "message": "<human readable>"}
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    """Format HTTPExceptions into consistent JSON errors."""
    if isinstance(exc.detail, dict):
        error_code = exc.detail.get("error", "HTTP_ERROR")
        message = exc.detail.get("message", str(exc.detail))
        details = {k: v for k, v in exc.detail.items() if k not in ("error", "message")}
        content: dict = {"error": error_code, "message": message}
        if details:
            content.update(details)
    else:
        status_to_code = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            409: "CONFLICT",
            422: "UNPROCESSABLE_ENTITY",
            500: "INTERNAL_SERVER_ERROR",
        }
        error_code = status_to_code.get(exc.status_code, "ERROR")
        content = {"error": error_code, "message": str(exc.detail)}

    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Format Pydantic request validation errors into consistent JSON format."""
    messages = []
    for err in exc.errors():
        loc = " -> ".join(str(item) for item in err.get("loc", []))
        msg = err.get("msg", "Invalid value")
        messages.append(f"{loc}: {msg}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "VALIDATION_ERROR",
            "message": "; ".join(messages),
            "details": exc.errors(),
        },
    )


# Health check
@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Health check endpoint to verify API and DB status."""
    return {"status": "ok", "service": "voice-assistant-backend"}


# Mount API routers
app.include_router(businesses_router)
app.include_router(availability_router)
app.include_router(bookings_router)
app.include_router(calls_router)
