from __future__ import annotations

import copy
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, engine, run_async
from app.core.security import hash_password, verify_password
from app.models import Base
from app.models.report import Report, ReportStatus
from app.models.user import User, UserRole
from app.services.supabase_storage import MEDIA_DIR
from app.services.translation import apply_glossary

DEMO_DOCTOR_EMAIL = os.getenv("DEMO_DOCTOR_EMAIL", "dr.rohan@mediscribe.ai")
DEMO_DOCTOR_PASSWORD = os.getenv("DEMO_DOCTOR_PASSWORD", "demo1234")
DEMO_PATIENT_EMAIL = os.getenv("DEMO_PATIENT_EMAIL", "ananya@mediscribe.ai")
DEMO_PATIENT_PASSWORD = os.getenv("DEMO_PATIENT_PASSWORD", "demo1234")
DEMO_PATIENT_DOB = date.fromisoformat(os.getenv("DEMO_PATIENT_DOB", "1992-04-18"))

DOCTOR_VOICE = "hi-IN-MadhurNeural"
PATIENT_VOICE = "hi-IN-SwaraNeural"


def _mp3_duration(path: Path) -> float:
    import subprocess

    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True,
        text=True,
    )
    try:
        return float(r.stdout.strip() or 0)
    except Exception:
        return 0.0


async def _synth_speech(segments: list[dict], filename: str) -> tuple[str, list[dict]]:
    """Speak each transcript segment with a per-speaker Hindi voice, concatenate the
    parts with ffmpeg, and return (media_url, per-segment real start/end times).

    Doctor segments use a male Hindi voice, patient segments a female Hindi voice, so
    the demo recording is genuinely two-speaker and the transcript highlight syncs to
    the real audio timeline. Falls back to a single-voice MP3 (and the caller's
    original times) when ffmpeg is unavailable, and "" when audio can't be produced.
    """
    try:
        import edge_tts
    except Exception:
        return "", []
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    text = " ".join((seg.get("text") or "") for seg in segments)
    timed = [
        {"start": seg.get("start", 0.0), "end": seg.get("end", 0.0)} for seg in segments
    ]
    try:
        import shutil
        import subprocess

        parts_dir = MEDIA_DIR / f"{filename}.parts"
        parts_dir.mkdir(exist_ok=True)
        parts: list[Path] = []
        for i, seg in enumerate(segments):
            voice = DOCTOR_VOICE if str(seg.get("speaker", "")).lower().startswith("doctor") else PATIENT_VOICE
            part = parts_dir / f"{i:03d}.mp3"
            await edge_tts.Communicate(seg.get("text") or "", voice=voice).save(str(part))
            parts.append(part)

        start = 0.0
        timed = []
        for part in parts:
            dur = _mp3_duration(part) or 0.5
            timed.append({"start": round(start, 2), "end": round(start + dur, 2)})
            start += dur

        out = MEDIA_DIR / filename
        listf = parts_dir / "list.txt"
        listf.write_text("\n".join(f"file '{p}'" for p in parts))
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listf), "-c", "copy", str(out)],
            capture_output=True,
        )
        shutil.rmtree(parts_dir, ignore_errors=True)
        if out.stat().st_size > 0:
            return f"/media/{filename}", timed
    except Exception:
        pass
    # Fallback: one voice speaking the whole transcript.
    try:
        out = MEDIA_DIR / filename
        await edge_tts.Communicate(text, voice=DOCTOR_VOICE).save(str(out))
        if out.stat().st_size > 0:
            return f"/media/{filename}", timed
    except Exception:
        pass
    return "", []


async def _ensure_user(
    db, email: str, password: str, name: str, role: UserRole, *, reset_password: bool = False, **kwargs
) -> User:
    user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            name=name,
            email=email,
            hashed_password=hash_password(password),
            role=role,
            **kwargs,
        )
        db.add(user)
        await db.flush()
        print(f"Created {role.value}: {email}")
    elif reset_password and not verify_password(password, user.hashed_password):
        user.hashed_password = hash_password(password)
        print(f"Reset password for: {email}")
    return user


