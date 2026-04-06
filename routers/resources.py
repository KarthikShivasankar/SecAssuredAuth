from fastapi import APIRouter, Depends, Security
from sqlalchemy import desc
from sqlalchemy.orm import Session

from core import LoginActivity, get_db, verify_scopes

router = APIRouter(prefix="/api")


@router.get("/dashboard")
def get_dashboard(token_data: dict = Security(verify_scopes, scopes=["read:profile"]), db: Session = Depends(get_db)):
    history = (
        db.query(LoginActivity)
        .filter(LoginActivity.entity_id == token_data["sub"])
        .order_by(desc(LoginActivity.timestamp))
        .limit(5)
        .all()
    )
    return {
        "entity": token_data["sub"],
        "type": token_data["type"],
        "granted_scopes": token_data["scopes"],
        "recent_logins": [{"ip": h.ip_address, "status": h.status, "risk": h.risk_level, "time": h.timestamp} for h in history],
    }


@router.get("/admin/data")
def get_admin_data(token_data: dict = Security(verify_scopes, scopes=["admin:all"])):
    return {"message": "Welcome to the highly sensitive admin portal."}


@router.post("/llm/generate")
def llm_generate_endpoint(prompt: dict, token_data: dict = Security(verify_scopes, scopes=["ai:generate"])):
    return {"response": f"AI Response to: {prompt.get('text')}", "generated_by": token_data["sub"]}


@router.post("/mcp/stream")
def mcp_stream(token_data: dict = Security(verify_scopes, scopes=["mcp:stream"])):
    return {"status": "streaming_started", "mcp_client": token_data["sub"]}
