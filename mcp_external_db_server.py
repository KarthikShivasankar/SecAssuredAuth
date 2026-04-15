import os
import sqlite3
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query

MCP_SHARED_TOKEN = os.getenv("MCP_SHARED_TOKEN", "local-mcp-token")
DATA_PATH = Path(os.getenv("EXTERNAL_DB_PATH", "external_data.db"))

app = FastAPI(title="Sample MCP External DB Server")


def _check_token(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.replace("Bearer ", "", 1)
    if token != MCP_SHARED_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")


def _init_db():
    conn = sqlite3.connect(DATA_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            content TEXT NOT NULL
        )
        """
    )
    cur.execute("SELECT COUNT(*) FROM knowledge")
    count = cur.fetchone()[0]
    if count == 0:
        cur.executemany(
            "INSERT INTO knowledge(topic, content) VALUES(?, ?)",
            [
                ("oauth", "OAuth 2.1 prefers Authorization Code + PKCE for browser apps."),
                ("mfa", "Step-up MFA should be triggered by contextual risk signals."),
                ("agent-security", "Use short-lived scoped tokens and immutable audit logs."),
            ],
        )
    conn.commit()
    conn.close()


@app.on_event("startup")
def startup():
    _init_db()


@app.get("/health")
def health():
    return {"status": "ok", "service": "external-db"}


@app.get("/mcp/records")
def records(
    keyword: str = Query(..., min_length=1, max_length=64),
    authorization: str | None = Header(default=None),
):
    _check_token(authorization)
    conn = sqlite3.connect(DATA_PATH)
    cur = conn.cursor()
    like_kw = f"%{keyword.lower()}%"
    cur.execute(
        """
        SELECT id, topic, content
        FROM knowledge
        WHERE lower(topic) LIKE ? OR lower(content) LIKE ?
        ORDER BY id ASC
        LIMIT 10
        """,
        (like_kw, like_kw),
    )
    rows = cur.fetchall()
    conn.close()
    return {
        "tool": "external-db",
        "keyword": keyword,
        "results": [{"id": r[0], "topic": r[1], "content": r[2]} for r in rows],
    }
