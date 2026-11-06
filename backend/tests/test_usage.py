import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
import mongomock

from app.main import app
from app.db import db_instance

@pytest.fixture(autouse=True)
def mock_db():
    client = mongomock.MongoClient()
    db = client["metermind_test"]
    db_instance.client = client
    db_instance.db = db
    # setup indexes
    db["users"].create_index("email", unique=True)
    db["usage_records"].create_index("idempotency_key", unique=True, sparse=True)
    yield db
    client.close()

@pytest.fixture
def client():
    return TestClient(app)

def create_user_and_token(client, email="user@example.com"):
    client.post("/auth/register", json={
        "name": "Test User",
        "email": email,
        "password": "password123"
    })
    res = client.post("/auth/login", json={
        "email": email,
        "password": "password123"
    })
    return res.json()["access_token"]

def test_track_usage_server_side_calculation(client):
    token = create_user_and_token(client, "alice@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "service_name": "gpt-4o",
        "request_count": 5,
        "input_tokens": 1500,
        "output_tokens": 500
    }
    res = client.post("/usage/track", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["service_name"] == "gpt-4o"
    assert data["request_count"] == 5
    assert data["input_tokens"] == 1500
    assert data["output_tokens"] == 500
    # Server-side total_tokens computation
    assert data["total_tokens"] == 2000
    assert data["status"] == "unbilled"
    assert data["invoice_id"] is None
    assert "id" in data

def test_usage_tracking_idempotency(client):
    token = create_user_and_token(client, "bob@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "service_name": "claude-3-5-sonnet",
        "request_count": 2,
        "input_tokens": 300,
        "output_tokens": 200,
        "idempotency_key": "unique-req-abc-123"
    }

    # First attempt
    res1 = client.post("/usage/track", json=payload, headers=headers)
    assert res1.status_code == 201
    record1 = res1.json()

    # Second attempt with same key
    res2 = client.post("/usage/track", json=payload, headers=headers)
    assert res2.status_code in (200, 201)
    record2 = res2.json()

    # Must return the existing record and not create another
    assert record1["id"] == record2["id"]
    assert record2["total_tokens"] == 500

    # Verify collection only has 1 record
    history = client.get("/usage/history", headers=headers).json()
    assert len(history) == 1

def test_usage_history_order_and_user_isolation(client):
    token1 = create_user_and_token(client, "user1@example.com")
    token2 = create_user_and_token(client, "user2@example.com")
    h1 = {"Authorization": f"Bearer {token1}"}
    h2 = {"Authorization": f"Bearer {token2}"}

    # User 1 tracks 2 records
    client.post("/usage/track", json={
        "service_name": "service-1",
        "request_count": 1,
        "input_tokens": 100,
        "output_tokens": 50
    }, headers=h1)

    client.post("/usage/track", json={
        "service_name": "service-2",
        "request_count": 2,
        "input_tokens": 200,
        "output_tokens": 100
    }, headers=h1)

    # User 2 tracks 1 record
    client.post("/usage/track", json={
        "service_name": "service-other",
        "request_count": 10,
        "input_tokens": 1000,
        "output_tokens": 500
    }, headers=h2)

    # User 1 should see only 2 records, newest first
    res1 = client.get("/usage/history", headers=h1)
    assert res1.status_code == 200
    list1 = res1.json()
    assert len(list1) == 2
    assert list1[0]["service_name"] == "service-2"
    assert list1[1]["service_name"] == "service-1"

    # User 2 should see only 1 record
    res2 = client.get("/usage/history", headers=h2)
    assert res2.status_code == 200
    list2 = res2.json()
    assert len(list2) == 1
    assert list2[0]["service_name"] == "service-other"

def test_usage_unauthorized(client):
    res = client.post("/usage/track", json={
        "service_name": "gemini-1.5-pro",
        "request_count": 1,
        "input_tokens": 100,
        "output_tokens": 100
    })
    assert res.status_code == 403 or res.status_code == 401
