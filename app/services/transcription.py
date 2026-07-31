from __future__ import annotations

import httpx

from app.core.config import Settings, get_settings

_settings = get_settings()

MISTRAL_TRANSCRIBE_URL = "https://api.mistral.ai/v1/audio/transcriptions"


async def transcribe_audio(file_bytes: bytes, filename: str, settings: Settings | None = None) -> dict:
    """Transcribe audio with Mistral ASR including speaker diarization.

    If no API key is configured, returns a demo transcript so the pipeline can be
    exercised end-to-end without external credentials.
    """
    settings = settings or _settings
    if not settings.mistral_api_key:
        return _demo_transcript()

    async with httpx.AsyncClient(timeout=120.0) as client:
        files = {
            "file": (filename, file_bytes, f"audio/{filename.rsplit('.', 1)[-1]}"),
        }
        data = {
            "model": "mistral-large-latest",
            "diarize": "true",
            "language": "en",
            "timestamp_granularities": "segment",
        }
        headers = {"Authorization": f"Bearer {settings.mistral_api_key}"}
        response = await client.post(
            MISTRAL_TRANSCRIBE_URL,
            files=files,
            data=data,
            headers=headers,
        )
        response.raise_for_status()
        return response.json()


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
