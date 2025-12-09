# QueryArc – System Overview

## Purpose
QueryArc is a multi-tool platform designed to help creators understand how LLMs read, segment, rank, and reuse content. The long-term goal is to offer all tools inside one unified SaaS application.

## High-Level Architecture
QueryArc is built using three main components:

### 1. Marketing Site (Lovable)
- Built and hosted on Lovable Cloud.
- Includes:
  - Home page
  - Learn pages
  - Tool description pages
  - Training pages
  - About page
  - Blog (optional)
- Purpose:
  - SEO
  - Education
  - Conversions (single CTA to app)

### 2. App UI (Lovable → Exported)
- A separate Lovable project used for:
  - Designing screens of the QueryArc app
  - Matching the look/feel of the marketing site
  - Exporting React/Tailwind code to GitHub
- Not used as the production app.

### 3. SaaS Application (Railway)
- The real QueryArc application lives outside Lovable.
- Stack:
  - **Backend:** Python + FastAPI
  - **Frontend:** React/Next.js (Lovable-exported and extended)
  - **Database:** PostgreSQL
  - **Hosting:** Railway (backend + frontend + DB)
- Purpose:
  - Serve the live tools
  - Handle authentication, billing (later)
  - Run all LLM logic

## Multi-Tool Vision
- One login
- One dashboard
- Many tools (Arc Rank, Semantic Blocks, Fanout Visualizer, etc.)
- Each tool:
  - Has a marketing page on Lovable
  - Has an interactive version in the SaaS app