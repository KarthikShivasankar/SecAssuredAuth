from datetime import timedelta
import base64
import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import Base, app, create_jwt, get_db

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


def generate_pkce_pair():
    verifier = "this_is_a_secure_random_verifier_string_12345"
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def test_contextual_risk_flows():
    client.post("/api/register/user", json={"username": "bob", "password": "123", "role": "user"})
    verifier, challenge = generate_pkce_pair()

    req_med = client.post(
        "/api/authorize",
        json={"username": "bob", "password": "123", "code_challenge": challenge},
        headers={"X-Simulated-IP": "10.0.0.1"},
    )
    assert req_med.json()["status"] == "mfa_required"
    assert req_med.json()["risk"] == "MEDIUM"

    mfa_req = client.post(
        "/api/mfa",
        json={"mfa_token": req_med.json()["mfa_token"], "otp_code": "123456", "code_challenge": challenge},
        headers={"X-Simulated-IP": "10.0.0.1"},
    )
    assert mfa_req.json()["status"] == "success"

    req_low = client.post(
        "/api/authorize",
        json={"username": "bob", "password": "123", "code_challenge": challenge},
        headers={"X-Simulated-IP": "10.0.0.1"},
    )
    assert req_low.json()["status"] == "success"
    assert req_low.json()["risk"] == "LOW"

    req_med2 = client.post(
        "/api/authorize",
        json={"username": "bob", "password": "123", "code_challenge": challenge},
        headers={"X-Simulated-IP": "192.168.1.5"},
    )
    assert req_med2.json()["status"] == "mfa_required"
    assert req_med2.json()["risk"] == "MEDIUM"

    req_high = client.post(
        "/api/authorize",
        json={"username": "bob", "password": "123", "code_challenge": challenge},
        headers={"X-Simulated-IP": "66.249.1.1"},
    )
    assert req_high.status_code == 403
    assert "High Risk" in req_high.json()["detail"]


def test_machine_blocked_ip():
    client.post("/api/register/machine", json={"client_id": "ai-1", "client_secret": "sec", "role": "llm"})

    req = client.post(
        "/api/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "ai-1",
            "client_secret": "sec",
        },
        headers={"X-Simulated-IP": "66.249.5.5"},
    )

    assert req.status_code == 403
    assert "High Risk" in req.json()["detail"]


def test_agent_execute_requires_confirmation_for_code():
    token = create_jwt(
        "agent-test",
        "agent",
        ["agent:execute", "agent:code_exec"],
        timedelta(minutes=10),
    )
    req = client.post(
        "/api/agent/execute",
        json={"python_code": "print(1+1)", "confirm_consequential": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert req.status_code == 400
    assert "sandbox_python requires confirm_consequential=true" == req.json()["detail"]
