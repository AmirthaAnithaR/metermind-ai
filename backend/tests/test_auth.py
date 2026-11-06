import pytest
from fastapi.testclient import TestClient
import mongomock
from unittest.mock import patch

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
    yield db
    client.close()

@pytest.fixture
def client():
    return TestClient(app)

def test_register_and_login_flow(client):
    # 1. Register a new user
    register_payload = {
        "name": "Alice Developer",
        "email": "alice@example.com",
        "password": "strongPassword123"
    }
    reg_res = client.post("/auth/register", json=register_payload)
    assert reg_res.status_code == 201
    reg_data = reg_res.json()
    assert reg_data["email"] == "alice@example.com"
    assert "id" in reg_data
    assert "password_hash" not in reg_data

    # 2. Duplicate registration should fail
    dup_res = client.post("/auth/register", json=register_payload)
    assert dup_res.status_code == 400
    assert "already registered" in dup_res.json()["detail"].lower()

    # 3. Login with wrong password should fail
    wrong_login = client.post("/auth/login", json={
        "email": "alice@example.com",
        "password": "wrongPassword"
    })
    assert wrong_login.status_code == 401

    # 4. Login with correct password
    login_res = client.post("/auth/login", json={
        "email": "alice@example.com",
        "password": "strongPassword123"
    })
    assert login_res.status_code == 200
    token_data = login_res.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    token = token_data["access_token"]

    # 5. Access protected /auth/me
    me_res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["email"] == "alice@example.com"
    assert me_data["name"] == "Alice Developer"

def test_invalid_token_rejected(client):
    res = client.get("/auth/me", headers={"Authorization": "Bearer invalid.fake.token"})
    assert res.status_code == 401
