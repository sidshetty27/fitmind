"""Stripe webhook: signature handling, event routing, and the object mapping.

No network and no database. The endpoint tests reach only the paths that end
before a database session is opened, and the mapping tests run against **real**
`stripe.Subscription` objects built with `construct_from` rather than hand-rolled
fakes — a fake would agree with whatever `to_state` currently does, which is
precisely the thing under test.

The mapping is where the risk actually is. Everything else here is plumbing.
"""

import hashlib
import hmac
import json
import time

import pytest
import stripe
from httpx import AsyncClient

from app.api.routes import stripe_webhooks
from app.core import stripe_client
from app.core.config import settings
from app.core.stripe_client import to_state

_SECRET = "whsec_test_signing_secret"
_PERIOD_END = 1800000000  # 2027-01-15T08:00:00Z


def _sign(payload: bytes, timestamp: int | None = None) -> str:
    """Build a `Stripe-Signature` header the SDK will accept.

    Stripe signs `"{timestamp}.{body}"` with the whole `whsec_...` string as the
    HMAC key — the prefix included, unlike Svix which base64-decodes its secret.

    The timestamp must be *now*: `construct_event` enforces a 300-second replay
    tolerance against the system clock and offers no way to override it, so a
    hardcoded one would make every signature stale and every test here pass with
    a 400 for the wrong reason.
    """
    timestamp = int(time.time()) if timestamp is None else timestamp
    signed = f"{timestamp}.".encode() + payload
    digest = hmac.new(_SECRET.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def _subscription(
    *,
    status: str = "active",
    with_items: bool = True,
    cancel_at_period_end: bool = False,
) -> stripe.Subscription:
    items = (
        [
            {
                "id": "si_1",
                "object": "subscription_item",
                "current_period_end": _PERIOD_END,
                "price": {"id": "price_premium", "object": "price"},
            }
        ]
        if with_items
        else []
    )
    return stripe.Subscription.construct_from(
        {
            "id": "sub_1",
            "object": "subscription",
            "customer": "cus_1",
            "status": status,
            "cancel_at_period_end": cancel_at_period_end,
            "items": {"object": "list", "data": items},
        },
        "sk_test",
    )


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "stripe_webhook_secret", _SECRET)
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_dummy")


@pytest.fixture
def unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    """The absence of configuration, stated rather than assumed.

    `settings` is loaded from `backend/.env`, so a test that just *hopes* Stripe
    is unset passes in CI (no `.env` there) and fails on any machine with real
    keys — and fails as a 400 from signature verification, which reads like a
    signing bug rather than a missing fixture. Pinning both halves to None makes
    the fail-closed path reachable wherever the suite runs.
    """
    monkeypatch.setattr(settings, "stripe_webhook_secret", None)
    monkeypatch.setattr(settings, "stripe_secret_key", None)


def _envelope(body: dict) -> dict:
    """Wrap an event body in the fields every real Stripe delivery carries.

    `object` is not decoration: `construct_event` reads it to tell a v1 event
    from a v2 one, and raises `AttributeError` if it is absent. A fixture without
    it fails in a way no real payload ever would.
    """
    return {"id": "evt_test", "object": "event", "data": {}, **body}


async def _post(client: AsyncClient, body: dict, *, sign: bool = True):
    payload = json.dumps(_envelope(body)).encode()
    headers = {"stripe-signature": _sign(payload)} if sign else {}
    return await client.post(
        "/api/webhooks/stripe", content=payload, headers=headers
    )


# ---------------------------------------------------------------- the mapping


def test_period_end_is_read_from_the_subscription_item() -> None:
    """The field moved off the subscription and onto its items.

    Code written from memory reads `subscription.current_period_end`, gets None,
    and stores a NULL period end. Nothing raises and nothing looks broken — the
    settings page just quietly stops saying when the plan renews. This test is
    the only thing that would notice.
    """
    state = to_state(_subscription())

    assert state.current_period_end is not None
    assert state.current_period_end.year == 2027
    assert state.current_period_end.tzinfo is not None, "must be timezone-aware"


