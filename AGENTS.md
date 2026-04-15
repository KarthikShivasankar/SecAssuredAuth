# AGENTS.md

## Development Rules

- Use `uv` for all Python package management and execution.
- Do not use `pip install -r requirements.txt`; dependencies are defined in `pyproject.toml`.
- Prefer `uv run <command>` for running app tools and tests.
- Keep security controls enabled in agent paths (approval gates + audit logs).

## Common Commands

- Create env: `uv venv --python 3.11`
- Sync deps: `uv sync --dev`
- Run API: `uv run uvicorn main:app --reload`
- Run MCP calculator: `uv run uvicorn mcp_calculator_server:app --host 0.0.0.0 --port 8101`
- Run MCP external DB: `uv run uvicorn mcp_external_db_server:app --host 0.0.0.0 --port 8102`
- Run tests: `uv run pytest -q`
- Run stress/extensibility tests: `uv run pytest -q tests/test_stress_and_extensibility.py`

## Project Notes

- Backend entrypoint: `main.py`
- Frontend: `index.html`
- Tests: `test_main.py`
- Docker build uses `uv sync --frozen --no-dev` with lockfile support.
- Agent runtime helpers: `agent_runtime.py`
- Sample MCP services: `mcp_calculator_server.py`, `mcp_external_db_server.py`
- Agent endpoint: `POST /api/agent/execute`
- Agent registry extension API: `register_agent_action(...)`

## Authentication Behavior

- Low risk: known IP + known User-Agent -> allow.
- Medium risk: new/unknown context -> require MFA.
- High risk: blocked subnet -> reject immediately.

## Agent Security Controls

- `agent:execute` scope required for agent endpoint.
- Action-level scopes are mandatory:
  - `agent:web_search`
  - `agent:calc`
  - `agent:db_read`
  - `agent:llm`
  - `agent:code_exec`
- MCP services require bearer token (`MCP_SHARED_TOKEN`).
- Sandboxed Python execution requires `confirm_consequential=true`.
- All agent runs are logged in `agent_audit`.

## MCP Auth/Security Expectations

- Apply least-privilege scopes and progressive elevation.
- Do not implement token passthrough to downstream resources.
- Validate token audience/resource indicators for intended resource server.
- Prefer HTTPS in production and protect OAuth flows with strict `state` handling.
- Add SSRF protections for any metadata discovery or outbound URL fetch path.
