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
python -m app.server            # http://localhost:8000/docs
```

> **Windows:** always start the server with `python -m app.server` (or
> `uvicorn app.main:app --loop app.core.asyncio:selector_loop_factory`).
> Uvicorn otherwise picks `ProactorEventLoop`, which psycopg's async driver
> cannot use — every database request would fail with a misleading
> `503 "the service is temporarily busy"`.

## Tests

```bash
pytest tests/                      # unit tests; integration tests auto-skip without a DB
```

Without `MISTRAL_API_KEY` / `GEMINI_API_KEY`, the AI pipeline runs on built-in demo transcripts and extractions so the whole flow works offline.

## Public contact form

`POST /api/v1/public/contact` (and the legacy `POST /api/v1/contact`) routes on the
sender's `intent`:

| `intent` | Target | Where it lands |
|---|---|---|
| `patient_to_doctor` | `doctor_id` **or** `doctor_email` (must be an approved doctor) | that doctor's inbox |
| `doctor_to_us` | none | admin inbox |

`doctor_to_us` messages carry the applicant's `specialization` so the admin can
onboard them straight from the dashboard.
