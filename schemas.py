from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated


UsernameStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")]
PasswordStr = Annotated[str, StringConstraints(min_length=12, max_length=128)]
PKCEStr = Annotated[str, StringConstraints(min_length=43, max_length=128, pattern=r"^[A-Za-z0-9._~-]+$")]
OtpStr = Annotated[str, StringConstraints(min_length=6, max_length=8, pattern=r"^[0-9]+$")]


class UserRole(str, Enum):
    user = "user"
    admin = "admin"


class MachineRole(str, Enum):
    llm = "llm"
    agent = "agent"
    mcp_server = "mcp_server"


class UserCreate(BaseModel):
    username: UsernameStr
    password: PasswordStr
    role: UserRole = UserRole.user


class MachineCreate(BaseModel):
    client_id: UsernameStr
    client_secret: PasswordStr
    role: MachineRole


class AuthorizeRequest(BaseModel):
    username: UsernameStr
    password: PasswordStr
    code_challenge: PKCEStr


class MFAVerify(BaseModel):
    mfa_token: Annotated[str, StringConstraints(min_length=32, max_length=4096)]
    otp_code: OtpStr
    code_challenge: PKCEStr


class AgentExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: Optional[str] = None
    web_query: Optional[str] = None
    calculator_expression: Optional[str] = None
    db_keyword: Optional[str] = None
    python_code: Optional[str] = None
    custom_actions: Optional[dict[str, Any]] = None
    confirm_consequential: bool = Field(default=False)
