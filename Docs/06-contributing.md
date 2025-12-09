# Contributing Guide (Minimal)

## Requirements
- Python 3.10+
- Node 18+
- Git + GitHub access

## Setup

### Backend

cd backend
pip install -r requirements.txt
uvicorn app.main:app –reload


### Frontend

cd frontend
npm install
npm run dev


## Adding a New Tool

1. **Backend**
   - Create file: `backend/app/api/tools/<tool>.py`
   - Implement `/run` endpoint using the API template.

2. **Frontend**
   - Create folder: `frontend/app/tools/<tool>/`
   - Create page: `page.tsx`
   - Use the standard tool UI layout.
   - Connect to backend endpoint.

3. **Marketing Page**
   - Add a new tool page in Lovable.
   - Link the CTA to `https://app.queryarc.com/tools/<tool>`.

## Code Style
- Python: type hints required.
- JS/TS: use TypeScript when possible.
- Keep components small and reusable.