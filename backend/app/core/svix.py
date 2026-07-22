"""Svix webhook signature verification, implemented from the spec.

Clerk delivers webhooks through Svix, which signs every request. We verify that
signature ourselves with the standard library rather than pulling in the `svix`
package: the scheme is small, stable, and security-critical, and owning ~40 lines
we can read beats depending on a wheel whose internals we would trust blindly for
exactly the check that keeps forged payloads out.

The scheme (https://docs.svix.com/receiving/verifying-payloads/how-manual):
  - Signed content is `{svix-id}.{svix-timestamp}.{raw-body}`.
  - The secret is `whsec_<base64>`; the bytes after the prefix are the HMAC key.
  - Signature = base64(HMAC-SHA256(key, signed_content)).
  - The `svix-signature` header is a space-separated list of `v1,<sig>` entries
    (there can be several during secret rotation); a match against any is valid.
  - The timestamp is checked against a tolerance window to blunt replay attacks.

Comparisons use `hmac.compare_digest` so verification takes constant time and
cannot be turned into a timing oracle.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

# How far the webhook timestamp may drift from our clock, in seconds. Five
# minutes is Svix's own default: wide enough for clock skew and delivery latency,
# tight enough that a captured request cannot be replayed indefinitely.
_TOLERANCE_SECONDS = 5 * 60


class SvixVerificationError(Exception):
    """Raised when a webhook cannot be trusted. Never leaks *why* to the caller."""


def _decode_secret(secret: str) -> bytes:
    """Turn a `whsec_...` secret into the raw HMAC key bytes."""
    raw = secret.split("_", 1)[1] if secret.startswith("whsec_") else secret
    return base64.b64decode(raw)


def verify(
    *,
    secret: str,
    payload: bytes,
    svix_id: str | None,
    svix_timestamp: str | None,
    svix_signature: str | None,
    now: float | None = None,
) -> None:
    """Verify a Svix-signed webhook. Returns None on success, raises otherwise.

    `payload` must be the raw request body **exactly as received** — re-encoding
    a parsed JSON body reorders keys and changes whitespace, which changes the
    signature and makes every delivery fail.
    """
    if not (svix_id and svix_timestamp and svix_signature):
        raise SvixVerificationError("missing Svix headers")

    # Reject stale (replayed) or future-dated deliveries.
    try:
        sent_at = int(svix_timestamp)
    except ValueError as exc:
        raise SvixVerificationError("bad timestamp") from exc
    current = now if now is not None else time.time()
    if abs(current - sent_at) > _TOLERANCE_SECONDS:
        raise SvixVerificationError("timestamp outside tolerance")

    key = _decode_secret(secret)
    signed_content = b"%s.%s.%s" % (
        svix_id.encode(),
        svix_timestamp.encode(),
        payload,
    )
    expected = base64.b64encode(hmac.new(key, signed_content, hashlib.sha256).digest())

    # The header may carry multiple space-separated `v1,<sig>` versions.
    for part in svix_signature.split():
        _, _, candidate = part.partition(",")
        if candidate and hmac.compare_digest(candidate.encode(), expected):
            return
    raise SvixVerificationError("no matching signature")
