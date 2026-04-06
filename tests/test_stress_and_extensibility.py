import base64
import hashlib
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import Base, app, create_jwt, get_db, register_agent_action

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


def generate_pkce_pair(seed: str):
    verifier = f"secure_verifier_{seed}_1234567890abcdef"
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def _register_and_authorize(username: str, password: str, ip: str):
    verifier, challenge = generate_pkce_pair(username)
    client.post("/api/register/user", json={"username": username, "password": password, "role": "user"})
    response = client.post(
        "/api/authorize",
        json={"username": username, "password": password, "code_challenge": challenge},
        headers={"X-Simulated-IP": ip, "X-Simulated-UA": "stress-tester/1.0"},
    )
    return response.status_code, response.json()


def test_stress_burst_first_logins_trigger_mfa():
    # Stable stress test: burst of many sequential requests with unique users/contexts.
    user_count = 100
    results = []
    for i in range(user_count):
        results.append(_register_and_authorize(f"user_{i}", "StrongPassword123!", f"10.0.0.{i+1}"))

    assert len(results) == user_count
    assert all(status == 200 for status, _ in results)
    assert all(payload.get("status") == "mfa_required" for _, payload in results)
    assert all(payload.get("risk") == "MEDIUM" for _, payload in results)


def test_action_level_scope_enforcement_for_web_search():
    token = create_jwt("agent-a", "agent", ["agent:execute"], timedelta(minutes=10))
    req = client.post(
        "/api/agent/execute",
        json={"web_query": "oauth 2.1 best practices"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert req.status_code == 403
    assert req.json()["detail"] == "Missing scope: agent:web_search"


def test_registry_extensibility_with_custom_action():
    # Dynamically register a new action to emulate onboarding a new microservice capability.
    register_agent_action("echo_tool", "agent:echo", lambda value: {"echo": value})
    token = create_jwt("agent-b", "agent", ["agent:execute", "agent:echo"], timedelta(minutes=10))

    req = client.post(
        "/api/agent/execute",
        json={"custom_actions": {"echo_tool": "hello-world"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert req.status_code == 200
    data = req.json()
    assert data["actions"]["echo_tool"]["echo"] == "hello-world"


def test_registry_rejects_unknown_action():
    token = create_jwt("agent-c", "agent", ["agent:execute"], timedelta(minutes=10))
    req = client.post(
        "/api/agent/execute",
        json={"custom_actions": {"missing_tool": {"k": "v"}}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert req.status_code == 400
    assert req.json()["detail"] == "Unknown action: missing_tool"
