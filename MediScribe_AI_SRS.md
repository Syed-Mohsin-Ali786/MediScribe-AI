# Software Requirements Specification (SRS)
## MediScribe AI — Turning Conversations into Intelligent Medical Records

**Version:** 1.0
**Date:** 31 July 2026
**Component Scope:** Backend (FastAPI) — developed by [Your Name]
**Prepared for:** Hackathon Submission (Generative AI Track)

---

## 1. Introduction

### 1.1 Purpose
This document specifies the functional and non-functional requirements for the backend of **MediScribe AI**, an AI-powered healthcare documentation assistant. The backend is responsible for authentication, role-based access control, patient/doctor management, the AI-driven transcription-to-SOAP-note pipeline, medication validation, and report storage.

### 1.2 Scope
MediScribe AI converts doctor-patient conversation audio recordings into structured, editable medical records (SOAP notes) using Generative AI, with a human-in-the-loop review step before finalization. The system supports three roles — **Admin**, **Doctor**, and **Patient** — each with a distinct, scoped view of the system.

The backend is built with **FastAPI** and **SQLAlchemy** (ORM for schema management and migrations), backed by a **Supabase (PostgreSQL)** database with Row-Level Security as a defense-in-depth layer.

### 1.3 Intended Audience
- Development team (backend, frontend, AI integration)
- Hackathon evaluation panel
- Future maintainers

### 1.4 Definitions & Acronyms
| Term | Meaning |
|---|---|
| SOAP | Subjective, Objective, Assessment, Plan — standard clinical note format |
| ASR | Automatic Speech Recognition |
| RLS | Row-Level Security (PostgreSQL) |
| JWT | JSON Web Token |
| ORM | Object-Relational Mapping |
| RxNorm | NIH's normalized drug naming database, used for medication validation |

---

## 2. Overall Description

### 2.1 Product Perspective
MediScribe AI is a standalone web application consisting of:
- A **FastAPI backend** (this document's primary scope) exposing REST endpoints
- A **frontend** (built by another team member) consuming these endpoints
- **Supabase** for Postgres database hosting, Auth, and RLS enforcement
- External AI/ML services: **Mistral** (speech-to-text + diarization), **Gemini 3.6 Flash** (structured clinical extraction), **RxNorm API** (medication validation)

### 2.2 Product Functions (Summary)
1. Role-based authentication and authorization (Admin / Doctor / Patient)
2. Doctor onboarding via self-registration + Admin approval
3. Patient onboarding via Doctor invitation (no public self-registration)
4. Audio upload and AI-driven transcription with speaker diarization
5. AI-driven structured clinical extraction and SOAP note generation
6. Medication/dosage validation against RxNorm with confidence flagging
7. Doctor review, editing, and approval workflow
8. Patient-scoped, read-only access to their own approved reports
9. PDF export of finalized reports

### 2.3 User Classes and Characteristics

| Role | Description | Key Permissions |
|---|---|---|
| **Admin** | Platform administrator | Approves/rejects doctor registrations. Cannot manage patients directly. |
| **Doctor** | Licensed practitioner (self-registers, pending admin approval) | Creates/invites patients, uploads consultation audio, reviews & approves AI-generated reports, views all their own patients' reports |
| **Patient** | Invited by a doctor, no self-registration | Views only their own approved reports |

### 2.4 Operating Environment
- Backend: Python 3.11+, FastAPI, SQLAlchemy (ORM), Uvicorn/Gunicorn
- Database: PostgreSQL via Supabase
- Auth: Supabase Auth issuing JWTs with custom `role` claims
- External APIs: Mistral (ASR), Gemini 3.6 Flash (LLM), RxNorm (drug validation)
- Deployment: Cloud-hosted (e.g., Render/Railway/Fly.io) with environment-based secrets management

### 2.5 Design & Implementation Constraints
- Hackathon timeline: development window 30 July 2026 – 1 August 2026 (submission deadline 11:59 PM)
- No real patient license/NPI verification (out of scope) — doctor signup collects Name, Email, Specialization only
- No real-time/live transcription — batch (post-upload) processing only
- Medication validation is a lightweight safety net (RxNorm + local JSON fallback), not a certified clinical decision support system

### 2.6 Assumptions & Dependencies
- Third-party APIs (Mistral, Gemini, RxNorm) are available and within free/trial usage limits during development and demo
- Demo audio is scripted/roleplayed by team members — no real patient data is used, avoiding compliance overhead
- Supabase project is provisioned before backend development begins

---

## 3. System Architecture

### 3.1 High-Level Data Flow

```
[Audio Recording]
        |
        v
[Mistral API] — Transcription + Speaker Diarization
        |
        v
[Gemini 3.6 Flash] — Single-call structured extraction:
        symptoms, history, diagnosis, medications,
        recommendations, SOAP (S/O/A/P), highlights,
        follow-up points, confidence flags
        |
        v
[Medication Validation] — RxNorm API (+ local JSON fallback)
        flags unrecognized drug names / dosages
        |
        v
[Supabase Insert] — status: "draft_generated"
        |
        v
[Doctor Review UI] (frontend, consumes backend API)
    - Audio player + diarized transcript
    - Editable form pre-filled with AI JSON
    - Warnings on flagged/low-confidence fields
        |
        v
[Doctor Approves] --> [Supabase Update] — status: "approved"
        |
        v
[PDF Export] --> Patient can view finalized report
```

### 3.2 Technology Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI |
| ORM / Schema Management | SQLAlchemy |
| Database | PostgreSQL (Supabase) |
| Authentication | Supabase Auth + custom JWT claims |
| Authorization | FastAPI dependency injection (route guards) + Supabase RLS |
| Speech-to-Text | Mistral `/v1/audio/transcriptions` (`diarize: true`) |
| Clinical Extraction / SOAP Generation | Gemini 3.6 Flash (structured JSON output) |
| Medication Validation | RxNorm REST API + local JSON dictionary fallback |
| PDF Generation | Backend-generated (library TBD — e.g., WeasyPrint/ReportLab) |
| Frontend | Built by separate team member (out of scope for this document) |

### 3.3 Security Model (Defense-in-Depth)
1. **Primary layer — FastAPI JWT guards:** Custom `role` claim (`admin` / `doctor` / `patient`) embedded in the Supabase-issued JWT. Protected routes use dependencies such as `Depends(require_role("doctor"))` to reject unauthorized requests before any database call.
2. **Secondary layer — Supabase RLS:** Postgres-level policies using `auth.jwt() ->> 'role'` and `auth.uid()` ensure that even a manipulated route parameter cannot return rows outside a user's own scope (e.g., a patient cannot query another patient's `patient_id`).

