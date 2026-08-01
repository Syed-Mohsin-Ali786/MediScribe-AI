# AGENTS.md — MediScribe AI

> **Living project document.** Read this first. Update it after every work session so the next agent can pick up instantly.

## 1. Project Overview

**MediScribe AI** converts doctor–patient conversation audio into structured, editable SOAP-note medical records using Generative AI, with a human-in-the-loop doctor review step before a patient can view anything.

- **Full spec:** [`MediScribe_AI_SRS.md`](./MediScribe_AI_SRS.md) (v1.0, 31 Jul 2026) — read it for detailed requirements, schema, and API contracts.
- **Context:** Hackathon submission (Generative AI Track), deadline **1 Aug 2026, 11:59 PM**.
- **Roles:** `Admin`, `Doctor`, `Patient`. No public self-registration — the **admin creates doctors**, and doctors create their own patients.

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

**Last updated:** 1 Aug 2026 (transcript display upgrade — **speaker diarization is now content-aware**: the old "first speaker = Doctor" heuristic mislabeled consultations whenever the patient spoke first; `app/services/transcription.py::classify_speaker` now reads each utterance (question starters/medical guidance → Doctor, symptom descriptions/responses → Patient), with per-cluster majority voting so a real voice never flip-flops. Added a **bilingual transcript**: every segment now carries `text_en` (English) + `text_ur` (Urdu script), translated by Gemini at generation time with an offline glossary fallback (`app/services/translation.py`); the frontend `Transcript` component has a language select (**As spoken · English · اردو**, RTL for Urdu) and the patient report page now shows the transcript too. Demo reports re-seeded idempotently with bilingual segments; 14 tests pass, ruff clean, frontend build clean. Earlier today: demo audio re-seeded (Hindi 2-voice + Romanized Urdu transcripts live); **doctor onboarding via admin** — `POST /auth/register` removed, admin creates `POST /admin/doctors`, edits `PATCH /admin/users/{id}`, deletes `DELETE /admin/users/{id}` (guard: doctor with patients/reports blocked); admin console = "Onboard doctor" + Doctors & Patients directory with Edit modal + Delete; live dashboard + analytics (`/admin/analytics`, Recharts); `data-scroll-behavior="smooth"` fix; "invite"→"add/create patient" wording.) Latest: **all 9 live reports backfilled** (`app/backfill_translations.py`) with `text_en`/`text_ur` + content-corrected `speaker` labels via a new combined LLM annotation path — `translation.py` now also classifies `Doctor`/`Patient` per segment (Gemini structured output, **Mistral instant failover** since the Gemini free tier 429s), `_SegmentTranslation.speaker`, `translate_transcript(force=True)` re-annotates everything, and the backfill re-labels any degenerate all-one-speaker transcript. Verified via API: every report shows correct D/P alternation (patient-speaks-first now labeled correctly) and full English+Urdu translations; 14 tests pass, ruff clean. Fix: **report generation 500 → `extract_clinical` Gemini 429** — `app/services/extraction.py` now falls back to **Mistral** (`_extract_mistral`, same `ClinicalExtraction` JSON schema) and only then to the demo extraction, so `/generate-report` never dies when Gemini rate-limits. Verified live: 201 → `draft_generated`, transcript + translations + Mistral-extracted symptoms/medications present.) UI pass: **landing "Our Doctors" section** replaces the old roles block — new public `GET /api/v1/public/doctors` (approved doctors, no auth) + `frontend/components/landing-doctors.tsx` (doctor count, compact cards that expand to full details, "Contact Now" modal with name/email/age/message form). **Admin can no longer edit patients** (`PATCH /admin/users/{id}` now 400s for non-doctors; Edit button hidden for patient rows) and patients now show **age** (computed from existing `dob`, `ageFromDob` in `format.ts`) in the admin directory and doctor patient cards; `AdminUserOut.dob` added. 14 tests pass, ruff clean, `npm run build` clean.) **Contact messages inbox**: landing "Contact Now" form now actually persists — new `contact_messages` table (migration `0002`), public `POST /api/v1/public/contact` (no auth, validates the doctor exists), `GET /api/v1/doctor/messages` (+ `?unread_only`) and `PATCH /api/v1/doctor/messages/{id}/read` (doctor-owned). Frontend: `/doctor/messages` inbox page (name/email/age/message, Mark-read, New badge), Messages nav item with a live unread-count badge (polled 20s in `app-shell.tsx`), and an unread banner on the doctor overview. Verified live: contact → 201 → shows in Dr. Rohan's inbox.

