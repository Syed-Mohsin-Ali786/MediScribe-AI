from __future__ import annotations

import os

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Base
from app.models.contact_message import ContactMessage
from app.models.user import User, UserRole

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set TEST_DATABASE_URL to a Postgres database to run integration tests",
)


@pytest.fixture()
async def client():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, session_factory

    app.dependency_overrides.clear()
    await engine.dispose()


async def _create_doctor(client: httpx.AsyncClient, admin_token: str, email: str, name: str) -> dict:
    resp = await client.post(
        "/api/v1/admin/doctors",
        json={
            "name": name,
            "email": email,
            "password": "DoctorPass!123",
            "specialization": "General Practice",
        },
        headers=_auth(admin_token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _seed_admin(session_factory) -> None:
    async with session_factory() as session:
        session.add(
            User(
                name="Admin",
                email="admin@test.ai",
                hashed_password=hash_password("AdminPass!123"),
                role=UserRole.ADMIN,
                is_approved=True,
            )
        )
        await session.commit()


async def _login(client: httpx.AsyncClient, email: str, password: str) -> str:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_admin_contact_messages_endpoints(client) -> None:
    ac, session_factory = client
    await _seed_admin(session_factory)

    admin_token = await _login(ac, "admin@test.ai", "AdminPass!123")
    doctor_payload = await _create_doctor(ac, admin_token, "doctor@test.ai", "Dr. Alex Rivera")
    doctor_id = doctor_payload["id"]

    async with session_factory() as session:
        older = ContactMessage(
            doctor_id=doctor_id,
            name="Older Sender",
            email="older@example.com",
            phone="+1 111 111 1111",
            message="First message",
            read=True,
        )
        newer = ContactMessage(
            doctor_id=doctor_id,
            name="Newer Sender",
            email="newer@example.com",
            phone="+1 222 222 2222",
            message="Second message",
            read=False,
        )
        session.add_all([older, newer])
        await session.commit()
        await session.refresh(newer)
        await session.refresh(older)
        newer_id = newer.id

    list_resp = await ac.get("/api/v1/admin/contact-messages", headers=_auth(admin_token))
    assert list_resp.status_code == 200, list_resp.text
    messages = list_resp.json()
    assert len(messages) == 2
    assert messages[0]["id"] == str(newer_id)
    assert messages[0]["read"] is False
    assert messages[1]["read"] is True

    read_resp = await ac.patch(
        f"/api/v1/admin/contact-messages/{newer_id}/read",
        headers=_auth(admin_token),
    )
    assert read_resp.status_code == 200, read_resp.text
    assert read_resp.json()["read"] is True

    unauth_resp = await ac.get("/api/v1/admin/contact-messages")
    assert unauth_resp.status_code == 401

    doctor_token = await _login(ac, "doctor@test.ai", "DoctorPass!123")
    doctor_forbidden = await ac.get(
        "/api/v1/admin/contact-messages",
        headers=_auth(doctor_token),
    )
    assert doctor_forbidden.status_code == 403


@pytest.mark.asyncio
async def test_full_workflow(client) -> None:
    ac, session_factory = client

    # 1. Admin creates the doctor directly (no self-registration).
    await _seed_admin(session_factory)

    admin_token = await _login(ac, "admin@test.ai", "AdminPass!123")
    await _create_doctor(ac, admin_token, "doctor@test.ai", "Dr. Alex Rivera")

    # 2. Doctor logs in immediately (approved by default).
    doctor_token = await _login(ac, "doctor@test.ai", "DoctorPass!123")
    create_patient = await ac.post(
        "/api/v1/doctor/patients",
        json={"name": "Jamie Morgan", "email": "jamie@test.ai", "dob": "1990-05-01", "password": "PatientPass!123"},
        headers=_auth(doctor_token),
    )
    assert create_patient.status_code == 201, create_patient.text
    patient_info = create_patient.json()
    patient_id = patient_info["id"]

    # Doctor directory endpoints only expose this doctor's patients.
    patients = await ac.get("/api/v1/doctor/patients", headers=_auth(doctor_token))
    assert patients.status_code == 200, patients.text
    assert patients.json()[0]["id"] == patient_id
    search = await ac.get(
        "/api/v1/doctor/patients/search",
        params={"q": "Jamie"},
        headers=_auth(doctor_token),
    )
    assert search.status_code == 200, search.text
    assert [patient["id"] for patient in search.json()] == [patient_id]

    # 4. Doctor generates a report from uploaded audio (demo pipeline, no API keys).
    gen = await ac.post(
        "/api/v1/generate-report",
        data={"patient_id": patient_id},
        files={"audio": ("consultation.webm", b"fake-audio-bytes", "audio/webm")},
        headers=_auth(doctor_token),
    )
    assert gen.status_code == 201, gen.text
    report = gen.json()
    assert report["status"] == "draft_generated"
    assert report["extraction_json"]["diagnosis"]
    assert isinstance(report["validation_flags"], list)

    # 5. Patient cannot see a draft report (403) — reports are doctor-only now.
    patient_token = await _login(ac, "jamie@test.ai", "PatientPass!123")
    doctors = await ac.get("/api/v1/patient/doctors", headers=_auth(patient_token))
    assert doctors.status_code == 200, doctors.text
    assert doctors.json()[0]["email"] == "doctor@test.ai"
    draft_fetch = await ac.get(f"/api/v1/records/{report['id']}", headers=_auth(patient_token))
    assert draft_fetch.status_code == 403

    # 6. Doctor approves; patient can only see appointment history (date, time, doctor).
    approve = await ac.post(
        f"/api/v1/records/{report['id']}/approve", headers=_auth(doctor_token)
    )
    assert approve.status_code == 200, approve.text
    approved_report = approve.json()
    assert approved_report["status"] == "approved"
    assert approved_report["id"] == report["id"]

    # Doctor can list their reports via GET /doctor/reports.
    doctor_reports = await ac.get("/api/v1/doctor/reports", headers=_auth(doctor_token))
    assert doctor_reports.status_code == 200, doctor_reports.text
    assert len(doctor_reports.json()) >= 1
    assert any(r["id"] == report["id"] for r in doctor_reports.json())

    patient_list = await ac.get("/api/v1/patient/history", headers=_auth(patient_token))
    assert patient_list.status_code == 200, patient_list.text
    items = patient_list.json()
    assert [r["id"] for r in items] == [report["id"]]
    # Only metadata — no clinical content leaks to the patient.
    assert "doctor_name" in items[0]
    assert "appointment_at" in items[0]
    assert "extraction_json" not in items[0]
    assert "audio_url" not in items[0]

    # Patient can no longer fetch the report body or export the PDF.
    detail_fetch = await ac.get(f"/api/v1/records/{report['id']}", headers=_auth(patient_token))
    assert detail_fetch.status_code == 403
    pdf = await ac.get(f"/api/v1/records/{report['id']}/pdf", headers=_auth(patient_token))
    assert pdf.status_code == 403


@pytest.mark.asyncio
async def test_doctor_cannot_access_other_doctors_report(client) -> None:
    ac, session_factory = client
    await _seed_admin(session_factory)
    admin_token = await _login(ac, "admin@test.ai", "AdminPass!123")
    await _create_doctor(ac, admin_token, "doctor@test.ai", "Dr. Alex Rivera")

    doctor_token = await _login(ac, "doctor@test.ai", "DoctorPass!123")
    patient = (
        await ac.post(
            "/api/v1/doctor/patients",
            json={"name": "P1", "email": "p1@test.ai", "password": "PatientPass!123"},
            headers=_auth(doctor_token),
        )
    ).json()
    report = (
        await ac.post(
            "/api/v1/generate-report",
            data={"patient_id": patient["id"]},
            files={"audio": ("a.webm", b"x", "audio/webm")},
            headers=_auth(doctor_token),
        )
    ).json()

    # Second doctor is created directly by the admin.
    await _create_doctor(ac, admin_token, "second@test.ai", "Dr. Second")
    second_token = await _login(ac, "second@test.ai", "DoctorPass!123")

    resp = await ac.get(f"/api/v1/records/{report['id']}", headers=_auth(second_token))
    assert resp.status_code == 403
