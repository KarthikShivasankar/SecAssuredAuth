from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from jose import jwt
from sqlalchemy.orm import Session

from core import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    AUTH_CODE_EXPIRE_MINUTES,
    ROLE_SCOPES,
    SECRET_KEY,
    AuthCode,
    MachineClient,
    User,
    create_jwt,
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


def issue_auth_code(db: Session, user_id: int, username: str, code_challenge: str, ip_address: str, user_agent: str, risk_level: str):
    import secrets

    code = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(minutes=AUTH_CODE_EXPIRE_MINUTES)
    db.add(AuthCode(code=code, user_id=user_id, code_challenge=code_challenge, expires_at=expires))
    log_activity(db, username, ip_address, user_agent, "SUCCESS", risk_level)
    db.commit()
    return {"status": "success", "auth_code": code, "risk": risk_level}


@router.post("/register/user")
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == user.username).first():
        raise HTTPException(status_code=400, detail="Username exists")
    db.add(User(username=user.username, hashed_password=get_hash(user.password), role=user.role))
    db.commit()
    return {"message": f"User '{user.username}' registered as '{user.role}'"}


@router.post("/register/machine")
def register_machine(machine: MachineCreate, db: Session = Depends(get_db)):
    if db.query(MachineClient).filter(MachineClient.client_id == machine.client_id).first():
        raise HTTPException(status_code=400, detail="Client ID exists")
    db.add(MachineClient(client_id=machine.client_id, hashed_secret=get_hash(machine.client_secret), role=machine.role))
    db.commit()
    return {"message": f"Machine '{machine.client_id}' registered as '{machine.role}'"}


@router.post("/authorize")
def authorize(request: Request, data: AuthorizeRequest, db: Session = Depends(get_db)):
    ip_address, user_agent = get_client_context(request)
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
        mfa_token = create_jwt(user.username, "mfa_pending", [], timedelta(minutes=5))
        return {"status": "mfa_required", "mfa_token": mfa_token, "risk": risk_level, "message": "Medium Risk: Unrecognized device/location detected. Step-up MFA required."}
    return issue_auth_code(db, user.id, user.username, data.code_challenge, ip_address, user_agent, risk_level)


@router.post("/mfa")
def verify_mfa(request: Request, data: MFAVerify, db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(data.mfa_token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "mfa_pending":
            raise ValueError("invalid mfa type")
        username = payload.get("sub")
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid MFA token") from exc

    user = db.query(User).filter(User.username == username).first()
    if not user or data.otp_code != "123456":
        raise HTTPException(status_code=400, detail="Invalid OTP")
    ip_address, user_agent = get_client_context(request)
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
    if grant_type == "authorization_code":
        auth_record = db.query(AuthCode).filter(AuthCode.code == code).first()
        if not auth_record or auth_record.expires_at < datetime.now(timezone.utc):
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
