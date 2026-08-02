from __future__ import annotations

import copy

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, run_async
from app.models.report import Report
from app.services.transcription import classify_speaker
from app.services.translation import translate_transcript


async def backfill_translations() -> int:
    """Re-annotate every report's transcript with speaker labels + translations.

    Runs the same `translate_transcript` the generate pipeline uses (Gemini with
    an offline glossary fallback), so reports created before the bilingual
    transcript feature get English + Urdu translations too. `force=True`
    re-labels every segment's `speaker` from content (old reports carry wrong
    labels — the first-speaker-is-Doctor heuristic — or no labels at all). Any
    segment still unlabelled after the LLM pass is assigned by the offline
    content classifier as a final safety net.
    """
    updated = 0
    async with AsyncSessionLocal() as db:
        reports = (await db.scalars(select(Report))).all()
        for report in reports:
            tx = report.transcript_json or {}
            segments = tx.get("segments") or []
            if not segments:
                continue
            speakers = {s.get("speaker") for s in segments}
            if all(
                s.get("text_en") and s.get("text_ur") and s.get("speaker") in ("Doctor", "Patient")
                for s in segments
            ) and (len(segments) == 1 or len(speakers) >= 2):
                continue

            fresh = copy.deepcopy(tx)
            await translate_transcript(fresh, force=True)
            new_segments = fresh.get("segments") or []
            for seg in new_segments:
                if seg.get("speaker") not in ("Doctor", "Patient"):
                    seg["speaker"] = classify_speaker(seg.get("text", "")) or "Patient"
            translated = sum(1 for s in new_segments if s.get("text_en") and s.get("text_ur"))
            if translated:
                report.transcript_json = fresh
                updated += 1
            print(
                f"report {report.id} · {report.status} · "
                f"translated {translated}/{len(new_segments)}"
            )
        await db.commit()
    return updated


if __name__ == "__main__":
    n = run_async(backfill_translations())
    print(f"Backfill complete: {n} report(s) updated.")
