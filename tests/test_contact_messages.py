from __future__ import annotations

from app.schemas.message import ContactMessageCreate


def test_contact_message_create_allows_optional_doctor_id() -> None:
    payload = ContactMessageCreate(
        doctor_id=None,
        name="Jane Doe",
        email="jane@example.com",
        phone="+92 300 1234567",
        message="Hello from the landing page",
    )

    assert payload.doctor_id is None
    assert payload.name == "Jane Doe"
