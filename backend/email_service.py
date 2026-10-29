"""Compatibility wrapper for the secure, explicit email-notification service."""

from email_notifications import send_email


def send_workflow_email(user_id: int, subject: str, text: str) -> bool:
    """Legacy internal API; delivery remains disabled unless explicitly configured."""
    return send_email(user_id, subject, text)
