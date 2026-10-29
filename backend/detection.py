"""Memory-only detection using GoodFind's bundled custom YOLO model."""

import io
import os
import threading
from pathlib import Path

from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
MAX_IMAGE_DIMENSION = 10_000
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
DEFAULT_CONFIDENCE = 0.35
EXPECTED_LABELS = frozenset({"mobile_phone", "backpack_bag", "keys", "wallet_purse", "water_bottle"})


class InvalidImageError(ValueError):
    pass


class DetectionUnavailableError(RuntimeError):
    pass


async def read_upload_limited(upload, max_bytes=MAX_IMAGE_BYTES):
    """Read at most one byte beyond the limit, rejecting oversized bodies early."""
    image_bytes = await upload.read(max_bytes + 1)
    if len(image_bytes) > max_bytes:
        raise InvalidImageError("Image must be 5 MB or smaller")
    return image_bytes


_model = None
_model_lock = threading.Lock()


def get_model_path() -> Path:
    """Return the explicitly configured model path, defaulting to bundled weights."""
    configured_path = os.getenv("YOLO_MODEL_PATH")
    path = Path(configured_path) if configured_path else Path(__file__).with_name("goodfind_best.pt")
    return path.expanduser().resolve()


def _load_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                try:
                    from ultralytics import YOLO
                    model_path = get_model_path()
                    if not model_path.is_file():
                        raise FileNotFoundError(f"Custom GoodFind model was not found at {model_path}")
                    model = YOLO(str(model_path))
                    model_labels = {str(label) for label in model.names.values()}
                    if model_labels != EXPECTED_LABELS:
                        raise ValueError("Custom model labels do not match the GoodFind detection mapping")
                    _model = model
                except Exception as error:
                    raise DetectionUnavailableError(
                        "The GoodFind custom object-detection model is unavailable. "
                        "Verify YOLO_MODEL_PATH or backend/goodfind_best.pt."
                    ) from error
    return _model


def validate_image(image_bytes: bytes, content_type: str | None):
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise InvalidImageError("Supported image types are JPEG, PNG, and WebP")
    if not image_bytes:
        raise InvalidImageError("Image file is empty")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise InvalidImageError("Image must be 5 MB or smaller")
    try:
        image = Image.open(io.BytesIO(image_bytes))
        width, height = image.size
        if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION or width * height > MAX_IMAGE_PIXELS:
            raise InvalidImageError("Image dimensions are too large")
        image.verify()
        image = Image.open(io.BytesIO(image_bytes))
        image.load()
        return image.convert("RGB")
    except InvalidImageError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as error:
        raise InvalidImageError("Uploaded file is not a valid image") from error


def detect_image(image_bytes: bytes, content_type: str | None, confidence=DEFAULT_CONFIDENCE):
    image = validate_image(image_bytes, content_type)
    try:
        result = _load_model()(image, conf=confidence, verbose=False)[0]
        names = result.names
        detections = []
        for box in result.boxes:
            class_id = int(box.cls[0].item())
            label = str(names[class_id])
            if label not in EXPECTED_LABELS:
                continue
            x1, y1, x2, y2 = (round(float(value), 2) for value in box.xyxy[0].tolist())
            detections.append({
                "label": label,
                "confidence": round(float(box.conf[0].item()), 4),
                "box": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
            })
        return detections
    except DetectionUnavailableError:
        raise
    except Exception as error:
        raise DetectionUnavailableError("Object detection could not process this image") from error
