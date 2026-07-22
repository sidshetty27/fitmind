"""Svix signature verification and the Clerk webhook's fail-closed behaviour.

These are the checks that keep forged `user.deleted` (and friends) out. All are
deterministic and need no database or network: the signing algorithm is exercised
directly, and the endpoint tests only reach its rejection paths.
"""

import base64
import hashlib
import hmac

import pytest
from httpx import AsyncClient

from app.core import svix
from app.core.config import settings

_KEY = b"super-secret-signing-key-bytes!!"
_SECRET = "whsec_" + base64.b64encode(_KEY).decode()


def _sign(svix_id: str, timestamp: str, payload: bytes) -> str:
    signed = b"%s.%s.%s" % (svix_id.encode(), timestamp.encode(), payload)
    digest = hmac.new(_KEY, signed, hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode()


def test_valid_signature_passes() -> None:
    payload = b'{"type":"user.created"}'
    ts = "1700000000"
    sig = _sign("msg_1", ts, payload)
    # Must not raise.
    svix.verify(
        secret=_SECRET,
        payload=payload,
        svix_id="msg_1",
        svix_timestamp=ts,
        svix_signature=sig,
        now=1700000010,  # 10s later, inside tolerance
    )


def test_tampered_payload_is_rejected() -> None:
    ts = "1700000000"
    sig = _sign("msg_1", ts, b'{"type":"user.created"}')
    with pytest.raises(svix.SvixVerificationError):
        svix.verify(
            secret=_SECRET,
            payload=b'{"type":"user.deleted"}',  # body changed after signing
            svix_id="msg_1",
            svix_timestamp=ts,
            svix_signature=sig,
            now=1700000010,
        )


def test_wrong_secret_is_rejected() -> None:
    payload = b"{}"
    ts = "1700000000"
    sig = _sign("msg_1", ts, payload)
    other = "whsec_" + base64.b64encode(b"a-different-key-entirely--------").decode()
    with pytest.raises(svix.SvixVerificationError):
        svix.verify(
            secret=other,
            payload=payload,
            svix_id="msg_1",
            svix_timestamp=ts,
            svix_signature=sig,
            now=1700000010,
        )


def test_stale_timestamp_is_rejected() -> None:
    payload = b"{}"
    ts = "1700000000"
    sig = _sign("msg_1", ts, payload)
    with pytest.raises(svix.SvixVerificationError):
        svix.verify(
            secret=_SECRET,
            payload=payload,
            svix_id="msg_1",
            svix_timestamp=ts,
            svix_signature=sig,
            now=1700000000 + 10_000,  # far outside the 5-min window → replay guard
        )


def test_missing_headers_are_rejected() -> None:
    with pytest.raises(svix.SvixVerificationError):
        svix.verify(
            secret=_SECRET,
            payload=b"{}",
            svix_id=None,
            svix_timestamp=None,
            svix_signature=None,
        )


async def test_webhook_refuses_when_unconfigured(client: AsyncClient) -> None:
    """No signing secret must fail closed (503), never accept unverified data."""
    assert settings.clerk_webhook_secret is None
    response = await client.post("/api/webhooks/clerk", content=b"{}")
    assert response.status_code == 503


async def test_webhook_rejects_bad_signature(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a secret set, a delivery with no/invalid signature is a 400."""
    monkeypatch.setattr(settings, "clerk_webhook_secret", _SECRET)
    response = await client.post(
        "/api/webhooks/clerk",
        content=b'{"type":"user.created"}',
        headers={
            "svix-id": "msg_1",
            "svix-timestamp": "1700000000",
            "svix-signature": "v1,not-a-real-signature",
        },
    )
    assert response.status_code == 400
