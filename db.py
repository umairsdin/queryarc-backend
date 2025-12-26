import os
import psycopg2


def get_conn():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is missing")
    return psycopg2.connect(db_url, connect_timeout=5)


# -------------------------------------------------------------------
# Legacy tables (keep for compatibility)
# -------------------------------------------------------------------
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
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_preview_runs_project_id ON ai_preview_runs(project_id);"
    )
    conn.commit()
    cur.close()
    conn.close()


# -------------------------------------------------------------------
# Phase 1: reproducible data model tables
# -------------------------------------------------------------------
def ensure_projects_table():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
          id UUID PRIMARY KEY,
          owner_id TEXT NULL,
          name TEXT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    conn.commit()
    cur.close()
    conn.close()


def ensure_entities_table():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS entities (
          id UUID PRIMARY KEY,
          project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          type TEXT NOT NULL CHECK (type IN ('customer','competitor')),
          name TEXT NOT NULL,
          website TEXT NULL,
          brand_terms JSONB NOT NULL DEFAULT '[]'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entities_project_id ON entities(project_id);")
    conn.commit()
    cur.close()
    conn.close()


def ensure_question_sets_table():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS question_sets (
          id UUID PRIMARY KEY,
          project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          version TEXT NOT NULL,
          questions JSONB NOT NULL DEFAULT '[]'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          UNIQUE(project_id, version)
        );
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_question_sets_project_id ON question_sets(project_id);"
    )
    conn.commit()
    cur.close()
    conn.close()


def ensure_runs_table():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
          id UUID PRIMARY KEY,
          project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          question_set_version TEXT NOT NULL,
          model TEXT NOT NULL,
          prompt_version TEXT NOT NULL,
          status TEXT NOT NULL CHECK (status IN ('queued','running','succeeded','failed','cancelled')),
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          started_at TIMESTAMPTZ NULL,
          finished_at TIMESTAMPTZ NULL,
          input_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_runs_project_id ON runs(project_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at DESC);")
    conn.commit()
    cur.close()
    conn.close()


def ensure_run_items_table():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS run_items (
          id UUID PRIMARY KEY,
          run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
          entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
          question_index INT NOT NULL,
          question_text TEXT NOT NULL,
          raw_answer TEXT NULL,
          raw_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
          error JSONB NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          UNIQUE(run_id, entity_id, question_index)
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_run_items_run_id ON run_items(run_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_run_items_entity_id ON run_items(entity_id);")
    conn.commit()
    cur.close()
    conn.close()


def ensure_analysis_items_table():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_items (
          id UUID PRIMARY KEY,
          run_item_id UUID NOT NULL REFERENCES run_items(id) ON DELETE CASCADE,
          analyzer_version TEXT NOT NULL,
          brand_mentioned BOOLEAN NULL,
          competitors_mentioned JSONB NOT NULL DEFAULT '[]'::jsonb,
          strength_score DOUBLE PRECISION NULL,
          evidence_snippet TEXT NULL,
          summary TEXT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          UNIQUE(run_item_id, analyzer_version)
        );
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_analysis_items_run_item_id ON analysis_items(run_item_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_analysis_items_analyzer_version ON analysis_items(analyzer_version);"
    )
    conn.commit()
    cur.close()
    conn.close()


def ensure_tables():
    # Keep one entry-point called from FastAPI startup
    ensure_ai_projects_table()
    ensure_ai_preview_runs_table()

    # Phase 1 tables
    ensure_projects_table()
    ensure_entities_table()
    ensure_question_sets_table()
    ensure_runs_table()
    ensure_run_items_table()
    ensure_analysis_items_table()