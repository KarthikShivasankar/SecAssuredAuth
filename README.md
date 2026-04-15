# SecAssuredAuth

A full-stack authentication demo built with **FastAPI**, **SQLAlchemy**, **Docker**, and a single-file **HTML/JS** frontend. Implements OAuth 2.1 patterns (Authorization Code + PKCE for humans, Client Credentials for machines), contextual risk-based access control, and a secure agentic execution engine with MCP-style microservices.

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    main.py (FastAPI)                │
│  ┌──────────────┐ ┌─────────────────┐ ┌──────────┐ │
│  │ routers/auth │ │routers/resources│ │routers/  │ │
│  │              │ │                 │ │ agent    │ │
│  └──────────────┘ └─────────────────┘ └──────────┘ │
│            core.py (DB models + auth utils)         │
└───────────────────────────┬─────────────────────────┘
                            │
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
    PostgreSQL        MCP Calculator    MCP External DB
    (SQLAlchemy)      :8101             :8102
```

## Key Features

- **Contextual Risk Engine** — evaluates IP + User-Agent on every login
- **OAuth 2.1** — Authorization Code + PKCE (humans), Client Credentials (machines)
- **JWT RBAC** — fine-grained scopes per role (`guest`, `user`, `admin`, `llm`, `agent`, `mcp_server`)
- **Agent Orchestration** — secure multi-action endpoint with per-action scope enforcement
- **MCP-style Microservices** — calculator and external-DB sub-agents with bearer token auth
- **Human-in-the-loop** — sandboxed Python execution requires explicit `confirm_consequential=true`
- **Audit Logging** — every login attempt and agent execution is recorded to the DB

## Risk Decision Matrix

| Condition | Risk Level | Action |
|-----------|-----------|--------|
| IP in blocked subnet (`66.249.x.x`) | HIGH | Block immediately (403) |
| New IP or User-Agent (no prior history) | MEDIUM | Step-up MFA challenge |
| Same IP + UA as last successful login | LOW | Allow immediately |

## Role & Scope Map

| Role | Scopes |
|------|--------|
| `guest` | `read:public` |
| `user` | `read:public`, `read:profile`, `write:profile` |
| `admin` | `read:public`, `read:profile`, `write:profile`, `admin:all` |
| `llm` | `read:context`, `ai:generate` |
| `agent` | `read:context`, `write:context`, `agent:execute`, `agent:web_search`, `agent:calc`, `agent:db_read`, `agent:llm`, `agent:code_exec` |
| `mcp_server` | `mcp:connect`, `mcp:stream`, `read:context` |

## API Reference

### Auth Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/register/user` | Register a human user (returns one-time MFA setup secret) |
| `POST` | `/api/register/machine` | Register a machine client (bootstrap token required) |
| `POST` | `/api/authorize` | Contextual login → auth code or MFA challenge |
| `POST` | `/api/mfa` | Complete MFA step-up |
| `POST` | `/api/token` | Exchange auth code or client credentials for JWT |

#### POST /api/register/user
```json
{ "username": "alice", "password": "StrongPassword123!", "role": "user" }
```
Returns:
```json
{
  "message": "User 'alice' registered as 'user'",
  "mfa_setup": {
    "secret": "BASE32SECRET...",
    "provisioning_uri": "otpauth://totp/..."
  }
}
```

#### POST /api/authorize
```json
{ "username": "alice", "password": "secret", "code_challenge": "<S256 PKCE challenge>" }
```
Headers: `X-Simulated-IP`, `X-Simulated-UA` (optional, for testing)

Returns on medium risk:
```json
{ "status": "mfa_required", "mfa_token": "...", "risk": "MEDIUM" }
```
Returns on low risk:
```json
{ "status": "success", "auth_code": "...", "risk": "LOW" }
```

#### POST /api/token (authorization_code)
```
grant_type=authorization_code&code=<auth_code>&code_verifier=<PKCE verifier>
```

#### POST /api/token (client_credentials)
```
grant_type=client_credentials&client_id=<id>&client_secret=<secret>
```

### Resource Endpoints

| Method | Path | Required Scope |
|--------|------|---------------|
| `GET` | `/api/dashboard` | `read:profile` |
| `GET` | `/api/admin/data` | `admin:all` |
| `POST` | `/api/llm/generate` | `ai:generate` |
| `POST` | `/api/mcp/stream` | `mcp:stream` |

### Agent Endpoints

| Method | Path | Required Scope |
|--------|------|---------------|
| `POST` | `/api/agent/execute` | `agent:execute` |
| `GET` | `/api/agent/actions` | `agent:execute` |

#### POST /api/agent/execute
```json
{
  "web_query": "latest AI news",
  "calculator_expression": "2 ** 10",
  "db_keyword": "security",
  "prompt": "Explain PKCE in one sentence",
  "python_code": "print(1+1)",
  "confirm_consequential": true,
  "custom_actions": {
    "my_action": { "key": "value" }
  }
}
```
All fields are optional. `confirm_consequential` must be `true` to run `python_code`.

Each action also requires its own scope in the token:
- `web_query` → `agent:web_search`
- `calculator_expression` → `agent:calc`
- `db_keyword` → `agent:db_read`
- `prompt` → `agent:llm`
- `python_code` → `agent:code_exec`

## Project Structure