def test_price_id_comes_from_the_item_too() -> None:
    assert to_state(_subscription()).price_id == "price_premium"


def test_maps_the_remaining_fields() -> None:
    state = to_state(_subscription(status="trialing", cancel_at_period_end=True))

    assert state.customer_id == "cus_1"
    assert state.subscription_id == "sub_1"
    assert state.status == "trialing"
    assert state.cancel_at_period_end is True


def test_an_itemless_subscription_still_maps_its_status() -> None:
    """Status is what gates access, so it must survive a shape we did not expect.

    Losing the renewal date is a cosmetic problem; losing the status would mean
    a paying customer stops being premium because of a missing nested field.
    """
    state = to_state(_subscription(with_items=False))

    assert state.status == "active"
    assert state.current_period_end is None
    assert state.price_id is None


def test_customer_is_read_whether_expanded_or_not() -> None:
    """`customer` is an id string normally and an object when expanded. Reading
    `.id` unconditionally works until the first unexpanded response arrives."""
    expanded = stripe.Subscription.construct_from(
        {
            "id": "sub_2",
            "object": "subscription",
            "customer": {"id": "cus_expanded", "object": "customer"},
            "status": "active",
            "cancel_at_period_end": False,
            "items": {"object": "list", "data": []},
        },
        "sk_test",
    )
    assert to_state(expanded).customer_id == "cus_expanded"


# --------------------------------------------------------------- event routing


def test_checkout_session_points_at_its_subscription() -> None:
    found = stripe_webhooks._subscription_id_from(
        "checkout.session.completed", {"id": "cs_1", "subscription": "sub_9"}
    )
    assert found == "sub_9", "must follow the reference, not use the session id"


def test_checkout_session_subscription_may_be_expanded() -> None:
    found = stripe_webhooks._subscription_id_from(
        "checkout.session.completed", {"id": "cs_1", "subscription": {"id": "sub_9"}}
    )
    assert found == "sub_9"


def test_subscription_events_use_their_own_id() -> None:
    found = stripe_webhooks._subscription_id_from(
        "customer.subscription.updated", {"id": "sub_3"}
    )
    assert found == "sub_3"


def test_a_one_off_payment_session_references_no_subscription() -> None:
    found = stripe_webhooks._subscription_id_from(
        "checkout.session.completed", {"id": "cs_1", "subscription": None}
    )
    assert found is None


# ------------------------------------------------------------------- endpoint


async def test_unconfigured_webhook_fails_closed(
    client: AsyncClient, unconfigured
) -> None:
    """No secret must mean "reject", never "trust whatever arrived"."""
    response = await _post(client, {"type": "customer.subscription.updated"})
    assert response.status_code == 503


