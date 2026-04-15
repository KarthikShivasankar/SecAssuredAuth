from datetime import datetime, timedelta, timezone
import os
import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from jose import jwt
import pyotp
from sqlalchemy.orm import Session

from core import (
    APP_ENV,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    AUTH_CODE_EXPIRE_MINUTES,
    JWT_AUDIENCE,
    JWT_ISSUER,
    MFA_TOKEN_EXPIRE_MINUTES,
    ROLE_SCOPES,
    SECRET_KEY,
    AuthCode,
    MFAChallenge,
    MachineClient,
    User,
    create_jwt,
    enforce_rate_limit,
    evaluate_context,
    get_client_context,
    get_db,
    get_hash,
    log_activity,
    verify_hash,
    verify_pkce,
)
from schemas import AuthorizeRequest, MFAVerify, MachineCreate, UserCreate

router = APIRouter(prefix="/api")
ADMIN_BOOTSTRAP_TOKEN = os.getenv("ADMIN_BOOTSTRAP_TOKEN")
MAX_MFA_ATTEMPTS = int(os.getenv("MAX_MFA_ATTEMPTS", "5"))
ALLOWED_MACHINE_ROLES = {"llm", "agent", "mcp_server"}


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def issue_auth_code(db: Session, user_id: int, username: str, code_challenge: str, ip_address: str, user_agent: str, risk_level: str):
    code = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(minutes=AUTH_CODE_EXPIRE_MINUTES)
    db.add(AuthCode(code=code, user_id=user_id, code_challenge=code_challenge, expires_at=expires))
    log_activity(db, username, ip_address, user_agent, "SUCCESS", risk_level)
    db.commit()
    return {"status": "success", "auth_code": code, "risk": risk_level}


def _require_bootstrap_token(request: Request):
    if APP_ENV != "production" and not ADMIN_BOOTSTRAP_TOKEN:
        return
    provided = request.headers.get("X-Admin-Bootstrap-Token")
    if not ADMIN_BOOTSTRAP_TOKEN or provided != ADMIN_BOOTSTRAP_TOKEN:
        raise HTTPException(status_code=403, detail="Bootstrap token required")


@router.post("/register/user")
def register_user(user: UserCreate, request: Request, db: Session = Depends(get_db)):
    ip_address, _ = get_client_context(request)
    enforce_rate_limit(f"register:user:{ip_address}:{user.username}")
    if db.query(User).filter(User.username == user.username).first():
        raise HTTPException(status_code=400, detail="Username exists")
    requested_role = user.role
    role = "user"
    if requested_role != "user":
        _require_bootstrap_token(request)
        role = requested_role
    mfa_secret = pyotp.random_base32()
    db.add(User(username=user.username, hashed_password=get_hash(user.password), role=role, mfa_secret=mfa_secret))
    db.commit()
    totp = pyotp.TOTP(mfa_secret)
    provisioning_uri = totp.provisioning_uri(name=user.username, issuer_name=JWT_ISSUER)
    return {
        "message": f"User '{user.username}' registered as '{role}'",
        "mfa_setup": {
            "secret": mfa_secret,
            "provisioning_uri": provisioning_uri,
        },
    }


@router.post("/register/machine")
def register_machine(machine: MachineCreate, request: Request, db: Session = Depends(get_db)):
    ip_address, _ = get_client_context(request)
    enforce_rate_limit(f"register:machine:{ip_address}:{machine.client_id}")
    _require_bootstrap_token(request)
    if db.query(MachineClient).filter(MachineClient.client_id == machine.client_id).first():
        raise HTTPException(status_code=400, detail="Client ID exists")
    if machine.role not in ALLOWED_MACHINE_ROLES:
        raise HTTPException(status_code=400, detail="Invalid machine role")
    db.add(MachineClient(client_id=machine.client_id, hashed_secret=get_hash(machine.client_secret), role=machine.role))
    db.commit()
    return {"message": f"Machine '{machine.client_id}' registered as '{machine.role}'"}


