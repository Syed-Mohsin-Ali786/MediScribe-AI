from __future__ import annotations

import json

import httpx

from app.core.config import Settings, get_settings

_settings = get_settings()

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"
)

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "symptoms": {"type": "array", "items": {"type": "string"}},
        "medical_history": {"type": "array", "items": {"type": "string"}},
        "diagnosis": {"type": "string"},
        "medications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "dosage": {"type": "string"},
                    "frequency": {"type": "string"},
                    "duration": {"type": "string"},
                },
                "required": ["name"],
            },
        },
        "recommendations": {"type": "array", "items": {"type": "string"}},
        "soap": {
            "type": "object",
            "properties": {
                "subjective": {"type": "string"},
                "objective": {"type": "string"},
                "assessment": {"type": "string"},
                "plan": {"type": "string"},
            },
            "required": ["subjective", "objective", "assessment", "plan"],
        },
        "highlights": {"type": "array", "items": {"type": "string"}},
        "follow_up_points": {"type": "array", "items": {"type": "string"}},
        "confidence_flags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["field", "reason"],
            },
        },
    },
    "required": ["symptoms", "diagnosis", "medications", "soap", "confidence_flags"],
}


async def extract_clinical(transcript: dict, settings: Settings | None = None) -> dict:
    """Send diarized transcript to Gemini 3.6 Flash and return structured clinical data."""
    settings = settings or _settings
    transcript_text = transcript.get("text", "")
    if not settings.gemini_api_key:
        return _demo_extraction(transcript_text)

    prompt = (
        "You are a clinical documentation assistant. Extract a structured clinical note "
        "from the following doctor-patient conversation. "
        "Return JSON matching the provided schema exactly.\n\n"
        f"Transcript:\n{transcript_text}\n"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                ],
            },
        ],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": EXTRACTION_SCHEMA,
        },
    }

    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(
            GEMINI_URL,
            params={"key": settings.gemini_api_key},
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        data = response.json()

    candidates = data.get("candidates", [])
    if not candidates:
        return _demo_extraction(transcript_text)

    text = candidates[0]["content"]["parts"][0]["text"]
    return json.loads(text)


def _demo_extraction(transcript_text: str) -> dict:
    return {
        "symptoms": ["sore throat", "fever", "headache", "body aches"],
        "medical_history": [],
        "diagnosis": "Acute pharyngitis, likely viral",
        "medications": [
            {
                "name": "acetaminophen",
                "dosage": "500 mg",
                "frequency": "every 6 hours as needed",
                "duration": "3 days",
            }
        ],
        "recommendations": ["Rest", "Hydration", "Monitor fever"],
        "soap": {
            "subjective": (
                "Patient reports sore throat and fever for two days, accompanied by headache "
                "and body aches. Denies cough and shortness of breath."
            ),
            "objective": "No physical exam data recorded in audio.",
            "assessment": "Acute pharyngitis, likely viral etiology.",
            "plan": "Acetaminophen 500 mg every 6 hours PRN. Rest and fluids. Follow up if symptoms worsen.",
        },
        "highlights": ["Fever present", "No respiratory symptoms"],
        "follow_up_points": ["Return if fever persists beyond 3 days"],
        "confidence_flags": [
            {"field": "objective", "reason": "No physical exam details captured in audio."}
        ],
    }
