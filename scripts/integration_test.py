import sys
import requests

BASE = "https://queryarc-backend-staging.up.railway.app"

def check(name: str, ok: bool, details: str = ""):
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" - {details}" if details else ""))
    return ok

def main() -> int:
    failures = 0

    # 1) /health
    r = requests.get(f"{BASE}/health", timeout=20)
    failures += 0 if check("/health returns 200", r.status_code == 200, f"status={r.status_code}") else 1

    # 2) /contract
    r = requests.get(f"{BASE}/api/tools/ai-answer-presence/contract", timeout=20)
    ok = r.status_code == 200 and isinstance(r.json(), dict) and "version" in r.json()
    failures += 0 if check("ai-answer-presence /contract returns version", ok, f"status={r.status_code}") else 1

    # 3) /test-contract valid
    payload = {
        "project_name": "QueryArc",
        "core_topic": "LLM SEO",
        "brand_terms": ["QueryArc", "Arc Rank"],
    }
    r = requests.post(f"{BASE}/api/tools/ai-answer-presence/test-contract", json=payload, timeout=20)
    body = r.json() if r.headers.get("content-type","").startswith("application/json") else {}
    ok = r.status_code == 200 and body.get("accepted") is True and body.get("echo", {}) == payload
    failures += 0 if check("ai-answer-presence /test-contract echoes payload", ok, f"status={r.status_code}") else 1

    # 4) arc-rank-checker /analyze returns required top-level keys (smoke test)
    r = requests.post(
        f"{BASE}/api/tools/arc-rank-checker/analyze",
        json={"url": "https://queryarc.com"},
        timeout=60,
    )
    required_keys = {"page_metadata", "executive_summary", "score_matrix", "fix_roadmap"}
    body = r.json() if r.headers.get("content-type","").startswith("application/json") else {}
    ok = r.status_code == 200 and required_keys.issubset(set(body.keys()))
    failures += 0 if check("arc-rank-checker /analyze returns required keys", ok, f"status={r.status_code}") else 1

    print("\nDone.")
    return 0 if failures == 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())