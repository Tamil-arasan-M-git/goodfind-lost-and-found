import unittest
from unittest.mock import MagicMock, patch

import notifications


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value

    @patch("notifications.get_connection")
    def test_notification_is_persisted(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.return_value = (5, "claim_status", "Claim accepted", None, "now")
        result = notifications.create_notification(12, "claim_status", "Claim accepted")
        self.assertEqual(result["notification_id"], 5)
        self.connection.commit.assert_called_once()

    @patch("notifications.get_connection")
    def test_only_owner_can_mark_notification_read(self, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.return_value = None
        with self.assertRaises(PermissionError):
            notifications.mark_notification_read(5, 99)


if __name__ == "__main__":
    unittest.main()
