import os
import json
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from bs4 import BeautifulSoup
from readability import Document
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()


class AnalyzeRequest(BaseModel):
    url: str


def validate_llm_output(data: dict):
    # Top-level keys
    required_top = ["llm_view", "evaluation", "blocks"]
    missing = [k for k in required_top if k not in data]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid format: missing top-level keys {missing}"
        )

    # Basic checks on evaluation scores
    scores = data.get("evaluation", {}).get("scores", {})
    required_scores = [
        "intent_clarity",
        "coverage",
        "structure",
        "definitions",
        "answerability",
        "trust",
        "overall",
    ]
    missing_scores = [k for k in required_scores if k not in scores]
    if missing_scores:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid format: missing evaluation scores {missing_scores}"
        )

    if not isinstance(scores.get("overall"), (int, float)):
        raise HTTPException(
            status_code=422,
            detail="Invalid format: overall score must be a number"
        )

    # Blocks basic checks
    blocks = data.get("blocks", {})
    for key in ["summary_block", "definitions_block", "faq_block", "canonical_resources"]:
        if key not in blocks:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid format: blocks missing '{key}'"
            )

    return True


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/analyze")
def analyze_page(data: AnalyzeRequest):

    url = data.url

    # Fetch the page
    try:
        response = requests.get(url, timeout=10)
        html = response.text
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {str(e)}")

    # Extract readable content
    try:
        doc = Document(html)
        cleaned_html = doc.summary()
        soup = BeautifulSoup(cleaned_html, "html.parser")
        text = soup.get_text("\n", strip=True)
        text = text[:15000]  # trim long pages
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process HTML: {str(e)}")

    # Master prompt
    prompt = f"""
You are an LLM-SEO optimization engine.

Step 1 – Read the page content as if you are a large language model trying to answer user questions. Extract what you actually understand from it.

Step 2 – Evaluate the page against this framework (0–10 each):
- intent_clarity: How clear is it what this page is about and who it is for?
- coverage: Does it answer the main questions a user has on this topic?
- structure: Is the information organized in a way that is easy to reuse in answers?
- definitions: Are key terms and entities clearly defined?
- answerability: Could an LLM give concrete, useful answers from this page?
- trust: Are there signals of expertise, author, brand, or sources?
- overall: Your overall score, not an average – your expert judgment.

Step 3 – Suggest improvements based on gaps vs this framework.

Step 4 – Generate LLM-friendly content blocks.

CONTENT TO ANALYZE:
{text}

Return ONLY valid JSON in this EXACT format:

{{
  "llm_view": {{
    "primary_topic": "",
    "primary_intent": "",
    "audience": "",
    "user_questions_answered": [],
    "user_questions_missing": [],
    "key_facts": [],
    "important_entities": []
  }},
  "evaluation": {{
    "scores": {{
      "intent_clarity": 0,
      "coverage": 0,
      "structure": 0,
      "definitions": 0,
      "answerability": 0,
      "trust": 0,
      "overall": 0
    }},
    "issues": [],
    "recommendations": [],
    "priority_fixes": []
  }},
  "blocks": {{
    "summary_block": {{
      "purpose": "",
      "audience": "",
      "key_points": []
    }},
    "definitions_block": [
      {{
        "term": "",
        "definition": "",
        "context": ""
      }}
    ],
    "faq_block": [
      {{
        "question": "",
        "answer": ""
      }}
    ],
    "canonical_resources": [
      {{
        "title": "",
        "url": ""
      }}
    ]
  }}
}}
"""

    # Send to OpenAI
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a structured content engine for LLM SEO."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
        )
    except RateLimitError:
        raise HTTPException(
            status_code=429,
            detail="OpenAI quota exceeded or no credits available. Check your billing."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM error: {str(e)}")

    # Extract model output
    raw_content = completion.choices[0].message.content

    # Parse JSON from the output
    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="Model returned invalid JSON. Check model output or adjust the prompt."
        )

    # Validate structure against our framework
    validate_llm_output(parsed)

    return parsed
