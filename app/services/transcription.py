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
    if not settings.mistral_api_key:
        logger.warning("No MISTRAL_API_KEY configured — using demo transcript")
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
            language="en",
            timestamp_granularities=["segment"],
        )
    segments = []
    for seg in res.segments or []:
        segments.append({
            "speaker": getattr(seg, "speaker", None),
            "start": getattr(seg, "start", None),
            "end": getattr(seg, "end", None),
            "text": getattr(seg, "text", ""),
        })
    return {"text": res.text, "segments": segments}


def _demo_transcript() -> dict:
    return {
        "text": (
            "Doctor: Good morning, what brings you in today? "
            "Patient: I've had a sore throat and fever for two days. "
            "Doctor: Any cough or shortness of breath? "
            "Patient: No, just a headache and body aches. "
            "Doctor: I'll prescribe acetaminophen 500 mg and rest."
        ),
        "segments": [
            {"speaker": "Doctor", "start": 0.0, "end": 3.5, "text": "Good morning, what brings you in today?"},
            {"speaker": "Patient", "start": 3.8, "end": 7.2, "text": "I've had a sore throat and fever for two days."},
            {"speaker": "Doctor", "start": 7.5, "end": 11.0, "text": "Any cough or shortness of breath?"},
            {"speaker": "Patient", "start": 11.3, "end": 15.0, "text": "No, just a headache and body aches."},
            {"speaker": "Doctor", "start": 15.5, "end": 19.0, "text": "I'll prescribe acetaminophen 500 mg and rest."},
        ],
    }
