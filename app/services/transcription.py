from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter, defaultdict

from mistralai import File, Mistral

from app.core.config import Settings, get_settings

logger = logging.getLogger("mediscribe.transcription")

_settings = get_settings()

_WORD = re.compile(r"[\w']+", re.UNICODE)


def _normalize(text: str) -> str:
    return " ".join(_WORD.findall((text or "").lower()))


# --- Content-aware speaker classification ------------------------------------
#
# Mistral's diarization only tells us that two *distinct voices* exist — it does
# not tell us which voice belongs to the doctor. The old heuristic (first speaker
# seen = Doctor) broke whenever the patient spoke first, which mislabeled the
# whole consultation. Instead we read *what* is being said: doctors ask questions
# and give guidance, patients describe symptoms and answer.
#
# Question-starters (weight 2) are the strongest doctor signal.

DOCTOR_PHRASES = {
    # question starters (weight 2)
    "bataiye", "batao", "bataaen", "boliye", "sunaaiye", "dikhaiye",
    "kahan", "kab", "kaise", "kyon", "kyu", "kya", "kitna", "kitne", "kitni",
    "kis", "kaunsi", "kaunsa", "kitni der", "kab se",
    # results / exam / vitals
    "blood pressure", "blood work", "lab", "lab reports", "test results",
    "protein", "sugar", "weight", "pulse", "temperature", "x-ray", "ultrasound",
    "ekg", "ecg", "scan", "report", "jaanch",
    # prescribing / treatment
    "dawa", "medicine", "medication", "dose", "tablet", "injection", "diet",
    "aaram", "salaah", "nuskha", "shuru", "jaari", "rakhein", "rakhiye",
    "deti hoon", "deta hoon", "denge", "prescribe",
    # framing / directing the conversation
    "namaste", "aaiye", "chaliye", "baithiye", "suniye", "main aapko", "aapko",
    "aapka", "aapki", "aapke", "average", "normal", "readings", "do hafte",
    "teen mahine", "dobara",
}

_QUESTION_STARTERS = {
    "bataiye", "batao", "bataaen", "boliye", "sunaaiye", "dikhaiye",
    "kahan", "kab", "kaise", "kyon", "kyu", "kya", "kitna", "kitne", "kitni",
    "kis", "kaunsi", "kaunsa", "kitni der", "kab se",
}

PATIENT_PHRASES = {
    # symptom complaints
    "shukriya doctor", "shukriya", "dhanyavaad", "doctor sahab", "doctor ji",
    "sahab", "madam",
    "bukhar", "thakan", "chakkar", "soojan", "khaansi", "khansi", "takleef",
    "mehsoos ho rahi", "mehsoos kar rahi", "kaafi thakan", "kaafi kam",
    "sar mein dard", "sar ka dard", "sar ke peechhe", "gale mein", "gale",
    "pet mein", "badan mein", "sir dard", "sar dard", "kamzor", "dorad", "dora",
    "bardasht", "anguthiyaan", "peshaab", "khadi hoti hoon", "khada hota hoon",
    # duration
    "din se", "hafton se", "mahine se", "saal se", "kal se", "raat ko", "roz",
    "subah", "baar baar", "pichhle", "jab main",
    # personal response
    "mujhe", "mera", "meri", "haan ji", "haan", "nahi", "theek", "behtar",
    "bahut behtar", "aata hai", "rehti hai", "padta hai", "hota hai", "jaata nahi",
}

_FIRST_TOKEN = {
    "bataiye": ("doctor", 2), "batao": ("doctor", 2), "kya": ("doctor", 2),
    "kahan": ("doctor", 2), "kab": ("doctor", 2), "kaise": ("doctor", 2),
    "namaste": ("doctor", 1), "chaliye": ("doctor", 1), "suniye": ("doctor", 1),
    "main": ("doctor", 1),
    "nahi": ("patient", 1), "haan": ("patient", 1), "shukriya": ("patient", 2),
    "theek": ("patient", 1), "behtar": ("patient", 1), "mujhe": ("patient", 1),
    "zyadatar": ("patient", 1), "bahut": ("patient", 1), "jab": ("patient", 1),
}


def classify_speaker(text: str) -> str | None:
    """Return "Doctor", "Patient", or None when the content is ambiguous.

    Scores the utterance with weighted doctor/patient keyword phrases; the first
    word is the strongest cue for who is speaking.
    """
    normalized = _normalize(text)
    if not normalized:
        return None
    score = 0

    for phrase in DOCTOR_PHRASES:
        if phrase in normalized:
            score += 2 if phrase in _QUESTION_STARTERS else 1
    for phrase in PATIENT_PHRASES:
        if phrase in normalized:
            score -= 1

    first = normalized.split(" ", 1)[0]
    if first in _FIRST_TOKEN:
        role, weight = _FIRST_TOKEN[first]
        score += weight if role == "doctor" else -weight

    if score > 0:
        return "Doctor"
    if score < 0:
        return "Patient"
    return None


