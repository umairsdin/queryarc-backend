from fastapi import APIRouter, Body, HTTPException
from datetime import datetime, timezone
import os
import json
import uuid
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Optional, Tuple

from openai import OpenAI
from psycopg2.extras import Json

from db import (
    get_conn,
    ensure_ai_projects_table,
    ensure_ai_preview_runs_table,
)

from schemas.contracts import (
    AIAnswerPresenceRequest,
    AIAnswerPresenceResponse,
    CONTRACT_VERSION,
    get_ai_answer_presence_contract,
)

# ---------------------------------------------------------
# Router
# ---------------------------------------------------------

router = APIRouter(
    prefix="/api/tools/ai-answer-presence",
    tags=["ai-answer-presence"],
)

# ---------------------------------------------------------
# Test contract endpoint (used by staging + CI)
# ---------------------------------------------------------

@router.post(
    "/test-contract",
    response_model=AIAnswerPresenceResponse,
)
def test_contract(payload: AIAnswerPresenceRequest):
    return AIAnswerPresenceResponse(
        accepted=True,
        version=CONTRACT_VERSION,
        received_at=datetime.now(timezone.utc),
        echo=payload,
    )

# ---------------------------------------------------------
# Preview endpoint (supports project_id mode + direct payload)
# ---------------------------------------------------------

@router.post("/preview")
def preview(payload: dict = Body(...)):
    project_id = payload.get("project_id")

    # Mode 1: load from db using project_id
    if project_id:
        ensure_ai_projects_table()
        ensure_ai_preview_runs_table()

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT website, topics, competitors, questions FROM ai_projects WHERE id = %s",
            (project_id,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="project not found")

        website, topics, competitors, questions = row
        mode = "project_id"

    # Mode 2: direct payload
    else:
        website = (payload.get("website") or "").strip()
        questions = payload.get("questions") or []
        topics = payload.get("topics") or []
        competitors = payload.get("competitors") or []
        mode = "direct"

        if not website:
            raise HTTPException(status_code=400, detail="website is required")
        if not isinstance(questions, list) or not questions:
            raise HTTPException(status_code=400, detail="questions must be a non-empty list")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is missing on server")

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    questions_used = (questions or [])[:3]
    results = []

    for q in questions_used:
        prompt = f"""
You are analyzing brand presence in LLM answers.

Brand website: {website}
Topics: {topics}
Known competitors: {competitors}

Question: {q}

Return ONLY valid JSON with exactly these keys:
{{
  "brand_mentioned": true/false,
  "competitors_mentioned": ["..."],
  "recommendation_strength": 0.0,
  "short_summary": "one sentence",
  "evidence_snippet": "short quote from the answer"
}}
""".strip()

        resp = client.responses.create(model=model, input=prompt)
        text = (resp.output_text or "").strip()

        clean = text
        if clean.startswith("```"):
            clean = clean.strip().lstrip("`")
            if clean.lower().startswith("json"):
                clean = clean[4:].lstrip()
            if clean.endswith("```"):
                clean = clean[:-3].strip()

        try:
            parsed = json.loads(clean)
        except Exception:
            parsed = {
                "brand_mentioned": None,
                "competitors_mentioned": [],
                "recommendation_strength": None,
                "short_summary": "Could not parse JSON output",
                "evidence_snippet": "",
                "raw": text[:800],
            }

        results.append({"question": q, "result": parsed})

    mention_bools = [
        r["result"].get("brand_mentioned")
        for r in results
        if isinstance(r["result"].get("brand_mentioned"), bool)
    ]
    mention_rate = (sum(1 for v in mention_bools if v) / len(mention_bools)) if mention_bools else 0.0

    run_id = None
    if project_id:
        run_id = str(uuid.uuid4())
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO ai_preview_runs (id, project_id, result) VALUES (%s, %s, %s)",
            (
                run_id,
                project_id,
                Json(
                    {
                        "website": website,
                        "questions_used": questions_used,
                        "brand_mention_rate": mention_rate,
                        "results": results,
                    }
                ),
            ),
        )
        conn.commit()
        cur.close()
        conn.close()

    return {
        "ok": True,
        "mode": mode,
        "project_id": project_id,
        "run_id": run_id,
        "website": website,
        "questions_used": questions_used,
        "brand_mention_rate": mention_rate,
        "results": results,
        "locked": True,
    }

# ---------------------------------------------------------
# Latest preview endpoint
# ---------------------------------------------------------

