# AGENTS.md — MediScribe AI

> **Living project document.** Read this first. Update it after every work session so the next agent can pick up instantly.

## 1. Project Overview

**MediScribe AI** converts doctor–patient conversation audio into structured, editable SOAP-note medical records using Generative AI, with a human-in-the-loop doctor review step before a patient can view anything.

- **Full spec:** [`MediScribe_AI_SRS.md`](./MediScribe_AI_SRS.md) (v1.0, 31 Jul 2026) — read it for detailed requirements, schema, and API contracts.
- **Context:** Hackathon submission (Generative AI Track), deadline **1 Aug 2026, 11:59 PM**.
- **Roles:** `Admin`, `Doctor`, `Patient`. Patients cannot self-register — only doctors (after admin approval) can invite them.

### Tech Stack (latest versions, checked Jul 2026)
| Layer | Tech | Version |
|---|---|---|
| Runtime | Python | 3.14.x (3.13.x also OK) |
| API | FastAPI | 0.141.x |
| Data validation | Pydantic | 2.13.x |
| ORM | SQLAlchemy | 2.0.51 (2.1 in beta — stick to 2.0 stable) |
| Migrations | Alembic | 1.18.x |
| ASGI server | Uvicorn | 0.52.x |
| DB | PostgreSQL via Supabase | 18.x (Supabase-managed) |
| DB driver | psycopg (v3) | 3.3.x |
| Auth | Supabase Auth, JWT with custom `role` / `user_id` claims | n/a |
| Speech-to-Text | Mistral `/v1/audio/transcriptions` (`diarize: true`) | n/a (API) |
| Clinical Extraction | Gemini 3.6 Flash (structured JSON) | n/a (API) |
| Medication Validation | RxNorm REST API + local JSON fallback | n/a (API) |
| PDF Export | Backend-generated (WeasyPrint/ReportLab — TBD) | TBD |
| Frontend | Separate team member — out of scope for this backend repo | n/a |

### Security Model (Defense-in-Depth)
1. FastAPI JWT guards via `Depends(require_role("doctor"))` before any DB call.
2. Supabase RLS using `auth.jwt()` and `auth.uid()` as a fallback isolation layer.

---

## 2. Project Status

| Phase | Status |
|---|---|
| Requirements / SRS | ✅ Complete (v1.0) |
| Backend scaffolding (FastAPI app, config, DB connection) | ✅ Complete |
| Auth & roles | ✅ Complete |
| Patient management | ✅ Complete |
| AI report pipeline (Mistral + Gemini + RxNorm) | ✅ Complete (offline demo fallbacks built in) |
| Doctor review / approval workflow | ✅ Complete |
| Patient access | ✅ Complete |
| PDF export | ✅ Complete (ReportLab) |
| DB migrations (Alembic) | ✅ Applied to live DB |
| Tests | ✅ All 10 tests pass (unit + integration) |
| RLS policies (Supabase) | 🔲 Not started |
| Deployment & demo prep | 🔲 Not started |

**Last updated:** 31 Jul 2026 (session 2)

---

## 3. Feature Progress Checklist

| ID | Feature | Status |
|---|---|---|
| FR-1 | Auth & role management (doctor self-register, admin approve, JWT role claims) | ✅ |
| FR-2 | Patient management (doctor-owned: create, invite, list) | ✅ |
| FR-3 | AI report generation (upload → Mistral diarize → Gemini extraction → RxNorm validate → persist draft) | ✅ |
| FR-4 | Doctor review & approval (fetch draft, edit fields, approve) | ✅ |
| FR-5 | Patient access (read-only, own approved reports only) | ✅ |
| FR-6 | PDF export of approved reports | ✅ |
| FR-7 | Admin functions (doctor approvals only, no patient mgmt) | ✅ |

---

## 4. API Endpoint Status

| Method | Endpoint | Role | Status |
|---|---|---|---|
| POST | `/auth/register` | Public | ✅ |
| POST | `/auth/login` | Public | ✅ |
| GET | `/admin/pending-doctors` | Admin | ✅ |
| PATCH | `/admin/users/{user_id}/promote-to-doctor` | Admin | ✅ |
| POST | `/doctor/patients` | Doctor | ✅ |
| GET | `/doctor/patients` | Doctor | ✅ |
| POST | `/generate-report` | Doctor | ✅ |
| GET | `/records/{id}` | Doctor, Patient (own) | ✅ |
| PATCH | `/records/{id}` | Doctor | ✅ |
| POST | `/records/{id}/approve` | Doctor | ✅ |
| GET | `/patient/reports` | Patient | ✅ |
| GET | `/records/{id}/pdf` | Doctor, Patient (own) | ✅ |

All routes are mounted under prefix **`/api/v1`** in `app/main.py`. Note: FastAPI 0.141 registers included routers lazily — routes appear in `/openapi.json` and at runtime but are wrapped as `_IncludedRouter` in `app.routes`.

Legend: ✅ done · 🔲 not started · ⚠️ in progress / blocked

---

## 5. Current Plan / Next Steps

Ordered by the hackathon timeline (30 Jul – 1 Aug 2026). Work top to bottom.

