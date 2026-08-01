from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from httpx import AsyncClient, Timeout


async def _probe(url: str, **kwargs: Any) -> int | None:
    """Return HTTP status code, or None if the host is unreachable/timeout."""
    async with AsyncClient(timeout=Timeout(5.0)) as client:
        try:
            resp = await client.get(url, **kwargs)
            return resp.status_code
        except Exception:
            return None


async def check_integrations() -> dict[str, Any]:
    """Live check of every integration the pipeline relies on.

    Each entry reports whether the credential is configured and whether the
    upstream is actually reachable right now. DB and external probes are real
    network calls with a short timeout; Gemini is reported as configured-only
    because probing it requires a billed generation call.
    """
    from sqlalchemy import text

    from app.core.config import get_settings
    from app.core.database import engine

    settings = get_settings()

    database: dict[str, Any] = {"configured": True, "status": "ok", "detail": "Connected"}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        database = {
            "configured": True,
            "status": "error",
            "detail": f"{type(exc).__name__}: {exc}"[:120],
        }

    mistral: dict[str, Any]
    if settings.mistral_api_key:
        code = await _probe(
            "https://api.mistral.ai/v1/models",
            headers={"Authorization": f"Bearer {settings.mistral_api_key}"},
        )
        if code == 200:
            mistral = {"configured": True, "status": "ok", "detail": "Key valid"}
        elif code is None:
            mistral = {"configured": True, "status": "error", "detail": "Unreachable"}
        else:
            mistral = {"configured": True, "status": "error", "detail": f"HTTP {code}"}
    else:
        mistral = {"configured": False, "status": "unconfigured", "detail": "MISTRAL_API_KEY not set"}

    gemini: dict[str, Any]
    if settings.gemini_api_key:
        gemini = {"configured": True, "status": "ok", "detail": "GEMINI_API_KEY present"}
    else:
        gemini = {"configured": False, "status": "unconfigured", "detail": "GEMINI_API_KEY not set"}

    supabase: dict[str, Any]
    if settings.supabase_url and settings.supabase_service_key:
        supabase = {
            "configured": True,
            "status": "ok",
            "detail": "URL + service key present",
        }
    else:
        supabase = {
            "configured": False,
            "status": "unconfigured",
            "detail": "Supabase URL/service key not set",
        }

    rxnorm: dict[str, Any]
    code = await _probe("https://rxnav.nlm.nih.gov/REST/drugs", params={"name": "aspirin"})
    if code == 200:
        rxnorm = {"configured": True, "status": "ok", "detail": "Reachable"}
    elif code is None:
        rxnorm = {"configured": True, "status": "error", "detail": "Unreachable"}
    else:
        rxnorm = {"configured": True, "status": "error", "detail": f"HTTP {code}"}

    return {
        "database": database,
        "mistral": mistral,
        "gemini": gemini,
        "supabase": supabase,
        "rxnorm": rxnorm,
        "checked_at": datetime.now(UTC),
    }
