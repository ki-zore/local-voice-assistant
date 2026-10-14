"""Routes package."""

from backend.app.routes.availability import router as availability_router
from backend.app.routes.bookings import router as bookings_router
from backend.app.routes.businesses import router as businesses_router
from backend.app.routes.calls import router as calls_router

__all__ = [
    "businesses_router",
    "availability_router",
    "bookings_router",
    "calls_router",
]
