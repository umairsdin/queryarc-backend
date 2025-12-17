from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime, timezone


aiap_router = APIRouter(
    prefix="/api/tools/ai-answer-presence",
    tags=["ai-answer-presence"],
)


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