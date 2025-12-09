from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import os
import json
import requests
import urllib.parse
import time
from datetime import datetime

from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, APIRouter
from pydantic import BaseModel
from bs4 import BeautifulSoup
from readability import Document
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError

# -------------------------------------------------------------------
# Config
# -------------------------------------------------------------------

MAX_TEXT_CHARS = 8000      # hard cap for plain text sent to LLM
MAX_HTML_CHARS = 6000      # hard cap for HTML snippet sent to LLM

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

class AnalyzeRequest(BaseModel):
    url: str
def run_llm_seo_analysis(url: str) -> dict:
    """
    Core pipeline: fetch page, extract metadata, run LLM, validate, rescore.
    """

    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    start_time = time.time()

    # Fetch the page
    try:
        response = requests.get(url, timeout=15)
        html = response.text
        crawl_status = "success" if response.status_code == 200 else "partial"
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {str(e)}")

    # Extract metadata
    try:
        metadata = extract_page_metadata(html, url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract metadata: {str(e)}")

    # Extract readable text with fallback
    try:
        doc = Document(html)
        cleaned_html = doc.summary()
        soup = BeautifulSoup(cleaned_html, "html.parser")

        text = soup.get_text("\n", strip=True)
        text = text[:MAX_TEXT_CHARS]
        word_count = len(text.split()) if text else 0

        if word_count < 150:
            soup_full = BeautifulSoup(html, "html.parser")
            body = soup_full.body or soup_full

            full_text = body.get_text("\n", strip=True)
            full_text = full_text[:MAX_TEXT_CHARS]
            full_wc = len(full_text.split()) if full_text else 0

            if full_wc > word_count:
                text = full_text
                cleaned_html = str(body)
                word_count = full_wc

        cleaned_html = cleaned_html[:MAX_HTML_CHARS]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process HTML: {str(e)}")

    tokens = word_count
    processing_time = round(time.time() - start_time, 3)

    # Content type heuristic
    parsed_url = urllib.parse.urlparse(url)
    path = parsed_url.path or "/"
    lower_path = path.lower()
    if path == "/" or path == "":
        content_type = "homepage"
    elif any(seg in lower_path for seg in ["category", "tag", "section", "topics"]):
        content_type = "collection"
    elif any(seg in lower_path for seg in ["product", "shop", "cart"]):
        content_type = "product"
    else:
        content_type = "article"

    detected_language = metadata.get("detected_language", "en")
    last_crawled = datetime.utcnow().isoformat() + "Z"
    llm_version = "gpt-4o-mini"
    metadata["word_count"] = word_count

    # KEEP YOUR EXACT SYSTEM PROMPT
    system_prompt = """YOUR EXISTING SYSTEM PROMPT HERE"""

    # KEEP YOUR EXACT USER PROMPT CODE
    user_prompt = f"""YOUR EXISTING USER PROMPT HERE"""

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
    except RateLimitError:
        raise HTTPException(
            status_code=429,
            detail="OpenAI quota exceeded or no credits available. Check your billing.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM error: {str(e)}")

    raw_content = completion.choices[0].message.content

    if isinstance(raw_content, dict):
        parsed = raw_content
    else:
        if raw_content is None:
            raise HTTPException(
                status_code=500,
                detail="Model returned empty content. Check model output or prompt.",
            )
        try:
            parsed = json.loads(raw_content)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Model returned malformed JSON. Error: {str(e)}",
            )

    parsed["page_metadata"]["url"] = url
    parsed["page_metadata"]["crawl_status"] = crawl_status
    parsed["page_metadata"]["detected_language"] = detected_language
    parsed["page_metadata"]["content_type"] = content_type
    parsed["page_metadata"]["word_count"] = word_count
    parsed["page_metadata"]["last_crawled"] = last_crawled
    parsed["page_metadata"]["llm_version"] = llm_version

    parsed["raw_data"]["clean_text"] = text
    parsed["raw_data"]["html_extracted"] = cleaned_html
    parsed["raw_data"]["tokens"] = tokens
    parsed["raw_data"]["processing_time"] = processing_time

    validate_llm_output(parsed)
    parsed = apply_scoring_algorithm(parsed)

    return parsed