async def test_bad_signature_is_rejected(client: AsyncClient, configured) -> None:
    response = await client.post(
        "/api/webhooks/stripe",
        content=b'{"type":"customer.subscription.updated"}',
        headers={"stripe-signature": f"t={int(time.time())},v1=deadbeef"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid signature"


async def test_missing_signature_is_rejected(client: AsyncClient, configured) -> None:
    response = await _post(
        client, {"type": "customer.subscription.updated"}, sign=False
    )
    assert response.status_code == 400


async def test_a_replayed_delivery_is_rejected(
    client: AsyncClient, configured
) -> None:
    """A correctly-signed body from an hour ago must still be refused.

    `verify_header` takes `tolerance=None` by default, which skips the timestamp
    check entirely — so this passes only because the call supplies it explicitly.
    Without that argument the signature still verifies and nothing looks wrong,
    which is what makes the omission worth a test rather than a comment.
    """
    payload = json.dumps(_envelope({"type": "customer.subscription.updated"})).encode()
    stale = _sign(payload, timestamp=int(time.time()) - 3600)

    response = await client.post(
        "/api/webhooks/stripe", content=payload, headers={"stripe-signature": stale}
    )
    assert response.status_code == 400


async def test_tampered_body_is_rejected(client: AsyncClient, configured) -> None:
    """Signed one payload, sent another — the case signatures exist to catch."""
    signature = _sign(json.dumps(_envelope({"type": "invoice.paid"})).encode())
    response = await client.post(
        "/api/webhooks/stripe",
        content=json.dumps(
            _envelope(
                {
                    "type": "customer.subscription.updated",
                    "data": {"object": {"id": "sub_x"}},
                }
            )
        ).encode(),
        headers={"stripe-signature": signature},
    )
    assert response.status_code == 400


async def test_irrelevant_events_are_acknowledged_without_calling_stripe(
    client: AsyncClient, configured, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stripe sends far more than we subscribe to. Ignoring is correct; 500ing
    on an unasked-for event would be worse than useless."""

    async def fail(*args, **kwargs):
        raise AssertionError("must not call Stripe for an irrelevant event")

    monkeypatch.setattr(stripe_client, "retrieve_subscription", fail)

    response = await _post(client, {"type": "invoice.payment_succeeded", "data": {}})
    assert response.status_code == 204


async def test_subscription_event_without_an_id_is_acknowledged(
    client: AsyncClient, configured, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail(*args, **kwargs):
        raise AssertionError("nothing to fetch")

    monkeypatch.setattr(stripe_client, "retrieve_subscription", fail)

    response = await _post(
        client,
        {
            "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_1", "subscription": None}},
        },
    )
    assert response.status_code == 204


async def test_a_failed_fetch_asks_stripe_to_retry(
    client: AsyncClient, configured, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The most important behaviour in this file.

    A 2xx tells Stripe the event is handled and it will never be resent. If a
    failed fetch were swallowed into a 204, that subscription change would be
    lost permanently — a cancellation that never takes effect, or an upgrade the
    customer paid for and never received.
    """

    async def boom(subscription_id: str):
        raise stripe.APIConnectionError("network down")

    monkeypatch.setattr(stripe_client, "retrieve_subscription", boom)

    response = await _post(
        client,
        {
            "type": "customer.subscription.updated",
            "data": {"object": {"id": "sub_1"}},
        },
    )
    assert response.status_code >= 500, "a lost event is worse than a retried one"


# ------------------------------------------------------- cancel on delete path


async def test_cancelling_an_already_cancelled_subscription_is_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stripe's error for this is a description of the state we wanted.

    Account deletion must not fail because billing had already stopped — that
    would block the delete, and Clerk would retry it forever.
    """

    class FakeSubscriptions:
        async def cancel_async(self, subscription_id: str):
            raise stripe.InvalidRequestError(
                "No such subscription: sub_gone", param="subscription"
            )

    monkeypatch.setattr(
        stripe_client,
        "_client",
        lambda: type(
            "C", (), {"v1": type("V", (), {"subscriptions": FakeSubscriptions()})()}
        )(),
    )

    # Must not raise.
    await stripe_client.cancel_subscription("sub_gone")


async def test_an_unexpected_stripe_error_still_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only "already gone" is benign. Anything else must reach the caller, so the
    account deletion aborts and Clerk retries rather than losing the record of a
    subscription that is still charging someone."""

    class FakeSubscriptions:
        async def cancel_async(self, subscription_id: str):
            raise stripe.InvalidRequestError("Invalid API key", param=None)

    monkeypatch.setattr(
        stripe_client,
        "_client",
        lambda: type(
            "C", (), {"v1": type("V", (), {"subscriptions": FakeSubscriptions()})()}
        )(),
    )

    with pytest.raises(stripe.InvalidRequestError):
        await stripe_client.cancel_subscription("sub_live")
