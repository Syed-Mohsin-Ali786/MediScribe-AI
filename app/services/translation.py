from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings

logger = logging.getLogger("mediscribe.translation")

_settings = get_settings()

_WORD = re.compile(r"[\w']+", re.UNICODE)

# Translate in small batches so very long transcripts stay inside the model's
# output window and a single bad response only costs one small retry.
_CHUNK_SIZE = 15

_SYSTEM_INSTRUCTION = """\
You are a medical transcript annotator. For each numbered conversation turn you must \
(1) identify who is speaking — "Doctor" or "Patient" — from the content alone (doctors \
ask questions, give instructions and medical guidance; patients greet, describe symptoms \
and answer), and (2) translate the turn into BOTH English (field `en`) and Urdu in \
Nastaʿlīq / Urdu script (field `ur`). Keep clinical terms accurate, keep the numbering \
from the input, and do not add or drop any medical information. Return only JSON.
"""


class _SegmentTranslation(BaseModel):
    index: int = Field(description="0-based index of the transcript segment")
    speaker: str | None = Field(
        default=None, description="Who is speaking: 'Doctor' or 'Patient'"
    )
    en: str = Field(description="English translation of the segment")
    ur: str = Field(description="Urdu-script translation of the segment")


class _TranslationResult(BaseModel):
    segments: list[_SegmentTranslation]


# Offline fallback glossary for the demo consultations. Keys are the normalized
# (lowercase, punctuation-stripped) romanized phrases so the whole demo flow works
# without any API keys. Live transcripts get real Gemini translations.
_DEMO_GLOSSARY: dict[str, dict[str, str]] = {
    "namaste ananya aapke blood work aa gaye hain chaliye baat karte hain": {
        "en": "Hello Ananya, your blood work results are in. Let's have a talk about them.",
        "ur": "نمستے اننیا، آپ کے خون کے ٹیسٹ کے نتائج آ گئے ہیں۔ چلیے بات کرتے ہیں۔",
    },
    "shukriya doctor pichhle teen hafton se mujhe kaafi thakan mehsoos ho rahi hai aur sar mein dard bhi rehta hai jo jaata nahi": {
        "en": "Thank you doctor. For the last three weeks I have been feeling very tired, and I keep having a headache that doesn't go away.",
        "ur": "شکریہ ڈاکٹر۔ پچھلے تین ہفتوں سے مجھے کافی تھکن محسوس ہو رہی ہے، اور سر میں بھی درد رہتا ہے جو جاتا نہیں۔",
    },
    "bataiye sar ka dard kahan hota hai subah zyada hota hai ya kisi aur waqt": {
        "en": "Tell me, where is the headache? Is it worse in the morning or at any other time?",
        "ur": "بتائیے، سر کا درد کہاں ہوتا ہے؟ صبح زیادہ ہوتا ہے یا کسی اور وقت؟",
    },
    "zyadatar sar ke peechhe subah ke waqt aur jab main turant khadi hoti hoon to halka chakkar aa jaata hai": {
        "en": "Mostly at the back of the head, in the morning. And when I stand up quickly I get a little dizzy.",
        "ur": "زیادہ تر سر کے پیچھے، صبح کے وقت۔ اور جب میں جلدی کھڑی ہوتی ہوں تو ہلکا سا چکر آ جاتا ہے۔",
    },
    "kya haathon ya pairon mein soojan aayi hai": {
        "en": "Have you noticed any swelling in your hands or feet?",
        "ur": "کیا آپ کے ہاتھوں یا پیروں میں سوجن آئی ہے؟",
    },
    "anguthiyaan tight lagne lagi hain aur raat ko baar baar peshaab ke liye uthna padta hai": {
        "en": "My rings have started to feel tight, and I have to get up to urinate again and again at night.",
        "ur": "انگوٹھیاں تنگ لگنے لگی ہیں، اور رات کو بار بار پیشاب کے لیے اٹھنا پڑتا ہے۔",
    },
    "aaj aapka blood pressure 158 bay 96 hai aur peshaab ki jaanch mein protein mila hai main aapko halki dawa aur kam namak wali diet shuru kar rahi hoon do hafte mein wapas milte hain": {
        "en": "Your blood pressure today is 158 over 96, and protein was found in your urine test. I am starting you on a mild medicine and a low-salt diet. Let's meet again in two weeks.",
        "ur": "آج آپ کا بلڈ پریشر 158 بائے 96 ہے، اور پیشاب کے ٹیسٹ میں پروٹین ملا ہے۔ میں آپ کو ہلکی دوا اور کم نمک والی غذا شروع کر رہی ہوں۔ دو ہفتے میں پھر ملیں گے۔",
    },
    "dawa shuru karne ke baad aap kaise mehsoos kar rahi hain": {
        "en": "How have you been feeling since you started the medicine?",
        "ur": "دوا شروع کرنے کے بعد آپ کیسا محسوس کر رہی ہیں؟",
    },
    "bahut behtar hoon sar ka dard ab kaafi kam hai bas shaam ko thodi thakan rehti hai": {
        "en": "Much better. The headache is much less now, I just feel a little tired in the evening.",
        "ur": "بہت بہتر ہوں۔ سر کا درد اب کافی کم ہے، بس شام کو تھوڑی تھکن رہتی ہے۔",
    },
    "aapka blood pressure log achha hai average 132 bay 84 wahi dose jaari rakhein aur teen mahine baad labs dobara kar lete hain": {
        "en": "Your blood pressure log is good — averaging 132 over 84. Keep the same dose, and let's repeat the labs after three months.",
        "ur": "آپ کا بلڈ پریشر ریکارڈ اچھا ہے — اوسطاً 132 بائے 84۔ وہی خوراک جاری رکھیں، اور تین ماہ بعد ٹیسٹ دوبارہ کر لیتے ہیں۔",
    },
    "namaste aaj aapko kya takleef hai": {
        "en": "Hello, what's troubling you today?",
        "ur": "نمستے، آج آپ کو کیا تکلیف ہے؟",
    },
    "do din se gale mein dard aur bukhar hai": {
        "en": "For two days I've had a sore throat and fever.",
        "ur": "دو دن سے گلے میں درد اور بخار ہے۔",
    },
    "kya khaansi ya saans ki takleef hai": {
        "en": "Do you have a cough or any breathing difficulty?",
        "ur": "کیا کھانسی یا سانس کی تکلیف ہے؟",
    },
    "nahi bas sir dard aur badan mein dard hai": {
        "en": "No, just a headache and body aches.",
        "ur": "نہیں، بس سر درد اور بدن میں درد ہے۔",
    },
    "main aapko acetaminophen 500 mg aur aaram ki salaah deti hoon": {
        "en": "I'm prescribing you acetaminophen 500 mg and advising rest.",
        "ur": "میں آپ کو ایسیٹامنوفین 500 ملی گرام اور آرام کی صلاح دے رہی ہوں۔",
    },
}


