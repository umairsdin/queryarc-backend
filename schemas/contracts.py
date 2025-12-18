from pydantic import BaseModel, Field
from typing import List, Literal
from datetime import datetime

CONTRACT_VERSION = "0.1.0"


class AIAnswerPresenceRequest(BaseModel):
    project_name: str = Field(..., example="QueryArc")
    core_topic: str = Field(..., example="LLM SEO")
    brand_terms: List[str] = Field(..., example=["QueryArc", "Arc Rank"])


class AIAnswerPresenceResponse(BaseModel):
    accepted: Literal[True]
    version: str
    received_at: datetime
    echo: AIAnswerPresenceRequest


def get_ai_answer_presence_contract():
    return {
        "version": CONTRACT_VERSION,
        "request": AIAnswerPresenceRequest.model_json_schema(),
        "response": AIAnswerPresenceResponse.model_json_schema(),
    }