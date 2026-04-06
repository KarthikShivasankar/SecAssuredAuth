from typing import Any, Optional

from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "user"


class MachineCreate(BaseModel):
    client_id: str
    client_secret: str
    role: str


class AuthorizeRequest(BaseModel):
    username: str
    password: str
    code_challenge: str


class MFAVerify(BaseModel):
    mfa_token: str
    otp_code: str
    code_challenge: str


class AgentExecutionRequest(BaseModel):
    prompt: Optional[str] = None
    web_query: Optional[str] = None
    calculator_expression: Optional[str] = None
    db_keyword: Optional[str] = None
    python_code: Optional[str] = None
    custom_actions: Optional[dict[str, Any]] = None
    confirm_consequential: bool = False
