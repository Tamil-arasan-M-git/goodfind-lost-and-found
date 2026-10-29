import unittest
from unittest.mock import MagicMock, patch

import items
import main


class PublicItemQueryTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value

    def _configure_query(self, rows=None, total=0):
        self.cursor.fetchall.return_value = rows or []
        self.cursor.fetchone.return_value = (total,)

    @patch("items.get_connection")
    def test_public_item_response_does_not_include_owner_id(self, get_connection):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [(1, "LOST", "Wallet", "Accessories", "Black", "2026-10-01", "Library", "ACTIVE", "now")]
        cursor.fetchone.return_value = (1,)
        get_connection.return_value = connection
        results, total = items.get_lost_items(search="wallet", limit=20, offset=0)
        self.assertEqual(total, 1)
        self.assertNotIn("user_id", results[0])
        self.assertEqual(results[0]["item_name"], "Wallet")

    def test_detection_labels_are_normalized(self):
        self.assertEqual(items.normalize_detection_labels([" Backpack ", "backpack", "person"]), ["backpack", "person"])

    @patch("items.get_connection")
    def test_ineligible_item_images_are_not_selected(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.return_value = None
        self.assertIsNone(items.get_item_image(7))
        query = self.cursor.execute.call_args.args[0]
        self.assertIn("status IN ('ACTIVE', 'HANDOVER_IN_PROGRESS')", query)

    @patch("items.get_connection")
    def test_resolution_locks_match_and_items_and_updates_active_rows(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.return_value = (42, 1, 2, "PENDING", "ACTIVE", "ACTIVE")
        result = items.resolve_match_for_handover(42, 10)
        self.assertEqual(result, {"match_id": 42, "status": "RESOLVED"})
        lock_query = self.cursor.execute.call_args_list[0].args[0]
        self.assertIn("FOR UPDATE OF m, l, f", lock_query)
        self.assertTrue(any("UPDATE matches" in call.args[0] for call in self.cursor.execute.call_args_list))
        self.connection.commit.assert_called_once()

    @patch("items.get_connection")
    def test_resolution_rejects_stale_lifecycle_while_locked(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.return_value = (42, 1, 2, "RESOLVED", "RESOLVED", "RESOLVED")
        with self.assertRaisesRegex(ValueError, "no longer eligible"):
            items.resolve_match_for_handover(42, 10)
        self.assertEqual(self.cursor.execute.call_count, 1)
        self.connection.commit.assert_not_called()

    @patch("items.get_connection")
    def test_search_uses_name_or_description_with_literal_case_insensitive_pattern(self, get_connection):
        get_connection.return_value = self.connection
        self._configure_query(total=2)
        items.get_lost_items(search="  Wallet%_ ")
        query, parameters = self.cursor.execute.call_args_list[0].args
        self.assertIn("item_name ILIKE %s ESCAPE", query)
        self.assertIn("OR description ILIKE %s ESCAPE", query)
        self.assertEqual(parameters[1:3], ["%Wallet\\%\\_%", "%Wallet\\%\\_%"])

    @patch("items.get_connection")
    def test_combined_filters_use_and_and_trim_values(self, get_connection):
        get_connection.return_value = self.connection
        self._configure_query(total=1)
        items.get_found_items(search=" phone ", category=" electronics ", location=" library ", status=" active ")
        query, parameters = self.cursor.execute.call_args_list[0].args
        self.assertIn(" AND category ILIKE", query)
        self.assertIn(" AND location ILIKE", query)
        self.assertIn(" AND status = %s", query)
        self.assertEqual(parameters, ["FOUND", "%phone%", "%phone%", "electronics", "%library%", "ACTIVE", 20, 0])

    @patch("items.get_connection")
    def test_whitespace_only_filters_are_absent(self, get_connection):
        get_connection.return_value = self.connection
        self._configure_query(total=3)
        items.get_lost_items(search="  ", category="\t", location="\n", status=" ")
        query, parameters = self.cursor.execute.call_args_list[0].args
        self.assertNotIn("ILIKE", query)
        self.assertEqual(parameters, ["LOST", 20, 0])

    def test_status_filter_accepts_only_schema_statuses(self):
        self.assertEqual(items.normalize_status_filter(" handover_in_progress "), "HANDOVER_IN_PROGRESS")
        with self.assertRaisesRegex(ValueError, "Invalid item status"):
            items.normalize_status_filter("WITHDRAWN")

    @patch("items.get_connection")
    def test_type_isolation_stable_order_and_count_use_same_where_clause(self, get_connection):
        get_connection.return_value = self.connection
        self._configure_query(total=23)
        items.get_found_items(search="keys", limit=1, offset=22)
        page_query, page_parameters = self.cursor.execute.call_args_list[0].args
        count_query, count_parameters = self.cursor.execute.call_args_list[1].args
        self.assertIn("item_type = %s", page_query)
        self.assertEqual(page_parameters[0], "FOUND")
        self.assertIn("ORDER BY created_at DESC, item_id DESC", page_query)
        self.assertEqual(page_parameters[:-2], count_parameters)
        self.assertEqual(page_parameters[-2:], [1, 22])
        self.assertEqual(self.cursor.fetchone.return_value, (23,))


class ItemListingRouteTests(unittest.TestCase):
    @patch("main.get_lost_items", return_value=([], 51))
    def test_page_metadata_and_count_are_preserved(self, get_lost_items):
        response = main.get_lost_items_api(page=2, page_size=50)
        self.assertEqual(response, {"count": 0, "total": 51, "page": 2, "page_size": 50, "items": []})
        self.assertEqual(get_lost_items.call_args.kwargs["offset"], 50)
        self.assertEqual(get_lost_items.call_args.kwargs["limit"], 50)

    @patch("main.get_found_items", side_effect=ValueError("Invalid item status"))
    def test_invalid_status_becomes_validation_response(self, _get_found_items):
        with self.assertRaises(Exception) as error:
            main.get_found_items_api(status="WITHDRAWN", page=1, page_size=20)
        self.assertEqual(error.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
