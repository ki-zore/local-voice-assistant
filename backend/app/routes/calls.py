"""Phone calls, conversation transcripts, and unanswered question triage routes."""

from datetime import datetime
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
import pymongo

from backend.app.db import get_db
from backend.app.models.call import (
    CallCreateRequest,
    CallResponse,
    CallUpdateRequest,
    TranscriptItem,
    UnansweredQuestionItem,
    UnansweredQuestionRequest,
)

router = APIRouter(tags=["Calls & Unanswered Questions"])


@router.post("/calls", response_model=CallResponse, status_code=status.HTTP_201_CREATED)
async def create_call(
    request: CallCreateRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> CallResponse:
    """Record the initiation of a voice phone call."""
    call_id = f"call_{uuid.uuid4().hex[:12]}"
    started_at = request.started_at or datetime.utcnow()

    doc = {
        "id": call_id,
        "business_id": request.business_id,
        "started_at": started_at,
        "ended_at": None,
        "transcript": [],
        "outcome": "in_progress",
        "unanswered_questions": [],
    }

    await db["calls"].insert_one(doc)

    return CallResponse(
        id=call_id,
        business_id=request.business_id,
        started_at=started_at,
        ended_at=None,
        transcript=[],
        outcome="in_progress",
        unanswered_questions=[],
    )


@router.get("/calls", response_model=List[CallResponse])
async def list_calls(
    business_id: str = Query(..., description="Business ID to filter calls"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> List[CallResponse]:
    """List recorded calls for a business ordered by most recent first."""
    cursor = (
        db["calls"]
        .find({"business_id": business_id})
        .sort("started_at", pymongo.DESCENDING)
        .skip(offset)
        .limit(limit)
    )
    records = await cursor.to_list(length=limit)

    return [
        CallResponse(
            id=r["id"],
            business_id=r["business_id"],
            started_at=r["started_at"],
            ended_at=r.get("ended_at"),
            transcript=[
                TranscriptItem(
                    role=t["role"],
                    message=t["message"],
                    timestamp=t.get("timestamp", datetime.utcnow()),
                )
                for t in r.get("transcript", [])
            ],
            outcome=r.get("outcome"),
            unanswered_questions=r.get("unanswered_questions", []),
        )
        for r in records
    ]


@router.get("/calls/{call_id}", response_model=CallResponse)
async def get_call(
    call_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> CallResponse:
    """Retrieve full details, transcript, and outcome for a specific call."""
    call = await db["calls"].find_one({"$or": [{"id": call_id}, {"_id": call_id}]})
    if not call:
        raise HTTPException(
            status_code=404,
            detail={"error": "CALL_NOT_FOUND", "message": f"Call '{call_id}' not found."},
        )

    return CallResponse(
        id=call["id"],
        business_id=call["business_id"],
        started_at=call["started_at"],
        ended_at=call.get("ended_at"),
        transcript=[
            TranscriptItem(
                role=t["role"],
                message=t["message"],
                timestamp=t.get("timestamp", datetime.utcnow()),
            )
            for t in call.get("transcript", [])
        ],
        outcome=call.get("outcome"),
        unanswered_questions=call.get("unanswered_questions", []),
    )


@router.patch("/calls/{call_id}", response_model=CallResponse)
async def update_call(
    call_id: str,
    request: CallUpdateRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> CallResponse:
    """Update call outcome, set ended_at, or append a transcript item."""
    call = await db["calls"].find_one({"$or": [{"id": call_id}, {"_id": call_id}]})
    if not call:
        raise HTTPException(
            status_code=404,
            detail={"error": "CALL_NOT_FOUND", "message": f"Call '{call_id}' not found."},
        )

    updates: dict = {}
    if request.ended_at is not None:
        updates["ended_at"] = request.ended_at
    if request.outcome is not None:
        updates["outcome"] = request.outcome

    update_query: dict = {}
    if updates:
        update_query["$set"] = updates

    if request.transcript_item is not None:
        update_query["$push"] = {"transcript": request.transcript_item.model_dump()}

    if update_query:
        await db["calls"].update_one({"_id": call["_id"]}, update_query)

    updated_call = await db["calls"].find_one({"_id": call["_id"]})
    return CallResponse(
        id=updated_call["id"],
        business_id=updated_call["business_id"],
        started_at=updated_call["started_at"],
        ended_at=updated_call.get("ended_at"),
        transcript=[
            TranscriptItem(
                role=t["role"],
                message=t["message"],
                timestamp=t.get("timestamp", datetime.utcnow()),
            )
            for t in updated_call.get("transcript", [])
        ],
        outcome=updated_call.get("outcome"),
        unanswered_questions=updated_call.get("unanswered_questions", []),
    )


@router.post("/calls/{call_id}/unanswered", response_model=dict)
async def log_call_unanswered_question(
    call_id: str,
    request: UnansweredQuestionRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict:
    """Log an unanswered caller question into the call transcript and triage collection."""
    call = await db["calls"].find_one({"$or": [{"id": call_id}, {"_id": call_id}]})
    if not call:
        raise HTTPException(
            status_code=404,
            detail={"error": "CALL_NOT_FOUND", "message": f"Call '{call_id}' not found."},
        )

    clean_q = request.question.strip()
    now_ts = datetime.utcnow()

    # Append to call document
    await db["calls"].update_one(
        {"_id": call["_id"]},
        {"$addToSet": {"unanswered_questions": clean_q}},
    )

    # Insert into separate collection for manager triage dashboard
    unanswered_doc = {
        "id": f"unq_{uuid.uuid4().hex[:12]}",
        "call_id": call["id"],
        "business_id": call["business_id"],
        "question": clean_q,
        "created_at": now_ts,
    }
    await db["unanswered_questions"].insert_one(unanswered_doc)

    return {
        "status": "logged",
        "call_id": call["id"],
        "question": clean_q,
    }


@router.get("/unanswered", response_model=List[UnansweredQuestionItem])
async def list_unanswered_questions(
    business_id: str = Query(..., description="Business ID to filter unanswered questions"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> List[UnansweredQuestionItem]:
    """Retrieve all logged unanswered questions for a business."""
    cursor = (
        db["unanswered_questions"]
        .find({"business_id": business_id})
        .sort("created_at", pymongo.DESCENDING)
        .limit(limit)
    )
    records = await cursor.to_list(length=limit)

    return [
        UnansweredQuestionItem(
            id=r["id"],
            call_id=r["call_id"],
            business_id=r["business_id"],
            question=r["question"],
            created_at=r["created_at"],
        )
        for r in records
    ]
