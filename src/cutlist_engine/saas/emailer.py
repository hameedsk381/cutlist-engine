"""Transactional email. Uses SMTP when CUTLIST_SMTP_* is configured;
otherwise logs the message so development and self-hosted setups still work.
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)

APP_URL = os.environ.get("CUTLIST_APP_URL", "").rstrip("/")


def _smtp_configured() -> bool:
    return bool(os.environ.get("CUTLIST_SMTP_HOST", "").strip())


def send_email(to: str, subject: str, body: str) -> None:
    host = os.environ.get("CUTLIST_SMTP_HOST", "").strip()
    if not host:
        logger.info(
            "email (SMTP not configured — CUTLIST_SMTP_HOST unset). to=%s subject=%s body:\n%s",
            to, subject, body,
        )
        return

    port = int(os.environ.get("CUTLIST_SMTP_PORT", "587"))
    user = os.environ.get("CUTLIST_SMTP_USER", "").strip()
    password = os.environ.get("CUTLIST_SMTP_PASSWORD", "").strip()
    sender = os.environ.get("CUTLIST_SMTP_FROM", user or "noreply@cutlistengine.com")

    msg = EmailMessage()
    msg["To"] = to
    msg["From"] = sender
    msg["Subject"] = subject
    msg.set_content(body)

    if port == 465:
        with smtplib.SMTP_SSL(host, port) as smtp:
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port) as smtp:
            smtp.starttls()
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)

    logger.info("email sent to=%s subject=%s", to, subject)


def send_verification_email(to: str, token: str) -> None:
    link = f"{APP_URL or 'http://localhost:8000'}/auth/verify/{token}"
    send_email(
        to,
        "Verify your CutList account",
        (
            "Welcome to CutList!\n\n"
            f"Confirm your email address: {link}\n\n"
            "If you didn't create this account, ignore this email."
        ),
    )


def send_password_reset_email(to: str, token: str) -> None:
    link = f"{APP_URL or 'http://localhost:8000'}/?reset={token}"
    send_email(
        to,
        "Reset your CutList password",
        (
            "Someone asked to reset the password for this CutList account.\n\n"
            f"Choose a new password (the link works once, for one hour): {link}\n\n"
            "If this was not you, ignore this email. Your password has not changed."
        ),
    )
