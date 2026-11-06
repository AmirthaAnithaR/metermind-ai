from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId

from app.auth import get_current_user
from app.db import invoices_collection, usage_records_collection
from app.models import InvoiceResponse
from app.billing import calculate_bill

router = APIRouter(prefix="/invoices", tags=["Invoices"])

def _format_invoice(doc: dict) -> InvoiceResponse:
    return InvoiceResponse(
        id=str(doc["_id"]),
        user_id=str(doc["user_id"]),
        total_requests=doc["total_requests"],
        total_tokens=doc["total_tokens"],
        amount=float(doc["amount"]),
        currency=doc.get("currency", "USD"),
        status=doc["status"],
        created_at=doc["created_at"]
    )

@router.post("/generate", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
def generate_invoice(current_user: dict = Depends(get_current_user)):
    """
    Generate an invoice from all unbilled usage records:
    - Verifies unbilled usage exists.
    - Aggregates request counts and token counts.
    - Computes bill using pricing engine.
    - Creates a "pending" invoice.
    - Marks all included usage records as "billed" with the invoice_id.
    """
    usage_col = usage_records_collection()
    invoices_col = invoices_collection()
    user_id = str(current_user["id"])

    # Query all unbilled records for user
    unbilled_docs = list(usage_col.find({"user_id": user_id, "status": "unbilled"}))
    if not unbilled_docs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No unbilled usage available to generate invoice"
        )

    unbilled_ids = [doc["_id"] for doc in unbilled_docs]
    total_requests = sum(doc.get("request_count", 0) for doc in unbilled_docs)
    total_tokens = sum(doc.get("total_tokens", 0) for doc in unbilled_docs)
    
    amount_decimal = calculate_bill(total_requests)
    amount_float = float(amount_decimal)

    invoice_doc = {
        "user_id": user_id,
        "total_requests": total_requests,
        "total_tokens": total_tokens,
        "amount": amount_float,
        "currency": "USD",
        "status": "pending",
        "created_at": datetime.now(timezone.utc)
    }

    insert_result = invoices_col.insert_one(invoice_doc)
    invoice_id = insert_result.inserted_id
    invoice_doc["_id"] = invoice_id

    # Mark the usage records as billed
    usage_col.update_many(
        {"_id": {"$in": unbilled_ids}},
        {"$set": {"status": "billed", "invoice_id": str(invoice_id)}}
    )

    return _format_invoice(invoice_doc)

@router.get("", response_model=List[InvoiceResponse])
def get_invoices(current_user: dict = Depends(get_current_user)):
    """
    List all invoices belonging to the authenticated user, newest first.
    """
    invoices_col = invoices_collection()
    user_id = str(current_user["id"])

    cursor = invoices_col.find({"user_id": user_id}).sort("created_at", -1)
    return [_format_invoice(doc) for doc in cursor]
