import ast
import os
import re
import subprocess
from typing import Any

import httpx
from duckduckgo_search import DDGS

MCP_SHARED_TOKEN = os.getenv("MCP_SHARED_TOKEN", "local-mcp-token")
MCP_CALCULATOR_URL = os.getenv("MCP_CALCULATOR_URL", "http://localhost:8101")
MCP_EXTERNAL_DB_URL = os.getenv("MCP_EXTERNAL_DB_URL", "http://localhost:8102")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")


def _mcp_headers() -> dict:
    return {"Authorization": f"Bearer {MCP_SHARED_TOKEN}"}


def search_web(query: str, max_results: int = 5) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    with DDGS() as ddgs:
        for row in ddgs.text(query, max_results=max_results):
            results.append(
                {
                    "title": row.get("title", ""),
                    "href": row.get("href", ""),
                    "body": row.get("body", ""),
                }
            )
    return results


def calculator_mcp(expression: str) -> dict[str, Any]:
    with httpx.Client(timeout=10) as client:
        response = client.post(
            f"{MCP_CALCULATOR_URL}/mcp/calculate",
            json={"expression": expression},
            headers=_mcp_headers(),
        )
        response.raise_for_status()
        return response.json()


def external_db_mcp(keyword: str) -> dict[str, Any]:
    with httpx.Client(timeout=10) as client:
        response = client.get(
            f"{MCP_EXTERNAL_DB_URL}/mcp/records",
            params={"keyword": keyword},
            headers=_mcp_headers(),
        )
        response.raise_for_status()
        return response.json()


def ollama_generate(prompt: str) -> dict[str, Any]:
    with httpx.Client(timeout=30) as client:
        response = client.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        )
        response.raise_for_status()
        return response.json()


def run_sandboxed_python(code: str, timeout_seconds: int = 3) -> dict[str, Any]:
    # Very small "safe enough for demo" guardrail:
    # - no imports
    # - no file/network/process operations by keyword denylist
    # - isolated python execution with timeout
    deny_pattern = re.compile(r"\b(import|open|exec|eval|compile|__import__|os\.|sys\.|subprocess|socket|requests)\b")
    if deny_pattern.search(code):
        raise ValueError("Code contains blocked operation.")

    tree = ast.parse(code, mode="exec")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.With, ast.Try, ast.Raise, ast.ClassDef, ast.FunctionDef)):
            raise ValueError("Only simple inline Python is allowed in sandbox mode.")

    cmd = ["python3", "-I", "-c", code]
    completed = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds, check=False)
    return {
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }
