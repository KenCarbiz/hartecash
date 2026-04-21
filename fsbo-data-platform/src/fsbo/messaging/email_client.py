"""Unified transactional-email send.

Three backends, selected automatically:

    EMAIL_BACKEND=console     # dev default — logs the full email body
    EMAIL_BACKEND=sendgrid    # production — HTTP API
    EMAIL_BACKEND=smtp        # production fallback — any SMTP server

Call sites use `await send_email(to, subject, text_body, html_body=?)`
and don't have to care which backend is in play.
"""

from __future__ import annotations

import asyncio
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

import httpx

from fsbo.config import settings
from fsbo.logging import get_logger

log = get_logger(__name__)


@dataclass
class EmailResult:
    backend: str
    sent: bool
    error: str | None = None


async def send_email(
    to: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
    from_address: str | None = None,
) -> EmailResult:
    if not to or "@" not in to:
        return EmailResult(backend="none", sent=False, error="invalid recipient")

    backend = (settings.email_backend or "console").lower()
    sender = (from_address or settings.email_from or "noreply@autocurb.local").strip()

    if backend == "sendgrid":
        return await _send_via_sendgrid(to, sender, subject, text_body, html_body)
    if backend == "smtp":
        return await _send_via_smtp(to, sender, subject, text_body, html_body)
    return _send_via_console(to, sender, subject, text_body, html_body)


def _send_via_console(
    to: str, sender: str, subject: str, text: str, html: str | None
) -> EmailResult:
    log.info(
        "email.console",
        to=to,
        sender=sender,
        subject=subject,
        preview=text[:160],
        has_html=bool(html),
    )
    return EmailResult(backend="console", sent=True)


async def _send_via_sendgrid(
    to: str,
    sender: str,
    subject: str,
    text: str,
    html: str | None,
) -> EmailResult:
    if not settings.sendgrid_api_key:
        return EmailResult(
            backend="sendgrid",
            sent=False,
            error="SENDGRID_API_KEY not configured",
        )
    payload: dict = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": sender, "name": settings.email_from_name or "AutoCurb"},
        "subject": subject,
        "content": [{"type": "text/plain", "value": text}],
    }
    if html:
        payload["content"].append({"type": "text/html", "value": html})

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {settings.sendgrid_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.HTTPError as e:
        return EmailResult(backend="sendgrid", sent=False, error=str(e)[:200])

    if resp.status_code >= 400:
        return EmailResult(
            backend="sendgrid",
            sent=False,
            error=f"HTTP {resp.status_code}: {resp.text[:200]}",
        )
    return EmailResult(backend="sendgrid", sent=True)


async def _send_via_smtp(
    to: str,
    sender: str,
    subject: str,
    text: str,
    html: str | None,
) -> EmailResult:
    host = settings.smtp_host
    if not host:
        return EmailResult(
            backend="smtp", sent=False, error="SMTP_HOST not configured"
        )
    port = settings.smtp_port or 587
    user = settings.smtp_user or None
    password = settings.smtp_password or None
    use_tls = settings.smtp_use_tls

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")

    def _blocking_send() -> None:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            if use_tls:
                smtp.starttls()
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)

    try:
        await asyncio.to_thread(_blocking_send)
    except (smtplib.SMTPException, OSError) as e:
        return EmailResult(backend="smtp", sent=False, error=str(e)[:200])
    return EmailResult(backend="smtp", sent=True)