---

## 4. Functional Requirements

### FR-1: Authentication & Role Management
- **FR-1.1** Doctors self-register via `POST /auth/register` providing Name, Email, Password, Specialization. Account is created with `role = pending_doctor`, `is_approved = false`.
- **FR-1.2** Pending doctors see a status page indicating their account is awaiting Admin review (frontend responsibility; backend must expose status via API).
- **FR-1.3** Admin views pending doctor requests via `GET /admin/pending-doctors`.
- **FR-1.4** Admin approves a doctor via `PATCH /admin/users/{user_id}/promote-to-doctor`, setting `role = doctor`, `is_approved = true`.
- **FR-1.5** Patients cannot self-register. Patient accounts are created only by an approved Doctor.
- **FR-1.6** Login issues a JWT containing the user's `role` and `user_id` as custom claims.

### FR-2: Patient Management (Doctor-Owned)
- **FR-2.1** An approved Doctor creates a patient via `POST /doctor/patients` with Name, DOB, Email. The system auto-generates a patient record with `role = patient` and `doctor_id` set to the creating doctor.
- **FR-2.2** System sends an email invite with a temporary password/link (email delivery mechanism TBD/stubbed for hackathon demo).
- **FR-2.3** Patient logs in and is prompted to set a new password on first login.
- **FR-2.4** A Doctor can view all patients linked to them via `GET /doctor/patients`.

### FR-3: AI Report Generation Pipeline
- **FR-3.1** Doctor uploads a consultation audio file via `POST /generate-report` (combined transcription + extraction, per `patient_id`).
- **FR-3.2** Backend sends audio to Mistral ASR with `diarize: true` to obtain a speaker-separated transcript.
- **FR-3.3** Backend sends the diarized transcript to Gemini 3.6 Flash in a single call using a unified structured JSON schema, returning:
  - Symptoms, medical history, diagnosis, medications, doctor recommendations
  - SOAP note (Subjective, Objective, Assessment, Plan)
  - Highlights and follow-up points
  - Per-field confidence flags for uncertain extractions
- **FR-3.4** Backend cross-checks extracted medication names/dosages against the RxNorm API (with local JSON fallback if RxNorm is unavailable), appending validation flags to the response.
- **FR-3.5** The generated report is persisted in Supabase with `status = draft_generated`.

