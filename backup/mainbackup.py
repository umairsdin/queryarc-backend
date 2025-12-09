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
You are an LLM SEO Optimization Engine.

Analyze the following webpage content and generate structured blocks for LLM optimization.

CONTENT:
{text}

Return ONLY valid JSON in this format:

{{
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
  ],
  "llm_readiness_score": 0,
  "recommendations": []
}}
"""

    # Send to OpenAI
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a structured content engine."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
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
            detail="Model returned invalid JSON. Check model output or adjust your prompt."
        )

    return parsed
