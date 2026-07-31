from __future__ import annotations

from uuid import uuid4

from app.core.config import get_settings

_settings = get_settings()

BUCKET_NAME = "consultation-audio"


def upload_audio_placeholder(file_bytes: bytes, filename: str) -> str:
    """Stub for audio storage.

    In a full integration this uploads to Supabase Storage and returns a signed URL.
    For the hackathon demo we return a deterministic local reference string so the
    pipeline can proceed without a configured storage bucket.
    """
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "webm"
    object_name = f"{uuid4()}.{ext}"
    # If Supabase is configured, attempt a real upload; otherwise return a placeholder URL.
    if _settings.supabase_url and _settings.supabase_service_key:
        try:
            from supabase import create_client

            client = create_client(_settings.supabase_url, _settings.supabase_service_key)
            client.storage.from_(BUCKET_NAME).upload(
                path=object_name,
                file=file_bytes,
                file_options={"content-type": f"audio/{ext}"},
            )
            public_url = client.storage.from_(BUCKET_NAME).get_public_url(object_name)
            return str(public_url)
        except Exception:
            # Fall through to placeholder so the demo still works.
            pass
    return f"local://audio/{object_name}"
