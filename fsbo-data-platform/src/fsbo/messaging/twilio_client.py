"""Thin Twilio client. No Twilio SDK dependency — we POST to the REST API
directly with httpx. This keeps cold-start fast and avoids a heavyweight
dep for a single endpoint.
"""

from dataclasses import dataclass

import httpx

from fsbo.config import settings


@dataclass
class TwilioSendResult:
    sid: str | None
    status: str
    error_code: str | None = None
    error_message: str | None = None


async def send_sms(
    to_number: str,
    body: str,
    status_callback: str | None = None,
) -> TwilioSendResult:
    """Send an SMS. Returns status=skipped if Twilio isn't configured — the
    caller still records the Message row so the outreach isn't lost.

    A2P 10DLC: use a Messaging Service SID (provisioned through Twilio's
    console after carrier registration) rather than a raw from-number.
    """
    if not (settings.twilio_account_sid and settings.twilio_auth_token):
        return TwilioSendResult(
            sid=None,
            status="skipped",
            error_message="Twilio not configured",
        )

    if not (settings.twilio_messaging_service_sid or settings.twilio_from_number):
        return TwilioSendResult(
            sid=None,
            status="skipped",
            error_message="No messaging service SID or from-number configured",
        )

    data = {"To": to_number, "Body": body}
    if settings.twilio_messaging_service_sid:
        data["MessagingServiceSid"] = settings.twilio_messaging_service_sid
    else:
        data["From"] = settings.twilio_from_number
    if status_callback or settings.twilio_status_callback:
        data["StatusCallback"] = status_callback or settings.twilio_status_callback

    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/"
        f"{settings.twilio_account_sid}/Messages.json"
    )
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(
                url,
                data=data,
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            )
        except httpx.HTTPError as e:
            return TwilioSendResult(
                sid=None, status="failed", error_message=str(e)[:200]
            )

    if resp.status_code >= 400:
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        return TwilioSendResult(
            sid=None,
            status="failed",
            error_code=str(payload.get("code", resp.status_code)),
            error_message=str(payload.get("message", resp.text[:200])),
        )

    payload = resp.json()
    return TwilioSendResult(
        sid=payload.get("sid"),
        status=payload.get("status", "queued"),
        error_code=payload.get("error_code"),
        error_message=payload.get("error_message"),
    )
