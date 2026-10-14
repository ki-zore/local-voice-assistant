"""Phone Call and Conversation Log models."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class TranscriptItem(BaseModel):
    """Single message line in a call transcript."""

    role: str = Field(..., description="'customer' or 'assistant'")
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class CallCreateRequest(BaseModel):
    """Payload to record the start of a call."""

    business_id: str
    started_at: Optional[datetime] = None


class CallUpdateRequest(BaseModel):
    """Payload to update an ongoing or completed call."""

    ended_at: Optional[datetime] = None
    outcome: Optional[str] = None
    transcript_item: Optional[TranscriptItem] = None


class UnansweredQuestionRequest(BaseModel):
    """Payload to log an unanswered question from a caller."""

    question: str = Field(..., min_length=3)


class UnansweredQuestionItem(BaseModel):
    """Unanswered question record for triage dashboard."""

    id: str
    call_id: str
    business_id: str
    question: str
    created_at: datetime


class CallResponse(BaseModel):
    """Call entity returned by API."""

    id: str
    business_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    transcript: List[TranscriptItem] = Field(default_factory=list)
    outcome: Optional[str] = None
    unanswered_questions: List[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)
