from __future__ import annotations

import os

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, run_async
from app.core.security import hash_password
from app.models.user import User, UserRole

DEMO_DOCTOR_EMAIL = os.getenv("DEMO_DOCTOR_EMAIL", "doctor@mediscribe.ai")
DEMO_DOCTOR_PASSWORD = os.getenv("DEMO_DOCTOR_PASSWORD", "DoctorPass!123")
DEMO_PATIENT_EMAIL = os.getenv("DEMO_PATIENT_EMAIL", "patient@mediscribe.ai")
DEMO_PATIENT_PASSWORD = os.getenv("DEMO_PATIENT_PASSWORD", "PatientPass!123")


async def seed() -> None:
    settings = get_settings()
    async with AsyncSessionLocal() as db:
        # Admin (from env, so it can be rotated per deployment).
        if settings.admin_email and settings.admin_password:
            admin = await db.scalar(select(User).where(User.email == settings.admin_email))
            if admin is None:
                db.add(
                    User(
                        name="Platform Admin",
                        email=settings.admin_email,
                        hashed_password=hash_password(settings.admin_password),
                        role=UserRole.ADMIN,
                        is_approved=True,
                    )
                )
                print(f"Created admin: {settings.admin_email}")

        # Demo doctor (pre-approved for the demo flow).
        doctor = await db.scalar(select(User).where(User.email == DEMO_DOCTOR_EMAIL))
        if doctor is None:
            doctor = User(
                name="Dr. Alex Rivera",
                email=DEMO_DOCTOR_EMAIL,
                hashed_password=hash_password(DEMO_DOCTOR_PASSWORD),
                role=UserRole.DOCTOR,
                is_approved=True,
                specialization="General Practice",
            )
            db.add(doctor)
            await db.flush()
            print(f"Created demo doctor: {DEMO_DOCTOR_EMAIL}")

        # Demo patient linked to the demo doctor.
        patient = await db.scalar(select(User).where(User.email == DEMO_PATIENT_EMAIL))
        if patient is None:
            db.add(
                User(
                    name="Jamie Morgan",
                    email=DEMO_PATIENT_EMAIL,
                    hashed_password=hash_password(DEMO_PATIENT_PASSWORD),
                    role=UserRole.PATIENT,
                    is_approved=True,
                    doctor_id=doctor.id,
                )
            )
            print(f"Created demo patient: {DEMO_PATIENT_EMAIL}")

        await db.commit()

    print("Seed complete.")


if __name__ == "__main__":
    run_async(seed())