1. ✅ **Scaffold backend**: FastAPI app layout, `pyproject.toml`/`requirements.txt` (pin versions from §1), config + env loading, Supabase Postgres connection via SQLAlchemy + psycopg.
2. ✅ **Models + migrations**: `users` and `reports` tables per SRS §5 (UUID PKs, enums, JSONB columns, self-referential `doctor_id`). Alembic migration `0001` written; run `alembic upgrade head` once a DB URL is live.
3. ✅ **Auth layer**: register/login, JWT `role` claim decoding, `require_role(...)` dependencies; admin approve/reject flow.
4. ✅ **Patient management**: doctor creates/invites patients, lists own patients. Invite email stubbed/manual for demo (doctor receives a temporary password to share offline).
5. ✅ **AI pipeline**: `/generate-report` — Mistral transcription (diarized) → Gemini structured extraction → RxNorm validation (with local JSON fallback) → persist `status = draft_generated`. Offline demo transcripts/extractions kick in when API keys are absent.
6. ✅ **Review workflow**: fetch draft, PATCH edits, POST approve (`status = approved`, set `approved_at`).
7. ✅ **Patient access**: `GET /patient/reports` (approved only).
8. ✅ **PDF export** on approved reports (ReportLab — WeasyPrint dropped because GTK/Pango is not installed on the Windows dev box).
9. 🔲 **RLS policies** in Supabase as defense-in-depth.
10. 🔲 **Deploy + demo**: cloud hosting (Render/Railway/Fly.io), env-based secrets, scripted demo audio.

### Blockers / notes
- ✅ Verified: `/openapi.json` lists all 12 `/api/v1` routes (FastAPI 0.141 lazy router registration confirmed working). All 10 tests pass, ruff clean.
- ✅ **Friendly error responses**: `app/core/errors.py` — request-ID middleware + global handlers return clean JSON (`status_code`, `detail`, `error_code`, `request_id`) instead of raw 500s. `SQLAlchemyError` → 503 "service temporarily busy", validation → 422 with `errors` detail, anything else → 500 "Something went wrong". Full traceback logged server-side via `mediscribe.errors` logger. Registered in `app/main.py`.
- ✅ **DB connected**: Supabase pooler (`aws-0-ap-southeast-1.pooler.supabase.com:6543`) works; direct host (`db.*.supabase.co`) does not resolve from dev machine. Alembic migration `0001` applied.
- ✅ **Integration tests pass**: set `TEST_DATABASE_URL` to the async pooler URL (`postgresql+psycopg_async://postgres.<ref>:<pass>@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres`).
- ✅ **Bugs fixed (session 2)**: `user.role.value` crash on login (role is plain str from DB); `created_at: str` → `datetime` in schemas; Mistral/Gemini API errors now gracefully fall back to demo data; `conftest.py` added for Windows SelectorEventLoop.
- `.env` exists locally — do not commit.

### Non-functional must-haves
- Reject unauthorized requests at FastAPI layer before any DB query (NFR-2).
- `status = approved` gate before patients see anything (NFR-5).
- RxNorm must degrade to local JSON fallback if unreachable (NFR-6).
- No real patient PII in the demo (NFR-4).

---

## 6. Setup & Run

```bash
# 1. Install deps (or: uv add -r requirements.txt)
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

# 2. Environment variables (copy .env.example -> .env, fill in values)
# SUPABASE_URL=...
# SUPABASE_SERVICE_KEY=...
# JWT_SECRET=...
# MISTRAL_API_KEY=...
# GEMINI_API_KEY=...
# DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db

# 3. Migrate + optional demo seed
alembic upgrade head
python -m app.seed

# 4. Run
uvicorn app.main:app --reload   # docs at http://localhost:8000/docs
```

> Without `MISTRAL_API_KEY`/`GEMINI_API_KEY` the AI pipeline uses built-in demo transcripts
> and extractions, so the full flow works offline for the demo.

### External API references (SRS §9)
- Mistral Transcription: `POST /v1/audio/transcriptions` (`diarize`, `language`, `timestamp_granularities`)
- Gemini 3.6 Flash: `client.interactions.create()` with structured output configuration
- RxNorm: NIH public REST API for drug name/dosage normalization

---

## 7. Agent Notes / Conventions

- **Update this file after every session**: tick completed features/endpoints, refresh "Last updated", append blockers to Next Steps.
- Out of scope for the hackathon: real-time transcription, license/NPI verification, multilingual support, ICD-10, EHR integration, real email service.
- No real patient data — demo uses scripted/roleplayed audio only.
- Follow the SRS as the source of truth; note any deviations from the spec here.
- **Decisions made** (recorded for the next agent):
  - **PDF → ReportLab** (not WeasyPrint): WeasyPrint needs GTK/Pango system libs missing on the Windows dev box; ReportLab is pure Python.
  - **`psycopg[binary]`** in deps: pure-python psycopg has no libpq on Windows; the binary extra bundles it.
  - **Patient accounts get a temporary password** (auto-generated unless the doctor supplies one) returned in `POST /doctor/patients` — this satisfies FR-2.2/2.3 for the demo instead of a real email invite.
  - **Password hashing → Argon2** (`argon2-cffi`), not bcrypt/passlib: bcrypt caps passwords at 72 bytes and passlib's bcrypt backend is broken with current `bcrypt` releases. Hashes start with `$argon2id$`. Any bcrypt-hashed rows from before this switch will no longer verify.
  - **FastAPI 0.141 lazy router registration**: included routers appear as `_IncludedRouter` in `app.routes`; endpoints are live in OpenAPI/runtime, so verify with `/openapi.json`.
  - **String enums** (`String(50)`) for `users.role` and `reports.status` instead of Postgres `ENUM` types — avoids ALTER-type migration friction.
  - **`run_async()` helper in `app/core/database.py`**: standalone async entry points (`app/seed.py`, `alembic/env.py`) must run on `asyncio.SelectorEventLoop` on Windows — psycopg async cannot run on the default ProactorEventLoop. Uvicorn already selects a compatible loop for the API, so only scripts needed the fix. Use `run_async(coro)` instead of `asyncio.run(coro)`.
- **Env quirk**: `DATABASE_URL` uses `postgresql+psycopg://`; the async engine and Alembic env convert it to `postgresql+psycopg_async://` at import time.
