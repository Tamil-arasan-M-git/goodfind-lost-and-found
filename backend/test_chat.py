import os
import unittest
from unittest.mock import MagicMock, patch

import auth
import chat
import main
from pydantic import ValidationError


class ChatSecurityTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value

    @patch("chat.get_connection")
    def test_only_lost_owner_can_request_chat(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.return_value = (10, 20, "Wallet")  # lost owner, found owner, item
        with self.assertRaises(PermissionError):
            chat.create_chat_request(3, 99)
        self.connection.rollback.assert_called_once()

    @patch("chat.get_connection")
    def test_blocked_pair_cannot_create_a_new_chat_request(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.side_effect = [(10, 20, "Wallet"), (1,)]
        with self.assertRaisesRegex(PermissionError, "blocked"):
            chat.create_chat_request(3, 10)

    @patch("chat.get_connection")
    def test_chat_request_query_requires_pending_match_and_active_reports(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.return_value = None
        with self.assertRaisesRegex(ValueError, "Match not found"):
            chat.create_chat_request(3, 10)
        query = self.cursor.execute.call_args.args[0]
        self.assertIn("m.status = 'PENDING'", query)
        self.assertIn("l.status = 'ACTIVE'", query)
        self.assertIn("f.status = 'ACTIVE'", query)
        self.assertIn("FOR UPDATE OF m, l, f", query)

    @patch("chat.get_connection")
    def test_recipient_acceptance_creates_anonymous_conversation(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.side_effect = [
            (7, 3, 10, 20, "PENDING", "created", None, "PENDING", "ACTIVE", "ACTIVE"),
            ("PENDING", "ACTIVE", "ACTIVE"),
            (7, 3, 10, 20, "ACCEPTED", "created", "responded"),
            (42, "ACTIVE", "created"),
            (1, "chat_accepted", "accepted", None, "created"),
        ]
        request, conversation = chat.respond_to_chat_request(7, 20, True)
        self.assertEqual(request["status"], "ACCEPTED")
        self.assertEqual(conversation["conversation_id"], 42)
        participant_insert = self.cursor.executemany.call_args.args[1]
        self.assertEqual({row[1] for row in participant_insert}, {10, 20})
        self.assertNotIn("10", participant_insert[0][2])
        self.assertNotIn("20", participant_insert[1][2])

    @patch("chat.get_connection")
    def test_acceptance_rejects_lifecycle_changed_match(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.side_effect = [
            (7, 3, 10, 20, "PENDING", "created", None),
            ("RESOLVED", "RESOLVED", "RESOLVED"),
        ]
        with self.assertRaisesRegex(ValueError, "no longer eligible"):
            chat.respond_to_chat_request(7, 20, True)
        self.assertEqual(self.cursor.execute.call_count, 2)
        self.connection.commit.assert_not_called()

    @patch("chat.get_connection")
    def test_only_recipient_can_respond_to_request(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.return_value = (7, 3, 10, 20, "PENDING", "created", None)
        with self.assertRaises(PermissionError):
            chat.respond_to_chat_request(7, 10, False)

    @patch("chat.get_connection")
    def test_non_participant_cannot_read_messages(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.return_value = None
        with self.assertRaises(PermissionError):
            chat.get_messages(42, 99)

    @patch("chat.get_connection")
    def test_closed_conversation_cannot_receive_messages(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.return_value = ("CLOSED", "GoodFind member abc", None)
        with self.assertRaisesRegex(ValueError, "closed"):
            chat.send_message(42, 10, "Are you available?")

    @patch("chat.get_connection")
    def test_close_requires_participation(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.return_value = None
        with self.assertRaises(PermissionError):
            chat.close_conversation(42, 99)

    @patch("chat.get_connection")
    def test_block_prevents_future_message(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.side_effect = [
            ("ACTIVE", "GoodFind member one", None), (20,), (20,), ("blocked-at",),
        ]
        result = chat.block_conversation_participant(42, 10)
        self.assertTrue(result["blocked"])
        self.cursor.reset_mock()
        self.cursor.fetchone.side_effect = None
        self.cursor.fetchone.return_value = ("ACTIVE", "GoodFind member one", "blocked-at")
        with self.assertRaises(PermissionError):
            chat.send_message(42, 10, "Hello")

    @patch("chat.get_connection")
    def test_non_participant_cannot_report(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.return_value = None
        with self.assertRaises(PermissionError):
            chat.report_conversation_participant(42, 99, "Harassment")

    def test_report_reason_has_length_limits(self):
        with self.assertRaisesRegex(ValueError, "between 1 and 500"):
            chat.report_conversation_participant(42, 10, " ")

    @patch("chat.get_connection")
    def test_duplicate_report_is_rejected(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.side_effect = [
            ("ACTIVE", "GoodFind member one", None), (20,), (1,),
        ]
        with self.assertRaisesRegex(ValueError, "already reported"):
            chat.report_conversation_participant(42, 10, "Harassment")

    @patch("chat.get_connection")
    def test_repeated_closure_returns_existing_closed_state(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.side_effect = [
            ("CLOSED", "GoodFind member one", None), None, (42, "CLOSED", "closed-at"),
        ]
        result = chat.close_conversation(42, 10)
        self.assertEqual(result["status"], "CLOSED")

    @patch("chat.get_connection")
    def test_conversation_inbox_includes_safe_preview_and_block_state(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchall.return_value = [
            (42, "ACTIVE", "created", "My alias", "blocked-at", "Wallet",
             "GoodFind member abc", "I found it", "message-created")
        ]
        conversations = chat.list_conversations(10)
        self.assertEqual(conversations[0]["item_name"], "Wallet")
        self.assertEqual(conversations[0]["other_alias"], "GoodFind member abc")
        self.assertEqual(conversations[0]["last_message_at"], "message-created")
        self.assertTrue(conversations[0]["is_blocked"])
        self.assertNotIn("user_id", conversations[0])

    @patch("chat.get_connection")
    def test_request_inbox_includes_item_without_exposing_an_identity(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchall.return_value = [
            (7, 3, 10, 20, "PENDING", "created", None, "Wallet")
        ]
        requests = chat.list_chat_requests(20)
        self.assertEqual(requests[0]["item_name"], "Wallet")
        self.assertEqual(requests[0]["other_alias"], "GoodFind member")
        self.assertTrue(requests[0]["is_incoming"])
        self.assertNotIn("email", requests[0])
        self.assertNotIn("phone", requests[0])

    def test_forged_item_user_id_is_rejected(self):
        with self.assertRaises(ValidationError):
            main.LostItemRequest(
                user_id=999, item_name="Wallet", category="Accessories",
                description="Black", item_date="2026-10-21", location="Library",
            )

    @patch("main.update_item", side_effect=PermissionError("You do not own this item"))
    def test_cross_user_item_update_is_forbidden(self, _update_item):
        request = main.ItemUpdateRequest(item_name="Wallet", category="Accessories",
                                         description="", item_date="2026-10-21", location="Library")
        with self.assertRaises(Exception) as error:
            main.update_item_api(1, request, user_id=99)
        self.assertEqual(error.exception.status_code, 403)

    @patch("main.delete_item", side_effect=PermissionError("You do not own this item"))
    def test_cross_user_item_delete_is_forbidden(self, _delete_item):
        with self.assertRaises(Exception) as error:
            main.delete_item_api(1, user_id=99)
        self.assertEqual(error.exception.status_code, 403)

    @patch("main.create_claim", side_effect=ValueError("You are not the owner of this lost item"))
    def test_unauthorized_claim_is_rejected(self, _create_claim):
        with self.assertRaises(Exception) as error:
            main.create_claim_api(3, user_id=99)
        self.assertEqual(error.exception.status_code, 400)


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.previous_secret = os.environ.get("AUTH_SECRET")
        os.environ["AUTH_SECRET"] = "test-secret"

    def tearDown(self):
        if self.previous_secret is None:
            os.environ.pop("AUTH_SECRET", None)
        else:
            os.environ["AUTH_SECRET"] = self.previous_secret

    def test_signed_token_returns_authenticated_user(self):
        token = auth.create_access_token(123)
        self.assertEqual(auth.get_token_user_id(token), 123)

    def test_tampered_token_is_rejected(self):
        token = auth.create_access_token(123)
        self.assertIsNone(auth.get_token_user_id(f"{token}x"))


if __name__ == "__main__":
    unittest.main()