@router.post("/authorize")
def authorize(request: Request, data: AuthorizeRequest, db: Session = Depends(get_db)):
    ip_address, user_agent = get_client_context(request)
    enforce_rate_limit(f"authorize:{ip_address}:{data.username}")
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not verify_hash(data.password, user.hashed_password):
        log_activity(db, data.username, ip_address, user_agent, "FAILED", "UNKNOWN")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    risk_level, action = evaluate_context(db, user.username, ip_address, user_agent)
    if action == "BLOCK":
        log_activity(db, user.username, ip_address, user_agent, "BLOCKED", risk_level)
        raise HTTPException(status_code=403, detail="High Risk: Login blocked from known malicious IP.")
    if action == "STEP_UP":
        log_activity(db, user.username, ip_address, user_agent, "MFA_REQUIRED", risk_level)
        challenge_id = secrets.token_urlsafe(24)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=MFA_TOKEN_EXPIRE_MINUTES)
        db.add(MFAChallenge(challenge_id=challenge_id, username=user.username, expires_at=expires_at, attempt_count=0))
        db.commit()
        mfa_token = jwt.encode(
            {
                "sub": user.username,
                "type": "mfa_pending",
                "challenge_id": challenge_id,
                "iss": JWT_ISSUER,
                "aud": JWT_AUDIENCE,
                "exp": expires_at,
            },
            SECRET_KEY,
            algorithm=ALGORITHM,
        )
        return {"status": "mfa_required", "mfa_token": mfa_token, "risk": risk_level, "message": "Medium Risk: Unrecognized device/location detected. Step-up MFA required."}
    return issue_auth_code(db, user.id, user.username, data.code_challenge, ip_address, user_agent, risk_level)


@router.post("/mfa")
def verify_mfa(request: Request, data: MFAVerify, db: Session = Depends(get_db)):
    ip_address, _ = get_client_context(request)
    enforce_rate_limit(f"mfa:{ip_address}")
    try:
        payload = jwt.decode(
            data.mfa_token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
        )
        if payload.get("type") != "mfa_pending":
            raise ValueError("invalid mfa type")
        username = payload.get("sub")
        challenge_id = payload.get("challenge_id")
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid MFA token") from exc

    user = db.query(User).filter(User.username == username).first()
    challenge = db.query(MFAChallenge).filter(MFAChallenge.challenge_id == challenge_id).first()
    if not challenge or challenge.username != username or challenge.used_at is not None or challenge.expires_at < _utc_now_naive():
        raise HTTPException(status_code=400, detail="MFA challenge expired or invalid")
    if challenge.attempt_count >= MAX_MFA_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many OTP attempts")
    if not user or not user.mfa_secret:
        raise HTTPException(status_code=400, detail="MFA is not configured")
    if not pyotp.TOTP(user.mfa_secret).verify(data.otp_code, valid_window=1):
        challenge.attempt_count += 1
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid OTP")
    challenge.used_at = datetime.now(timezone.utc)
    db.commit()
    _, user_agent = get_client_context(request)
    return issue_auth_code(db, user.id, user.username, data.code_challenge, ip_address, user_agent, "MEDIUM (Verified)")


@router.post("/token")
def generate_token(
    request: Request,
    grant_type: str = Form(...),
    code: str = Form(None),
    code_verifier: str = Form(None),
    client_id: str = Form(None),
    client_secret: str = Form(None),
    db: Session = Depends(get_db),
):
    ip_address, user_agent = get_client_context(request)
    enforce_rate_limit(f"token:{ip_address}:{grant_type}")
    if grant_type == "authorization_code":
        if not code or not code_verifier:
            raise HTTPException(status_code=400, detail="Missing code or code_verifier")
        auth_record = db.query(AuthCode).filter(AuthCode.code == code).first()
        if not auth_record or auth_record.expires_at < _utc_now_naive():
            raise HTTPException(status_code=400, detail="Invalid or expired auth code")
        if not verify_pkce(auth_record.code_challenge, code_verifier):
            raise HTTPException(status_code=400, detail="PKCE validation failed")
        user = db.query(User).filter(User.id == auth_record.user_id).first()
        scopes = ROLE_SCOPES.get(user.role, [])
        db.delete(auth_record)
        db.commit()
        token = create_jwt(user.username, "user", scopes, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
        return {"access_token": token, "token_type": "bearer", "scopes": scopes}
    if grant_type == "client_credentials":
        if not client_id or not client_secret:
            raise HTTPException(status_code=400, detail="Missing client credentials")
        machine = db.query(MachineClient).filter(MachineClient.client_id == client_id).first()
        if not machine or not verify_hash(client_secret, machine.hashed_secret):
            log_activity(db, client_id, ip_address, "Machine", "FAILED", "UNKNOWN")
            raise HTTPException(status_code=401, detail="Invalid client credentials")
        risk_level, action = evaluate_context(db, client_id, ip_address, "Machine")
        if action == "BLOCK":
            log_activity(db, client_id, ip_address, "Machine", "BLOCKED", risk_level)
            raise HTTPException(status_code=403, detail="High Risk: Machine IP blocked.")
        scopes = ROLE_SCOPES.get(machine.role, [])
        log_activity(db, client_id, ip_address, "Machine", "SUCCESS", risk_level)
        token = create_jwt(machine.client_id, machine.role, scopes, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
        return {"access_token": token, "token_type": "bearer", "scopes": scopes}
    raise HTTPException(status_code=400, detail="Unsupported grant_type")
