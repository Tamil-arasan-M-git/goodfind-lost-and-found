import unittest

import main
from pydantic import ValidationError


def run_coroutine(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value


class RequestValidationTests(unittest.TestCase):
    def _run_limited_request(self, content_type, chunks, content_length=None):
        events = [
            {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
            for index, chunk in enumerate(chunks)
        ]
        scope = {
            "type": "http",
            "headers": [(b"content-type", content_type.encode())]
            + ([(b"content-length", content_length.encode())] if content_length is not None else []),
        }
        downstream = {"called": False, "body": b""}

        async def receive():
            return events.pop(0) if events else {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.start":
                downstream["status"] = message["status"]
            elif message["type"] == "http.response.body":
                downstream["body"] += message.get("body", b"")

        async def app(scope, receive, send):
            downstream["called"] = True
            while True:
                event = await receive()
                if event["type"] != "http.request":
                    break
                downstream["body"] += event.get("body", b"")
                if not event.get("more_body"):
                    break

        middleware = main.RequestBodyLimitMiddleware(app)
        run_coroutine(middleware(scope, receive, send))
        return downstream

    def test_valid_registration_item_update_and_message_inputs(self):
        registration = main.RegisterRequest(name="A", email="a@example.com", password="secret")
        item = main.LostItemRequest(
            item_name="Wallet", category="Accessories", item_date="2026-10-27", location="Library"
        )
        update = main.ItemUpdateRequest(
            item_name="Updated wallet", category="Accessories", item_date="2026-10-27", location="Library"
        )
        message = main.MessageCreate(content="Please describe a safe handover location.")
        self.assertEqual(registration.name, "A")
        self.assertEqual(item.item_name, "Wallet")
        self.assertEqual(update.item_name, "Updated wallet")
        self.assertTrue(message.content)

    def test_schema_aligned_boundaries_are_accepted(self):
        main.RegisterRequest(name="n" * 100, email="a@example.com", password="p" * 128)
        main.LostItemRequest(
            item_name="i" * 200,
            category="c" * 100,
            description="d" * 5000,
            item_date="2026-10-27",
            location="l" * 255,
        )
        main.MessageCreate(content="m" * 2000)

    def test_oversized_fields_are_validation_errors(self):
        with self.assertRaises(ValidationError):
            main.RegisterRequest(name="n", email="a@example.com", password="p" * 129)
        with self.assertRaises(ValidationError):
            main.LostItemRequest(
                item_name="i" * 201,
                category="c",
                item_date="2026-10-27",
                location="l",
            )
        with self.assertRaises(ValidationError):
            main.ItemUpdateRequest(
                item_name="i",
                category="c",
                item_date="2026-10-27",
                location="l",
                description="d" * 5001,
            )
        with self.assertRaises(ValidationError):
            main.MessageCreate(content="m" * 2001)

    def test_json_body_below_limit_replays_multichunk_body(self):
        body = [b'{"name":', b'"value"}']
        result = self._run_limited_request("application/json", body)
        self.assertTrue(result["called"])
        self.assertEqual(result["body"], b''.join(body))

    def test_json_body_above_limit_is_rejected_without_downstream_parsing(self):
        result = self._run_limited_request(
            "application/json", [b"x" * (main.MAX_JSON_BODY_BYTES - 1), b"xx"]
        )
        self.assertFalse(result["called"])
        self.assertEqual(result["status"], 413)

    def test_multipart_body_below_limit_replays_without_content_length(self):
        body = [b"--boundary\r\n", b"content\r\n--boundary--\r\n"]
        result = self._run_limited_request("multipart/form-data; boundary=boundary", body)
        self.assertTrue(result["called"])
        self.assertEqual(result["body"], b''.join(body))

    def test_multipart_body_above_limit_is_rejected(self):
        result = self._run_limited_request(
            "multipart/form-data; boundary=boundary",
            [b"x" * main.MAX_MULTIPART_BODY_BYTES, b"x"],
        )
        self.assertFalse(result["called"])
        self.assertEqual(result["status"], 413)

    def test_invalid_content_length_does_not_bypass_actual_count(self):
        result = self._run_limited_request(
            "application/json",
            [b"x" * main.MAX_JSON_BODY_BYTES, b"x"],
            content_length="not-a-number",
        )
        self.assertFalse(result["called"])
        self.assertEqual(result["status"], 413)


if __name__ == "__main__":
    unittest.main()
