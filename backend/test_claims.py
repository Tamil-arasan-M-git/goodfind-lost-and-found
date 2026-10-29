import unittest
from unittest.mock import MagicMock, patch

from fastapi import BackgroundTasks

import claims
import main


class ClaimServiceTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.match = (9, 11, 12, 20, "PENDING", "ACTIVE", "ACTIVE")
        self.claim = (5, 9, 10, 20, "PENDING", "created")

    @patch("claims.get_connection")
    def test_claim_creation_requires_lost_owner_and_creates_notification(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.side_effect = [self.match, (10,), None, None, self.claim, (1, "claim_request", "notice", None, "now")]
        result = claims.create_claim(9, 10)
        self.assertTrue(result["created"])
        self.assertFalse(result["already_pending"])
        self.connection.commit.assert_called_once()

    @patch("claims.get_connection")
    def test_pending_duplicate_is_idempotent_without_notification(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.side_effect = [self.match, (10,), self.claim]
        result = claims.create_claim(9, 10)
        self.assertFalse(result["created"])
        queries = [call.args[0] for call in self.cursor.execute.call_args_list]
        self.assertFalse(any("INSERT INTO notifications" in query for query in queries))

    @patch("claims.get_connection")
    def test_terminal_claim_cannot_reopen(self, get_connection):
        get_connection.return_value = self.connection
        terminal = (5, 9, 10, 20, "ACCEPTED", "created")
        self.cursor.fetchone.side_effect = [self.match, (10,), terminal]
        with self.assertRaisesRegex(claims.ClaimConflictError, "cannot be reopened"):
            claims.create_claim(9, 10)

    @patch("claims.get_connection")
    def test_self_claim_is_rejected(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.side_effect = [(9, 11, 12, 10, "PENDING", "ACTIVE", "ACTIVE"), (10,)]
        with self.assertRaisesRegex(ValueError, "own found item"):
            claims.create_claim(9, 10)

    @patch("claims.get_connection")
    def test_ineligible_match_or_report_is_rejected(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.side_effect = [(9, 11, 12, 20, "RESOLVED", "ACTIVE", "ACTIVE"), (10,)]
        with self.assertRaisesRegex(claims.ClaimConflictError, "no longer eligible"):
            claims.create_claim(9, 10)

    @patch("claims.get_connection")
    def test_review_requires_found_owner(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.return_value = (5, 20, "PENDING", 12, "PENDING", "ACTIVE", "ACTIVE")
        with self.assertRaises(PermissionError):
            claims.update_claim_status(5, 10, "ACCEPTED")

    @patch("claims.get_connection")
    def test_review_uses_conditional_update_and_rejects_competing_claims(self, get_connection):
        get_connection.return_value = self.connection
        accepted = (5, 9, 10, 20, "ACCEPTED", "created")
        self.cursor.fetchone.side_effect = [
            (5, 20, "PENDING", 12, "PENDING", "ACTIVE", "ACTIVE"), accepted,
            (1, "claim_status", "accepted", None, "now"),
            (2, "claim_status", "rejected", None, "now"),
        ]
        self.cursor.fetchall.return_value = [(30,)]
        result = claims.update_claim_status(5, 20, "accepted")
        self.assertEqual(result["competing_claims_rejected"], 1)
        update_query = next(call.args[0] for call in self.cursor.execute.call_args_list if "UPDATE claims\n                SET status" in call.args[0])
        self.assertIn("AND status = 'PENDING'", update_query)
        self.assertTrue(any("UPDATE claims competing" in call.args[0] for call in self.cursor.execute.call_args_list))

    @patch("claims.get_connection")
    def test_claim_list_contains_no_email_or_contact_fields(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchall.return_value = [(5, 9, 10, 20, "PENDING", "created", 11, "Lost wallet", "accessories", 12, "Found wallet", "accessories")]
        result = claims.get_claims_for_user(10)
        self.assertEqual(result[0]["lost_item"]["item_name"], "Lost wallet")
        self.assertNotIn("email", result[0])
        self.assertNotIn("phone", result[0])

    @patch("claims.get_connection")
    def test_found_item_claim_selects_authenticated_users_best_persisted_match(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.return_value = (9,)
        with patch("claims.create_claim", return_value={"claim_id": 5, "match_id": 9, "created": True}) as create:
            result = claims.create_claim_for_found_item(12, 10)
        self.assertEqual(result["match_id"], 9)
        create.assert_called_once_with(9, 10)
        query = self.cursor.execute.call_args.args[0]
        self.assertIn("l.user_id = %s", query)
        self.assertIn("m.found_item_id = %s", query)


class ClaimRouteTests(unittest.TestCase):
    @patch("main.create_claim", side_effect=claims.ClaimConflictError("reviewed"))
    def test_claim_conflict_maps_to_409(self, _create_claim):
        with self.assertRaises(Exception) as error:
            main.create_claim_api(9, user_id=10)
        self.assertEqual(error.exception.status_code, 409)

    @patch("main.update_claim_status", side_effect=PermissionError("not owner"))
    def test_review_permission_maps_to_403(self, _update_claim_status):
        request = main.ClaimStatusRequest(status="ACCEPTED")
        with self.assertRaises(Exception) as error:
            main.update_claim_api(5, request, BackgroundTasks(), user_id=10)
        self.assertEqual(error.exception.status_code, 403)

    @patch("main.create_claim_for_found_item", return_value={"claim_id": 5, "match_id": 9, "created": True})
    def test_found_item_claim_route_uses_authenticated_user(self, create_claim):
        result = main.create_claim_for_found_item_api(12, user_id=10)
        self.assertEqual(result["claim"]["match_id"], 9)
        create_claim.assert_called_once_with(12, 10)


if __name__ == "__main__":
    unittest.main()