@router.get("/project/{project_id}/latest-preview")
def latest_preview(project_id: str):
    ensure_ai_projects_table()
    ensure_ai_preview_runs_table()

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, created_at, result
        FROM ai_preview_runs
        WHERE project_id = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (project_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="no preview runs found")

    run_id, created_at, result = row
    return {
        "ok": True,
        "project_id": project_id,
        "run_id": str(run_id),
        "created_at": created_at,
        "result": result,
    }

# ---------------------------------------------------------
# Contract introspection endpoint
# ---------------------------------------------------------

@router.get("/contract")
def contract():
    """
    Returns the locked request/response schema for this tool.
    Used by frontend generators (Lovable, etc.) and tests.
    """
    return get_ai_answer_presence_contract()

# ---------------------------------------------------------
# Create project endpoint
# ---------------------------------------------------------

@router.post("/project")
def create_project(payload: dict = Body(...)):
    website = (payload.get("website") or "").strip()
    topics = payload.get("topics") or []
    competitors = payload.get("competitors") or []
    questions = payload.get("questions") or []

    if not website:
        raise HTTPException(status_code=400, detail="website is required")

    project_id = str(uuid.uuid4())

    try:
        ensure_ai_projects_table()
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO ai_projects (id, website, topics, competitors, questions)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (project_id, website, Json(topics), Json(competitors), Json(questions)),
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"ok": True, "project_id": project_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Project insert failed: {type(e).__name__}: {e}")

# ---------------------------------------------------------
# Debug seed endpoint (phase 1 proof) - staging/dev only
# ---------------------------------------------------------

@router.post("/debug/seed-run")
def debug_seed_run():
    # Safety: only allow outside production
    if os.getenv("ENV") == "production":
        raise HTTPException(status_code=403, detail="disabled in production")

    # Ensure legacy tables still exist (no-op if already)
    ensure_ai_projects_table()
    ensure_ai_preview_runs_table()

    # Ensure phase 1 tables exist
    from db import (
        ensure_projects_table,
        ensure_entities_table,
        ensure_question_sets_table,
        ensure_runs_table,
        ensure_run_items_table,
        ensure_analysis_items_table,
    )

    ensure_projects_table()
    ensure_entities_table()
    ensure_question_sets_table()
    ensure_runs_table()
    ensure_run_items_table()
    ensure_analysis_items_table()

    project_id = str(uuid.uuid4())
    entity_id = str(uuid.uuid4())
    qs_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    run_item_id = str(uuid.uuid4())
    analysis_id = str(uuid.uuid4())

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    prompt_version = os.getenv("PROMPT_VERSION", "v1")
    analyzer_version = os.getenv("ANALYZER_VERSION", "v1")
    qs_version = "v1"

    question_text = "Seed question: does this schema work?"

    conn = get_conn()
    cur = conn.cursor()

    # projects
    cur.execute(
        "INSERT INTO projects (id, name) VALUES (%s, %s)",
        (project_id, "seed project"),
    )

    # entities
    cur.execute(
        """
        INSERT INTO entities (id, project_id, type, name, website, brand_terms)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (entity_id, project_id, "customer", "Seed brand", "https://example.com", Json(["Seed brand"])),
    )

    # question_sets
    cur.execute(
        """
        INSERT INTO question_sets (id, project_id, version, questions)
        VALUES (%s, %s, %s, %s)
        """,
        (qs_id, project_id, qs_version, Json([question_text])),
    )

    # runs
    now = datetime.now(timezone.utc)
    cur.execute(
        """
        INSERT INTO runs (id, project_id, question_set_version, model, prompt_version, status, started_at, finished_at, input_snapshot)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            run_id,
            project_id,
            qs_version,
            model,
            prompt_version,
            "succeeded",
            now,
            now,
            Json({"seed": True, "prompt_template": "seed"}),
        ),
    )

    # run_items
    cur.execute(
        """
        INSERT INTO run_items (id, run_id, entity_id, question_index, question_text, raw_answer, raw_meta, error)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            run_item_id,
            run_id,
            entity_id,
            0,
            question_text,
            "Seed raw answer text",
            Json({"seed": True}),
            None,
        ),
    )

    # analysis_items
    cur.execute(
        """
        INSERT INTO analysis_items (id, run_item_id, analyzer_version, brand_mentioned, competitors_mentioned, strength_score, evidence_snippet, summary)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            analysis_id,
            run_item_id,
            analyzer_version,
            True,
            Json([]),
            1.0,
            "Seed brand",
            "Seed analysis summary",
        ),
    )

    conn.commit()
    cur.close()
    conn.close()

    return {
        "ok": True,
        "project_id": project_id,
        "run_id": run_id,
        "run_item_id": run_item_id,
        "analysis_id": analysis_id,
    }

