import base64
import binascii
import hashlib
import hmac
import json
import os
import time

from pwdlib import PasswordHash

from database import get_connection


password_hash = PasswordHash.recommended()
# Used to perform the same password-hash work when an email is unknown.  This
# is not associated with any account and is never returned or stored.
_DUMMY_PASSWORD_HASH = password_hash.hash("GoodFind dummy password verification value")


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_base64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_access_token(user_id: int) -> str:
    """Create a short-lived, signed token without adding a JWT dependency."""
    secret = os.getenv("AUTH_SECRET")
    if not secret:
        raise RuntimeError("AUTH_SECRET environment variable is required")
    payload = {"sub": str(user_id), "exp": int(time.time()) + 60 * 60 * 24}
    encoded = _base64url(json.dumps(payload, separators=(",", ":")).encode())
    signature = _base64url(
        hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
    )
    return f"{encoded}.{signature}"


def get_token_user_id(token: str) -> int | None:
    secret = os.getenv("AUTH_SECRET")
    if not secret:
        raise RuntimeError("AUTH_SECRET environment variable is required")
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected_signature = _base64url(
            hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return None
        payload = json.loads(_decode_base64url(encoded))
        if int(payload["exp"]) < time.time():
            return None
        return int(payload["sub"])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError, binascii.Error):
        return None


def create_user(name: str, email: str, password: str):
    hashed_password = password_hash.hash(password)

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users (name, email, password_hash)
                VALUES (%s, %s, %s)
                RETURNING user_id, name, email, created_at;
                """,
                (name, email, hashed_password),
            )

            user = cursor.fetchone()

        connection.commit()

        return {
            "user_id": user[0],
            "name": user[1],
            "email": user[2],
            "created_at": user[3],
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()
def authenticate_user(email, password):
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id, name, email, password_hash, created_at
                FROM users
                WHERE email = %s
                """,
                (email,),
            )

            user = cursor.fetchone()

            if user is None:
                password_hash.verify(password, _DUMMY_PASSWORD_HASH)
                return None

            user_id, name, user_email, stored_password_hash, created_at = user

            if not password_hash.verify(password, stored_password_hash):
                return None

            return {
                "user_id": user_id,
                "name": name,
                "email": user_email,
                "created_at": created_at,
            }

    finally:
        connection.close()
