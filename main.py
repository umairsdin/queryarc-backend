from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
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

# -------------------------------------------------------------------
# Config
# -------------------------------------------------------------------

# Load environment variables
load_dotenv()



app = FastAPI()

app.include_router(ai_answer_presence_router)
app.include_router(arc_rank_checker_router)

# Include routers
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


@app.get("/", response_class=HTMLResponse)
def serve_index():
    """Serve the frontend UI."""
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