def _norm(text: str) -> str:
    return " ".join(_WORD.findall((text or "").lower()))


def apply_glossary(transcript: dict[str, Any]) -> None:
    for seg in transcript.get("segments") or []:
        translation = _DEMO_GLOSSARY.get(_norm(seg.get("text", "")))
        if translation:
            seg["text_en"] = translation["en"]
            seg["text_ur"] = translation["ur"]


def _apply_translations(transcript: dict[str, Any], translations: list[_SegmentTranslation]) -> None:
    segments = transcript.get("segments") or []
    for t in translations:
        if 0 <= t.index < len(segments):
            segments[t.index]["text_en"] = t.en
            segments[t.index]["text_ur"] = t.ur
            if t.speaker in ("Doctor", "Patient"):
                segments[t.index]["speaker"] = t.speaker


def _map_indices(result: list[_SegmentTranslation], indices: list[int]) -> list[_SegmentTranslation]:
    out: list[_SegmentTranslation] = []
    for t in result:
        if 0 <= t.index < len(indices):
            out.append(t.model_copy(update={"index": indices[t.index]}))
    return out


def _translate_chunk_sync(
    segments: list[dict],
    indices: list[int],
    settings: Settings,
) -> list[_SegmentTranslation]:
    """Translate one chunk of segments with Gemini. `indices` holds the global
    (transcript-wide) index of each segment, so the numbering in the prompt and
    the returned `index` values can be mapped back to the original transcript."""
    from google import genai

    joined = "\n".join(f"{j}. {seg.get('text', '')}" for j, seg in enumerate(segments))
    client = genai.Client(api_key=settings.gemini_api_key)
    interaction = client.interactions.create(
        model="gemini-3.6-flash",
        input=f"{_SYSTEM_INSTRUCTION}\n\nTranslate each numbered line:\n\n{joined}",
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": _TranslationResult.model_json_schema(),
        },
    )
    result = _TranslationResult.model_validate_json(interaction.output_text).segments
    return _map_indices(result, indices)


