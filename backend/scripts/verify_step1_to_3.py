import sys
import os
from pathlib import Path

# Add backend to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from app.main import app
from app.db import init_db

def run_verification():
    print("==================================================")
    print("[*] RUNNING END-TO-END VERIFICATION (STEPS 1 - 3)")
    print("==================================================")
    
    # 1. Initialize DB indexes
    init_db()
    client = TestClient(app)
    
    # Generate unique test email to avoid duplicate conflicts
    import time
    timestamp = int(time.time())
    email = f"developer_{timestamp}@example.com"
    password = "SecurePassword#2026"
    
    # Step 1: Auth - Register
    print(f"\n[1] Registering user: {email}")
    reg_res = client.post("/auth/register", json={
        "name": "Alex Developer",
        "email": email,
        "password": password
    })
    print("Register response status:", reg_res.status_code)
    assert reg_res.status_code == 201, f"Failed register: {reg_res.text}"
    user_data = reg_res.json()
    print("Registered User ID:", user_data["id"])
    print("User Email:", user_data["email"])
    
    # Step 1: Auth - Login
    print("\n[2] Logging in to retrieve JWT access token...")
    login_res = client.post("/auth/login", json={
        "email": email,
        "password": password
    })
    print("Login response status:", login_res.status_code)
    assert login_res.status_code == 200, f"Failed login: {login_res.text}"
    token = login_res.json()["access_token"]
    print("Obtained JWT Token (first 25 chars):", token[:25] + "...")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Step 1: Verify profile (/auth/me)
    me_res = client.get("/auth/me", headers=headers)
    assert me_res.status_code == 200
    print("Authenticated user profile:", me_res.json()["name"], f"({me_res.json()['email']})")

    # Step 2: Usage Tracking - Track AI usage
    print("\n[3] Tracking usage record 1 (gpt-4o, 150 requests, 1200 in / 800 out)...")
    u1_res = client.post("/usage/track", json={
        "service_name": "gpt-4o",
        "request_count": 150,
        "input_tokens": 1200,
        "output_tokens": 800,
        "idempotency_key": f"key-a-{timestamp}"
    }, headers=headers)
    print("Usage 1 status:", u1_res.status_code)
    assert u1_res.status_code == 201
    u1_data = u1_res.json()
    print(f"Record 1 -> Total Tokens: {u1_data['total_tokens']}, Status: {u1_data['status']}")
    assert u1_data["total_tokens"] == 2000
    assert u1_data["status"] == "unbilled"

    # Step 2: Idempotency deduplication check
    print("\n[4] Retrying usage record 1 with the SAME idempotency key (deduplication check)...")
    u1_dup = client.post("/usage/track", json={
        "service_name": "gpt-4o",
        "request_count": 150,
        "input_tokens": 1200,
        "output_tokens": 800,
        "idempotency_key": f"key-a-{timestamp}"
    }, headers=headers)
    print("Duplicate track status:", u1_dup.status_code)
    assert u1_dup.json()["id"] == u1_data["id"]
    print("Deduplication verified: Returned identical record ID without double counting.")

    # Track usage record 2
    print("\n[5] Tracking usage record 2 (claude-3-5-sonnet, 50 requests, 600 in / 400 out)...")
    u2_res = client.post("/usage/track", json={
        "service_name": "claude-3-5-sonnet",
        "request_count": 50,
        "input_tokens": 600,
        "output_tokens": 400
    }, headers=headers)
    assert u2_res.status_code == 201
    u2_data = u2_res.json()
    print(f"Record 2 -> Total Tokens: {u2_data['total_tokens']}, Status: {u2_data['status']}")

    # Step 2: Usage History
    print("\n[6] Fetching usage history...")
    history_res = client.get("/usage/history", headers=headers)
    assert history_res.status_code == 200
    history = history_res.json()
    print(f"Total history records retrieved: {len(history)} (newest first)")
    assert len(history) >= 2
    print(f"Most recent record: {history[0]['service_name']}, requests: {history[0]['request_count']}")

    # Step 3: Billing Summary
    print("\n[7] Querying Billing Summary before invoicing...")
    # Expected: 150 + 50 = 200 requests. 200 / 100 * $1.00 = $2.00
    # Total tokens: 2000 + 1000 = 3000 tokens
    sum_res = client.get("/billing/summary", headers=headers)
    assert sum_res.status_code == 200
    summary = sum_res.json()
    print("Billing Summary:")
    print(f" - Total Requests: {summary['total_requests']}")
    print(f" - Total Tokens:   {summary['total_tokens']}")
    print(f" - Unbilled Items: {summary['unbilled_usage']}")
    print(f" - Current Bill:   ${summary['current_bill']:.2f} USD")
    assert summary["total_requests"] == 200
    assert summary["total_tokens"] == 3000
    assert summary["current_bill"] == 2.00
    assert summary["unbilled_usage"] == 2

    # Step 3: Invoices - Generate
    print("\n[8] Generating invoice for all unbilled usage...")
    inv_res = client.post("/invoices/generate", headers=headers)
    print("Generate Invoice status:", inv_res.status_code)
    assert inv_res.status_code == 201
    invoice = inv_res.json()
    print(f"Invoice Generated:")
    print(f" - Invoice ID:     {invoice['id']}")
    print(f" - Requests:       {invoice['total_requests']}")
    print(f" - Tokens:         {invoice['total_tokens']}")
    print(f" - Amount Due:     ${invoice['amount']:.2f} {invoice['currency']}")
    print(f" - Status:         {invoice['status']}")
    assert invoice["amount"] == 2.00
    assert invoice["status"] == "pending"

    # Step 3: Verify usage records were transitioned to "billed"
    print("\n[9] Verifying usage records status transitioned to 'billed'...")
    history_after = client.get("/usage/history", headers=headers).json()
    for rec in history_after[:2]:
        print(f" - Record {rec['service_name']}: status={rec['status']}, invoice_id={rec['invoice_id']}")
        assert rec["status"] == "billed"
        assert rec["invoice_id"] == invoice["id"]

    # Step 3: Verify summary is now 0 unbilled
    print("\n[10] Verifying billing summary is now reset...")
    sum_after = client.get("/billing/summary", headers=headers).json()
    print(f" - Unbilled items remaining: {sum_after['unbilled_usage']}")
    print(f" - Current bill: ${sum_after['current_bill']:.2f}")
    assert sum_after["unbilled_usage"] == 0
    assert sum_after["current_bill"] == 0.0

    # Step 3: Prevent duplicate empty invoice generation
    print("\n[11] Verifying empty invoice generation is refused (400 Bad Request)...")
    empty_res = client.post("/invoices/generate", headers=headers)
    print("Attempting duplicate invoice generation status:", empty_res.status_code)
    assert empty_res.status_code == 400
    print("Refusal detail:", empty_res.json()["detail"])

    # Step 3: List invoices
    print("\n[12] Listing user invoices...")
    inv_list_res = client.get("/invoices", headers=headers)
    assert inv_list_res.status_code == 200
    invoices = inv_list_res.json()
    print(f"Found {len(invoices)} invoice(s). Top invoice ID: {invoices[0]['id']}, Status: {invoices[0]['status']}")
    assert invoices[0]["id"] == invoice["id"]

    print("\n==================================================")
    print("[PASS] ALL CHECKS PASSED SUCCESSFULLY (STEPS 1 - 3)")
    print("==================================================")

if __name__ == "__main__":
    run_verification()
