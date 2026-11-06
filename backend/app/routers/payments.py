from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.auth import get_current_user
from app.db import invoices_collection, payments_collection
from app.models import (
    CreateOrderRequest,
    CreateOrderResponse,
    CapturePaymentRequest,
    CapturePaymentResponse
)
from app.paypal import paypal_client

router = APIRouter(prefix="/payments", tags=["Payments"])

@router.post("/create-order", response_model=CreateOrderResponse)
def create_order(
    request: CreateOrderRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a PayPal order for a pending invoice.
    - Validates invoice ownership.
    - Ensures invoice status is 'pending'.
    - Uses exact invoice amount from database (never trusts client amount).
    """
    invoices_col = invoices_collection()
    user_id = str(current_user["id"])

    # Lookup invoice
    invoice = None
    try:
        invoice = invoices_col.find_one({"_id": ObjectId(request.invoice_id)})
    except Exception:
        invoice = invoices_col.find_one({"_id": request.invoice_id})

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )

    # Ownership check
    if str(invoice.get("user_id")) != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this invoice"
        )

    # Status check
    if invoice.get("status") != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invoice cannot be paid because status is '{invoice.get('status')}'"
        )

    amount = float(invoice["amount"])
    currency = invoice.get("currency", "USD")

    # Call PayPal to create order
    order_data = paypal_client.create_order(
        invoice_id=str(invoice["_id"]),
        amount=amount,
        currency=currency
    )

    return CreateOrderResponse(
        order_id=order_data["order_id"],
        approval_url=order_data.get("approval_url"),
        invoice_id=str(invoice["_id"]),
        amount=amount,
        currency=currency
    )

@router.post("/capture", response_model=CapturePaymentResponse)
def capture_payment(
    request: CapturePaymentRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Capture a PayPal order:
    - Idempotent: if already captured, returns existing payment record.
    - Captures order on PayPal.
    - Verifies COMPLETED status, amount, and currency match the invoice.
    - Records payment and transitions invoice status to 'paid'.
    """
    payments_col = payments_collection()
    invoices_col = invoices_collection()
    user_id = str(current_user["id"])
    order_id = request.order_id.strip()

    # 1. Idempotency check: Has this order already been captured and processed?
    existing_payment = payments_col.find_one({"paypal_order_id": order_id})
    if existing_payment:
        # Verify ownership
        if str(existing_payment.get("user_id")) != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this payment"
            )
        return CapturePaymentResponse(
            status=existing_payment.get("payment_status", "COMPLETED"),
            payment_id=str(existing_payment["_id"]),
            order_id=existing_payment["paypal_order_id"],
            transaction_id=existing_payment.get("transaction_id"),
            amount=float(existing_payment["amount"]),
            currency=existing_payment.get("currency", "USD")
        )

    # 2. Call PayPal to capture the order
    capture_data = paypal_client.capture_order(order_id)
    if capture_data.get("status") != "COMPLETED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"PayPal order not completed. Current status: {capture_data.get('status')}"
        )

    # 3. Locate and validate associated invoice
    reference_id = capture_data.get("reference_id")
    invoice = None
    if reference_id:
        try:
            invoice = invoices_col.find_one({"_id": ObjectId(reference_id)})
        except Exception:
            invoice = invoices_col.find_one({"_id": reference_id})

    if not invoice:
        # Fallback: look for pending invoice for this user matching amount
        invoice = invoices_col.find_one({
            "user_id": user_id,
            "status": "pending",
            "amount": capture_data.get("amount")
        })

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated invoice not found for this capture"
        )

    if str(invoice.get("user_id")) != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to pay for this invoice"
        )

    # 4. Verify amount and currency match
    captured_amount = capture_data.get("amount")
    captured_currency = capture_data.get("currency", "USD")

    if captured_amount is not None:
        if abs(captured_amount - float(invoice["amount"])) > 0.01:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Captured amount (${captured_amount}) does not match invoice amount (${invoice['amount']})"
            )

    if captured_currency != invoice.get("currency", "USD"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Captured currency ({captured_currency}) does not match invoice currency ({invoice.get('currency')})"
        )

    # 5. Persist payment
    payment_doc = {
        "user_id": user_id,
        "invoice_id": str(invoice["_id"]),
        "paypal_order_id": order_id,
        "transaction_id": capture_data.get("transaction_id"),
        "amount": captured_amount if captured_amount is not None else float(invoice["amount"]),
        "currency": captured_currency,
        "payment_status": "COMPLETED",
        "created_at": datetime.now(timezone.utc)
    }

    try:
        insert_res = payments_col.insert_one(payment_doc)
        payment_id = str(insert_res.inserted_id)
    except DuplicateKeyError:
        # Race condition idempotency handling
        existing = payments_col.find_one({"paypal_order_id": order_id})
        return CapturePaymentResponse(
            status=existing.get("payment_status", "COMPLETED"),
            payment_id=str(existing["_id"]),
            order_id=existing["paypal_order_id"],
            transaction_id=existing.get("transaction_id"),
            amount=float(existing["amount"]),
            currency=existing.get("currency", "USD")
        )

    # 6. Mark invoice as paid
    invoices_col.update_one(
        {"_id": invoice["_id"]},
        {"$set": {"status": "paid", "updated_at": datetime.now(timezone.utc)}}
    )

    return CapturePaymentResponse(
        status="COMPLETED",
        payment_id=payment_id,
        order_id=order_id,
        transaction_id=payment_doc["transaction_id"],
        amount=payment_doc["amount"],
        currency=payment_doc["currency"]
    )
