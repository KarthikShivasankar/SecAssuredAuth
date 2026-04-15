from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class AgentActionSpec:
    required_scope: str
    handler: Callable[[Any], Any]
    requires_confirmation: bool = False


AGENT_ACTIONS: dict[str, AgentActionSpec] = {}


def register_agent_action(
    name: str,
    required_scope: str,
    handler: Callable[[Any], Any],
    requires_confirmation: bool = False,
):
    AGENT_ACTIONS[name] = AgentActionSpec(
        required_scope=required_scope,
        handler=handler,
        requires_confirmation=requires_confirmation,
    )


def init_default_actions(
    *,
    search_web: Callable[[str], Any],
    calculator_mcp: Callable[[str], Any],
    external_db_mcp: Callable[[str], Any],
    ollama_generate: Callable[[str], Any],
    run_sandboxed_python: Callable[[str], Any],
):
    # Idempotent registrations for app startup and test imports.
    register_agent_action(
        name="web_search",
        required_scope="agent:web_search",
        handler=lambda q: search_web(str(q)),
    )
    register_agent_action(
        name="calculator_mcp",
        required_scope="agent:calc",
        handler=lambda expr: calculator_mcp(str(expr)),
    )
    register_agent_action(
        name="external_db_mcp",
        required_scope="agent:db_read",
        handler=lambda kw: external_db_mcp(str(kw)),
    )
    register_agent_action(
        name="ollama",
        required_scope="agent:llm",
        handler=lambda p: ollama_generate(str(p)),
    )
    register_agent_action(
        name="sandbox_python",
        required_scope="agent:code_exec",
        handler=lambda code: run_sandboxed_python(str(code)),
        requires_confirmation=True,
    )
