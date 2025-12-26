from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from db import get_conn, ensure_tables
from tools.ai_answer_presence import router as ai_answer_presence_router
from tools.arc_rank_checker import router as arc_rank_checker_router

# -------------------------------------------------------------------
# Config
# -------------------------------------------------------------------
load_dotenv()

app = FastAPI()

# -------------------------------------------------------------------
# CORS (single middleware)
# -------------------------------------------------------------------
origins = [
    "https://tools.queryarc.com",
    "https://tools-staging.queryarc.com",
]

# Optional: allow local dev
if os.getenv("ENV") != "production":
    origins += ["http://localhost:5173", "http://127.0.0.1:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,  # keep False unless you are using cookies-based auth
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------------
# Routers
# -------------------------------------------------------------------
app.include_router(ai_answer_presence_router)
app.include_router(arc_rank_checker_router)

# -------------------------------------------------------------------
# Health + DB
# -------------------------------------------------------------------
@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/db-health")
def db_health():
    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("SELECT 1;")
        val = cur.fetchone()[0]

        cur.execute("SELECT current_database(), inet_server_addr(), inet_server_port();")
        db_name, server_addr, server_port = cur.fetchone()

        cur.execute("""
            select tablename
            from pg_tables
            where schemaname = 'public'
              and tablename in ('projects','entities','question_sets','runs','run_items','analysis_items')
            order by tablename;
        """)
        phase1_tables = [r[0] for r in cur.fetchall()]

        cur.close()
        conn.close()

        return {
            "db": "ok",
            "select_1": val,
            "current_database": db_name,
            "server_addr": str(server_addr),
            "server_port": server_port,
            "phase1_tables_found": phase1_tables,
        }
    except Exception as e:
        return {"db": "error", "detail": str(e)}

@app.on_event("startup")
def on_startup():
    """
    In production/staging on Railway, we want to fail fast if DB is misconfigured.
    Locally, you can run without DB by not setting DATABASE_URL.
    """
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        if os.getenv("ENV") == "production":
            raise RuntimeError("DATABASE_URL is missing")
        # Local/dev: skip table creation
        return
    ensure_tables()

# -------------------------------------------------------------------
# Root behavior (API-only)
# -------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def root():
    # Keep API domains looking like an API, not an old UI.
    return RedirectResponse(url="/docs", status_code=302)

# -------------------------------------------------------------------
# Legacy HTML pages (optional, behind a flag)
# -------------------------------------------------------------------
SERVE_LEGACY_UI = os.getenv("SERVE_LEGACY_UI", "").lower() in ("1", "true", "yes")

if SERVE_LEGACY_UI:
    app.mount("/static", StaticFiles(directory="static"), name="static")

    @app.head("/ai_answer_presence")
    def head_ai_answer_presence():
        return

    @app.get("/tools", response_class=HTMLResponse)
    def serve_tools_home():
        base_dir = os.path.dirname(__file__)
        path = os.path.join(base_dir, "static", "tools.html")

        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return HTMLResponse(
                content="<h1>tools.html not found</h1><p>Place it inside /static.</p>",
                status_code=500,
            )

    @app.get("/site", response_class=HTMLResponse)
    def serve_marketing_site():
        base_dir = os.path.dirname(__file__)
        path = os.path.join(base_dir, "website", "index.html")

        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return HTMLResponse(
                "<h1>Marketing site not found</h1><p>Place index.html inside /website folder.</p>",
                status_code=500,
            )

    @app.get("/arc-rank-checker", response_class=HTMLResponse, include_in_schema=False)
    def serve_arc_rank_checker():
        base_dir = os.path.dirname(__file__)
        index_path = os.path.join(base_dir, "index.html")

        try:
            with open(index_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return HTMLResponse(
                content="<h1>index.html not found</h1><p>Place index.html next to main.py.</p>",
                status_code=500,
            )

    @app.get("/ai_answer_presence", response_class=HTMLResponse)
    def serve_ai_answer_presence():
        base_dir = os.path.dirname(__file__)
        path = os.path.join(base_dir, "static", "ai_answer_presence.html")

        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return HTMLResponse(
                content="<h1>ai_answer_presence.html not found</h1><p>Place it inside /static.</p>",
                status_code=500,
            )