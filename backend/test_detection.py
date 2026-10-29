import io
import unittest
from unittest.mock import patch

from PIL import Image

import detection
import main
from matching import calculate_match_score
from security import get_current_user_id


def png_bytes():
    output = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(output, format="PNG")
    return output.getvalue()


class FakeTensor:
    def __init__(self, value): self.value = value
    def item(self): return self.value
    def tolist(self): return self.value


class FakeBox:
    cls = [FakeTensor(0)]
    conf = [FakeTensor(0.91)]
    xyxy = [FakeTensor([1, 2, 5, 6])]


class FakeResult:
    names = {0: "keys"}
    boxes = [FakeBox()]


class FakeModel:
    def __call__(self, image, conf, verbose): return [FakeResult()]


class FakeUpload:
    def __init__(self, payload, content_type):
        self.payload, self.content_type, self.closed = payload, content_type, False
    async def read(self, size=-1):
        if size < 0:
            return self.payload
        chunk, self.payload = self.payload[:size], self.payload[size:]
        return chunk
    async def close(self): self.closed = True


class DetectionTests(unittest.TestCase):
    def test_incremental_upload_reader_rejects_oversized_body(self):
        upload = FakeUpload(b"x" * 11, "image/png")
        with self.assertRaisesRegex(detection.InvalidImageError, "5 MB"):
            detection.read_upload_limited(upload, max_bytes=10).send(None)

    def test_dimension_limit_rejects_large_image(self):
        with patch("detection.Image.open") as image_open:
            image_open.return_value.size = (detection.MAX_IMAGE_DIMENSION + 1, 1)
            with self.assertRaisesRegex(detection.InvalidImageError, "dimensions"):
                detection.validate_image(b"image", "image/png")

    def test_successful_detection_returns_label_confidence_and_box(self):
        with patch("detection._load_model", return_value=FakeModel()):
            result = detection.detect_image(png_bytes(), "image/png")
        self.assertEqual(result, [{"label": "keys", "confidence": 0.91,
                                  "box": {"x1": 1.0, "y1": 2.0, "x2": 5.0, "y2": 6.0}}])

    def test_invalid_image_is_rejected(self):
        with self.assertRaises(detection.InvalidImageError):
            detection.detect_image(b"not an image", "image/png")

    def test_unsupported_type_is_rejected(self):
        with self.assertRaises(detection.InvalidImageError):
            detection.detect_image(png_bytes(), "image/gif")

    def test_oversized_image_is_rejected(self):
        with self.assertRaises(detection.InvalidImageError):
            detection.detect_image(b"0" * (detection.MAX_IMAGE_BYTES + 1), "image/png")

    def test_inference_failure_is_safe(self):
        with patch("detection._load_model", side_effect=RuntimeError("weights missing")):
            with self.assertRaises(detection.DetectionUnavailableError):
                detection.detect_image(png_bytes(), "image/png")

    def test_route_maps_inference_failure_to_service_unavailable(self):
        upload = FakeUpload(png_bytes(), "image/png")
        with patch("main.detect_image", side_effect=detection.DetectionUnavailableError("offline")):
            with self.assertRaises(Exception) as error:
                # This coroutine only awaits the in-memory upload helpers in this
                # unit test. Advancing it directly avoids creating a Windows
                # Proactor event loop, which can require a socketpair even though
                # no network or asynchronous I/O is exercised here.
                main.detect_objects_api(upload, user_id=1).send(None)
        self.assertEqual(error.exception.status_code, 503)
        self.assertTrue(upload.closed)

    def test_detection_route_rejects_oversized_body_before_inference(self):
        upload = FakeUpload(b"x" * (detection.MAX_IMAGE_BYTES + 1), "image/png")
        with patch("main.detect_image") as detector:
            with self.assertRaises(Exception) as error:
                main.detect_objects_api(upload, user_id=1).send(None)
        self.assertEqual(error.exception.status_code, 422)
        detector.assert_not_called()
        self.assertTrue(upload.closed)

    def test_unauthenticated_detection_request_is_rejected(self):
        route = next(route for route in main.app.routes if route.path == "/api/detections")
        self.assertIn(
            get_current_user_id,
            [dependency.call for dependency in route.dependant.dependencies],
        )
        with self.assertRaises(Exception) as error:
            get_current_user_id(None)
        self.assertEqual(error.exception.status_code, 401)

    def test_labels_are_only_a_small_matching_signal(self):
        base = {
            "item_name": "blue bag", "category": "accessories", "description": "canvas",
            "location": "library", "item_date": "2026-10-20",
        }
        without_labels = calculate_match_score({**base, "detection_labels": []}, {**base, "detection_labels": []})
        with_labels = calculate_match_score({**base, "detection_labels": ["backpack"]}, {**base, "detection_labels": ["backpack"]})
        self.assertEqual(with_labels - without_labels, 5)


if __name__ == "__main__":
    unittest.main()
