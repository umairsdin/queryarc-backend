from fastapi import APIRouter, Body
from datetime import datetime, timezone

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
@router.post("/preview")
def preview(payload: dict = Body(...)):
    """
    MVP preview endpoint (placeholder).
    Next step: connect OpenAI + DB.
    """
    website = payload.get("website", "")
    topics = payload.get("topics", [])
    questions = payload.get("questions", [])
    competitors = payload.get("competitors", [])

    questions_used = questions[:5] if isinstance(questions, list) else []

    return {
        "ok": True,
        "website": website,
        "topics_count": len(topics) if isinstance(topics, list) else 0,
        "competitors_count": len(competitors) if isinstance(competitors, list) else 0,
        "questions_used": questions_used,
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