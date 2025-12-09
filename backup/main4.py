import os
import json
import requests
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
    required_top = ["llm_view", "evaluation", "blocks"]
    missing = [k for k in required_top if k not in data]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid format: missing top-level keys {missing}"
        )

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

    blocks = data.get("blocks", {})
    for key in ["summary_block", "definitions_block", "faq_block", "canonical_resources"]:
        if key not in blocks:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid format: blocks missing '{key}'"
            )
        
        # Ensure canonical_resources is a non-empty list
    resources = blocks.get("canonical_resources", [])
    if not isinstance(resources, list) or len(resources) == 0:
        raise HTTPException(
            status_code=422,
            detail="Invalid format: canonical_resources must be a non-empty list."
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

    # Extract metadata from raw HTML
    try:
        metadata = extract_page_metadata(html, url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract metadata: {str(e)}")

    # Extract readable content for body analysis
    try:
        doc = Document(html)
        cleaned_html = doc.summary()
        soup = BeautifulSoup(cleaned_html, "html.parser")
        text = soup.get_text("\n", strip=True)
        text = text[:15000]  # trim long pages
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process HTML: {str(e)}")

    metadata_json = json.dumps(metadata, ensure_ascii=False, indent=2)

    # Master prompt
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
  - primary_intent (what the page is trying to help the user do or understand)
  - audience (who the page is meant for)
  - user_questions_answered (main questions the page clearly answers)
  - user_questions_missing (important questions for this topic that are not well answered)
  - key_facts (bullet list of concrete, reusable facts)
  - important_entities (products, brands, tools, concepts, locations, etc.)

STEP 2 – EVALUATION AGAINST FRAMEWORK (0–10 each)
Score the page on:
- intent_clarity: How clear is what this page is about and who it is for?
- coverage: Does it answer the main questions a user has on this topic?
- structure: Is content organized in a way that makes it easy for an LLM to extract concise answers?
- definitions: Are key terms and entities clearly defined?
- answerability: Could an LLM answer common user questions accurately using only this page?
- trust: Are there signals of expertise, brand credibility, author, or references?
- overall: Your expert judgment of how LLM-ready this page is (not just the average).

Based on the scores, set "verdict" to one of:
- "excellent" – highly LLM-ready
- "good" – usable but can be improved
- "needs_improvement" – significant gaps; LLM will struggle
- "poor" – not suitable for LLM answers in current form

Also:
- List key "issues" (problems).
- List "recommendations" (what to improve).
- List 2–5 "priority_fixes" (the most impactful changes).

STEP 3 – LLM-FRIENDLY BLOCKS
Generate reusable blocks designed for LLM consumption:

- summary_block (purpose, audience, key_points)

- definitions_block (5–15 important terms/entities)

- faq_block (5–10 important Q&A pairs)

- canonical_resources:
  - Always include the analyzed page URL as the FIRST item, with a clear title.
  - Add 2–5 additional authoritative resources.
  - Prefer other important internal pages from the SAME domain (category pages, pillar pages, glossary, about page, key product/guide pages).
  - Only add external links if they are globally authoritative and directly relevant (e.g., official documentation, Wikipedia, government/standards sites).
  - Do NOT include UI-only URLs (login, newsletter popup, cookie policy) unless the page itself is about those.


PAGE METADATA (use this primarily for topic and intent):
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
    import urllib.parse

def score_canonical_resources(resources, page_url):
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

        # Check external authority sources
        if any(sd in domain for sd in strong_external_domains):
            external_authority = True

    # A: internal authority (0–5)
    if internal_count >= 2:
        score_A = 5
    elif internal_count == 1:
        score_A = 2
    else:
        score_A = 0

    # B: first resource is correct
    first_url_correct = resources[0].get("url", "") == page_url
    score_B = 3 if first_url_correct else 0

    # C: external authority
    score_C = 2 if external_authority else 0

    total_score = score_A + score_B + score_C

    # Generate issues + recommendations
    issues = []
    recommendations = []

    if not first_url_correct:
        issues.append("First canonical resource should be the page itself.")
        recommendations.append("Place the page URL as the first canonical resource.")

    if internal_count == 0:
        issues.append("No internal authoritative pages included.")
        recommendations.append("Add 1–3 important internal pages from the same site.")

    if not external_authority:
        issues.append("No external authoritative resource provided.")
        recommendations.append("Add one globally recognized external authority (e.g., Wikipedia).")

    return total_score, issues, recommendations

    # Optional: add a simple boolean flag for pass/fail
overall = parsed.get("evaluation", {}).get("scores", {}).get("overall", 0)


    # Optional: add a simple boolean flag for pass/fail
    overall = parsed.get("evaluation", {}).get("scores", {}).get("overall", 0)
    if isinstance(overall, (int, float)) and overall < 4:
        parsed["evaluation"]["llm_ready"] = False
    else:
        parsed["evaluation"]["llm_ready"] = True

    return parsed