### FR-4: Doctor Review & Approval
- **FR-4.1** Doctor retrieves a draft report via `GET /records/{id}`, including transcript, AI JSON, and confidence/validation flags.
- **FR-4.2** Doctor edits any field via `PATCH /records/{id}`.
- **FR-4.3** Doctor finalizes the report via an approval action, setting `status = approved`. Once approved, the report becomes visible to the linked patient.

### FR-5: Patient Access
- **FR-5.1** Patient retrieves only their own approved reports via `GET /patient/reports`.
- **FR-5.2** Patients cannot view draft/unapproved reports or any other patient's data (enforced by both FastAPI guards and RLS).

### FR-6: PDF Export
- **FR-6.1** Once a report is approved, it can be exported as a PDF via `GET /records/{id}/pdf`, including doctor/specialization info, SOAP note, and follow-up highlights.

### FR-7: Admin Functions
- **FR-7.1** Admin manages doctor approvals only (FR-1.3, FR-1.4). Admin has no direct patient management capability.

---

## 5. Database Schema (SQLAlchemy Models)

> Managed via SQLAlchemy ORM; Alembic recommended for migrations if time permits.

### 5.1 `users`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | Matches Supabase `auth.uid()` |
| name | String | |
| email | String (unique) | |
| role | Enum(`admin`, `pending_doctor`, `doctor`, `patient`) | |
| is_approved | Boolean | Default `false` for `pending_doctor` |
| specialization | String (nullable) | Doctor-only field |
| doctor_id | UUID (FK → users.id, nullable) | Set only for patients |
| dob | Date (nullable) | Patient-only field |
| created_at | Timestamp | |

### 5.2 `reports`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| patient_id | UUID (FK → users.id) | |
| doctor_id | UUID (FK → users.id) | |
| audio_url | String | Storage reference |
| transcript_json | JSONB | Diarized transcript from Mistral |
| extraction_json | JSONB | Structured Gemini output (symptoms, history, diagnosis, meds, SOAP, highlights, confidence flags) |
| validation_flags | JSONB | RxNorm validation results |
| status | Enum(`draft_generated`, `approved`) | |
| created_at | Timestamp | |
| approved_at | Timestamp (nullable) | |

### 5.3 Relationships
- `users.doctor_id` → self-referential FK (patient → doctor)
- `reports.patient_id` and `reports.doctor_id` → FK to `users.id`

---

## 6. API Endpoint Summary

| Method | Endpoint | Role Required | Purpose |
|---|---|---|---|
| POST | `/auth/register` | Public | Doctor self-registration (pending) |
| POST | `/auth/login` | Public | Login, returns JWT with role claim |
| GET | `/admin/pending-doctors` | Admin | List pending doctor approvals |
| PATCH | `/admin/users/{user_id}/promote-to-doctor` | Admin | Approve a doctor |
| POST | `/doctor/patients` | Doctor | Create/invite a patient |
| GET | `/doctor/patients` | Doctor | List own patients |
| POST | `/generate-report` | Doctor | Upload audio → transcribe + extract + validate |
| GET | `/records/{id}` | Doctor, Patient (own only) | Fetch a report |
| PATCH | `/records/{id}` | Doctor | Edit draft report |
| POST | `/records/{id}/approve` | Doctor | Approve and finalize report |
| GET | `/patient/reports` | Patient | List own approved reports |
| GET | `/records/{id}/pdf` | Doctor, Patient (own only) | Export report as PDF |

---

## 7. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-1 | Backend responses for `/generate-report` should complete within a reasonable demo-friendly time (target: under 30s for a short sample recording) |
| NFR-2 | All role-protected endpoints must reject unauthorized requests at the FastAPI layer before any DB query executes |
| NFR-3 | RLS policies must independently enforce data isolation as a fallback, even if application-layer checks fail |
| NFR-4 | No real patient PII should be used in the hackathon demo; only scripted/roleplayed data |
| NFR-5 | AI-generated clinical content must never be presented to a patient without doctor approval (`status = approved` gate) |
| NFR-6 | System should degrade gracefully if RxNorm API is unreachable, falling back to the local JSON dictionary |

---

## 8. Future Enhancements (Out of Scope for Hackathon)
- Real-time/live transcription during consultations
- License/NPI verification for doctors
- Multilingual and code-switched transcription support
- ICD-10 code suggestion
- EHR system integration
- Email delivery service for patient invites (currently stubbed/manual for demo)

---

## 9. Appendix: Key External API References
- Mistral Transcription: `POST /v1/audio/transcriptions` (`diarize`, `language`, `timestamp_granularities`)
- Gemini 3.6 Flash: `client.interactions.create()` with structured output configuration
- RxNorm API: NIH public REST API for drug name/dosage normalization
