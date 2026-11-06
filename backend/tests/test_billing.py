import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
import mongomock

from app.main import app
from app.db import db_instance
from app.billing import calculate_bill

@pytest.fixture(autouse=True)
def mock_db():
    client = mongomock.MongoClient()
    db = client["metermind_test"]
    db_instance.client = client
    db_instance.db = db
    db["users"].create_index("email", unique=True)
    db["usage_records"].create_index("idempotency_key", unique=True, sparse=True)
    yield db
    client.close()

@pytest.fixture
def client():
    return TestClient(app)

def create_user_and_token(client, email="billing_user@example.com"):
    client.post("/auth/register", json={
        "name": "Billing User",
        "email": email,
        "password": "password123"
    })
    res = client.post("/auth/login", json={
        "email": email,
        "password": "password123"
    })
    return res.json()["access_token"]

# ================= PURE BILLING ENGINE TESTS =================
def test_billing_math_pure_functions():
    # 100 requests = 1.00 USD
    assert calculate_bill(100) == Decimal("1.00")
    # 250 requests = 2.50 USD
    assert calculate_bill(250) == Decimal("2.50")
    # 0 requests = 0.00 USD
    assert calculate_bill(0) == Decimal("0.00")
    # 1 request = 0.01 USD (rounded)
    assert calculate_bill(1) == Decimal("0.01")
    # 149 requests = 1.49 USD
    assert calculate_bill(149) == Decimal("1.49")
    
    # Custom rate configuration
    custom_cfg = {"base_rate_per_100_requests": Decimal("2.50")}
    assert calculate_bill(100, custom_cfg) == Decimal("2.50")
    assert calculate_bill(200, custom_cfg) == Decimal("5.00")

    # Negative requests should raise ValueError
    with pytest.raises(ValueError):
        calculate_bill(-10)

# ================= BILLING SUMMARY & INVOICE ENDPOINT TESTS =================
def test_billing_summary_and_invoice_generation(client):
    token = create_user_and_token(client, "user_invoice@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Summary with 0 usage
    res = client.get("/billing/summary", headers=headers)
    assert res.status_code == 200
    summary = res.json()
    assert summary["total_requests"] == 0
    assert summary["total_tokens"] == 0
    assert summary["current_bill"] == 0.0
    assert summary["unbilled_usage"] == 0

    # 2. Generating invoice with no unbilled records must fail with 400
    empty_gen = client.post("/invoices/generate", headers=headers)
    assert empty_gen.status_code == 400
    assert "no unbilled usage" in empty_gen.json()["detail"].lower()

    # 3. Track two usage events
    client.post("/usage/track", json={
        "service_name": "gpt-4o",
        "request_count": 120,
        "input_tokens": 1000,
        "output_tokens": 500
    }, headers=headers)

    client.post("/usage/track", json={
        "service_name": "claude-3-5",
        "request_count": 80,
        "input_tokens": 2000,
        "output_tokens": 1000
    }, headers=headers)

    # 4. Check updated summary (total 200 requests = 2.00 USD)
    res_summary = client.get("/billing/summary", headers=headers)
    assert res_summary.status_code == 200
    summary_data = res_summary.json()
    assert summary_data["total_requests"] == 200
    assert summary_data["total_tokens"] == 4500
    assert summary_data["current_bill"] == 2.00
    assert summary_data["unbilled_usage"] == 2

    # 5. Generate invoice
    gen_res = client.post("/invoices/generate", headers=headers)
    assert gen_res.status_code == 201
    invoice = gen_res.json()
    assert invoice["total_requests"] == 200
    assert invoice["total_tokens"] == 4500
    assert invoice["amount"] == 2.00
    assert invoice["currency"] == "USD"
    assert invoice["status"] == "pending"
    invoice_id = invoice["id"]

    # 6. Verify usage records are now marked as "billed" and linked to invoice
    history = client.get("/usage/history", headers=headers).json()
    assert len(history) == 2
    for record in history:
        assert record["status"] == "billed"
        assert record["invoice_id"] == invoice_id

    # 7. Summary is now reset to 0 unbilled
    res_summary_after = client.get("/billing/summary", headers=headers)
    assert res_summary_after.json()["current_bill"] == 0.0
    assert res_summary_after.json()["unbilled_usage"] == 0

    # 8. Attempting to generate another invoice immediately fails
    double_gen = client.post("/invoices/generate", headers=headers)
    assert double_gen.status_code == 400

    # 9. List invoices
    invoices_list = client.get("/invoices", headers=headers).json()
    assert len(invoices_list) == 1
    assert invoices_list[0]["id"] == invoice_id
    assert invoices_list[0]["status"] == "pending"

def test_invoice_user_isolation(client):
    token1 = create_user_and_token(client, "user_iso1@example.com")
    token2 = create_user_and_token(client, "user_iso2@example.com")
    h1 = {"Authorization": f"Bearer {token1}"}
    h2 = {"Authorization": f"Bearer {token2}"}

    # User 1 tracks and generates invoice
    client.post("/usage/track", json={
        "service_name": "gpt-4o",
        "request_count": 100,
        "input_tokens": 500,
        "output_tokens": 200
    }, headers=h1)
    inv1 = client.post("/invoices/generate", headers=h1).json()

    # User 2 list invoices should be empty
    inv2_list = client.get("/invoices", headers=h2).json()
    assert len(inv2_list) == 0

    # User 1 list invoices should have 1
    inv1_list = client.get("/invoices", headers=h1).json()
    assert len(inv1_list) == 1
    assert inv1_list[0]["id"] == inv1["id"]
