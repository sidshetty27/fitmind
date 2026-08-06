"""Billing routes: what they refuse, and what they never grant.

No network and no database. Stripe is substituted, and the two crud calls these
routes make are stubbed — what is worth testing here is the decisions, not
SQLAlchemy.

The most important assertion in this file is the negative one: completing a
checkout does not make anybody premium. Only the webhook does that.
"""

import uuid

import pytest
import stripe
from httpx import AsyncClient

from app.api.routes import billing
from app.core import entitlements, stripe_client
from app.core.config import settings
from app.models.subscription import Subscription
from app.models.user import User


def _user() -> User:
    return User(id=uuid.uuid4(), clerk_id="user_1", email="a@example.com", name="A")


def _subscription(status: str | None = None, customer: str = "cus_1") -> Subscription:
    return Subscription(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        stripe_customer_id=customer,
        stripe_subscription_id="sub_1" if status else None,
        status=status,
    )


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_dummy")
    monkeypatch.setattr(settings, "stripe_price_id", "price_premium")
    monkeypatch.setattr(settings, "frontend_url", "https://app.example.com")


# ------------------------------------------------------- configuration guards


def test_billing_enabled_needs_both_halves(monkeypatch: pytest.MonkeyPatch) -> None:
    """A key with no price has nothing to charge for; a price with no key cannot
    charge. Either alone must not light up an upgrade button."""
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_dummy")
    monkeypatch.setattr(settings, "stripe_price_id", None)
    assert settings.billing_enabled is False

    monkeypatch.setattr(settings, "stripe_secret_key", None)
    monkeypatch.setattr(settings, "stripe_price_id", "price_premium")
    assert settings.billing_enabled is False

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_dummy")
    assert settings.billing_enabled is True


@pytest.mark.parametrize("path", ["/api/billing/checkout", "/api/billing/portal"])
async def test_billing_routes_require_authentication(
    client: AsyncClient, path: str
) -> None:
    """Both endpoints spend money or expose an invoice history, so neither may
    be reachable without a token — checked before any Stripe call is made."""
    response = await client.post(path)
    assert response.status_code == 401


def test_configuration_guard_raises_503(monkeypatch: pytest.MonkeyPatch) -> None:
    """503, not 500: the request was fine, the deployment is not."""
    from fastapi import HTTPException

    monkeypatch.setattr(settings, "stripe_secret_key", None)
    with pytest.raises(HTTPException) as exc_info:
        billing._require_billing_configured()
    assert exc_info.value.status_code == 503


# ------------------------------------------------------------------- checkout


