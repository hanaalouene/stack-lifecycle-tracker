"""Delivery layer: send the report by email with the standard library (no paid service)."""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

REQUIRED = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_TO")


def is_configured() -> bool:
    return all(os.environ.get(k) for k in REQUIRED)


def send_email(subject: str, text_body: str, html_body: str) -> bool:
    """Send the report. Credentials come from environment variables only, never from the code.

    SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASSWORD, MAIL_TO, MAIL_FROM (default SMTP_USER).
    Returns False when the variables are not set, so the report is still written to disk.
    """
    if not is_configured():
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ.get("MAIL_FROM") or os.environ["SMTP_USER"]
    msg["To"] = os.environ["MAIL_TO"]
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    port = int(os.environ.get("SMTP_PORT", "587"))
    with smtplib.SMTP(os.environ["SMTP_HOST"], port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(msg)
    return True
