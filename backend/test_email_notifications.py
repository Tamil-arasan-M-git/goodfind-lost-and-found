import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi import BackgroundTasks

import email_notifications
import main


class EmailNotificationTests(unittest.TestCase):
    def setUp(self):
        email_notifications._recent_events.clear()
        self.environment = {
            "EMAIL_NOTIFICATIONS_ENABLED": "true",
            "SMTP_HOST": "smtp.gmail.com",
            "SMTP_PORT": "587",
            "SMTP_USERNAME": "sender@example.com",
            "SMTP_APP_PASSWORD": "app-password-only-for-test",
            "EMAIL_FROM": "GoodFind <sender@example.com>",
            "FRONTEND_BASE_URL": "https://goodfind.example",
            "EMAIL_MESSAGE_COOLDOWN_SECONDS": "300",
        }

    @patch("email_notifications._email_for_user", return_value="recipient@example.com")
    @patch("email_notifications.smtplib.SMTP")
    def test_gmail_uses_tls_app_password_and_sender(self, smtp, _email):
        client = smtp.return_value.__enter__.return_value
        with patch.dict(os.environ, self.environment, clear=False):
            self.assertTrue(email_notifications.send_chat_request_email(7, "Wallet"))
        smtp.assert_called_once_with("smtp.gmail.com", 587, timeout=10)
        client.starttls.assert_called_once()
        client.login.assert_called_once_with("sender@example.com", "app-password-only-for-test")
        sent = client.send_message.call_args.args[0]
        self.assertEqual(sent["From"], "GoodFind <sender@example.com>")
        self.assertEqual(sent["To"], "recipient@example.com")
        self.assertIn("/messages", sent.get_content())
        self.assertNotIn("app-password-only-for-test", sent.get_content())

    def test_missing_or_disabled_configuration_does_not_access_database(self):
        with patch("email_notifications._email_for_user") as lookup, patch.dict(os.environ, {"EMAIL_NOTIFICATIONS_ENABLED": "false"}, clear=False):
            self.assertFalse(email_notifications.send_new_message_email(7, 42))
        lookup.assert_not_called()

    @patch("email_notifications._email_for_user", return_value="recipient@example.com")
    @patch("email_notifications.smtplib.SMTP", side_effect=OSError("not available"))
    def test_smtp_failure_is_non_fatal_and_sanitized(self, _smtp, _email):
        with patch.dict(os.environ, self.environment, clear=False):
            self.assertFalse(email_notifications.send_claim_decision_email(7, "ACCEPTED"))

    @patch("email_notifications._email_for_user", return_value="recipient@example.com")
    @patch("email_notifications.smtplib.SMTP")
    def test_message_cooldown_suppresses_repeated_alerts(self, smtp, _email):
        with patch.dict(os.environ, self.environment, clear=False):
            self.assertTrue(email_notifications.send_new_message_email(7, 42))
            self.assertFalse(email_notifications.send_new_message_email(7, 42))
        self.assertEqual(smtp.call_count, 1)

    @patch("main.create_chat_request")
    @patch("main.send_chat_request_email")
    def test_new_chat_request_queues_only_recipient_email_once(self, sender, create_request):
        create_request.return_value = {
            "request_id": 5, "recipient_user_id": 20, "_notify_recipient": True,
            "_email_item_name": "Wallet",
        }
        tasks = BackgroundTasks()
        result = main.create_chat_request_api(main.ChatRequestCreate(match_id=3), tasks, user_id=10)
        self.assertEqual(result["request"]["recipient_user_id"], 20)
        self.assertEqual(len(tasks.tasks), 1)
        self.assertIs(tasks.tasks[0].func, sender)
        self.assertEqual(tasks.tasks[0].args, (20, "Wallet"))

    @patch("main.send_new_message_email")
    @patch("main.send_message")
    def test_persisted_message_queues_only_other_participant(self, send_message, sender):
        send_message.return_value = {"message_id": 9, "content": "hello", "_notify_recipient_user_id": 20}
        tasks = BackgroundTasks()
        result = main.send_message_api(42, main.MessageCreate(content="hello"), tasks, user_id=10)
        self.assertNotIn("_notify_recipient_user_id", result["message"])
        self.assertEqual(tasks.tasks[0].args, (20, 42))

    @patch("main.send_new_message_email")
    @patch("main.send_message", side_effect=ValueError("This conversation is closed"))
    def test_failed_or_closed_message_does_not_queue_email(self, _send_message, sender):
        with self.assertRaises(Exception):
            main.send_message_api(42, main.MessageCreate(content="hello"), BackgroundTasks(), user_id=10)
        sender.assert_not_called()

    @patch("main.update_claim_status")
    @patch("main.send_claim_decision_email")
    def test_committed_claim_decision_queues_claimant_and_competing_claimants(self, sender, update_claim):
        update_claim.return_value = {
            "claim_id": 5, "claimant_user_id": 10, "status": "ACCEPTED",
            "_email_rejected_claimant_ids": [30],
        }
        tasks = BackgroundTasks()
        result = main.update_claim_api(5, main.ClaimStatusRequest(status="ACCEPTED"), tasks, user_id=20)
        self.assertNotIn("_email_rejected_claimant_ids", result["claim"])
        self.assertEqual([task.args for task in tasks.tasks], [(10, "ACCEPTED"), (30, "REJECTED")])


if __name__ == "__main__":
    unittest.main()