# ---------------------------------------------------------
# Helpers for Phase 2 optimizations
# ---------------------------------------------------------

def _safe_usage_to_json(usage: Any) -> Any:
    if usage is None:
        return None
    try:
        return usage.model_dump()
    except Exception:
        pass
    try:
        return dict(usage)
    except Exception:
        pass
    return str(usage)

def _call_openai_with_retries(
    *,
    api_key: str,
    model: str,
    prompt: str,
    max_retries: int = 3,
    base_backoff_s: float = 0.6,
) -> Tuple[Optional[str], Dict[str, Any], Optional[Dict[str, Any]]]:
    """
    Returns: (raw_answer, raw_meta, error_obj)
    """
    try:
        from openai import RateLimitError, APIError, APITimeoutError, APIConnectionError  # type: ignore
        retryable = (RateLimitError, APIError, APITimeoutError, APIConnectionError)
    except Exception:
        retryable = (Exception,)

    attempts = 0
    last_err: Optional[Dict[str, Any]] = None
    start = time.time()

    while attempts <= max_retries:
        attempts += 1
        try:
            client = OpenAI(api_key=api_key)
            resp = client.responses.create(model=model, input=prompt)
            raw_answer = (getattr(resp, "output_text", "") or "").strip()

            raw_meta: Dict[str, Any] = {
                "model": model,
                "attempts": attempts,
                "response_id": getattr(resp, "id", None),
                "latency_ms": int((time.time() - start) * 1000),
            }

            usage = getattr(resp, "usage", None)
            if usage is not None:
                raw_meta["usage"] = _safe_usage_to_json(usage)

            return raw_answer, raw_meta, None

        except retryable as e:
            last_err = {"type": type(e).__name__, "message": str(e)[:800], "attempts": attempts}
            if attempts > max_retries:
                break
            time.sleep(base_backoff_s * (2 ** (attempts - 1)))
        except Exception as e:
            last_err = {"type": type(e).__name__, "message": str(e)[:800], "attempts": attempts}
            break

    raw_meta = {
        "model": model,
        "attempts": attempts,
        "latency_ms": int((time.time() - start) * 1000),
    }
    return None, raw_meta, last_err

# ---------------------------------------------------------
# Phase 2: Fetch layer endpoint (fills run_items for entities × questions)
# Optimized: concurrency + retries + batch inserts + progress updates
# ---------------------------------------------------------