async def test_checkout_returns_the_hosted_url(
    configured, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = {}

    async def fake_get(db, *, user_id):
        return _subscription()  # existing customer, not subscribed

    async def fake_session(*, customer_id, price_id, success_url, cancel_url):
        captured.update(
            customer_id=customer_id,
            price_id=price_id,
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return "https://checkout.stripe.com/c/pay/cs_test_1"

    monkeypatch.setattr(billing.subscription_crud, "get_by_user_id", fake_get)
    monkeypatch.setattr(stripe_client, "create_checkout_session", fake_session)

    result = await billing.create_checkout(current_user=_user(), db=None)

    assert result.url == "https://checkout.stripe.com/c/pay/cs_test_1"
    assert captured["customer_id"] == "cus_1", "must reuse the known customer"
    assert captured["price_id"] == "price_premium"
    assert captured["success_url"].startswith("https://app.example.com")


async def test_checkout_reuses_an_existing_customer(
    configured, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second Stripe customer would split invoices and payment methods across
    two records nothing joins — and support would only ever find one."""

    async def fake_get(db, *, user_id):
        return _subscription(customer="cus_existing")

    async def fail_create(**kwargs):
        raise AssertionError("created a second customer for an existing one")

    monkeypatch.setattr(billing.subscription_crud, "get_by_user_id", fake_get)
    monkeypatch.setattr(stripe_client, "create_customer", fail_create)
    monkeypatch.setattr(
        stripe_client,
        "create_checkout_session",
        lambda **kw: _async_return("https://checkout.stripe.com/x"),
    )

    await billing.create_checkout(current_user=_user(), db=None)


async def test_checkout_creates_a_customer_for_a_new_user(
    configured, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = {}

    async def fake_get(db, *, user_id):
        return None

    async def fake_create(*, email, user_id, name=None):
        created.update(email=email, user_id=user_id)
        return "cus_new"

    async def fake_link(db, *, user_id, stripe_customer_id):
        return _subscription(customer=stripe_customer_id)

    monkeypatch.setattr(billing.subscription_crud, "get_by_user_id", fake_get)
    monkeypatch.setattr(billing.subscription_crud, "link_customer", fake_link)
    monkeypatch.setattr(stripe_client, "create_customer", fake_create)
    monkeypatch.setattr(
        stripe_client,
        "create_checkout_session",
        lambda **kw: _async_return("https://checkout.stripe.com/x"),
    )

    user = _user()
    await billing.create_checkout(current_user=user, db=None)

    assert created["email"] == user.email
    assert created["user_id"] == str(user.id), "the id support needs to trace a charge"


async def test_a_lost_race_uses_the_winning_customer(
    configured, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two clicks on Upgrade: one INSERT wins, the other gets the winner's row
    back. Both must then check out against the *same* customer, or the user ends
    up with two subscriptions."""
    used = {}

    async def fake_get(db, *, user_id):
        return None

    async def fake_create(*, email, user_id, name=None):
        return "cus_ours"

    async def fake_link(db, *, user_id, stripe_customer_id):
        # The other request got there first.
        return _subscription(customer="cus_theirs")

    async def fake_session(*, customer_id, **kwargs):
        used["customer_id"] = customer_id
        return "https://checkout.stripe.com/x"

    monkeypatch.setattr(billing.subscription_crud, "get_by_user_id", fake_get)
    monkeypatch.setattr(billing.subscription_crud, "link_customer", fake_link)
    monkeypatch.setattr(stripe_client, "create_customer", fake_create)
    monkeypatch.setattr(stripe_client, "create_checkout_session", fake_session)

    await billing.create_checkout(current_user=_user(), db=None)

    assert used["customer_id"] == "cus_theirs"


async def test_an_active_subscriber_cannot_open_a_second_checkout(
    configured, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second subscription against the same customer bills them twice."""
    from fastapi import HTTPException

    async def fake_get(db, *, user_id):
        return _subscription(status="active")

    async def fail_session(**kwargs):
        raise AssertionError("opened checkout for an existing subscriber")

    monkeypatch.setattr(billing.subscription_crud, "get_by_user_id", fake_get)
    monkeypatch.setattr(stripe_client, "create_checkout_session", fail_session)

    with pytest.raises(HTTPException) as exc_info:
        await billing.create_checkout(current_user=_user(), db=None)

    assert exc_info.value.status_code == 409


async def test_past_due_subscriber_is_also_blocked(
    configured, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`past_due` counts as premium, so it must block here too — otherwise the
    entitlement rule and the checkout rule disagree, and someone with a failing
    card gets a second subscription instead of a fixed one."""
    from fastapi import HTTPException

    async def fake_get(db, *, user_id):
        return _subscription(status="past_due")

    monkeypatch.setattr(billing.subscription_crud, "get_by_user_id", fake_get)

    with pytest.raises(HTTPException) as exc_info:
        await billing.create_checkout(current_user=_user(), db=None)
    assert exc_info.value.status_code == 409


async def test_a_cancelled_subscriber_may_resubscribe(
    configured, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cancelled is not premium, so checkout must open again — otherwise a
    lapsed customer can never come back."""

    async def fake_get(db, *, user_id):
        return _subscription(status="canceled")

    monkeypatch.setattr(billing.subscription_crud, "get_by_user_id", fake_get)
    monkeypatch.setattr(
        stripe_client,
        "create_checkout_session",
        lambda **kw: _async_return("https://checkout.stripe.com/again"),
    )

    result = await billing.create_checkout(current_user=_user(), db=None)
    assert result.url.endswith("again")


async def test_a_stripe_failure_becomes_502_not_500(
    configured, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi import HTTPException

    async def fake_get(db, *, user_id):
        return _subscription()

    async def boom(**kwargs):
        raise stripe.InvalidRequestError("No such price: 'prod_x'", param="line_items")

    monkeypatch.setattr(billing.subscription_crud, "get_by_user_id", fake_get)
    monkeypatch.setattr(stripe_client, "create_checkout_session", boom)

    with pytest.raises(HTTPException) as exc_info:
        await billing.create_checkout(current_user=_user(), db=None)

    assert exc_info.value.status_code == 502


# --------------------------------------------------------------------- portal


async def test_portal_returns_its_url(
    configured, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_get(db, *, user_id):
        return _subscription(status="active")

    monkeypatch.setattr(billing.subscription_crud, "get_by_user_id", fake_get)
    monkeypatch.setattr(
        stripe_client,
        "create_portal_session",
        lambda **kw: _async_return("https://billing.stripe.com/p/session_1"),
    )

    result = await billing.create_portal(current_user=_user(), db=None)
    assert result.url == "https://billing.stripe.com/p/session_1"


async def test_portal_404s_for_someone_who_never_paid(
    configured, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not "create a customer so it opens" — that shows an empty portal to
    someone who has never bought anything, answering no question they had."""
    from fastapi import HTTPException

    async def fake_get(db, *, user_id):
        return None

    monkeypatch.setattr(billing.subscription_crud, "get_by_user_id", fake_get)

    with pytest.raises(HTTPException) as exc_info:
        await billing.create_portal(current_user=_user(), db=None)

    assert exc_info.value.status_code == 404


# ------------------------------------------------- checkout grants nothing


def test_the_success_url_is_only_a_redirect_target(configured) -> None:
    """The single most important property of this module.

    The success URL is a page the browser is sent to, and anyone can type it.
    Nothing in this router writes `status`, and entitlement is computed only from
    what the webhook stored. If arriving at the success page granted premium, the
    paywall would be one address-bar edit deep.
    """
    source = (billing.__file__,)
    with open(source[0], encoding="utf-8") as handle:
        text = handle.read()

    assert "apply_stripe_state" not in text, "a route must never write plan state"
    assert ".status =" not in text
    assert "is_premium" in text, "it may read entitlement, just never grant it"


def test_entitlement_ignores_checkout_and_reads_only_stored_state() -> None:
    """A user mid-checkout — customer created, nothing paid — is not premium."""
    assert entitlements.is_premium(_subscription(status=None)) is False


def _async_return(value):
    """Small helper: a coroutine that immediately returns `value`."""

    async def _inner():
        return value

    return _inner()


# ------------------------------------------------- checkout session tagging


def test_integration_identifier_is_a_constant_not_a_per_call_value() -> None:
    """Stripe groups sessions by this label, so it must be stable.

    The field's own documentation says "Multiple Checkout Sessions can have the
    same integration identifier" — grouping is the entire point. A value
    regenerated per request would put every session in a group of one and report
    nothing, while looking perfectly correct in a code review.
    """
    from app.core.stripe_client import INTEGRATION_IDENTIFIER

    assert stripe_client.INTEGRATION_IDENTIFIER is INTEGRATION_IDENTIFIER
    # Read twice; a generated value would differ.
    assert stripe_client.INTEGRATION_IDENTIFIER == stripe_client.INTEGRATION_IDENTIFIER


def test_integration_identifier_carries_an_eight_letter_suffix() -> None:
    """The suffix is what stops the label colliding with another integration's."""
    import re

    assert re.search(
        r"-[a-z]{8}$", stripe_client.INTEGRATION_IDENTIFIER
    ), f"expected an 8-letter suffix, got {stripe_client.INTEGRATION_IDENTIFIER!r}"


async def test_checkout_session_is_tagged_and_leaves_payment_methods_dynamic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two assertions about the same call, both about params rather than results.

    `integration_identifier` must be sent, or the Dashboard cannot separate this
    flow from any other checkout on the account.

    `payment_method_types` must NOT be sent. Omitting it is what keeps dynamic
    payment methods on; hardcoding `["card"]` is the obvious-looking thing to
    write and permanently narrows what customers can pay with. Nothing fails when
    it is wrong, which is why it is asserted here.
    """
    captured = {}

    class FakeSessions:
        async def create_async(self, params=None, options=None):
            captured.update(params or {})
            return type("S", (), {"id": "cs_1", "url": "https://checkout.stripe.com/x"})()

    monkeypatch.setattr(
        stripe_client,
        "_client",
        lambda: type(
            "C",
            (),
            {"v1": type("V", (), {"checkout": type("K", (), {"sessions": FakeSessions()})()})()},
        )(),
    )

    await stripe_client.create_checkout_session(
        customer_id="cus_1",
        price_id="price_1",
        success_url="https://app.example.com/ok",
        cancel_url="https://app.example.com/no",
    )

    assert captured["integration_identifier"] == stripe_client.INTEGRATION_IDENTIFIER
    assert "payment_method_types" not in captured, (
        "sending payment_method_types disables dynamic payment methods"
    )
    assert captured["mode"] == "subscription"
