from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime, timezone
from schemas.contracts import get_ai_answer_presence_contract

from tools.contracts import (
    AIAnswerPresenceRequest,
    AIAnswerPresenceResponse,
    CONTRACT_VERSION,
)

router = APIRouter(
    prefix="/api/tools/ai-answer-presence",
    tags=["ai-answer-presence"],
)


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

aiap_router = APIRouter(
    prefix="/api/tools/ai-answer-presence",
    tags=["ai-answer-presence"],
)

@aiap_router.get("/contract")
def ai_answer_presence_contract():
    return get_ai_answer_presence_contract()
def get_contract():
    return {
        "tool": "ai-answer-presence",
        "version": "0.1",
        "description": "Detects how AI systems answer key questions about a brand and competitors.",
        "endpoints": {
            "create_project": {
                "method": "POST",
                "path": "/api/tools/ai-answer-presence/projects",
                "request_example": {
                    "project_name": "QueryArc",
                    "core_topic": "LLM SEO",
                    "brand_terms": ["QueryArc", "Arc Rank"]
                }
            },
            "create_run": {
                "method": "POST",
                "path": "/api/tools/ai-answer-presence/projects/{project_id}/runs",
                "request_example": {
                    "questions": [
                        { "text": "What is QueryArc?", "priority": "High" }
                    ],
                    "competitors": [
                        { "name": "CompetitorX", "brand_terms": ["CompetitorX"] }
                    ]
                }
            },
            "poll_run": {
                "method": "GET",
                "path": "/api/tools/ai-answer-presence/runs/{run_id}"
            }
        }
    }
@aiap_router.get("/capabilities")
def get_capabilities():
    return {
        "preview": {
            "max_questions": 5,
            "max_competitors": 1,
            "persistence": False
        },
        "paid": {
            "max_questions": 25,
            "max_competitors": 5,
            "persistence": True
        }
    }

class TestContractRequest(BaseModel):
    project_name: str
    core_topic: str
    brand_terms: list[str]


@aiap_router.post("/test-contract")
def test_contract(payload: TestContractRequest):
    return {
        "accepted": True,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "echo": payload.model_dump(),
    }