**Pending from earlier session:** (done) seed demo reports re-seeded with **Romanized Urdu (Hindustani)** transcripts + **Hindi 2-speaker TTS** (Doctor = male `hi-IN-MadhurNeural`, Patient = female `hi-IN-SwaraNeural`). Ananya's old English demo reports + real generated reports were deleted from Supabase and `media/`; `python -m app.seed` recreated 2 demo reports (approved `demo_ananya_01.mp3` 62.1s / 7 segments, draft `demo_ananya_02.mp3` 26s / 3 segments) with real ffmpeg-concat per-segment timestamps. Verified: audio served (`audio/mpeg`), patient sees only approved report, `GET /records/{id}` returns Urdu segments with start/end, PDF export works for doctor + patient, tests pass.

---

## 3. Feature Progress Checklist

| ID | Feature | Status |
|---|---|---|
| FR-1 | Auth & role management (admin creates doctors; JWT role claims) | ✅ |
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
| POST | `/auth/login` | Public | ✅ |
| POST | `/admin/doctors` | Admin | ✅ |
| PATCH | `/admin/users/{user_id}` | Admin | ✅ |
| DELETE | `/admin/users/{user_id}` | Admin | ✅ |
| GET | `/admin/pending-doctors` | Admin | ✅ |
| PATCH | `/admin/users/{user_id}/promote-to-doctor` | Admin | ✅ |
| DELETE | `/admin/users/{user_id}/reject` | Admin | ✅ |
| GET | `/admin/stats` | Admin | ✅ |
| GET | `/admin/users` | Admin | ✅ |
| GET | `/admin/integrations` | Admin | ✅ |
| GET | `/admin/analytics` | Admin | ✅ |
| POST | `/doctor/patients` | Doctor | ✅ |
| GET | `/doctor/patients` | Doctor | ✅ |
| GET | `/doctor/patients/search` | Doctor | ✅ |
| POST | `/generate-report` | Doctor | ✅ |
| GET | `/records/{id}` | Doctor, Patient (own) | ✅ |
| PATCH | `/records/{id}` | Doctor | ✅ |
| POST | `/records/{id}/approve` | Doctor | ✅ |
| GET | `/patient/reports` | Patient | ✅ |
| GET | `/patient/doctors` | Patient | ✅ |
| GET | `/records/{id}/pdf` | Doctor, Patient (own) | ✅ |

All routes are mounted under prefix **`/api/v1`** in `app/main.py`. Note: FastAPI 0.141 registers included routers lazily — routes appear in `/openapi.json` and at runtime but are wrapped as `_IncludedRouter` in `app.routes`.

Legend: ✅ done · 🔲 not started · ⚠️ in progress / blocked

---

## 5. Current Plan / Next Steps

Ordered by the hackathon timeline (30 Jul – 1 Aug 2026). Work top to bottom.

1. ✅ **Scaffold backend**: FastAPI app layout, `pyproject.toml`/`requirements.txt` (pin versions from §1), config + env loading, Supabase Postgres connection via SQLAlchemy + psycopg.
2. ✅ **Models + migrations**: `users` and `reports` tables per SRS §5 (UUID PKs, enums, JSONB columns, self-referential `doctor_id`). Alembic migration `0001` written; run `alembic upgrade head` once a DB URL is live.
3. ✅ **Auth layer**: login, JWT `role` claim decoding, `require_role(...)` dependencies; admin creates/edits doctors directly (`/admin/doctors`, `/admin/users/{id}`).
4. ✅ **Patient management**: doctor creates/invites patients, lists own patients. Doctor sets the patient's login password at invite time (`POST /doctor/patients` requires `password`). Invite email stubbed/manual for demo.
5. ✅ **AI pipeline**: `/generate-report` — Mistral transcription (diarized) → Gemini structured extraction → RxNorm validation (with local JSON fallback) → persist `status = draft_generated`. Offline demo transcripts/extractions kick in when API keys are absent.
6. ✅ **Review workflow**: fetch draft, PATCH edits, POST approve (`status = approved`, set `approved_at`).
7. ✅ **Patient access**: `GET /patient/reports` (approved only).
8. ✅ **PDF export** on approved reports (ReportLab — WeasyPrint dropped because GTK/Pango is not installed on the Windows dev box).
9. 🔲 **RLS policies** in Supabase as defense-in-depth.
10. 🔲 **Deploy + demo**: cloud hosting (Render/Railway/Fly.io), env-based secrets, scripted demo audio.

