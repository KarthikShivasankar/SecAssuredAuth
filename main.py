from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
app = FastAPI(title="Context-Based Auth & OAuth 2.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def serve_ui():
    return FileResponse("index.html")
from agent_actions import register_agent_action
from agent_runtime import calculator_mcp, external_db_mcp, ollama_generate, run_sandboxed_python, search_web
from core import Base, create_jwt, get_db
from routers.agent import router as agent_router
from routers.auth import router as auth_router
from routers.resources import router as resources_router
from agent_actions import init_default_actions

app.include_router(auth_router)
app.include_router(resources_router)
app.include_router(agent_router)

init_default_actions(
    search_web=lambda q: search_web(q, max_results=3),
    calculator_mcp=calculator_mcp,
    external_db_mcp=external_db_mcp,
    ollama_generate=ollama_generate,
    run_sandboxed_python=run_sandboxed_python,
)
