from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FALLBACK_PATH = PROJECT_ROOT / "data" / "medications_fallback.json"

RXNORM_BASE = "https://rxnav.nlm.nih.gov/REST"


def _load_fallback() -> dict:
    if FALLBACK_PATH.exists():
        with open(FALLBACK_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_fallback(data: dict) -> None:
    FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FALLBACK_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _normalize_name(name: str) -> str:
    return name.strip().lower().rstrip(".")


async def _rxnorm_lookup(name: str) -> dict | None:
    normalized = _normalize_name(name)
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(
                f"{RXNORM_BASE}/approximateTerm.json",
                params={"term": normalized, "maxEntries": 1},
            )
            response.raise_for_status()
            data = response.json()
            candidates = (
                data.get("approximateGroup", {})
                .get("candidate", [])
            )
            if candidates:
                return {
                    "name": name,
                    "normalized": normalized,
                    "rxnorm_match": candidates[0].get("name"),
                    "rxcui": candidates[0].get("rxcui"),
                    "score": candidates[0].get("score"),
                    "validated": True,
                    "source": "rxnorm",
                }
        except Exception:
            pass
    return None


_VAGUE_PATTERNS = ("unspecified", "unknown", "not stated", "not mentioned", "not captured")

_RXNORM_CONCURRENCY = 4
_rxnorm_semaphore = asyncio.Semaphore(_RXNORM_CONCURRENCY)


async def _lookup_with_semaphore(name: str) -> dict | None:
    async with _rxnorm_semaphore:
        return await _rxnorm_lookup(name)


def _is_vague_name(name: str) -> bool:
    lower = name.lower()
    return any(p in lower for p in _VAGUE_PATTERNS)


async def validate_medications(medications: list[dict]) -> list[dict]:
    """Validate a list of medication dicts against RxNorm, falling back to local JSON.

    Returns a list of dicts with keys: medication, status, note — compatible
    with the frontend's Record<string, string>[] validation_flags type.
    All RxNorm lookups run concurrently so N medications cost ~one lookup
    instead of N sequential round-trips.
    """
    fallback = _load_fallback()
    results: list[dict] = []

    names = [med.get("name", "") for med in medications]
    lookups = await asyncio.gather(*(_lookup_with_semaphore(name) for name in names if name))

    by_name: dict[str, dict | None] = {}
    it = iter(lookups)
    for name in names:
        if name:
            by_name[name] = next(it)

    for med in medications:
        name = med.get("name", "")
        if not name:
            results.append({"medication": str(med), "status": "unrecognized", "note": "Missing medication name"})
            continue

        if _is_vague_name(name):
            results.append({
                "medication": med,
                "name": name,
                "normalized": _normalize_name(name),
                "validated": False,
                "source": "none",
                "reason": "Medication name not explicitly stated in transcript — physician must fill in",
            })
            continue

        rx_result = by_name.get(name)
        if rx_result:
            results.append({"medication": name, "status": "valid", "note": f"RxNorm: {rx_result.get('rxnorm_match', '')}"})
            continue

        normalized = _normalize_name(name)
        if normalized in fallback:
            results.append({
                "medication": name,
                "status": "valid" if fallback[normalized].get("validated", True) else "warning",
                "note": fallback[normalized].get("notes", "Local fallback match"),
            })
        else:
            results.append({"medication": name, "status": "unrecognized", "note": "Not found in RxNorm or local fallback"})

    return results


def seed_fallback_entry(name: str, validated: bool = True, notes: str = "") -> None:
    fallback = _load_fallback()
    fallback[_normalize_name(name)] = {"validated": validated, "notes": notes}
    _save_fallback(fallback)
