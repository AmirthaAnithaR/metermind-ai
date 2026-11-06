from fastapi import APIRouter, Depends
from app.auth import get_current_user
from app.db import usage_records_collection
from app.models import BillingSummaryResponse
from app.billing import calculate_bill

router = APIRouter(prefix="/billing", tags=["Billing"])

@router.get("/summary", response_model=BillingSummaryResponse)
def get_billing_summary(current_user: dict = Depends(get_current_user)):
    """
    Get summary of current unbilled usage:
    - total_requests: sum of request_count in unbilled usage records
    - total_tokens: sum of total_tokens in unbilled usage records
    - current_bill: calculated charge based on pricing engine
    - unbilled_usage: number of unbilled records
    """
    records = usage_records_collection()
    user_id = str(current_user["id"])

    unbilled_docs = list(records.find({"user_id": user_id, "status": "unbilled"}))

    total_requests = sum(doc.get("request_count", 0) for doc in unbilled_docs)
    total_tokens = sum(doc.get("total_tokens", 0) for doc in unbilled_docs)
    unbilled_usage = len(unbilled_docs)
    
    bill_decimal = calculate_bill(total_requests)

    return BillingSummaryResponse(
        total_requests=total_requests,
        total_tokens=total_tokens,
        current_bill=float(bill_decimal),
        unbilled_usage=unbilled_usage
    )
