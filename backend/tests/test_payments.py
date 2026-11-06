import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import mongomock

from app.main import app
from app.db import db_instance
from app.paypal import paypal_client

@pytest.fixture(autouse=True)
def mock_db():
    client = mongomock.MongoClient()
    db = client["metermind_test"]
    db_instance.client = client
    db_instance.db = db
    db["users"].create_index("email", unique=True)
    db["usage_records"].create_index("idempotency_key", unique=True, sparse=True)
    db["payments"].create_index("paypal_order_id", unique=True)
    yield db
    client.close()

@pytest.fixture
def client():
    return TestClient(app)

def create_user_and_token(client, email="pay_user@example.com"):
    client.post("/auth/register", json={
        "name": "Pay User",
        "email": email,
        "password": "password123"
    })
    res = client.post("/auth/login", json={
        "email": email,
        "password": "password123"
    })
    return res.json()["access_token"]

def create_pending_invoice(client, headers, request_count=200):
    # Track usage (200 requests = $2.00)
    client.post("/usage/track", json={
        "service_name": "gpt-4o",
        "request_count": request_count,
        "input_tokens": 1000,
        "output_tokens": 500
    }, headers=headers)
    inv_res = client.post("/invoices/generate", headers=headers)
    return inv_res.json()

def test_create_order_flow(client):
    token = create_user_and_token(client, "buyer@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    invoice = create_pending_invoice(client, headers, request_count=200)

    # Mock paypal_client.create_order
    mock_order_response = {
        "order_id": "ORDER-MOCK-12345",
        "approval_url": "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-MOCK-12345",
        "invoice_id": invoice["id"],
        "amount": 2.00,
        "currency": "USD"
    }

    with patch.object(paypal_client, "create_order", return_value=mock_order_response) as mock_create:
        res = client.post("/payments/create-order", json={"invoice_id": invoice["id"]}, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["order_id"] == "ORDER-MOCK-12345"
        assert data["approval_url"] == "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-MOCK-12345"
        assert data["amount"] == 2.00
        assert data["currency"] == "USD"
        
        # Verify PayPal was called with amount from DB invoice
        mock_create.assert_called_once_with(
            invoice_id=invoice["id"],
            amount=2.00,
            currency="USD"
        )

def test_create_order_security_and_validation(client):
    token1 = create_user_and_token(client, "user_a@example.com")
    token2 = create_user_and_token(client, "user_b@example.com")
    h1 = {"Authorization": f"Bearer {token1}"}
    h2 = {"Authorization": f"Bearer {token2}"}

    invoice_a = create_pending_invoice(client, h1, request_count=100)

    # 1. Non-existent invoice -> 404
    res_404 = client.post("/payments/create-order", json={"invoice_id": "000000000000000000000000"}, headers=h1)
    assert res_404.status_code == 404

    # 2. User B trying to create order for User A's invoice -> 403 Forbidden
    res_403 = client.post("/payments/create-order", json={"invoice_id": invoice_a["id"]}, headers=h2)
    assert res_403.status_code == 403

def test_capture_payment_idempotency(client):
    token = create_user_and_token(client, "capture_tester@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    invoice = create_pending_invoice(client, headers, request_count=300)  # $3.00

    order_id = "ORDER-CAPTURE-999"

    mock_capture_data = {
        "status": "COMPLETED",
        "order_id": order_id,
        "transaction_id": "TXN-SANDBOX-888",
        "amount": 3.00,
        "currency": "USD",
        "reference_id": invoice["id"]
    }

    with patch.object(paypal_client, "capture_order", return_value=mock_capture_data) as mock_capture:
        # First capture call
        cap_res1 = client.post("/payments/capture", json={"order_id": order_id}, headers=headers)
        assert cap_res1.status_code == 200
        data1 = cap_res1.json()
        assert data1["status"] == "COMPLETED"
        assert data1["order_id"] == order_id
        assert data1["transaction_id"] == "TXN-SANDBOX-888"
        assert data1["amount"] == 3.00
        mock_capture.assert_called_once_with(order_id)

        # Invoice should now be marked "paid"
        inv_list = client.get("/invoices", headers=headers).json()
        assert inv_list[0]["id"] == invoice["id"]
        assert inv_list[0]["status"] == "paid"

        # Attempting to create order for already paid invoice should now fail
        order_paid = client.post("/payments/create-order", json={"invoice_id": invoice["id"]}, headers=headers)
        assert order_paid.status_code == 400

        # Reset mock call count to verify second capture does NOT call PayPal
        mock_capture.reset_mock()

        # Second capture call with same order_id (idempotency check)
        cap_res2 = client.post("/payments/capture", json={"order_id": order_id}, headers=headers)
        assert cap_res2.status_code == 200
        data2 = cap_res2.json()
        assert data2["payment_id"] == data1["payment_id"]
        assert data2["transaction_id"] == "TXN-SANDBOX-888"

        # PayPal API must NOT be called again
        mock_capture.assert_not_called()

def test_capture_amount_mismatch_rejected(client):
    token = create_user_and_token(client, "mismatch_user@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    invoice = create_pending_invoice(client, headers, request_count=100)  # $1.00

    order_id = "ORDER-MISMATCH-123"
    # PayPal captured $5.00 instead of $1.00
    mock_bad_capture = {
        "status": "COMPLETED",
        "order_id": order_id,
        "transaction_id": "TXN-BAD",
        "amount": 5.00,
        "currency": "USD",
        "reference_id": invoice["id"]
    }

    with patch.object(paypal_client, "capture_order", return_value=mock_bad_capture):
        res = client.post("/payments/capture", json={"order_id": order_id}, headers=headers)
        assert res.status_code == 400
        assert "does not match invoice amount" in res.json()["detail"].lower()

def test_paypal_client_token_caching():
    import httpx
    from app.paypal import PayPalClient

    fake_client = PayPalClient(client_id="fake_id", client_secret="fake_secret")
    
    mock_response = httpx.Response(
        200,
        json={"access_token": "ACCESS-TOKEN-XYZ", "expires_in": 3600},
        request=httpx.Request("POST", "https://api-m.sandbox.paypal.com/v1/oauth2/token")
    )

    with patch.object(httpx.Client, "post", return_value=mock_response) as mock_post:
        # First call fetches token
        tok1 = fake_client.get_access_token()
        assert tok1 == "ACCESS-TOKEN-XYZ"
        assert mock_post.call_count == 1

        # Second call returns cached token without making another HTTP request
        tok2 = fake_client.get_access_token()
        assert tok2 == "ACCESS-TOKEN-XYZ"
        assert mock_post.call_count == 1
