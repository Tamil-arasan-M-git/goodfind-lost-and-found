"""Safe local storage for report photographs in development deployments."""

import os
import uuid
from pathlib import Path

from detection import ALLOWED_CONTENT_TYPES, MAX_IMAGE_BYTES, InvalidImageError, validate_image


def _storage_root() -> Path:
    root = Path(os.getenv("ITEM_IMAGE_STORAGE_DIR", "item-images")).resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root


def save_report_image(image_bytes: bytes, content_type: str | None) -> dict:
    """Validate decoded bytes and persist under an opaque, server-generated name."""
    validate_image(image_bytes, content_type)
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise InvalidImageError("Image must be 5 MB or smaller")
    extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[content_type]
    filename = f"{uuid.uuid4().hex}{extension}"
    destination = _storage_root() / filename
    destination.write_bytes(image_bytes)
    return {"storage_key": filename, "content_type": content_type, "size": len(image_bytes)}


def get_report_image(storage_key: str) -> Path:
    """Resolve an opaque stored key without allowing traversal outside storage."""
    if not storage_key or Path(storage_key).name != storage_key:
        raise FileNotFoundError("Image not found")
    candidate = (_storage_root() / storage_key).resolve()
    if candidate.parent != _storage_root() or not candidate.is_file():
        raise FileNotFoundError("Image not found")
    return candidate