api_router = APIRouter(prefix="/api/tools/llm-seo", tags=["llm-seo"])


@api_router.post("/analyze")
def api_analyze_page(payload: AnalyzeRequest):
    """
    Primary API endpoint for the LLM SEO tool.
    This is what the future React/Next.js frontend will call.
    """
    return run_llm_seo_analysis(payload.url.strip())


app.include_router(api_router)




@app.get("/site", response_class=HTMLResponse)
def serve_marketing_site():
    base_dir = os.path.dirname(__file__)
    path = os.path.join(base_dir, "website", "index.html")

    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return HTMLResponse(
            "<h1>Marketing site not found</h1><p>Place index.html inside /website folder.</p>",
            status_code=500,
        )





def extract_page_metadata(html: str, url: str) -> Dict[str, Any]:
    """Extract basic metadata (title, meta description, H1, H2s) from raw HTML."""
    soup = BeautifulSoup(html, "html.parser")

    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""

    desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = desc_tag.get("content", "").strip() if desc_tag else ""

    h1_tag = soup.find("h1")
    h1 = h1_tag.get_text(strip=True) if h1_tag else ""

    h2_tags = soup.find_all("h2")
    h2_headings = [h.get_text(strip=True) for h in h2_tags[:10]]

    # Language from <html lang="...">
    html_tag = soup.find("html")
    detected_language = ""
    if html_tag and html_tag.get("lang"):
        detected_language = html_tag.get("lang").split("-")[0].lower()

    return {
        "url": url,
        "title": title,
        "meta_description": meta_description,
        "h1": h1,
        "h2_headings": h2_headings,
        "detected_language": detected_language or "en",
    }


def validate_llm_output(data: dict):
    """
    Validate that the LLM output roughly matches the LLM-SEO report schema.
    This is strict enough to catch obvious issues but not a full JSON Schema validator.
    """

    required_top = [
        "page_metadata",
        "executive_summary",
        "llm_interpretation",
        "summary_block",
        "definitions_block",
        "fanout_query_analysis",
        "faq_block",
        "canonical_resources_block",
        "content_structure",
        "clarity_readability",
        "eeat_block",
        "score_matrix",
        "fix_roadmap",
        "raw_data",
    ]
    missing_top = [k for k in required_top if k not in data]
    if missing_top:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid format: missing top-level keys {missing_top}",
        )

    # Basic score matrix validation
    sm = data.get("score_matrix", {})
    required_scores = [
        "summary_block",
        "definitions",
        "faq",
        "fanout_match",
        "canonical_resources",
        "structure",
        "clarity",
        "eeat",
        "final_score",
    ]
    missing_scores = [k for k in required_scores if k not in sm]
    if missing_scores:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid format: missing score_matrix keys {missing_scores}",
        )

    if not isinstance(sm.get("final_score"), int):
        raise HTTPException(
            status_code=422,
            detail="Invalid format: score_matrix.final_score must be an integer",
        )

    # Executive summary sanity check
    ex = data.get("executive_summary", {})
    if "overall_llm_readiness_score" not in ex or "verdict" not in ex:
        raise HTTPException(
            status_code=422,
            detail="Invalid format: executive_summary must contain overall_llm_readiness_score and verdict",
        )

    return True