def _translate_chunk_sync_mistral(
    segments: list[dict],
    indices: list[int],
    settings: Settings,
) -> list[_SegmentTranslation]:
    """Mistral fallback translator used when Gemini is rate-limited/unavailable.

    Uses the same numbered-line prompt and parses the same `{"segments":[...]}`
    JSON shape, so the chunk index mapping is identical to the Gemini path.
    """
    from mistralai import Mistral

    joined = "\n".join(f"{j}. {seg.get('text', '')}" for j, seg in enumerate(segments))
    prompt = (
        f"{_SYSTEM_INSTRUCTION}\n\nTranslate each numbered line:\n\n{joined}"
        '\n\nRespond with ONLY JSON: {"segments":[{"index":0,"speaker":"Doctor","en":"...","ur":"..."}]}'
    )
    with Mistral(api_key=settings.mistral_api_key) as mistral:
        resp = mistral.chat.complete(
            model="mistral-small-latest",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
    result = _TranslationResult.model_validate_json(resp.choices[0].message.content).segments
    return _map_indices(result, indices)


async def _translate_chunk_with_retry(
    segments: list[dict],
    indices: list[int],
    settings: Settings,
    *,
    gemini_disabled: asyncio.Event,
) -> list[_SegmentTranslation]:
    """Translate one chunk: Gemini first, Mistral as instant failover.

    Gemini's free tier is often rate-limited; when it fails we immediately fall
    back to the Mistral chat API on the same key that drives transcription. No
    long retry sleeps. If both fail, the error bubbles up to the glossary fallback.
    `gemini_disabled` is a circuit breaker: once a 429 is observed, the remaining
    chunks skip Gemini entirely and go straight to Mistral.
    """
    if not gemini_disabled.is_set():
        try:
            return await asyncio.to_thread(_translate_chunk_sync, segments, indices, settings)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini unavailable for chunk %d — falling back to Mistral: %.120s", indices[0], exc)
            if "429" in str(exc):
                gemini_disabled.set()
    try:
        return await asyncio.to_thread(_translate_chunk_sync_mistral, segments, indices, settings)
    except Exception as exc:  # noqa: BLE001
        raise exc


# Chunks are translated concurrently, but bounded: firing every Gemini call at
# once trips the free-tier per-minute quota (429). A small semaphore keeps the
# pipeline faster than sequential while staying under the rate limit; once the
# circuit breaker flips (Gemini quota exhausted) the chunks still flow at this
# concurrency through Mistral, which has no such quota.
_TRANSLATION_CONCURRENCY = asyncio.Semaphore(6)



async def translate_transcript(
    transcript: dict[str, Any],
    settings: Settings | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Add `text_en` / `text_ur` and correct `speaker` labels to every transcript
    segment (in place).

    Uses Gemini when a key is configured; otherwise (and on any Gemini failure)
    falls back to the built-in demo glossary so the feature works offline. Live
    transcripts that aren't in the glossary keep only their original text, and the
    frontend falls back to that. Long transcripts are translated in concurrent
    chunks (each chunk keeps its own Gemini→Mistral failover) so large reports
    don't pay the cost of sequential round-trips. With `force=True` every segment
    is re-annotated, overwriting prior labels.
    """
    settings = settings or _settings
    segments = transcript.get("segments") or []
    if not settings.gemini_api_key or not segments:
        apply_glossary(transcript)
        return transcript
    if force:
        for seg in segments:
            seg.pop("text_en", None)
            seg.pop("text_ur", None)
            seg.pop("speaker", None)
    missing = [
        (i, seg)
        for i, seg in enumerate(segments)
        if not (seg.get("text_en") and seg.get("text_ur"))
        or seg.get("speaker") not in ("Doctor", "Patient")
    ]
    if not missing:
        return transcript
    # Glossary-first fast path: if every missing segment is a known demo phrase,
    # translate instantly without spending Gemini quota.
    if all(_norm(seg.get("text", "")) in _DEMO_GLOSSARY for _, seg in missing):
        apply_glossary(transcript)
        return transcript
    try:
        batches = [
            missing[start : start + _CHUNK_SIZE]
            for start in range(0, len(missing), _CHUNK_SIZE)
        ]

        gemini_disabled = asyncio.Event()

        async def _run_batch(batch: list[tuple[int, dict]]) -> list[_SegmentTranslation]:
            async with _TRANSLATION_CONCURRENCY:
                return await _translate_chunk_with_retry(
                    [seg for _, seg in batch], [i for i, _ in batch], settings,
                    gemini_disabled=gemini_disabled,
                )

        # Translate chunks concurrently, bounded by a small semaphore so we get a
        # speedup over sequential without tripping Gemini's free-tier quota (429).
        results = await asyncio.gather(*[_run_batch(batch) for batch in batches])
        for chunk_translations in results:
            _apply_translations(transcript, chunk_translations)
    except Exception:
        logger.exception("Gemini translation failed — using glossary fallback")
        apply_glossary(transcript)
    return transcript
