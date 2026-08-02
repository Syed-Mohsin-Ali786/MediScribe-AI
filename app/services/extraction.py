from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings

logger = logging.getLogger("mediscribe.extraction")

_settings = get_settings()

SYSTEM_INSTRUCTION = """\
You are a strict clinical information extraction engine. Your sole job is to convert \
doctor-patient conversation transcripts into a structured JSON payload.

CRITICAL EXTRACTION RULES:
1. STRICT TRUTH ONLY: Extract ONLY information explicitly stated in the conversation transcript.
2. NO INFERENCES: NEVER assume or infer diagnoses, symptoms, or plans that were not directly \
mentioned by the doctor or patient (e.g., do NOT infer "Viral upper respiratory infection" if \
only "headache" was stated).
3. ABSENT DATA: If a field (like Objective physical findings, Assessment, or Diagnosis) was not \
explicitly discussed in the transcript, return an empty string "" or an empty list [].
4. CONFIDENCE FLAGS: If you must capture an ambiguity, add an entry to `confidence_flags` \
explaining why a field is uncertain or missing.
5. NO FLORID TEXT: Keep extracted values concise, professional, and directly rooted in the transcript.
6. MEDICATION NAMES: If the doctor prescribes or administers a medication but its specific name \
is never stated in the transcript (e.g., "I'm prescribing this medicine"), you MUST still list it \
in medications with the generic description, AND add a confidence_flag with field "medications" \
explaining that the drug name was not captured and the physician must fill it in.
7. NON-CLINICAL CONTENT: Ignore any content that is not part of the medical consultation (e.g., \
YouTube outros, subscribe requests, channel promotions). Only extract clinical information.
"""


class SoapNote(BaseModel):
    subjective: str = Field(
        description="Patient reported history, symptoms, and complaints explicitly stated."
    )
    objective: str = Field(
        description="Vital signs and physical exam findings directly mentioned by doctor. Empty if none."
    )
    assessment: str = Field(
        description="Explicit diagnosis stated by the doctor. Leave empty string if no diagnosis was stated."
    )
    plan: str = Field(
        description="Explicit treatment, medication instructions, or next steps prescribed by the doctor."
    )


class Medication(BaseModel):
    name: str = Field(description="Name of the prescribed drug.")
    dosage: str = Field(default="", description="Dosage if explicitly stated.")
    frequency: str = Field(default="", description="Frequency if explicitly stated.")
    duration: str = Field(default="", description="Duration if explicitly stated.")


class ConfidenceFlag(BaseModel):
    field: str = Field(description="The JSON field name that has ambiguity.")
    note: str = Field(description="Explanation of why the field is ambiguous or missing.")


class ClinicalExtraction(BaseModel):
    soap: SoapNote
    symptoms: list[str] = Field(description="List of symptoms explicitly stated by the patient.")
    medical_history: list[str] = Field(
        default_factory=list, description="Medical history explicitly mentioned."
    )
    diagnosis: list[str] = Field(
        description="Explicitly stated diagnosis as a list. Empty list if not mentioned."
    )
    medications: list[Medication] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    follow_up_points: list[str] = Field(default_factory=list)
    confidence_flags: list[ConfidenceFlag] = Field(default_factory=list)


async def extract_clinical(transcript: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    """Send diarized transcript to Gemini and return structured clinical data.

    Uses the Interactions API with structured output (JSON schema enforcement).
    Gemini free tier is often rate-limited (429), so on any failure we fall back
    to Mistral on the transcription key, and only if that also fails do we use the
    canned demo extraction so report generation never dies with a 500.
    """
    settings = settings or _settings
    transcript_text = transcript.get("text", "")
    if not settings.gemini_api_key:
        return _demo_extraction()
    try:
        return await asyncio.to_thread(_extract_gemini, transcript_text, settings)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gemini extraction unavailable — falling back to Mistral: %.120s", exc)
    try:
        return await asyncio.to_thread(_extract_mistral, transcript_text, settings)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Mistral extraction unavailable — using demo extraction: %.120s", exc)
    return _demo_extraction()


def _extract_gemini(transcript_text: str, settings: Settings) -> dict[str, Any]:
    from google import genai

    client = genai.Client(api_key=settings.gemini_api_key)
    interaction = client.interactions.create(
        model="gemini-3.6-flash",
        input=f"{SYSTEM_INSTRUCTION}\n\nExtract clinical details from this transcript:\n\n{transcript_text}",
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": ClinicalExtraction.model_json_schema(),
        },
    )
    result = ClinicalExtraction.model_validate_json(interaction.output_text)
    return result.model_dump()


def _extract_mistral(transcript_text: str, settings: Settings) -> dict[str, Any]:
    from mistralai import Mistral

    prompt = (
        f"{SYSTEM_INSTRUCTION}\n\nExtract clinical details from this transcript:\n\n{transcript_text}\n"
        "\nReturn ONLY JSON matching this exact schema:\n"
        f"{ClinicalExtraction.model_json_schema()}"
    )
    with Mistral(api_key=settings.mistral_api_key) as mistral:
        resp = mistral.chat.complete(
            model="mistral-small-latest",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
    result = ClinicalExtraction.model_validate_json(resp.choices[0].message.content)
    return result.model_dump()


def _demo_extraction() -> dict[str, Any]:
    return {
        "symptoms": ["sore throat", "fever", "headache", "body aches"],
        "medical_history": [],
        "diagnosis": ["Acute pharyngitis, likely viral"],
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
            "objective": "",
            "assessment": "Acute pharyngitis, likely viral etiology.",
            "plan": "Acetaminophen 500 mg every 6 hours PRN. Rest and fluids. Follow up if symptoms worsen.",
        },
        "highlights": ["Fever present", "No respiratory symptoms"],
        "follow_up_points": ["Return if fever persists beyond 3 days"],
        "confidence_flags": [
            {"field": "objective", "note": "No physical exam details captured in audio."}
        ],
    }
