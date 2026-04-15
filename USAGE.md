# Detailed Usage Guide

## 1) Start the stack

### Local (uv)

```bash
uv venv --python 3.11
uv sync --dev
uv run uvicorn main:app --reload
```

Start sample MCP services in separate terminals:

```bash
uv run uvicorn mcp_calculator_server:app --host 0.0.0.0 --port 8101
uv run uvicorn mcp_external_db_server:app --host 0.0.0.0 --port 8102
```

### Docker Compose

```bash
docker-compose up --build
```

## 2) Human auth flow (PKCE + contextual risk)

1. Open `http://localhost:8000`.
2. Set simulator IP/UA.
3. Register a user in the Human tab.
4. Login:
   - first login from new context -> MFA (`123456`)
   - repeated login from same context -> low risk direct access
   - blocked IP subnet (`66.249.x.x`) -> blocked

## 3) Machine auth flow (client credentials)

1. Switch to Machine tab.
2. Register machine role (`llm`, `agent`, or `mcp_server`).
3. Request token via machine credentials.

## 4) Resource endpoint checks

Use buttons in UI to call:

- `GET /api/dashboard`
- `GET /api/admin/data`
- `POST /api/llm/generate`
- `POST /api/mcp/stream`

## 5) Agent Playground (new)

Use the Agent Playground card to test:

- `web_query` -> web search action (`agent:web_search`)
- `calculator_expression` -> calculator MCP action (`agent:calc`)
- `db_keyword` -> external DB MCP action (`agent:db_read`)
- `prompt` -> Ollama generation (`agent:llm`)
- `python_code` -> sandboxed code execution (`agent:code_exec`) + `confirm_consequential`

You can inspect registered actions with `List Action Registry` (`GET /api/agent/actions`).

## 6) Extending backend with new microservices/tables/endpoints

The action system is registry-driven.

Backend API is now modular by router:

- `routers/auth.py` -> registration, authorize, MFA, token exchange
- `routers/resources.py` -> RBAC protected resource endpoints
- `routers/agent.py` -> agent execution and action registry listing
- `core.py` -> shared DB models, auth/security utilities, and dependencies
- `agent_actions.py` -> pluggable agent action registry

### Register a new action

Add this in startup/bootstrap code:

```python
from agent_actions import register_agent_action

register_agent_action(
    name="inventory_lookup",
    required_scope="agent:inventory_read",
    handler=lambda payload: {"inventory": "ok", "query": payload},
    requires_confirmation=False,
)
```

### Invoke from API

Call `/api/agent/execute` with:

```json
{
  "custom_actions": {
    "inventory_lookup": {"sku": "ABC-123"}
  }
}
```

### Add scope

Add the scope in:
- `ROLE_SCOPES` for relevant role
- `oauth2_scheme` scope descriptions

This preserves least privilege and keeps endpoint logic unchanged.
