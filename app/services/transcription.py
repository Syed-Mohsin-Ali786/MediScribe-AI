from __future__ import annotations

import asyncio
import logging

from mistralai import File, Mistral

from app.core.config import Settings, get_settings

logger = logging.getLogger("mediscribe.transcription")

_settings = get_settings()


async def transcribe_audio(file_bytes: bytes, filename: str, settings: Settings | None = None) -> dict:
    """Transcribe audio with Mistral Voxtral ASR including speaker diarization.

    If no API key is configured, returns a demo transcript so the pipeline can be
    exercised end-to-end without external credentials.
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
    seen: list[str] = []
    for seg in res.segments or []:
        raw = getattr(seg, "speaker_id", None) or getattr(seg, "speaker", None) or None
        if raw is not None and raw not in seen:
            seen.append(raw)
        # Map distinct diarized speakers to Doctor / Patient by first appearance
        # (consultations normally open with the doctor). Anything past the second
        # speaker gets a neutral "Speaker N" label.
        if raw is None:
            speaker = "Doctor"
        elif len(seen) <= 2 and seen.index(raw) == 0:
            speaker = "Doctor"
        elif len(seen) <= 2 and seen.index(raw) == 1:
            speaker = "Patient"
        else:
            speaker = f"Speaker {seen.index(raw) + 1}"
        segments.append({
            "speaker": speaker,
            "start": getattr(seg, "start", None),
            "end": getattr(seg, "end", None),
            "text": getattr(seg, "text", ""),
        })
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
