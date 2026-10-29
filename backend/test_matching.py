import unittest
from unittest.mock import MagicMock, patch

import matching
import main


def item(item_id, user_id, item_type, name, *, category="accessories", description="", location="Library", item_date="2026-10-20", labels=None, status="ACTIVE"):
    return {
        "item_id": item_id, "user_id": user_id, "item_type": item_type, "item_name": name,
        "category": category, "description": description, "location": location,
        "item_date": item_date, "detection_labels": labels or [], "image_path": None, "status": status,
    }


def row(value):
    return tuple(value[key] for key in ("item_id", "user_id", "item_type", "item_name", "category", "description", "item_date", "location", "detection_labels", "image_path", "status"))


class MatchingScoreTests(unittest.TestCase):
    def test_exact_normalized_match_is_100(self):
        lost = item(1, 10, "LOST", " Black, Leather Wallet ", description="Small gold logo", labels=["wallet_purse"])
        found = item(2, 20, "FOUND", "black leather wallet", description="small gold logo", labels=["wallet_purse"])
        self.assertEqual(matching.calculate_match_score(lost, found), 100.0)

    def test_synonymous_wallet_and_purse_are_more_similar_than_unrelated_type(self):
        lost = item(1, 10, "LOST", "black wallet")
        purse = item(2, 20, "FOUND", "black purse")
        bottle = item(3, 30, "FOUND", "black water bottle")
        self.assertGreater(matching.calculate_match_score(lost, purse), matching.calculate_match_score(lost, bottle))
        self.assertLess(matching.calculate_match_score(lost, bottle), matching.MATCH_THRESHOLD)

    def test_missing_values_never_supply_positive_evidence(self):
        lost = item(1, 10, "LOST", "", category="", description="", location="", item_date=None, labels=[])
        found = item(2, 20, "FOUND", "", category="", description="", location="", item_date=None, labels=[])
        details = matching.calculate_match_details(lost, found)
        self.assertEqual(details["score"], 0.0)
        self.assertTrue(details["explanation"]["missing_information"])

    def test_partial_detection_overlap_is_limited_and_explained(self):
        lost = item(1, 10, "LOST", "blue backpack", labels=["backpack_bag", "keys"])
        found = item(2, 20, "FOUND", "blue backpack", labels=["backpack_bag", "water_bottle"])
        details = matching.calculate_match_details(lost, found)
        self.assertEqual(details["components"]["detection_labels"], 1 / 3)
        self.assertLessEqual(matching.MATCH_WEIGHTS["detection_labels"] * 100, 5)

    def test_date_proximity_and_colour_conflict_are_deterministic(self):
        lost = item(1, 10, "LOST", "blue backpack", item_date="2026-10-20")
        near = item(2, 20, "FOUND", "red backpack", item_date="2026-10-21")
        details = matching.calculate_match_details(lost, near)
        self.assertEqual(details["components"]["date"], 0.8)
        self.assertIn("The reports describe different colours.", details["explanation"]["conflicts"])
        self.assertLess(details["score"], matching.MATCH_THRESHOLD)

    def test_weights_sum_to_one_and_score_is_bounded(self):
        self.assertAlmostEqual(sum(matching.MATCH_WEIGHTS.values()), 1.0)
        score = matching.calculate_match_score(item(1, 1, "LOST", "keys"), item(2, 2, "FOUND", "phone"))
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)


class MatchingWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.lost = item(1, 10, "LOST", "black wallet", description="leather", labels=["wallet_purse"])
        self.found = item(2, 20, "FOUND", "black wallet", description="leather", labels=["wallet_purse"])

    @patch("matching.get_connection")
    def test_refresh_creates_one_idempotent_pair_for_lost_or_found_source(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.side_effect = [row(self.lost), (42,)]
        self.cursor.fetchall.return_value = [row(self.found)]
        results = matching.refresh_matches_for_item(1)
        self.assertEqual(results[0]["match_id"], 42)
        insert = next(call.args[0] for call in self.cursor.execute.call_args_list if "INSERT INTO matches" in call.args[0])
        self.assertIn("ON CONFLICT (lost_item_id, found_item_id)", insert)
        self.connection.commit.assert_called_once()

    @patch("matching.get_connection")
    def test_found_source_compares_against_lost_candidates(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.side_effect = [row(self.found), (42,)]
        self.cursor.fetchall.return_value = [row(self.lost)]
        results = matching.refresh_matches_for_item(2)
        self.assertIn("lost_item", results[0])
        candidate_query = self.cursor.execute.call_args_list[1].args[0]
        self.assertIn("candidate.item_type = %s", candidate_query)

    @patch("matching.get_connection")
    def test_inactive_source_does_not_generate_suggestions(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.return_value = None
        self.assertEqual(matching.refresh_matches_for_item(1), [])
        queries = [call.args[0] for call in self.cursor.execute.call_args_list]
        self.assertFalse(any("INSERT INTO matches" in query for query in queries))

    @patch("matching.get_connection")
    def test_get_existing_matches_does_not_write_or_refresh(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.return_value = row(self.lost)
        self.cursor.fetchall.return_value = []
        self.assertEqual(matching.get_matches_for_item(1), [])
        queries = [call.args[0] for call in self.cursor.execute.call_args_list]
        self.assertFalse(any("INSERT INTO matches" in query or "UPDATE matches" in query for query in queries))
        self.connection.commit.assert_not_called()

    @patch("matching.get_connection")
    def test_candidate_query_excludes_blocked_pairs_and_inactive_reports(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.return_value = row(self.lost)
        self.cursor.fetchall.return_value = []
        matching.refresh_matches_for_item(1)
        query = self.cursor.execute.call_args_list[1].args[0]
        self.assertIn("candidate.status = 'ACTIVE'", query)
        self.assertIn("FROM user_blocks", query)


class MatchingRouteSecurityTests(unittest.TestCase):
    @patch("main.get_item_owner", return_value=10)
    def test_other_user_cannot_read_existing_matches(self, _get_item_owner):
        with self.assertRaises(Exception) as error:
            main.get_item_matches(1, user_id=99)
        self.assertEqual(error.exception.status_code, 403)

    @patch("main.get_item_owner", return_value=10)
    @patch("main.get_matches_for_item", return_value=[])
    def test_get_route_retrieves_without_refreshing(self, get_matches, _get_item_owner):
        result = main.get_item_matches(1, user_id=10)
        self.assertEqual(result["matches"], [])
        get_matches.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