### Blockers / notes
- ✅ Verified: `/openapi.json` lists all 14 `/api/v1` routes, including doctor patient search and patient doctor directory. Seven tests pass locally; three database-dependent tests skip without `TEST_DATABASE_URL`. Ruff clean.
- ✅ **Friendly error responses**: `app/core/errors.py` — request-ID middleware + global handlers return clean JSON (`status_code`, `detail`, `error_code`, `request_id`) instead of raw 500s. `SQLAlchemyError` → 503 "service temporarily busy", validation → 422 with `errors` detail, anything else → 500 "Something went wrong". Full traceback logged server-side via `mediscribe.errors` logger. Registered in `app/main.py`.
- ✅ **DB connected**: Supabase pooler (`aws-0-ap-southeast-1.pooler.supabase.com:6543`) works; direct host (`db.*.supabase.co`) does not resolve from dev machine. Alembic migration `0001` applied.
- ✅ **Integration tests pass**: set `TEST_DATABASE_URL` to the async pooler URL (`postgresql+psycopg_async://postgres.<ref>:<pass>@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres`).
- ✅ **Bugs fixed (session 2)**: `user.role.value` crash on login (role is plain str from DB); `created_at: str` → `datetime` in schemas; Mistral/Gemini API errors now gracefully fall back to demo data; `conftest.py` added for Windows SelectorEventLoop.
- `.env` exists locally — do not commit.
- `requirements.txt` uses the official `fastapi[standard]` extra; `requirements-dev.txt` adds pytest, pytest-asyncio, ruff, and mypy for local backend development.

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
  - **Doctor sets the patient's login password** (required `password` field on `POST /doctor/patients`) — no auto-generated/temporary password. Satisfies FR-2.2/2.3 for the demo instead of a real email invite. **UI wording uses "add/create patient" (not "invite")** — there is no email invite; a created patient appears in the doctor's patient list immediately (`setPatients(await api.myPatients())` after create).
  - **SQLite offline fallback**: `Settings.database_url` is now a plain `str` (was `PostgresDsn`); models use `Uuid` + `JSONBCompat` (JSONB on Postgres, JSON on SQLite) so `DATABASE_URL=sqlite:///./mediscribe_demo.db` runs the whole backend with zero external services. `aiosqlite` added to deps. Run `python -m app.seed` to create tables + demo accounts. Point `DATABASE_URL` at Supabase for prod — no code change needed.
  - **Password hashing → Argon2** (`argon2-cffi`), not bcrypt/passlib: bcrypt caps passwords at 72 bytes and passlib's bcrypt backend is broken with current `bcrypt` releases. Hashes start with `$argon2id$`. Any bcrypt-hashed rows from before this switch will no longer verify.
  - **FastAPI 0.141 lazy router registration**: included routers appear as `_IncludedRouter` in `app.routes`; endpoints are live in OpenAPI/runtime, so verify with `/openapi.json`.
  - **String enums** (`String(50)`) for `users.role` and `reports.status` instead of Postgres `ENUM` types — avoids ALTER-type migration friction.
  - **`run_async()` helper in `app/core/database.py`**: standalone async entry points (`app/seed.py`, `alembic/env.py`) must run on `asyncio.SelectorEventLoop` on Windows — psycopg async cannot run on the default ProactorEventLoop. Uvicorn already selects a compatible loop for the API, so only scripts needed the fix. Use `run_async(coro)` instead of `asyncio.run(coro)`.
- **Env quirk**: `DATABASE_URL` uses `postgresql+psycopg://`; the async engine and Alembic env convert it to `postgresql+psycopg_async://` at import time.
