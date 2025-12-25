import os
import psycopg2


def get_conn():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is missing")
    return psycopg2.connect(db_url, connect_timeout=5)


def ensure_ai_projects_table():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_projects (
          id UUID PRIMARY KEY,
          website TEXT NOT NULL,
          topics JSONB NOT NULL DEFAULT '[]'::jsonb,
          competitors JSONB NOT NULL DEFAULT '[]'::jsonb,
          questions JSONB NOT NULL DEFAULT '[]'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    conn.commit()
    cur.close()
    conn.close()


def ensure_ai_preview_runs_table():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_preview_runs (
          id UUID PRIMARY KEY,
          project_id UUID NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          result JSONB NOT NULL,
          CONSTRAINT fk_ai_preview_runs_project
            FOREIGN KEY (project_id) REFERENCES ai_projects(id) ON DELETE CASCADE
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ai_preview_runs_project_id ON ai_preview_runs(project_id);")
    conn.commit()
    cur.close()
    conn.close()


def ensure_tables():
    # Keep one entry-point called from FastAPI startup
    ensure_ai_projects_table()
    ensure_ai_preview_runs_table()