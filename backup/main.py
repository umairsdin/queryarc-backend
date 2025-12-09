from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import os
import json
import requests
import urllib.parse

from fastapi.middleware.cors import CORSMiddleware

from typing import Dict, Any

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

# Allow local HTML frontend to call API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/site", response_class=HTMLResponse)
def serve_marketing_site():
    base_dir = os.path.dirname(__file__)
    path = os.path.join(base_dir, "website", "index.html")

    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except:
        return HTMLResponse(
            "<h1>Marketing site not found</h1><p>Place index.html inside /website folder.</p>",
            status_code=500
        )

class AnalyzeRequest(BaseModel):
    url: str


def extract_page_metadata(html: str, url: str) -> Dict[str, Any]:
    """Extract basic metadata (title, meta description, H1, H2s) from raw HTML."""
    soup = BeautifulSoup(html, "html.parser")

    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""

    desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = desc_tag.get("content", "").strip() if desc_tag else ""

    h1_tag = soup.find("h1")
    h1 = h1_tag.get_text(strip=True) if h1_tag else ""

    h2_tags = soup.find_all("h2")
    h2_headings = [h.get_text(strip=True) for h in h2_tags[:5]]

    return {
        "url": url,
        "title": title,
        "meta_description": meta_description,
        "h1": h1,
        "h2_headings": h2_headings,
    }



def validate_llm_output(data: dict):
    # Top-level keys
    required_top = ["llm_view", "evaluation", "blocks"]
    missing = [k for k in required_top if k not in data]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid format: missing top-level keys {missing}"
        )

    # Evaluation scores
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

    # Blocks
    blocks = data.get("blocks", {})
    for key in ["summary_block", "definitions_block", "faq_block", "canonical_resources"]:
        if key not in blocks:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid format: blocks missing '{key}'"
            )

    # canonical_resources must be non-empty list
    resources = blocks.get("canonical_resources", [])
    if not isinstance(resources, list) or len(resources) == 0:
        raise HTTPException(
            status_code=422,
            detail="Invalid format: canonical_resources must be a non-empty list."
        )

    return True


def score_canonical_resources(resources: list, page_url: str):
    """Simple scoring for canonical_resources (0–10) + issues + recommendations."""
    page_domain = urllib.parse.urlparse(page_url).netloc

    internal_count = 0
    external_authority = False

    strong_external_domains = ["wikipedia.org", ".gov", ".edu", "iso.org"]

    for res in resources:
        if "url" not in res:
            continue
        url = res["url"]
        domain = urllib.parse.urlparse(url).netloc

        # Count internal links
        if domain == page_domain:
            internal_count += 1

        # Check external authoritative sources
        if any(sd in domain for sd in strong_external_domains):
            external_authority = True

    # A: internal authority (0–5)
    if internal_count >= 2:
        score_A = 5
    elif internal_count == 1:
        score_A = 2
    else:
        score_A = 0

    # B: first resource matches page itself (0–3)
    first_url_correct = resources[0].get("url", "") == page_url
    score_B = 3 if first_url_correct else 0

    # C: external authoritative domains (0–2)
    score_C = 2 if external_authority else 0

    total_score = score_A + score_B + score_C

    issues = []
    recommendations = []

    if not first_url_correct:
        issues.append("First canonical resource should be the page itself.")
        recommendations.append("Place the analyzed page URL as the first canonical resource.")

    if internal_count == 0:
        issues.append("No internal authoritative pages included.")
        recommendations.append("Add important internal pages from the same domain.")

    if not external_authority:
        issues.append("No globally authoritative external resource added.")
        recommendations.append("Add one strong external authority (e.g., Wikipedia or a .gov site).")

    return total_score, issues, recommendations

@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def serve_index():
    """Serve the frontend UI."""
    base_dir = os.path.dirname(__file__)
    index_path = os.path.join(base_dir, "index.html")

    try:
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>index.html not found</h1><p>Place index.html next to main.py.</p>",
            status_code=500,
        )


@app.post("/analyze")
def analyze_page(data: AnalyzeRequest):

    url = data.url

    # Fetch the page
    try:
        response = requests.get(url, timeout=10)
        html = response.text
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {str(e)}")

    # Extract metadata from raw HTML
    try:
        metadata = extract_page_metadata(html, url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract metadata: {str(e)}")

    # Extract readable text
    try:
        doc = Document(html)
        cleaned_html = doc.summary()
        soup = BeautifulSoup(cleaned_html, "html.parser")
        text = soup.get_text("\n", strip=True)
        text = text[:15000]  # trim long pages
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process HTML: {str(e)}")

    metadata_json = json.dumps(metadata, ensure_ascii=False, indent=2)

    # Prompt
    prompt = f"""
You are an LLM-SEO optimization engine.

You receive:
1) PAGE METADATA (title, meta description, URL, H1, H2 headings).
2) CLEANED BODY TEXT (main readable content).

Your tasks:

STEP 1 – LLM VIEW (what you, as an LLM, understand from this page)
- Determine the PRIMARY TOPIC using PAGE METADATA as your main signal (title, H1, meta description, URL, and H2 headings).
- If the page looks like a homepage or index page, set primary_topic to something like "Homepage – News portal" or "Category page – Chicken incubators", not to UI elements like notifications or cookie banners.
- Ignore cookie banners, consent popups, newsletter or notification prompts, login/register prompts, and generic UI text.
- Identify:
  - primary_topic
  - primary_intent
  - audience
  - user_questions_answered
  - user_questions_missing
  - key_facts
  - important_entities

STEP 2 – EVALUATION AGAINST FRAMEWORK (0–10 each)
Score the page on:
- intent_clarity
- coverage
- structure
- definitions
- answerability
- trust
- overall

Based on the scores, set "verdict" to one of:
- "excellent"
- "good"
- "needs_improvement"
- "poor"

Also:
- List key "issues".
- List "recommendations".
- List 2–5 "priority_fixes".

STEP 3 – LLM-FRIENDLY BLOCKS
Generate reusable blocks:

- summary_block (purpose, audience, key_points)

- definitions_block (5–15 important terms/entities)

- faq_block (5–10 important Q&A pairs)

- canonical_resources:
  - Always include the analyzed page URL as the FIRST item, with a clear title.
  - Add 2–5 additional authoritative resources.
  - Prefer other important internal pages from the SAME domain.
  - Only add external links if they are globally authoritative and directly relevant.
  - Do NOT include UI-only URLs (login, newsletter popup, cookie policy) unless the page itself is about those.

PAGE METADATA:
{metadata_json}

CLEANED BODY TEXT:
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
    "verdict": "",
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
                {"role": "user",    "content": prompt}
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

    raw_content = completion.choices[0].message.content

    # Parse JSON from the output
    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="Model returned invalid JSON. Check model output or adjust the prompt."
        )

    # Validate structure
    validate_llm_output(parsed)

    # Canonical scoring
    resources = parsed["blocks"]["canonical_resources"]
    canonical_score, canonical_issues, canonical_reco = score_canonical_resources(resources, url)

    parsed["evaluation"]["canonical_score"] = canonical_score
    parsed["evaluation"]["canonical_issues"] = canonical_issues
    parsed["evaluation"]["canonical_recommendations"] = canonical_reco

    # Simple overall LLM readiness flag
    overall = parsed.get("evaluation", {}).get("scores", {}).get("overall", 0)
    if isinstance(overall, (int, float)) and overall < 4:
        parsed["evaluation"]["llm_ready"] = False
    else:
        parsed["evaluation"]["llm_ready"] = True

    return parsed
