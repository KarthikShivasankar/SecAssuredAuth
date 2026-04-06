from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Security
from sqlalchemy.orm import Session

from agent_actions import AGENT_ACTIONS
from core import AgentAudit, get_db, verify_scopes
from schemas import AgentExecutionRequest

router = APIRouter(prefix="/api/agent")


@router.post("/execute")
def execute_agent(
    payload: AgentExecutionRequest,
    token_data: dict = Security(verify_scopes, scopes=["agent:execute"]),
    db: Session = Depends(get_db),
):
    actor = token_data["sub"]
    token_scopes = token_data.get("scopes", [])
    results: dict[str, Any] = {"actor": actor, "actions": {}}
    try:
        requested_actions: dict[str, Any] = {}
        if payload.web_query:
            requested_actions["web_search"] = payload.web_query
        if payload.calculator_expression:
            requested_actions["calculator_mcp"] = payload.calculator_expression
        if payload.db_keyword:
            requested_actions["external_db_mcp"] = payload.db_keyword
        if payload.prompt:
            requested_actions["ollama"] = payload.prompt
        if payload.python_code:
            requested_actions["sandbox_python"] = payload.python_code
        if payload.custom_actions:
            for action_name, value in payload.custom_actions.items():
                if action_name in requested_actions:
                    raise HTTPException(status_code=400, detail=f"Duplicate action in request: {action_name}")
                requested_actions[action_name] = value

        for action_name, value in requested_actions.items():
            spec = AGENT_ACTIONS.get(action_name)
            if not spec:
                raise HTTPException(status_code=400, detail=f"Unknown action: {action_name}")
            if spec.required_scope not in token_scopes:
                raise HTTPException(status_code=403, detail=f"Missing scope: {spec.required_scope}")
            if spec.requires_confirmation and not payload.confirm_consequential:
                raise HTTPException(status_code=400, detail=f"{action_name} requires confirm_consequential=true")
            results["actions"][action_name] = spec.handler(value)

        db.add(AgentAudit(actor=actor, action="agent_execute", status="SUCCESS", details=str(list(results["actions"].keys()))))
        db.commit()
        return results
    except Exception as exc:
        db.add(AgentAudit(actor=actor, action="agent_execute", status="FAILED", details=str(exc)))
        db.commit()
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=502, detail=f"Agent execution failed: {exc}") from exc


@router.get("/actions")
def list_agent_actions(token_data: dict = Security(verify_scopes, scopes=["agent:execute"])):
    return {
        "available_actions": [
            {"name": name, "required_scope": spec.required_scope, "requires_confirmation": spec.requires_confirmation}
            for name, spec in AGENT_ACTIONS.items()
        ],
        "caller": token_data["sub"],
    }
