from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings

_settings = get_settings()

BUCKET_NAME = "consultation-audio"
MEDIA_DIR = Path(__file__).resolve().parent.parent.parent / "media"


def _save_local(file_bytes: bytes, filename: str) -> Path:
    """Persist audio bytes under the local media dir and return the file path."""
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    object_name = f"{uuid4()}.{filename.rsplit('.', 1)[-1] if '.' in filename else 'webm'}"
    path = MEDIA_DIR / object_name
    path.write_bytes(file_bytes)
    return path


def upload_audio_placeholder(file_bytes: bytes, filename: str) -> str:
    """Store a consultation audio file and return a URL the browser can play.

    Primary path: save the file locally under ``media/`` and expose it via the
    ``/media`` static mount (returns a relative ``/media/...`` URL — the frontend
    prefixes it with the API origin). If Supabase Storage is configured we attempt
    a real upload and use the public URL instead; on any failure we fall back to
    the local copy so the demo still works.
    """
    if file_bytes:
        local_path = _save_local(file_bytes, filename)
        local_url = f"/media/{local_path.name}"
    else:
        local_path = None
        local_url = ""

    if _settings.supabase_url and _settings.supabase_service_key:
        try:
            from supabase import create_client

            ext = filename.rsplit(".", 1)[-1] if "." in filename else "webm"
            object_name = f"{uuid4()}.{ext}"
            client = create_client(_settings.supabase_url, _settings.supabase_service_key)
            client.storage.from_(BUCKET_NAME).upload(
                path=object_name,
                file=file_bytes,
                file_options={"content-type": f"audio/{ext}"},
            )
            return str(client.storage.from_(BUCKET_NAME).get_public_url(object_name))
        except Exception:
            # Fall through to the local copy so the demo still works.
            pass
    return local_url
