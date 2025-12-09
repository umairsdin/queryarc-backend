# Tool API Contract Template

Each tool follows a consistent API design.

## Base Path

/api/tools/<tool_name>

## Standard Endpoints
### POST /run
Executes the tool's core logic.

**Request example:**
```json
{
  "input": "some text",
  "options": {
    "depth": "standard",
    "model": "gpt-4.1-mini"
  }
}

Response example:

{
  "result": {
    "score": 0.88,
    "blocks": []
  },
  "meta": {
    "tokens": 1024,
    "duration_ms": 1450
  }
}

GET /status (optional)

Used for long-running tools.



Implementation Notes
	•	All tools return result and meta.
	•	All tools accept options for configuration.
	•	Keep endpoints stateless (except for authentication).


---

# 📁 **/docs/04-tool-ui-template.md**

```md
# Tool UI Template (Frontend)

Every tool page follows a consistent layout:

/app/tools//page.tsx

## Layout Pattern

- Sidebar (left):
  - Input fields
  - Settings/config
  - “Run Analysis” button
- Main panel (right):
  - Output/results area

## Example JSX Skeleton

```tsx
export default function ToolPage() {
  return (
    <main className="flex min-h-screen">
      <aside className="w-[320px] border-r p-6">
        {/* Inputs / settings */}
      </aside>
      <section className="flex-1 p-6">
        {/* Results */}
      </section>
    </main>
  );
}

Principles
	•	Use the same component system for all tools.
	•	Buttons and form elements match Lovable’s exported design.
	•	Keep one strong CTA inside each tool: “Run / Analyze”.

---

# 📁 **/docs/05-deployment.md**

```md
# Deployment Guide (Minimal)

## Hosting Provider
- **Railway** hosts:
  - FastAPI backend
  - Next.js frontend
  - PostgreSQL DB

## Environment Setup

### Backend ENV
- OPENAI_API_KEY=
- DATABASE_URL=
- FRONTEND_URL=
- APP_ENV=production

### Frontend ENV
- NEXT_PUBLIC_API_URL=https://app.queryarc.com/api

---

## Deployment Steps

### Backend
1. Push to GitHub.
2. Railway auto-builds FastAPI service.
3. Set environment variables.
4. Deploy.

### Frontend
1. Push code to GitHub.
2. Railway builds Next.js app.
3. Set `NEXT_PUBLIC_API_URL`.
4. Assign domain: `app.queryarc.com`.

### Database
- Railway Postgres service created manually.
- Automatically connects via `DATABASE_URL`.

---

## Domain Routing
- `queryarc.com` → Lovable Marketing project.
- `app.queryarc.com` → Railway Frontend.
- API served at `app.queryarc.com/api`.