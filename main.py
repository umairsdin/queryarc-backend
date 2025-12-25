from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
import os
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from dotenv import load_dotenv
from tools.ai_answer_presence import router as ai_answer_presence_router
from tools.arc_rank_checker import router as arc_rank_checker_router
from db import get_conn, ensure_tables
import uuid
import psycopg2
from psycopg2.extras import Json
from fastapi.middleware.cors import CORSMiddleware
import os

from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    return {"ok": True}


origins = [
  "https://tools.queryarc.com",
  "https://tools-staging.queryarc.com",
]

# optional: allow local dev
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
# Config
# -------------------------------------------------------------------

# Load environment variables
load_dotenv()

app = FastAPI()

app.include_router(ai_answer_presence_router)
app.include_router(arc_rank_checker_router)

# Allow local HTML frontend to call API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.head("/ai_answer_presence")
def head_ai_answer_presence():
    return


# ---------------- Existing routes / helpers ----------------

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


@app.get("/health")
def health_check():
    return {"status": "ok"}


# Root should behave like production: redirect to Arc rank checker
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/arc-rank-checker", status_code=302)


# Serve the Arc rank checker UI here (your existing index.html)
@app.get("/arc-rank-checker", response_class=HTMLResponse, include_in_schema=False)
def serve_arc_rank_checker():
    """Serve the Arc rank checker frontend UI (index.html)."""
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


@app.get("/db-health")
def db_health():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        val = cur.fetchone()[0]
        cur.close()
        conn.close()
        return {"db": "ok", "select_1": val}
    except Exception as e:
        return {"db": "error", "detail": str(e)}


@app.on_event("startup")
def on_startup():
    ensure_tables()


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