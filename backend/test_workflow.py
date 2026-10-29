import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from PIL import Image

import email_service
import main
import storage


class FakeUpload:
    def __init__(self, payload=b"image", content_type="image/png"):
        self.payload = payload
        self.content_type = content_type
        self.closed = False

    async def read(self, size=-1):
        if size < 0:
            return self.payload
        chunk, self.payload = self.payload[:size], self.payload[size:]
        return chunk

    async def close(self):
        self.closed = True


class PersistentPhotoTests(unittest.TestCase):
    def _png(self):
        output = io.BytesIO()
        Image.new("RGB", (2, 2), "green").save(output, format="PNG")
        return output.getvalue()

    def _run(self, coroutine):
        try:
            coroutine.send(None)
        except StopIteration as result:
            return result.value

    def test_validated_photo_survives_new_lookup(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory, patch.dict(os.environ, {"ITEM_IMAGE_STORAGE_DIR": directory}):
            saved = storage.save_report_image(self._png(), "image/png")
            self.assertEqual(saved["content_type"], "image/png")
            restored = storage.get_report_image(saved["storage_key"])
            self.assertEqual(restored.parent, Path(directory).resolve())
            self.assertTrue(restored.is_file())

    def test_traversal_key_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory, patch.dict(os.environ, {"ITEM_IMAGE_STORAGE_DIR": directory}):
            with self.assertRaises(FileNotFoundError):
                storage.get_report_image("../secret.png")

    def test_image_upload_checks_owner_before_writing(self):
        upload = FakeUpload()
        with patch("main.ensure_item_image_upload_allowed", side_effect=PermissionError("not owner")), \
             patch("main.read_upload_limited") as reader, \
             patch("main.save_report_image") as saver:
            with self.assertRaises(Exception) as error:
                main.upload_item_image(7, upload, user_id=99).send(None)
        self.assertEqual(error.exception.status_code, 403)
        reader.assert_not_called()
        saver.assert_not_called()
        self.assertTrue(upload.closed)

    def test_failed_attachment_removes_only_new_image(self):
        upload = FakeUpload()
        saved = {"storage_key": "new-key.png", "content_type": "image/png", "size": 5}
        with patch("main.ensure_item_image_upload_allowed"), \
             patch("main.read_upload_limited", new_callable=AsyncMock, return_value=b"image"), \
             patch("main.save_report_image", return_value=saved), \
             patch("main.attach_item_image", side_effect=RuntimeError("database unavailable")), \
             patch("main.get_report_image") as resolve:
            with self.assertRaises(RuntimeError):
                main.upload_item_image(7, upload, user_id=99).send(None)
        resolve.return_value.unlink.assert_called_once_with(missing_ok=True)
        self.assertTrue(upload.closed)

    def test_successful_replacement_removes_previous_image_after_commit(self):
        upload = FakeUpload()
        saved = {"storage_key": "new-key.png", "content_type": "image/png", "size": 5}
        attached = {"item_id": 7, "image_url": "/api/items/7/image", "content_type": "image/png", "size": 5,
                    "_previous_storage_key": "old-key.png"}
        with patch("main.ensure_item_image_upload_allowed"), \
             patch("main.read_upload_limited", new_callable=AsyncMock, return_value=b"image"), \
             patch("main.save_report_image", return_value=saved), \
             patch("main.attach_item_image", return_value=attached), \
             patch("main.image_storage_key_is_referenced", return_value=False), \
             patch("main.get_report_image") as resolve:
            result = self._run(main.upload_item_image(7, upload, user_id=99))
        self.assertNotIn("_previous_storage_key", result["image"])
        resolve.assert_called_once_with("old-key.png")
        resolve.return_value.unlink.assert_called_once_with(missing_ok=True)

    def test_replacement_tolerates_missing_previous_image(self):
        upload = FakeUpload()
        saved = {"storage_key": "new-key.png", "content_type": "image/png", "size": 5}
        attached = {"item_id": 7, "image_url": "/api/items/7/image", "content_type": "image/png", "size": 5,
                    "_previous_storage_key": "old-key.png"}
        with patch("main.ensure_item_image_upload_allowed"), \
             patch("main.read_upload_limited", new_callable=AsyncMock, return_value=b"image"), \
             patch("main.save_report_image", return_value=saved), \
             patch("main.attach_item_image", return_value=attached), \
             patch("main.image_storage_key_is_referenced", return_value=False), \
             patch("main.get_report_image", side_effect=FileNotFoundError):
            result = self._run(main.upload_item_image(7, upload, user_id=99))
        self.assertEqual(result["image"]["item_id"], 7)

    def test_replacement_preserves_a_key_still_referenced_by_another_item(self):
        upload = FakeUpload()
        saved = {"storage_key": "new-key.png", "content_type": "image/png", "size": 5}
        attached = {"item_id": 7, "image_url": "/api/items/7/image", "content_type": "image/png", "size": 5,
                    "_previous_storage_key": "shared-key.png"}
        with patch("main.ensure_item_image_upload_allowed"), \
             patch("main.read_upload_limited", new_callable=AsyncMock, return_value=b"image"), \
             patch("main.save_report_image", return_value=saved), \
             patch("main.attach_item_image", return_value=attached), \
             patch("main.image_storage_key_is_referenced", return_value=True), \
             patch("main.get_report_image") as resolve:
            self._run(main.upload_item_image(7, upload, user_id=99))
        resolve.assert_not_called()


class EmailConfigurationTests(unittest.TestCase):
    def test_missing_smtp_configuration_does_not_claim_delivery(self):
        with patch.dict(os.environ, {"SMTP_HOST": "", "SMTP_FROM": ""}, clear=False):
            self.assertFalse(email_service.send_workflow_email(1, "subject", "body"))


if __name__ == "__main__":
    unittest.main()
