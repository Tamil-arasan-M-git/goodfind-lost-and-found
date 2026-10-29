"""Best-effort Gmail SMTP notifications, isolated from database workflows."""

import logging
import os
import smtplib
import ssl
import threading
import time
from dataclasses import dataclass
from email.message import EmailMessage

from database import get_connection

logger = logging.getLogger(__name__)
_recent_events: dict[str, float] = {}
_recent_events_lock = threading.Lock()


@dataclass(frozen=True)
class EmailSettings:
    host: str
    port: int
    username: str
    app_password: str
    sender: str
    frontend_base_url: str


def _enabled() -> bool:
    return os.getenv("EMAIL_NOTIFICATIONS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _settings() -> EmailSettings | None:
    if not _enabled():
        return None
    # SMTP_HOST is part of the explicit SMTP configuration.  Do not silently
    # turn an explicitly empty value into the Gmail default: callers must not
    # be told delivery succeeded when configuration is incomplete.  The
    # default remains available when the variable is omitted for backwards
    # compatibility with existing Gmail-only deployments.
    raw_host = os.getenv("SMTP_HOST")
    host = "smtp.gmail.com" if raw_host is None else raw_host.strip()
    username = os.getenv("SMTP_USERNAME", "").strip()
    app_password = os.getenv("SMTP_APP_PASSWORD", "")
    sender = os.getenv("EMAIL_FROM", "").strip() or os.getenv("SMTP_FROM", "").strip() or username
    try:
        port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError:
        logger.warning("GoodFind email notifications are disabled because SMTP_PORT is invalid.")
        return None
    if not host or not username or not app_password or not sender:
        logger.warning("GoodFind email notifications are enabled but SMTP configuration is incomplete.")
        return None
    return EmailSettings(
        host=host,
        port=port,
        username=username,
        app_password=app_password,
        sender=sender,
        frontend_base_url=os.getenv("FRONTEND_BASE_URL", "http://127.0.0.1:5173").rstrip("/"),
    )


def _email_for_user(user_id: int) -> str | None:
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT email FROM users WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
            return row[0] if row else None
    finally:
        connection.close()


def _reserve_event(event_key: str | None, cooldown_seconds: int) -> bool:
    if not event_key or cooldown_seconds <= 0:
        return True
    now = time.monotonic()
    with _recent_events_lock:
        previous = _recent_events.get(event_key)
        if previous is not None and now - previous < cooldown_seconds:
            return False
        _recent_events[event_key] = now
        return True


def _release_event(event_key: str | None) -> None:
    if event_key:
        with _recent_events_lock:
            _recent_events.pop(event_key, None)


def send_email(user_id: int, subject: str, text: str, *, event_key: str | None = None, cooldown_seconds: int = 0) -> bool:
    """Send only after a workflow has committed. SMTP failure is always non-fatal."""
    settings = _settings()
    if not settings or not _reserve_event(event_key, cooldown_seconds):
        return False
    try:
        recipient = _email_for_user(user_id)
        if not recipient:
            _release_event(event_key)
            return False
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = settings.sender
        message["To"] = recipient
        message.set_content(text)
        with smtplib.SMTP(settings.host, settings.port, timeout=10) as client:
            client.starttls(context=ssl.create_default_context())
            client.login(settings.username, settings.app_password)
            client.send_message(message)
        return True
    except (OSError, smtplib.SMTPException, ValueError) as error:
        _release_event(event_key)
        logger.warning("GoodFind email delivery failed (%s).", type(error).__name__)
        return False


def _link(settings: EmailSettings | None, path: str) -> str:
    return f"{settings.frontend_base_url}{path}" if settings else path


def send_chat_request_email(user_id: int, item_name: str | None = None) -> bool:
    settings = _settings()
    item_line = f" Related item: {item_name}." if item_name else ""
    return send_email(user_id, "GoodFind: new private chat request", f"A GoodFind member requested a private conversation about a possible item match.{item_line}\n\nReview the request: {_link(settings, '/messages')}\n\nGoodFind never includes contact details in these notifications.")


def send_chat_accepted_email(user_id: int) -> bool:
    settings = _settings()
    return send_email(user_id, "GoodFind: your chat request was accepted", f"Your private chat request was accepted. You can coordinate a safe handover in GoodFind.\n\nOpen messages: {_link(settings, '/messages')}")


def send_new_message_email(user_id: int, conversation_id: int) -> bool:
    settings = _settings()
    try:
        cooldown = max(0, int(os.getenv("EMAIL_MESSAGE_COOLDOWN_SECONDS", "300")))
    except ValueError:
        cooldown = 300
    return send_email(user_id, "You have a new message on GoodFind.", f"You have a new private message on GoodFind. Open the app to read it and coordinate safely.\n\nOpen messages: {_link(settings, '/messages')}", event_key=f"message:{conversation_id}:{user_id}", cooldown_seconds=cooldown)


def send_claim_decision_email(user_id: int, status: str) -> bool:
    settings = _settings()
    decision = "accepted" if status == "ACCEPTED" else "rejected"
    return send_email(user_id, f"GoodFind: your claim was {decision}", f"Your item claim was {decision}. Review the claim and next steps in GoodFind.\n\nOpen claims: {_link(settings, '/claims')}")