@router.post("/run")
def run_fetch(payload: dict = Body(...)):
    # Ensure phase 1 tables exist
    from db import (
        ensure_projects_table,
        ensure_entities_table,
        ensure_question_sets_table,
        ensure_runs_table,
        ensure_run_items_table,
    )
    ensure_projects_table()
    ensure_entities_table()
    ensure_question_sets_table()
    ensure_runs_table()
    ensure_run_items_table()

    website = (payload.get("website") or "").strip()
    topics = payload.get("topics") or []
    competitors = payload.get("competitors") or []
    questions = payload.get("questions") or []

    if not website:
        raise HTTPException(status_code=400, detail="website is required")
    if not isinstance(questions, list) or not questions:
        raise HTTPException(status_code=400, detail="questions must be a non-empty list")

    # Optional quick test knobs
    max_questions = payload.get("max_questions")
    max_entities = payload.get("max_entities")

    if isinstance(max_questions, int) and max_questions > 0:
        questions = questions[:max_questions]

    # Entities = 1 customer + N competitors (same loop, no special casing)
    entity_specs = [{"type": "customer", "name": website, "website": website, "brand_terms": [website]}]
    for c in competitors:
        c = str(c).strip()
        if c:
            entity_specs.append({"type": "competitor", "name": c, "website": None, "brand_terms": [c]})

    if isinstance(max_entities, int) and max_entities > 0:
        entity_specs = entity_specs[:max_entities]

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is missing on server")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    prompt_version = os.getenv("PROMPT_VERSION", "v1")
    question_set_version = payload.get("question_set_version") or "v1"

    # Concurrency + retries (safe defaults)
    max_concurrency = payload.get("max_concurrency")
    if not isinstance(max_concurrency, int) or max_concurrency <= 0:
        max_concurrency = 4

    max_retries = payload.get("max_retries")
    if not isinstance(max_retries, int) or max_retries < 0:
        max_retries = 3

    run_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())

    prompt_template = (
        "You are an assistant.\n"
        "Entity: {entity_name}\n"
        "Website: {entity_website}\n"
        "Topics: {topics}\n"
        "Competitors: {competitors}\n\n"
        "Question: {question}\n"
    )

    conn = get_conn()
    cur = conn.cursor()

    # Create project
    cur.execute(
        "INSERT INTO projects (id, name) VALUES (%s, %s)",
        (project_id, "phase2 project"),
    )

    # Create question set
    qs_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO question_sets (id, project_id, version, questions) VALUES (%s, %s, %s, %s)",
        (qs_id, project_id, question_set_version, Json(questions)),
    )

    # Create entities
    entity_rows = []
    for es in entity_specs:
        entity_id = str(uuid.uuid4())
        entity_rows.append((entity_id, es))
        cur.execute(
            """
            INSERT INTO entities (id, project_id, type, name, website, brand_terms)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (entity_id, project_id, es["type"], es["name"], es["website"], Json(es["brand_terms"])),
        )

    total_items = len(entity_rows) * len(questions)

    # Create run
    started = datetime.now(timezone.utc)
    cur.execute(
        """
        INSERT INTO runs (id, project_id, question_set_version, model, prompt_version, status, started_at, input_snapshot)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            run_id,
            project_id,
            question_set_version,
            model,
            prompt_version,
            "running",
            started,
            Json({
                "prompt_template": "phase2_fetch_v1",
                "topics": topics,
                "competitors": competitors,
                "progress": {"total": total_items, "done": 0, "errors": 0},
                "settings": {"max_concurrency": max_concurrency, "max_retries": max_retries},
            }),
        ),
    )
    conn.commit()

    def build_task(entity_id: str, es: dict, qi: int, q: str):
        prompt = prompt_template.format(
            entity_name=es["name"],
            entity_website=es["website"] or "",
            topics=topics,
            competitors=competitors,
            question=str(q),
        )
        return entity_id, qi, str(q), prompt

    tasks = []
    for (entity_id, es) in entity_rows:
        for qi, q in enumerate(questions):
            tasks.append(build_task(entity_id, es, qi, q))

    created = 0
    errors = 0

    # Batch insert buffer
    batch_size = 25
    buffer_rows = []

    def worker(task):
        entity_id, qi, q_text, prompt = task
        raw_answer, raw_meta, err_obj = _call_openai_with_retries(
            api_key=api_key,
            model=model,
            prompt=prompt,
            max_retries=max_retries,
        )
        item_id = str(uuid.uuid4())
        return item_id, entity_id, qi, q_text, raw_answer, raw_meta, err_obj

    def flush_buffer():
        nonlocal buffer_rows, created, errors
        if not buffer_rows:
            return

        cur.executemany(
            """
            INSERT INTO run_items (id, run_id, entity_id, question_index, question_text, raw_answer, raw_meta, error)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            buffer_rows,
        )
        buffer_rows = []

        # Update progress inside input_snapshot (no schema changes needed)
        progress_json = json.dumps({"total": total_items, "done": created, "errors": errors})
        cur.execute(
            """
            UPDATE runs
            SET input_snapshot = jsonb_set(input_snapshot, '{progress}', %s::jsonb, true)
            WHERE id = %s
            """,
            (progress_json, run_id),
        )
        conn.commit()

    with ThreadPoolExecutor(max_workers=max_concurrency) as ex:
        futures = [ex.submit(worker, t) for t in tasks]
        for fut in as_completed(futures):
            item_id, entity_id, qi, q_text, raw_answer, raw_meta, err_obj = fut.result()

            buffer_rows.append(
                (
                    item_id,
                    run_id,
                    entity_id,
                    qi,
                    q_text,
                    raw_answer,
                    Json(raw_meta),
                    Json(err_obj) if err_obj else None,
                )
            )

            created += 1
            if err_obj:
                errors += 1

            if len(buffer_rows) >= batch_size:
                flush_buffer()

    # Final flush
    flush_buffer()

    finished = datetime.now(timezone.utc)
    status = "succeeded" if created > 0 else "failed"
    cur.execute(
        "UPDATE runs SET status=%s, finished_at=%s WHERE id=%s",
        (status, finished, run_id),
    )

    # Final progress update
    final_progress_json = json.dumps({"total": total_items, "done": created, "errors": errors})
    cur.execute(
        """
        UPDATE runs
        SET input_snapshot = jsonb_set(input_snapshot, '{progress}', %s::jsonb, true)
        WHERE id = %s
        """,
        (final_progress_json, run_id),
    )

    conn.commit()
    cur.close()
    conn.close()

    return {
        "ok": True,
        "run_id": run_id,
        "project_id": project_id,
        "entities_count": len(entity_rows),
        "questions_count": len(questions),
        "run_items_created": created,
        "run_items_errors": errors,
        "status": status,
        "settings": {"max_concurrency": max_concurrency, "max_retries": max_retries},
    }