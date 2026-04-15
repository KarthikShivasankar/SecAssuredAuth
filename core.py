import base64
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Generator, Tuple

from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, create_engine, desc
from sqlalchemy.orm import Session, declarative_base, sessionmaker

SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret-key-for-local-dev-1234")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
AUTH_CODE_EXPIRE_MINUTES = 5

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./local_dev.db")

ROLE_SCOPES = {
    "guest": ["read:public"],
    "user": ["read:public", "read:profile", "write:profile"],
    "admin": ["read:public", "read:profile", "write:profile", "admin:all"],
    "llm": ["read:context", "ai:generate"],
    "agent": [
        "read:context",
        "write:context",
        "agent:execute",
        "agent:web_search",
        "agent:calc",
        "agent:db_read",
        "agent:llm",
        "agent:code_exec",
    ],
    "mcp_server": ["mcp:connect", "mcp:stream", "read:context"],
}

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="user")


class MachineClient(Base):
    __tablename__ = "machine_clients"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(String, unique=True, index=True)
    hashed_secret = Column(String)
    role = Column(String)


class AuthCode(Base):
    __tablename__ = "auth_codes"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    code_challenge = Column(String)
    expires_at = Column(DateTime(timezone=True))


class LoginActivity(Base):
    __tablename__ = "login_activity"
    id = Column(Integer, primary_key=True, index=True)
    entity_id = Column(String, index=True)
    ip_address = Column(String)
    user_agent = Column(String)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    status = Column(String)
    risk_level = Column(String)


class AgentAudit(Base):
    __tablename__ = "agent_audit"
    id = Column(Integer, primary_key=True, index=True)
    actor = Column(String, index=True)
    action = Column(String)
    status = Column(String)
    details = Column(String)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/token",
    scopes={
        "read:public": "Read public data",
        "read:profile": "Read user profile",
        "write:profile": "Modify user profile",
        "admin:all": "Full admin access",
        "ai:generate": "Access LLM inference",
        "agent:execute": "Execute autonomous actions",
        "agent:web_search": "Agent web search capability",
        "agent:calc": "Agent calculator capability",
        "agent:db_read": "Agent external DB read capability",
        "agent:llm": "Agent Ollama generation capability",
        "agent:code_exec": "Agent sandboxed code execution capability",
        "mcp:stream": "Stream MCP protocol data",
    },
)


def verify_hash(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def get_hash(secret: str) -> str:
    return pwd_context.hash(secret)


def create_jwt(subject: str, entity_type: str, scopes: list, expires_delta: timedelta) -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode = {"sub": subject, "type": entity_type, "scopes": scopes, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_pkce(code_challenge: str, code_verifier: str) -> bool:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    expected_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return secrets.compare_digest(expected_challenge, code_challenge)


def get_client_context(request: Request) -> Tuple[str, str]:
    ip = (
        request.headers.get("X-Simulated-IP")
        or request.headers.get("x-forwarded-for", request.client.host).split(",")[0]
    )
    ua = request.headers.get("X-Simulated-UA") or request.headers.get("user-agent", "Unknown")
    return ip, ua


def evaluate_context(db: Session, entity_id: str, ip_address: str, user_agent: str) -> Tuple[str, str]:
    if ip_address.startswith("66.249.") or ip_address == "1.2.3.4":
        return "HIGH", "BLOCK"
    last_success = (
        db.query(LoginActivity)
        .filter(LoginActivity.entity_id == entity_id, LoginActivity.status == "SUCCESS")
        .order_by(desc(LoginActivity.timestamp))
        .first()
    )
    if not last_success or last_success.ip_address != ip_address or last_success.user_agent != user_agent:
        return "MEDIUM", "STEP_UP"
    return "LOW", "ALLOW"


def verify_scopes(security_scopes: SecurityScopes, token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        token_scopes = payload.get("scopes", [])
        for scope in security_scopes.scopes:
            if scope not in token_scopes:
                raise HTTPException(status_code=403, detail=f"Missing scope: {scope}")
        return payload
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


def log_activity(db: Session, entity_id: str, ip: str, ua: str, status: str, risk: str):
    db.add(LoginActivity(entity_id=entity_id, ip_address=ip, user_agent=ua, status=status, risk_level=risk))
    db.commit()
