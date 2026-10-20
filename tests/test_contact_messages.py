from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Base
from app.models.user import User, UserRole
from app.schemas.message import ContactMessageCreate

DOCTOR_EMAIL = "dr.rivera@example.com"


async def _seed_doctor(session_factory, email: str = DOCTOR_EMAIL) -> str:
    """Create an approved doctor we can address messages to."""
    async with session_factory() as session:
        doctor = User(
            name="Dr. Alex Rivera",
            email=email,
            hashed_password=hash_password("DoctorPass!123"),
            role=UserRole.DOCTOR,
            is_approved=True,
            specialization="General Practice",
        )
        session.add(doctor)
        await session.commit()
        await session.refresh(doctor)
        return str(doctor.id)


async def _post_contact(client: httpx.AsyncClient, payload: dict):
    return await client.post("/api/v1/contact", json=payload)


def _base_payload(**overrides) -> dict:
    payload = {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "+92 300 1234567",
        "message": "Hello from the landing page",
    }
    payload.update(overrides)
    return payload


@pytest.fixture()
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
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


@pytest.mark.asyncio
async def test_legacy_contact_route_accepts_public_submissions(client) -> None:
    ac, _ = client
    response = await _post_contact(
        ac,
        _base_payload(
            intent="doctor_to_us",
            subject="Registration enquiry",
        ),
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["name"] == "Jane Doe"
    assert payload["email"] == "jane@example.com"
    # A doctor asking to register carries no doctor — it routes to the admin inbox.
    assert payload["doctor_id"] is None
    assert payload["intent"] == "doctor_to_us"
    assert payload["subject"] == "Registration enquiry"


@pytest.mark.asyncio
async def test_patient_message_resolves_doctor_from_email(client) -> None:
    ac, session_factory = client
    doctor_id = await _seed_doctor(session_factory)

    response = await _post_contact(
        ac,
        _base_payload(
            intent="patient_to_doctor",
            doctor_email=DOCTOR_EMAIL,
            age=42,
        ),
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["doctor_id"] == doctor_id
    assert payload["intent"] == "patient_to_doctor"
    assert payload["age"] == 42


@pytest.mark.asyncio
async def test_patient_message_accepts_doctor_id_directly(client) -> None:
    ac, session_factory = client
    doctor_id = await _seed_doctor(session_factory)

    response = await _post_contact(
        ac,
        _base_payload(intent="patient_to_doctor", doctor_id=doctor_id),
    )

    assert response.status_code == 201, response.text
    assert response.json()["doctor_id"] == doctor_id


@pytest.mark.asyncio
async def test_patient_message_with_unknown_doctor_email_is_rejected(client) -> None:
    ac, _ = client
    response = await _post_contact(
        ac,
        _base_payload(intent="patient_to_doctor", doctor_email="nobody@example.com"),
    )

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "We couldn't find a doctor with that email address."


@pytest.mark.asyncio
async def test_patient_message_cannot_target_a_non_doctor(client) -> None:
    ac, session_factory = client

    async def _seed_patient() -> None:
        async with session_factory() as session:
            session.add(
                User(
                    name="A Patient",
                    email="patient@example.com",
                    hashed_password=hash_password("PatientPass!123"),
                    role=UserRole.PATIENT,
                    is_approved=True,
                )
            )
            await session.commit()

    await _seed_patient()

    response = await _post_contact(
        ac,
        _base_payload(intent="patient_to_doctor", doctor_email="patient@example.com"),
    )

    assert response.status_code == 404, response.text


@pytest.mark.asyncio
async def test_patient_message_without_a_target_is_a_validation_error(client) -> None:
    ac, _ = client
    response = await _post_contact(ac, _base_payload(intent="patient_to_doctor"))

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_intent_is_required(client) -> None:
    ac, _ = client
    response = await _post_contact(ac, _base_payload())

    assert response.status_code == 422, response.text


def test_contact_message_create_allows_optional_doctor_id() -> None:
    payload = ContactMessageCreate(
        intent="doctor_to_us",
        doctor_id=None,
        name="Jane Doe",
        email="jane@example.com",
        phone="+92 300 1234567",
        message="Hello from the landing page",
    )

    assert payload.doctor_id is None
    assert payload.name == "Jane Doe"
    assert payload.intent == "doctor_to_us"