def _assign_speakers(segments: list[dict]) -> None:
    """Label every segment Doctor/Patient using content + diarization clusters.

    When the audio has two real speaker clusters, per-cluster majority voting
    keeps each cluster consistent (a real voice never flip-flops) and overrides
    the wrong "first speaker = Doctor" assumption. When diarization collapsed to
    a single cluster, segments are labelled purely by their content.
    """
    clusters: dict[str, list[dict]] = defaultdict(list)
    order: list[str] = []
    for seg in segments:
        raw = seg.get("_raw")
        key = str(raw) if raw is not None else ""
        if key not in clusters:
            order.append(key)
        clusters[key].append(seg)

    for seg in segments:
        seg["_label"] = classify_speaker(seg.get("text", ""))

    if len(order) >= 2:
        for key in order:
            group = clusters[key]
            votes = Counter(seg["_label"] for seg in group if seg["_label"])
            label = votes.most_common(1)[0][0] if votes else (
                "Doctor" if order.index(key) == 0 else "Patient"
            )
            for seg in group:
                seg["speaker"] = label
    else:
        votes = Counter(seg["_label"] for seg in segments if seg["_label"])
        majority = votes.most_common(1)[0][0] if votes else "Doctor"
        for seg in segments:
            seg["speaker"] = seg["_label"] or majority


async def transcribe_audio(file_bytes: bytes, filename: str, settings: Settings | None = None) -> dict:
    """Transcribe audio with Mistral Voxtral ASR including speaker diarization.

    If no API key is configured, returns a demo transcript so the pipeline can be
    exercised end-to-end without external credentials. The spoken language is
    auto-detected by Voxtral (note: Urdu is not a supported target language, so
    Urdu speech is typically rendered as Hindi).
    """
    settings = settings or _settings
    if not settings.mistral_api_key or not file_bytes:
        logger.warning("No MISTRAL_API_KEY or empty audio — using demo transcript")
        return _demo_transcript()

    return await asyncio.to_thread(_transcribe_sync, file_bytes, filename, settings)


def _transcribe_sync(file_bytes: bytes, filename: str, settings: Settings) -> dict:
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "webm"
    audio_file = File(
        file_name=filename,
        content=file_bytes,
        content_type=f"audio/{ext}",
    )
    with Mistral(api_key=settings.mistral_api_key) as mistral:
        res = mistral.audio.transcriptions.complete(
            model="voxtral-mini-latest",
            file=audio_file,
            diarize=True,
            timestamp_granularities=["segment"],
        )
    segments = []
    for seg in res.segments or []:
        raw = getattr(seg, "speaker_id", None) or getattr(seg, "speaker", None) or None
        segments.append({
            "_raw": raw,
            "start": getattr(seg, "start", None),
            "end": getattr(seg, "end", None),
            "text": getattr(seg, "text", ""),
        })
    _assign_speakers(segments)
    for seg in segments:
        seg.pop("_raw", None)
        seg.pop("_label", None)
    return {"text": res.text, "segments": segments}


def _demo_transcript() -> dict:
    return {
        "text": (
            "Doctor: Namaste, aaj aapko kya takleef hai? "
            "Patient: Do din se gale mein dard aur bukhar hai. "
            "Doctor: Kya khaansi ya saans ki takleef hai? "
            "Patient: Nahi, bas sir dard aur badan mein dard hai. "
            "Doctor: Main aapko acetaminophen 500 mg aur aaram ki salaah deti hoon."
        ),
        "segments": [
            {"speaker": "Doctor", "start": 0.0, "end": 3.5, "text": "Namaste, aaj aapko kya takleef hai?"},
            {"speaker": "Patient", "start": 3.8, "end": 7.2, "text": "Do din se gale mein dard aur bukhar hai."},
            {"speaker": "Doctor", "start": 7.5, "end": 11.0, "text": "Kya khaansi ya saans ki takleef hai?"},
            {"speaker": "Patient", "start": 11.3, "end": 15.0, "text": "Nahi, bas sir dard aur badan mein dard hai."},
            {"speaker": "Doctor", "start": 15.5, "end": 19.0, "text": "Main aapko acetaminophen 500 mg aur aaram ki salaah deti hoon."},
        ],
    }
