from __future__ import annotations

import os

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Base
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


async def _register_doctor(client: httpx.AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Dr. Alex Rivera",
            "email": "doctor@test.ai",
            "password": "DoctorPass!123",
            "specialization": "General Practice",
        },
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
async def test_full_workflow(client) -> None:
    ac, session_factory = client

    # 1. Doctor self-registers as pending.
    await _register_doctor(ac)
    await _seed_admin(session_factory)

    admin_token = await _login(ac, "admin@test.ai", "AdminPass!123")

    # 2. Admin approves the doctor.
    pending = await ac.get("/api/v1/admin/pending-doctors", headers=_auth(admin_token))
    assert pending.status_code == 200, pending.text
    doctor_id = pending.json()[0]["id"]
    promote = await ac.patch(
        f"/api/v1/admin/users/{doctor_id}/promote-to-doctor", headers=_auth(admin_token)
    )
    assert promote.status_code == 200, promote.text
    assert promote.json()["role"] == "doctor"

    # 3. Doctor creates a patient.
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

    # 5. Patient cannot see a draft report (403).
    patient_token = await _login(ac, "jamie@test.ai", "PatientPass!123")
    doctors = await ac.get("/api/v1/patient/doctors", headers=_auth(patient_token))
    assert doctors.status_code == 200, doctors.text
    assert doctors.json()[0]["email"] == "doctor@test.ai"
    draft_fetch = await ac.get(f"/api/v1/records/{report['id']}", headers=_auth(patient_token))
    assert draft_fetch.status_code == 403

    # 6. Doctor approves; patient can now see the report and export the PDF.
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

    patient_list = await ac.get("/api/v1/patient/reports", headers=_auth(patient_token))
    assert patient_list.status_code == 200, patient_list.text
    assert [r["id"] for r in patient_list.json()] == [report["id"]]

    pdf = await ac.get(f"/api/v1/records/{report['id']}/pdf", headers=_auth(patient_token))
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_doctor_cannot_access_other_doctors_report(client) -> None:
    ac, session_factory = client
    await _register_doctor(ac)
    await _seed_admin(session_factory)
    admin_token = await _login(ac, "admin@test.ai", "AdminPass!123")
    doctor_id = (await ac.get("/api/v1/admin/pending-doctors", headers=_auth(admin_token))).json()[0][
        "id"
    ]
    await ac.patch(
        f"/api/v1/admin/users/{doctor_id}/promote-to-doctor", headers=_auth(admin_token)
    )

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

    # Second doctor registers and gets approved.
    await ac.post(
        "/api/v1/auth/register",
        json={
            "name": "Dr. Second",
            "email": "second@test.ai",
            "password": "DoctorPass!123",
            "specialization": "Internal Medicine",
        },
    )
    second_id = (
        await ac.get("/api/v1/admin/pending-doctors", headers=_auth(admin_token))
    ).json()[0]["id"]
    await ac.patch(
        f"/api/v1/admin/users/{second_id}/promote-to-doctor", headers=_auth(admin_token)
    )
    second_token = await _login(ac, "second@test.ai", "DoctorPass!123")

    resp = await ac.get(f"/api/v1/records/{report['id']}", headers=_auth(second_token))
    assert resp.status_code == 403
