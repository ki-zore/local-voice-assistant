"""Common Pydantic models and serializers."""

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict


class ErrorResponse(BaseModel):
    """Standardized error response matching project contract."""

    error: str
    message: str
    details: Optional[Any] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": "VALIDATION_ERROR",
                "message": "The requested booking time falls outside opening hours.",
            }
        }
    )
