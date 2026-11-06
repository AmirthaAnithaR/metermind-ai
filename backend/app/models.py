from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field

# ================= AUTH MODELS =================
class UserRegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)

class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    created_at: datetime

# ================= USAGE MODELS =================
class UsageTrackRequest(BaseModel):
    service_name: str = Field(..., min_length=1, max_length=100)
    request_count: int = Field(..., ge=1)
    input_tokens: int = Field(..., ge=0)
    output_tokens: int = Field(..., ge=0)
    idempotency_key: Optional[str] = Field(None, max_length=128)

class UsageRecordResponse(BaseModel):
    id: str
    user_id: str
    service_name: str
    request_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    idempotency_key: Optional[str] = None
    status: str = "unbilled"
    invoice_id: Optional[str] = None
    created_at: datetime

# ================= BILLING & INVOICE MODELS =================
class BillingSummaryResponse(BaseModel):
    total_requests: int
    total_tokens: int
    current_bill: float
    unbilled_usage: int

class InvoiceResponse(BaseModel):
    id: str
    user_id: str
    total_requests: int
    total_tokens: int
    amount: float
    currency: str = "USD"
    status: str  # "pending" | "paid"
    created_at: datetime

# ================= PAYMENT MODELS =================
class CreateOrderRequest(BaseModel):
    invoice_id: str

class CreateOrderResponse(BaseModel):
    order_id: str
    approval_url: Optional[str] = None
    invoice_id: str
    amount: float
    currency: str = "USD"

class CapturePaymentRequest(BaseModel):
    order_id: str

class CapturePaymentResponse(BaseModel):
    status: str
    payment_id: str
    order_id: str
    transaction_id: Optional[str] = None
    amount: float
    currency: str = "USD"