```
SecAssuredAuth/
├── main.py                      # FastAPI app entry point
├── core.py                      # DB models, JWT, PKCE, context evaluation
├── schemas.py                   # Pydantic request models
├── agent_actions.py             # Pluggable agent action registry
├── agent_runtime.py             # Web search, MCP clients, Ollama, sandbox runner
├── mcp_calculator_server.py     # MCP-style calculator microservice (port 8101)
├── mcp_external_db_server.py    # MCP-style external DB microservice (port 8102)
├── routers/
│   ├── auth.py                  # Registration, authorize, MFA, token
│   ├── resources.py             # RBAC-protected resource endpoints
│   └── agent.py                 # Agent execute + action listing
├── index.html                   # Single-file frontend UI
├── test_main.py                 # Functional auth tests
├── tests/
│   └── test_stress_and_extensibility.py
├── pyproject.toml               # uv/pip dependencies
├── docker-compose.yml           # Full stack: app + PostgreSQL + MCP servers
├── Dockerfile
├── USAGE.md                     # End-to-end usage guide
├── TESTING.md                   # Testing strategy
└── AGENTS.md                    # AI agent development rules
```

## Quick Start

### Local (uv)

```bash
# Create env and install deps
uv venv --python 3.11
uv sync --dev

# Start the main app
uv run uvicorn main:app --reload

# (Optional) Start MCP microservices in separate terminals
uv run uvicorn mcp_calculator_server:app --host 0.0.0.0 --port 8101
uv run uvicorn mcp_external_db_server:app --host 0.0.0.0 --port 8102
```

Open [http://localhost:8000](http://localhost:8000).

### Docker Compose

```bash
docker-compose up --build
```

This starts:
- `web` — main auth API on `:8000`
- `db` — PostgreSQL on `:5432`
- `mcp_calculator` — calculator MCP server on `:8101`
- `mcp_external_db` — external DB MCP server on `:8102`

For Ollama LLM support, run Ollama separately on the host (`http://localhost:11434`) and pull the model:
```bash
ollama pull llama3.1:8b
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `development` | Runtime mode (`production` enforces strict secret checks) |
| `SECRET_KEY` | `fallback-secret-key-for-local-dev-1234` | JWT signing key (must be strong in production) |
| `DATABASE_URL` | `sqlite:///./local_dev.db` | Database connection string |
| `MCP_SHARED_TOKEN` | `local-mcp-token` | Shared bearer token for MCP services (must be strong in production) |
| `ADMIN_BOOTSTRAP_TOKEN` | unset | Required for machine registration and elevated role provisioning |
| `ALLOWED_ORIGINS` | `http://localhost:8000,http://127.0.0.1:8000` | Comma-separated CORS allow-list for production |
| `TRUST_PROXY_HEADERS` | `false` | Trust `X-Forwarded-For` only when running behind trusted proxy |
| `JWT_ISSUER` | `secassured-auth` | JWT issuer claim |
| `JWT_AUDIENCE` | `secassured-api` | JWT audience claim |
| `MCP_CALCULATOR_URL` | `http://localhost:8101` | Calculator MCP service URL |
| `MCP_EXTERNAL_DB_URL` | `http://localhost:8102` | External DB MCP service URL |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API URL |
| `OLLAMA_MODEL` | `llama3.1:8b` | Ollama model name |

## Running Tests

```bash
# Functional auth tests
uv run pytest -q test_main.py

# Stress and extensibility tests
uv run pytest -q tests/test_stress_and_extensibility.py

# Full test suite
uv run pytest -q
```

## Extending with New Agent Actions

Register a new action at app startup:

```python
from agent_actions import register_agent_action

register_agent_action(
    name="inventory_lookup",
    required_scope="agent:inventory_read",
    handler=lambda payload: {"inventory": "ok", "query": payload},
    requires_confirmation=False,
)
```

Add the scope in `core.py` (`ROLE_SCOPES`) and `oauth2_scheme` scope descriptions. Then invoke via:

```json
POST /api/agent/execute
{
  "custom_actions": { "inventory_lookup": {"sku": "ABC-123"} }
}
```

See [USAGE.md](USAGE.md) for the complete extension workflow.

## Security Controls

| Control | Implementation |
|---------|---------------|
| Short-lived tokens | 30-minute JWT expiry |
| PKCE | S256 code challenge, single-use auth codes (5-min expiry) |
| Scope enforcement | `SecurityScopes` dependency on every protected route |
| Contextual blocking | IP subnet denylist + step-up MFA for new contexts |
| Audit trail | `login_activity` + `agent_audit` DB tables |
| No token passthrough | MCP services use server-side `MCP_SHARED_TOKEN` |
| Human-in-the-loop | `confirm_consequential=true` required for code execution |
| Sandboxed execution | AST denylist + keyword denylist + subprocess timeout |

### Production Hardening Checklist

Use [PROD_SECURITY_CHECKLIST.md](PROD_SECURITY_CHECKLIST.md) as the release gate source of truth.

### Frontend Notes

- Human registration now returns one-time MFA setup details; save the secret in an authenticator app before first login.
- Browser token storage uses in-memory state only (no `localStorage` persistence).
- Registration/login forms include client-side validation aligned to backend constraints (minimum secret/password length and structured API validation errors).

## References

- [OAuth 2.1 Draft Spec](https://oauth.net/2.1/)
- [MCP Security Best Practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices)
- [MCP Authorization Guide](https://modelcontextprotocol.io/docs/tutorials/security/authorization)
- [FusionAuth — Securing AI Agents](https://fusionauth.io/articles/ai/securing-ai-agents)
- [Securing AI Agents: A Practical Guide](https://medium.com/@bravekjh/securing-ai-agents-a-practical-guide-for-developers-936001de3502)
