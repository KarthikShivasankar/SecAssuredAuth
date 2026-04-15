import ast
import os

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

APP_ENV = os.getenv("APP_ENV", "development").lower()
DEFAULT_MCP_SHARED_TOKEN = "local-mcp-token"
MCP_SHARED_TOKEN = os.getenv("MCP_SHARED_TOKEN", DEFAULT_MCP_SHARED_TOKEN)
if APP_ENV == "production" and MCP_SHARED_TOKEN == DEFAULT_MCP_SHARED_TOKEN:
    raise RuntimeError("Insecure MCP_SHARED_TOKEN for production")

app = FastAPI(title="Sample MCP Calculator Server")


class CalcRequest(BaseModel):
    expression: str


def _check_token(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.replace("Bearer ", "", 1)
    if token != MCP_SHARED_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")


def _safe_eval(expr: str) -> float:
    tree = ast.parse(expr, mode="eval")
    allowed_nodes = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Constant,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Mod,
        ast.Pow,
        ast.USub,
        ast.UAdd,
        ast.FloorDiv,
    )
    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            raise ValueError("Expression contains unsupported syntax")
    return float(eval(compile(tree, "<calc>", "eval")))


@app.get("/health")
def health():
    return {"status": "ok", "service": "calculator"}


@app.post("/mcp/calculate")
def calculate(payload: CalcRequest, authorization: str | None = Header(default=None)):
    _check_token(authorization)
    try:
        result = _safe_eval(payload.expression)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid expression: {exc}") from exc
    return {"tool": "calculator", "expression": payload.expression, "result": result}
