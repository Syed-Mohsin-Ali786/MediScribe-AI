# MediScribe AI — Backend

AI-powered medical SOAP notes from doctor–patient conversations, with a human-in-the-loop doctor review step.

- **Spec:** [`MediScribe_AI_SRS.md`](./MediScribe_AI_SRS.md)
- **Handoff doc for agents:** [`AGENTS.md`](./AGENTS.md)

## Stack

FastAPI · SQLAlchemy 2.0 (async) · Alembic · PostgreSQL (Supabase) · psycopg3 · ReportLab (PDF)

## Setup

```bash
python -m venv .venv
.\.venv\Scripts\activate        # Windows
pip install -r requirements.txt
# For local development and tests instead:
pip install -r requirements-dev.txt

Copy-Item .env.example .env     # then fill in real values
alembic upgrade head            # create tables
python -m app.seed              # optional demo admin/doctor/patient
uvicorn app.main:app --reload   # http://localhost:8000/docs
```

## Tests

```bash
pytest tests/                      # unit tests; integration tests auto-skip without a DB
$env:TEST_DATABASE_URL="postgresql+psycopg://..." ; pytest tests/test_api_integration.py
```

Without `MISTRAL_API_KEY` / `GEMINI_API_KEY`, the AI pipeline runs on built-in demo transcripts and extractions so the whole flow works offline.