async def seed() -> None:
    settings = get_settings()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as db:
        # Admin (from env, so it can be rotated per deployment). Password is reset to
        # match ADMIN_PASSWORD so the frontend quick-login always works.
        if settings.admin_email and settings.admin_password:
            await _ensure_user(
                db,
                settings.admin_email,
                settings.admin_password,
                "Platform Admin",
                UserRole.ADMIN,
                is_approved=True,
                reset_password=True,
            )

        # Demo doctor (pre-approved for the demo flow).
        doctor = await _ensure_user(
            db,
            DEMO_DOCTOR_EMAIL,
            DEMO_DOCTOR_PASSWORD,
            "Dr. Rohan Deshpande",
            UserRole.DOCTOR,
            is_approved=True,
            specialization="Internal Medicine",
            reset_password=True,
        )

        # Demo patient linked to the demo doctor.
        patient = await _ensure_user(
            db,
            DEMO_PATIENT_EMAIL,
            DEMO_PATIENT_PASSWORD,
            "Ananya Sharma",
            UserRole.PATIENT,
            is_approved=True,
            doctor_id=doctor.id,
            dob=DEMO_PATIENT_DOB,
            reset_password=True,
        )

        # Demo reports so the dashboards show data out of the box.
        existing = await db.scalar(select(Report).where(Report.patient_id == patient.id))
        if existing is None:
            transcript = {
                "text": (
                    "Doctor: Namaste Ananya, aapke blood work aa gaye hain. Chaliye baat karte hain. "
                    "Patient: Shukriya doctor. Pichhle teen hafton se mujhe kaafi thakan mehsoos ho rahi "
                    "hai, aur sar mein dard bhi rehta hai jo jaata nahi. Doctor: Bataiye, sar ka dard kahan "
                    "hota hai? Subah zyada hota hai ya kisi aur waqt? Patient: Zyadatar sar ke peechhe, "
                    "subah ke waqt. Aur jab main turant khadi hoti hoon to halka chakkar aa jaata hai. "
                    "Doctor: Kya haathon ya pairon mein soojan aayi hai? Patient: Anguthiyaan tight lagne "
                    "lagi hain, aur raat ko baar baar peshaab ke liye uthna padta hai. Doctor: Aaj aapka "
                    "blood pressure 158 bay 96 hai, aur peshaab ki jaanch mein protein mila hai. Main aapko "
                    "halki dawa aur kam namak wali diet shuru kar rahi hoon. Do hafte mein wapas milte hain."
                ),
                "segments": [
                    {"speaker": "Doctor", "start": 0.0, "end": 0.0, "text": "Namaste Ananya, aapke blood work aa gaye hain. Chaliye baat karte hain.", "text_en": "Hello Ananya, your blood work results are in. Let's have a talk about them.", "text_ur": "نمستے اننیا، آپ کے خون کے ٹیسٹ کے نتائج آ گئے ہیں۔ چلیے بات کرتے ہیں۔"},
                    {"speaker": "Patient", "start": 0.0, "end": 0.0, "text": "Shukriya doctor. Pichhle teen hafton se mujhe kaafi thakan mehsoos ho rahi hai, aur sar mein dard bhi rehta hai jo jaata nahi.", "text_en": "Thank you doctor. For the last three weeks I have been feeling very tired, and I keep having a headache that doesn't go away.", "text_ur": "شکریہ ڈاکٹر۔ پچھلے تین ہفتوں سے مجھے کافی تھکن محسوس ہو رہی ہے، اور سر میں بھی درد رہتا ہے جو جاتا نہیں۔"},
                    {"speaker": "Doctor", "start": 0.0, "end": 0.0, "text": "Bataiye, sar ka dard kahan hota hai? Subah zyada hota hai ya kisi aur waqt?", "text_en": "Tell me, where is the headache? Is it worse in the morning or at any other time?", "text_ur": "بتائیے، سر کا درد کہاں ہوتا ہے؟ صبح زیادہ ہوتا ہے یا کسی اور وقت؟"},
                    {"speaker": "Patient", "start": 0.0, "end": 0.0, "text": "Zyadatar sar ke peechhe, subah ke waqt. Aur jab main turant khadi hoti hoon to halka chakkar aa jaata hai.", "text_en": "Mostly at the back of the head, in the morning. And when I stand up quickly I get a little dizzy.", "text_ur": "زیادہ تر سر کے پیچھے، صبح کے وقت۔ اور جب میں جلدی کھڑی ہوتی ہوں تو ہلکا سا چکر آ جاتا ہے۔"},
                    {"speaker": "Doctor", "start": 0.0, "end": 0.0, "text": "Kya haathon ya pairon mein soojan aayi hai?", "text_en": "Have you noticed any swelling in your hands or feet?", "text_ur": "کیا آپ کے ہاتھوں یا پیروں میں سوجن آئی ہے؟"},
                    {"speaker": "Patient", "start": 0.0, "end": 0.0, "text": "Anguthiyaan tight lagne lagi hain, aur raat ko baar baar peshaab ke liye uthna padta hai.", "text_en": "My rings have started to feel tight, and I have to get up to urinate again and again at night.", "text_ur": "انگوٹھیاں تنگ لگنے لگی ہیں، اور رات کو بار بار پیشاب کے لیے اٹھنا پڑتا ہے۔"},
                    {"speaker": "Doctor", "start": 0.0, "end": 0.0, "text": "Aaj aapka blood pressure 158 bay 96 hai, aur peshaab ki jaanch mein protein mila hai. Main aapko halki dawa aur kam namak wali diet shuru kar rahi hoon. Do hafte mein wapas milte hain.", "text_en": "Your blood pressure today is 158 over 96, and protein was found in your urine test. I am starting you on a mild medicine and a low-salt diet. Let's meet again in two weeks.", "text_ur": "آج آپ کا بلڈ پریشر 158 بائے 96 ہے، اور پیشاب کے ٹیسٹ میں پروٹین ملا ہے۔ میں آپ کو ہلکی دوا اور کم نمک والی غذا شروع کر رہی ہوں۔ دو ہفتے میں پھر ملیں گے۔"},
                ],
            }
            follow_up = {
                "text": (
                    "Doctor: Dawa shuru karne ke baad aap kaise mehsoos kar rahi hain? Patient: Bahut behtar "
                    "hoon. Sar ka dard ab kaafi kam hai, bas shaam ko thodi thakan rehti hai. Doctor: Aapka "
                    "blood pressure log achha hai — average 132 bay 84. Wahi dose jaari rakhein, aur teen "
                    "mahine baad labs dobara kar lete hain."
                ),
                "segments": [
                    {"speaker": "Doctor", "start": 0.0, "end": 0.0, "text": "Dawa shuru karne ke baad aap kaise mehsoos kar rahi hain?", "text_en": "How have you been feeling since you started the medicine?", "text_ur": "دوا شروع کرنے کے بعد آپ کیسا محسوس کر رہی ہیں؟"},
                    {"speaker": "Patient", "start": 0.0, "end": 0.0, "text": "Bahut behtar hoon. Sar ka dard ab kaafi kam hai, bas shaam ko thodi thakan rehti hai.", "text_en": "Much better. The headache is much less now, I just feel a little tired in the evening.", "text_ur": "بہت بہتر ہوں۔ سر کا درد اب کافی کم ہے، بس شام کو تھوڑی تھکن رہتی ہے۔"},
                    {"speaker": "Doctor", "start": 0.0, "end": 0.0, "text": "Aapka blood pressure log achha hai — average 132 bay 84. Wahi dose jaari rakhein, aur teen mahine baad labs dobara kar lete hain.", "text_en": "Your blood pressure log is good — averaging 132 over 84. Keep the same dose, and let's repeat the labs after three months.", "text_ur": "آپ کا بلڈ پریشر ریکارڈ اچھا ہے — اوسطاً 132 بائے 84۔ وہی خوراک جاری رکھیں، اور تین ماہ بعد ٹیسٹ دوبارہ کر لیتے ہیں۔"},
                ],
            }
            extraction = {
                "symptoms": ["Fatigue (3 weeks)", "Morning occipital headaches", "Dizziness on standing", "Peripheral edema (ring tightness)"],
                "medical_history": ["No known prior hypertension", "No family history of renal disease", "Non-smoker"],
                "diagnosis": ["Hypertension — stage 2 (158/96)", "Proteinuria — rule out early renal involvement"],
                "medications": [
                    {"name": "Amlodipine", "dosage": "5 mg", "frequency": "once daily", "rxnorm_status": "valid", "rxnorm_note": "RxNorm: amlodipine besylate 5 mg"},
                    {"name": "Lisinopril", "dosage": "10 mg", "frequency": "once daily", "rxnorm_status": "valid", "rxnorm_note": "RxNorm: lisinopril 10 mg"},
                ],
                "recommendations": ["Low-sodium diet (<2 g/day)", "Monitor BP twice daily at home", "Reduce caffeine intake"],
                "soap": {
                    "subjective": "Patient reports 3 weeks of fatigue, morning occipital headaches, lightheadedness on standing, and recent ring tightness. Denies chest pain, palpitations, or vision changes.",
                    "objective": "BP 158/96 both arms. Urinalysis positive for protein. No ankle edema on exam; rings tight bilaterally. Heart sounds normal, no murmurs.",
                    "assessment": "Stage 2 hypertension with proteinuria concerning for early hypertensive renal involvement.",
                    "plan": "Initiate amlodipine 5 mg + lisinopril 10 mg daily. Start low-sodium diet. Home BP log twice daily. Re-check BP and renal panel in 2 weeks.",
                },
                "highlights": ["New onset stage 2 hypertension", "Proteinuria present — renal involvement possible"],
                "follow_up_points": ["2-week follow-up with BP log", "Renal panel (creatinine, eGFR, urine protein/creatinine)"],
                "confidence_flags": [
                    {"field": "symptoms", "level": "high", "note": "Clear patient-reported timeline"},
                    {"field": "diagnosis", "level": "medium", "note": "Renal finding needs lab confirmation"},
                ],
            }
            validation_flags = [
                {"medication": "Amlodipine", "status": "valid", "note": "RxNorm matched"},
                {"medication": "Lisinopril", "status": "valid", "note": "RxNorm matched"},
            ]

            audio_approved, timed_approved = await _synth_speech(transcript["segments"], "demo_ananya_01.mp3")
            audio_draft, timed_draft = await _synth_speech(follow_up["segments"], "demo_ananya_02.mp3")
            for seg, t in zip(transcript["segments"], timed_approved, strict=True):
                seg["start"], seg["end"] = t["start"], t["end"]
            for seg, t in zip(follow_up["segments"], timed_draft, strict=True):
                seg["start"], seg["end"] = t["start"], t["end"]
            print(f"Demo audio: approved='{audio_approved}' draft='{audio_draft}'")
            db.add_all([
                Report(
                    patient_id=patient.id,
                    doctor_id=doctor.id,
                    audio_url=audio_approved or "local://audio/demo_ananya_01.mp3",
                    transcript_json=transcript,
                    extraction_json=extraction,
                    validation_flags=validation_flags,
                    status=ReportStatus.APPROVED,
                    approved_at=datetime.now(UTC) - timedelta(days=2),
                ),
                Report(
                    patient_id=patient.id,
                    doctor_id=doctor.id,
                    audio_url=audio_draft or "local://audio/demo_ananya_02.mp3",
                    transcript_json=follow_up,
                    extraction_json=extraction,
                    validation_flags=validation_flags,
                    status=ReportStatus.DRAFT_GENERATED,
                ),
            ])
            print(f"Seeded 2 demo reports for {DEMO_PATIENT_EMAIL}")

        # Idempotent refresh: ensure existing demo reports also carry the bilingual
        # transcript (text_en/text_ur) even when they predate this feature.
        for report in (await db.scalars(select(Report).where(Report.patient_id == patient.id))).all():
            tx = copy.deepcopy(report.transcript_json or {})
            if tx.get("segments"):
                apply_glossary(tx)
                report.transcript_json = tx

        await db.commit()

    print("Seed complete.")


if __name__ == "__main__":
    run_async(seed())
