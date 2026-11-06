import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import httpx
from fastapi import HTTPException, status
from app.config import settings

logger = logging.getLogger("metermind.paypal")

class PayPalClient:
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        base_url: Optional[str] = None,
        http_client: Optional[httpx.Client] = None
    ):
        self.client_id = client_id or settings.PAYPAL_CLIENT_ID
        self.client_secret = client_secret or settings.PAYPAL_CLIENT_SECRET
        self.base_url = (base_url or settings.PAYPAL_BASE_URL).rstrip("/")
        self._http_client = http_client
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    def _get_client(self) -> httpx.Client:
        if self._http_client is not None:
            return self._http_client
        return httpx.Client(timeout=15.0)

    def get_access_token(self) -> str:
        """
        Retrieve OAuth2 client-credentials access token from PayPal.
        Caches the token until its expiration.
        """
        now = datetime.now(timezone.utc)
        if self._access_token and self._token_expires_at and now < self._token_expires_at:
            return self._access_token

        if not self.client_id or not self.client_secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="PayPal client credentials are not configured"
            )

        token_url = f"{self.base_url}/v1/oauth2/token"
        headers = {
            "Accept": "application/json",
            "Accept-Language": "en_US"
        }
        data = {"grant_type": "client_credentials"}

        try:
            with self._get_client() as client:
                res = client.post(
                    token_url,
                    headers=headers,
                    data=data,
                    auth=(self.client_id, self.client_secret)
                )
        except httpx.RequestError as exc:
            logger.error(f"Network error connecting to PayPal token endpoint: {exc}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to connect to PayPal OAuth service"
            )

        if res.status_code != 200:
            logger.error(f"PayPal OAuth failed with status {res.status_code}: {res.text}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to authenticate with PayPal API"
            )

        token_data = res.json()
        self._access_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in", 3600)
        # Safe buffer of 60 seconds before actual expiration
        self._token_expires_at = now + timedelta(seconds=max(expires_in - 60, 60))
        return self._access_token

    def create_order(self, invoice_id: str, amount: float, currency: str = "USD") -> Dict[str, Any]:
        """
        Create a PayPal order for the exact invoice amount.
        Sends PayPal-Request-Id header for idempotency.
        """
        token = self.get_access_token()
        orders_url = f"{self.base_url}/v2/checkout/orders"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "PayPal-Request-Id": f"invoice-order-{invoice_id}"
        }

        formatted_amount = f"{amount:.2f}"
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": str(invoice_id),
                    "description": f"MeterMind AI Invoice #{invoice_id}",
                    "amount": {
                        "currency_code": currency,
                        "value": formatted_amount
                    }
                }
            ],
            "application_context": {
                "brand_name": "MeterMind AI",
                "landing_page": "NO_PREFERENCE",
                "user_action": "PAY_NOW",
                "return_url": "http://localhost:5173/billing?payment=success",
                "cancel_url": "http://localhost:5173/billing?payment=cancelled"
            }
        }

        try:
            with self._get_client() as client:
                res = client.post(orders_url, headers=headers, json=payload)
        except httpx.RequestError as exc:
            logger.error(f"Network error creating PayPal order for invoice {invoice_id}: {exc}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to connect to PayPal Order service"
            )

        if res.status_code not in (200, 201):
            logger.error(f"PayPal create order failed with status {res.status_code}: {res.text}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"PayPal order creation failed: {res.json().get('message', res.text)}"
            )

        order_data = res.json()
        order_id = order_data["id"]

        # Find approval url
        approval_url = None
        for link in order_data.get("links", []):
            if link.get("rel") in ("approve", "payer-action"):
                approval_url = link.get("href")
                break

        return {
            "order_id": order_id,
            "approval_url": approval_url,
            "invoice_id": invoice_id,
            "amount": amount,
            "currency": currency,
            "raw_order": order_data
        }

    def capture_order(self, order_id: str) -> Dict[str, Any]:
        """
        Capture a PayPal order by ID.
        Sends PayPal-Request-Id header for idempotency.
        """
        token = self.get_access_token()
        capture_url = f"{self.base_url}/v2/checkout/orders/{order_id}/capture"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "PayPal-Request-Id": f"capture-order-{order_id}"
        }

        try:
            with self._get_client() as client:
                res = client.post(capture_url, headers=headers)
        except httpx.RequestError as exc:
            logger.error(f"Network error capturing PayPal order {order_id}: {exc}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to connect to PayPal Capture service"
            )

        # Handle order already captured or completed
        if res.status_code not in (200, 201):
            logger.error(f"PayPal capture failed with status {res.status_code}: {res.text}")
            error_data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
            detail_msg = error_data.get("message") or error_data.get("name") or "PayPal order capture failed"
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=detail_msg
            )

        data = res.json()
        order_status = data.get("status")
        purchase_units = data.get("purchase_units", [])
        
        transaction_id = None
        captured_amount = None
        captured_currency = "USD"
        reference_id = None

        if purchase_units:
            pu = purchase_units[0]
            reference_id = pu.get("reference_id")
            payments = pu.get("payments", {})
            captures = payments.get("captures", [])
            if captures:
                first_capture = captures[0]
                transaction_id = first_capture.get("id")
                seller_receivable_breakdown = first_capture.get("amount", {})
                captured_amount = float(seller_receivable_breakdown.get("value", 0.0))
                captured_currency = seller_receivable_breakdown.get("currency_code", "USD")

        return {
            "status": order_status,
            "order_id": order_id,
            "transaction_id": transaction_id,
            "amount": captured_amount,
            "currency": captured_currency,
            "reference_id": reference_id,
            "raw_response": data
        }

# Global singleton client instance
paypal_client = PayPalClient()
