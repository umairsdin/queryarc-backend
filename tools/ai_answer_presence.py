from fastapi import APIRouter, Body, HTTPException
from datetime import datetime, timezone
import os
import json
import uuid

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