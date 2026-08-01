from __future__ import annotations

from app.services.transcription import _assign_speakers, classify_speaker
from app.services.translation import apply_glossary


def test_classify_speaker_doctor_questions() -> None:
    assert classify_speaker("Namaste, aaj aapko kya takleef hai?") == "Doctor"
    assert classify_speaker("Bataiye, sar ka dard kahan hota hai?") == "Doctor"
    assert classify_speaker("Aapka blood pressure 158 bay 96 hai.") == "Doctor"


def test_classify_speaker_patient_symptoms() -> None:
    assert classify_speaker("Do din se gale mein dard aur bukhar hai.") == "Patient"
    assert classify_speaker("Shukriya doctor, thakan aur chakkar hota hai.") == "Patient"
    assert classify_speaker("Nahi, bas sir dard aur badan mein dard hai.") == "Patient"


def test_assign_speakers_patient_first_is_corrected() -> None:
    """Regression: when the patient speaks first, the old first-speaker heuristic
    mislabeled the whole consultation. Cluster voting must recover the roles."""
    segments = [
        {"_raw": "speaker_A", "text": "Shukriya doctor. Teen hafton se thakan hai aur sar mein dard hai."},
        {"_raw": "speaker_B", "text": "Namaste, blood work aa gaye hain. Bataiye kahan dard hota hai?"},
        {"_raw": "speaker_A", "text": "Zyadatar sar ke peechhe, subah ke waqt."},
        {"_raw": "speaker_B", "text": "Aapka blood pressure 158 bay 96 hai. Main halki dawa deti hoon."},
    ]
    _assign_speakers(segments)
    assert [s["speaker"] for s in segments] == ["Patient", "Doctor", "Patient", "Doctor"]


def test_assign_speakers_single_cluster_by_content() -> None:
    segments = [
        {"_raw": None, "text": "Namaste, aaj aapko kya takleef hai?"},
        {"_raw": None, "text": "Do din se gale mein dard aur bukhar hai."},
    ]
    _assign_speakers(segments)
    assert [s["speaker"] for s in segments] == ["Doctor", "Patient"]


def test_apply_glossary_adds_bilingual_text() -> None:
    transcript = {"segments": [{"text": "Namaste, aaj aapko kya takleef hai?"}]}
    apply_glossary(transcript)
    seg = transcript["segments"][0]
    assert seg["text_en"] == "Hello, what's troubling you today?"
    assert "تکلیف" in seg["text_ur"]


def test_apply_glossary_leaves_unknown_phrase() -> None:
    transcript = {"segments": [{"text": "Something totally unrelated happened today."}]}
    apply_glossary(transcript)
    assert "text_en" not in transcript["segments"][0]
    assert "text_ur" not in transcript["segments"][0]