def apply_scoring_algorithm(report: dict) -> dict:
    """
    Apply the scoring algorithm:
    - Recompute final_score from component scores.
    - Apply simple penalties.
    - Update executive_summary.overall_llm_readiness_score and verdict.
    """

    sm = report.get("score_matrix", {})

    # Get component scores with sane defaults
    summary = sm.get("summary_block", 0)
    definitions = sm.get("definitions", 0)
    faq = sm.get("faq", 0)
    fanout = sm.get("fanout_match", 0)
    canonical_resources = sm.get("canonical_resources", 0)
    structure = sm.get("structure", 0)
    clarity = sm.get("clarity", 0)
    eeat = sm.get("eeat", 0)

    # Weighted base score (0–10)
    base = (
        summary * 0.15
        + definitions * 0.10
        + faq * 0.10
        + fanout * 0.20
        + canonical_resources * 0.10
        + structure * 0.10
        + clarity * 0.10
        + eeat * 0.15
    )

    # Convert to 0–100
    final_score = round(base * 10)

    # Penalty based on word count
    word_count = report.get("page_metadata", {}).get("word_count", 0)
    if isinstance(word_count, int):
        if word_count == 0:
            final_score -= 10  # essentially empty / parsing failed
        elif word_count < 150:
            final_score -= 3   # thin but not empty

    # Clamp
    final_score = max(0, min(100, final_score))

    # Update score_matrix and executive_summary
    report["score_matrix"]["final_score"] = final_score
    report["executive_summary"]["overall_llm_readiness_score"] = final_score

    # Verdict mapping
    if final_score >= 80:
        verdict = "Ready"
    elif final_score >= 60:
        verdict = "Partially Ready"
    elif final_score >= 40:
        verdict = "Needs Work"
    else:
        verdict = "Poor"

    report["executive_summary"]["verdict"] = verdict

    return report


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

    url = data.url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    start_time = time.time()

    # Fetch the page
    try:
        response = requests.get(url, timeout=15)
        html = response.text
        crawl_status = "success" if response.status_code == 200 else "partial"
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {str(e)}")

    # Extract metadata from raw HTML
    try:
        metadata = extract_page_metadata(html, url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract metadata: {str(e)}")

    # Extract readable text with fallback and hard limits
    try:
        # First attempt: readability content
        doc = Document(html)
        cleaned_html = doc.summary()
        soup = BeautifulSoup(cleaned_html, "html.parser")

        text = soup.get_text("\n", strip=True)
        text = text[:MAX_TEXT_CHARS]
        word_count = len(text.split()) if text else 0

        # Fallback to full <body> if too thin
        if word_count < 150:
            soup_full = BeautifulSoup(html, "html.parser")
            body = soup_full.body or soup_full

            full_text = body.get_text("\n", strip=True)
            full_text = full_text[:MAX_TEXT_CHARS]
            full_wc = len(full_text.split()) if full_text else 0

            if full_wc > word_count:
                text = full_text
                cleaned_html = str(body)
                word_count = full_wc

        # Always trim HTML snippet
        cleaned_html = cleaned_html[:MAX_HTML_CHARS]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process HTML: {str(e)}")

    tokens = word_count  # simple proxy
    processing_time = round(time.time() - start_time, 3)

    # Content type heuristic
    parsed_url = urllib.parse.urlparse(url)
    path = parsed_url.path or "/"
    lower_path = path.lower()
    if path == "/" or path == "":
        content_type = "homepage"
    elif any(seg in lower_path for seg in ["category", "tag", "section", "topics"]):
        content_type = "collection"
    elif any(seg in lower_path for seg in ["product", "shop", "cart"]):
        content_type = "product"
    else:
        content_type = "article"

    # Page metadata for LLM
    detected_language = metadata.get("detected_language", "en")
    last_crawled = datetime.utcnow().isoformat() + "Z"
    llm_version = "gpt-4o-mini"
    metadata["word_count"] = word_count

    # Compact system prompt: defines structure and rules
    system_prompt = """
You are an LLM-SEO evaluator. Output strict json only.

The json must have these top-level keys:
- page_metadata
- executive_summary
- llm_interpretation
- summary_block
- definitions_block
- fanout_query_analysis
- faq_block
- canonical_resources_block
- content_structure
- clarity_readability
- eeat_block
- score_matrix
- fix_roadmap
- raw_data

Required inner fields (exact keys):

page_metadata:
  url, crawl_status, detected_language, content_type, word_count, last_crawled, llm_version

executive_summary:
  overall_llm_readiness_score (int 0-100),
  verdict ("Ready" | "Partially Ready" | "Needs Work" | "Poor"),
  main_issue (string),
  top_3_fixes (array of strings)

llm_interpretation:
  primary_topic, secondary_topics (array), detected_intent,
  summary_llm_generated, key_claims_llm_detected (array), confidence_level

summary_block:
  score (0-10), found (bool), quality, problems (array), recommended_summary_block

definitions_block:
  score (0-10), found (bool),
  missing_critical_terms (array),
  quality_problems (array),
  recommended_definitions (array of {term, definition})

fanout_query_analysis:
  sub_questions_generated (array of {question, matched_content, match_quality, missing_answer_note}),
  coverage_score (0-10),
  main_gaps (array)

faq_block:
  score (0-10), found (bool),
  quality_problems (array),
  recommended_faqs (array of {q, a})

canonical_resources_block:
  score (0-10), found (bool),
  missing_resources (array),
  why_it_matters (string),
  recommended_resources (array of {title, url})

content_structure:
  score (0-10),
  headings_quality, visual_structure,
  problems (array),
  recommended_structure_changes (array)

clarity_readability:
  score (0-10),
  issues (array of strings),
  fixes (array of strings)

eeat_block:
  score (0-10),
  author_info_found (bool),
  expertise_visibility,
  experience_signals,
  trust_signals,
  missing_elements (array)

score_matrix:
  summary_block, definitions, faq, fanout_match,
  canonical_resources, structure, clarity, eeat (0-10 each),
  final_score (int 0-100)

fix_roadmap:
  immediate_fixes_next_24h (array),
  medium_priority_next_7_days (array),
  long_term_next_30_days (array)

raw_data:
  clean_text, html_extracted, tokens, processing_time

Rules:
- Never omit required keys.
- recommended_definitions: at least 3 items when possible.
- recommended_faqs: at least 5 items when possible.
- canonical_resources_block.recommended_resources: at least 3 items;
  first item MUST be the analyzed page URL.
- If content is thin, still infer helpful definitions, FAQ, and resources from
  URL, title, and visible text.
- Keep explanations concise and practical.
- Output JSON object only, no extra text.
"""

    # User prompt with page-specific data
    user_prompt = f"""
Analyze this web page and fill the JSON report.

Metadata:
- URL: {url}
- Crawl status: {crawl_status}
- Detected language: {detected_language}
- Content type: {content_type}
- Last crawled: {last_crawled}
- LLM version: {llm_version}
- Word count: {word_count}
- Token estimate: {tokens}
- Processing time (seconds): {processing_time}

CLEAN TEXT (trimmed):
{text}

HTML SNIPPET (trimmed):
{cleaned_html}

Use the clean text as your main signal. Use HTML only for structure (headings, sections, presence of FAQ/definitions).
If the page is thin or mostly UI, still propose an ideal summary, definitions, FAQ, and canonical resources
for what this page appears to be about.

Return ONLY the JSON object.
"""

    # Send to OpenAI
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},  # force JSON output
        )
    except RateLimitError:
        raise HTTPException(
            status_code=429,
            detail="OpenAI quota exceeded or no credits available. Check your billing.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM error: {str(e)}")

    # Model should now return JSON as a string (or dict in some SDKs)
    raw_content = completion.choices[0].message.content

    if isinstance(raw_content, dict):
        parsed = raw_content
    else:
        if raw_content is None:
            raise HTTPException(
                status_code=500,
                detail="Model returned empty content. Check model output or prompt.",
            )
        try:
            parsed = json.loads(raw_content)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Model returned malformed JSON (likely truncated). Error: {str(e)}",
            )

    # Fill in or overwrite some metadata/raw_data to be safe
    parsed["page_metadata"]["url"] = url
    parsed["page_metadata"]["crawl_status"] = crawl_status
    parsed["page_metadata"]["detected_language"] = detected_language
    parsed["page_metadata"]["content_type"] = content_type
    parsed["page_metadata"]["word_count"] = word_count
    parsed["page_metadata"]["last_crawled"] = last_crawled
    parsed["page_metadata"]["llm_version"] = llm_version

    parsed["raw_data"]["clean_text"] = text
    parsed["raw_data"]["html_extracted"] = cleaned_html
    parsed["raw_data"]["tokens"] = tokens
    parsed["raw_data"]["processing_time"] = processing_time

    # Validate structure
    validate_llm_output(parsed)

    # Apply backend scoring algorithm (recompute final_score + verdict)
    parsed = apply_scoring_algorithm(parsed)

    return parsed
