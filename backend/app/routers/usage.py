from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.db import usage_records_collection
from app.models import UsageTrackRequest, UsageRecordResponse
from app.auth import get_current_user

router = APIRouter(prefix="/usage", tags=["Usage Tracking"])

def _format_usage_record(doc: dict) -> UsageRecordResponse:
    return UsageRecordResponse(
        id=str(doc["_id"]),
        user_id=str(doc["user_id"]),
        service_name=doc["service_name"],
        request_count=doc["request_count"],
        input_tokens=doc["input_tokens"],
        output_tokens=doc["output_tokens"],
        total_tokens=doc["total_tokens"],
        idempotency_key=doc.get("idempotency_key"),
        status=doc.get("status", "unbilled"),
        invoice_id=str(doc["invoice_id"]) if doc.get("invoice_id") else None,
        created_at=doc["created_at"]
    )

@router.post("/track", response_model=UsageRecordResponse, status_code=status.HTTP_201_CREATED)
def track_usage(
    request: UsageTrackRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Track an AI service usage record.
    - Server-side calculation of total_tokens.
    - If idempotency_key is provided and already exists, returns existing record without duplicate counting.
    """
    records = usage_records_collection()
    user_id = str(current_user["id"])
    idempotency_key = request.idempotency_key.strip() if request.idempotency_key else None

    # Check for existing idempotency key
    if idempotency_key:
        existing = records.find_one({"idempotency_key": idempotency_key})
        if existing:
            # If exists for another user, reject
            if str(existing.get("user_id")) != user_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key already used by another entity"
                )
            return _format_usage_record(existing)

    total_tokens = request.input_tokens + request.output_tokens
    new_record = {
        "user_id": user_id,
        "service_name": request.service_name.strip(),
        "request_count": request.request_count,
        "input_tokens": request.input_tokens,
        "output_tokens": request.output_tokens,
        "total_tokens": total_tokens,
        "status": "unbilled",
        "invoice_id": None,
        "created_at": datetime.now(timezone.utc)
    }

    if idempotency_key:
        new_record["idempotency_key"] = idempotency_key

    try:
        result = records.insert_one(new_record)
        new_record["_id"] = result.inserted_id
        return _format_usage_record(new_record)
    except DuplicateKeyError:
        # Race condition handling for idempotency_key
        if idempotency_key:
            existing = records.find_one({"idempotency_key": idempotency_key})
            if existing and str(existing.get("user_id")) == user_id:
                return _format_usage_record(existing)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate usage record conflict"
        )

@router.get("/history", response_model=List[UsageRecordResponse])
def get_usage_history(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = Query(50, ge=1, le=500),
    skip: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieve usage history for the current user, newest first.
    Supports optional date filtering with start_date and end_date.
    """
    records = usage_records_collection()
    user_id = str(current_user["id"])

    query = {"user_id": user_id}
    date_filter = {}
    if start_date:
        date_filter["$gte"] = start_date
    if end_date:
        date_filter["$lte"] = end_date
    if date_filter:
        query["created_at"] = date_filter

    cursor = records.find(query).sort("created_at", -1).skip(skip).limit(limit)
    return [_format_usage_record(doc) for doc in cursor]
