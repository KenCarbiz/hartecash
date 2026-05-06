"""Twilio webhook HMAC signature verification.

Twilio signs every webhook with HMAC-SHA1 of:
    full_url + sorted(form_param_key + form_param_value)
keyed by the account's auth token. The signature lives in the
`X-Twilio-Signature` header. See:
https://www.twilio.com/docs/usage/webhooks/webhooks-security

Why we don't use twilio-python's RequestValidator: it expects you to
already have parsed form data + a fully-resolved URL. We build both
inside FastAPI's request lifecycle so we can guard with a Depends().
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from urllib.parse import urlparse, urlunparse

from fastapi import HTTPException, Request

from fsbo.config import settings


def _expected_signature(url: str, form_params: dict[str, str], auth_token: str) -> str:
    """Compute Twilio's request-signature value for an incoming POST."""
    # Sort params alphabetically by key, concatenate as key+value pairs.
    payload = url
    for k in sorted(form_params.keys()):
        payload += k + form_params[k]
    digest = hmac.new(
        auth_token.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def _public_url(request: Request) -> str:
    """Reconstruct the URL Twilio actually saw.

    Behind a reverse proxy, request.url.scheme can be "http" even
    though the public scheme was "https". Honor X-Forwarded-Proto and
    X-Forwarded-Host so the signature matches what Twilio computed.
    """
    parsed = urlparse(str(request.url))
    proto = request.headers.get("x-forwarded-proto") or parsed.scheme
    host = request.headers.get("x-forwarded-host") or parsed.netloc
    return urlunparse((proto, host, parsed.path, parsed.params, parsed.query, ""))


async def verify_twilio_signature(request: Request) -> None:
    """FastAPI dependency: raise 403 if the X-Twilio-Signature header
    doesn't match an HMAC-SHA1 of the full URL + sorted form params.

    Skipped entirely when no auth token is configured (dev / CI). Don't
    set TWILIO_AUTH_TOKEN in production until you're ready to enforce.
    """
    auth_token = settings.twilio_auth_token
    if not auth_token:
        return  # no token configured -> dev mode, skip

    signature = request.headers.get("x-twilio-signature")
    if not signature:
        raise HTTPException(status_code=403, detail="missing twilio signature")

    # We need to read the body so the route can also read it. Cache via
    # request.state so we don't double-consume the stream.
    if hasattr(request.state, "_twilio_form"):
        form: dict[str, str] = request.state._twilio_form
    else:
        raw_form = await request.form()
        form = {k: str(v) for k, v in raw_form.items()}
        request.state._twilio_form = form  # cached for the route handler

    expected = _expected_signature(_public_url(request), form, auth_token)
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=403, detail="invalid twilio signature")
