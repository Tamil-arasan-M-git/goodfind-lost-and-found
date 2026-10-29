import unittest
from unittest.mock import MagicMock, patch

import auth


class AuthenticationTimingTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value

    @patch("auth.get_connection")
    @patch.object(auth.password_hash, "verify", return_value=True)
    def test_unknown_email_performs_dummy_hash_verification(self, verify, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.return_value = None

        self.assertIsNone(auth.authenticate_user("unknown@example.com", "wrong-password"))
        verify.assert_called_once_with("wrong-password", auth._DUMMY_PASSWORD_HASH)

    @patch("auth.get_connection")
    @patch.object(auth.password_hash, "verify", return_value=False)
    def test_known_email_with_wrong_password_stays_generic(self, verify, get_connection):
        get_connection.return_value = self.connection
        self.cursor.fetchone.return_value = (7, "A User", "known@example.com", "stored-hash", "created")

        self.assertIsNone(auth.authenticate_user("known@example.com", "wrong-password"))
        verify.assert_called_once_with("wrong-password", "stored-hash")


if __name__ == "__main__":
    unittest.main()
