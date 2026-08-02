from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import UPLOADS_DIR

_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB

_SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]")


def save_avatar(file: UploadFile, owner_id: str) -> str:
    """Persist an uploaded profile photo and return its public /uploads/ URL.

    The filename is namespaced by the owner's id so re-uploads replace cleanly
    and two users can never collide.
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_EXT:
        raise ValueError("Only JPG, PNG, WEBP or GIF images are allowed")

    data = file.file.read()
    if len(data) > _MAX_BYTES:
        raise ValueError("Image is too large — max 5 MB")

    safe_id = _SAFE_NAME.sub("_", str(owner_id))
    filename = f"avatar_{safe_id}_{uuid.uuid4().hex[:8]}{ext}"
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    target = UPLOADS_DIR / filename
    target.write_bytes(data)
    return f"/uploads/{filename}"
