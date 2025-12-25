import os
import psycopg2

def get_conn():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is missing")
    return psycopg2.connect(db_url, connect_timeout=5)

def ensure_tables():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS ai_projects (
      id UUID PRIMARY KEY,
      website TEXT NOT NULL,
      topics JSONB NOT NULL DEFAULT '[]'::jsonb,
      competitors JSONB NOT NULL DEFAULT '[]'::jsonb,
      questions JSONB NOT NULL DEFAULT '[]'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """)

    conn.commit()
    cur.close()
    conn.close()