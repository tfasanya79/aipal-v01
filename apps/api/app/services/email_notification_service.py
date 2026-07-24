from __future__ import annotations

import logging
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import Notification, User

log = logging.getLogger("aipal.email_notifications")
settings = get_settings()


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def send_email_notification(db: AsyncSession, user: User, notification: Notification) -> Notification:
    """Send an email notification using SMTP when configured, otherwise no-op safely."""
    if not user.email:
        notification.status = "failed"
        notification.metadata_json = {**(notification.metadata_json or {}), "reason": "missing_email"}
    elif settings.email_notifications_provider == "smtp" and settings.smtp_host:
        try:
            _send_smtp(user.email, notification.title, notification.body)
            notification.status = "sent"
            notification.sent_at = _utcnow()
            notification.metadata_json = {**(notification.metadata_json or {}), "provider": "smtp"}
        except Exception as exc:
            log.exception("SMTP email notification failed")
            notification.status = "failed"
            notification.metadata_json = {
                **(notification.metadata_json or {}),
                "provider": "smtp",
                "reason": str(exc)[:240],
            }
    else:
        log.info("No-op email notification for %s: %s", user.email, notification.title)
        notification.status = "sent"
        notification.sent_at = _utcnow()
        notification.metadata_json = {**(notification.metadata_json or {}), "provider": "noop"}
    notification.updated_at = _utcnow()
    await db.commit()
    await db.refresh(notification)
    return notification


def _send_smtp(to_email: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from_email
    message["To"] = to_email
    message.set_content(body)

    if settings.smtp_use_tls:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
