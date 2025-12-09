# Architecture Diagram

```mermaid
flowchart LR
    U[User Browser] -->|Visits| M[queryarc.com - Marketing Site (Lovable)]
    U -->|Uses tools| F[app.queryarc.com - Frontend (Railway)]

    F -->|API Calls| B[FastAPI Backend (Railway)]
    B -->|Queries| DB[(Postgres Database)]
    B -->|LLM Requests| OAI[OpenAI API]


Summary:
	•	Public users land on Lovable (SEO-optimized).
	•	Authenticated users access app.queryarc.com (Next.js).
	•	The app communicates with the FastAPI backend.
	•	Backend uses Postgres and OpenAI.


---

# 📁 **/docs/02-repo-structure.md**

```md
# Repository Structure

queryarc/
backend/
app/
main.py
api/
tools/
arc_rank.py
semantic_blocks.py
fanout.py
llm_parser.py
definitions.py
auth/
core/
models/
services/
requirements.txt or pyproject.toml

frontend/
app/
tools/
arc-rank-checker-pro/
semantic-block-formatter/
fanout-visualizer/
llm-parser-demo/
definitions-expander/
components/
public/
package.json

docs/
00-system-overview.md
01-architecture-diagram.md
02-repo-structure.md
03-tool-api-contract-template.md
04-tool-ui-template.md
05-deployment.md
06-contributing.md

## Rules
- Each tool gets:
  - A backend module in `/backend/app/api/tools/<tool>.py`
  - A frontend page in `/frontend/app/tools/<tool>/page.tsx`
- Keep naming consistent (kebab-case for URLs, snake_case for backend).