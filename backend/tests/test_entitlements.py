"""Entitlement policy — who is premium, and what the free tier allows.

No database. Everything here is either a pure function over a row, or the policy
in `quota_state` with its two data-access calls stubbed out. That is deliberate:
the questions worth testing are *decisions* ("is `past_due` still premium?",
"does an unknown status grant access?"), and a live Postgres would add setup cost
without making any of those answers more certain.

The rule these tests exist to protect is that money decisions fail toward *not*
giving the product away, and never toward locking a paying customer out.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.core import entitlements
from app.core.config import settings
from app.core.entitlements import QuotaState, is_premium, quota_state, require_ai_quota
from app.models.subscription import Subscription
from app.models.user import User


def _subscription(status: str | None) -> Subscription:
    """An unattached row. No session needed to ask what a status means."""
    return Subscription(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        stripe_customer_id="cus_test",
        stripe_subscription_id="sub_test" if status else None,
        status=status,
    )


def _user() -> User:
    return User(id=uuid.uuid4(), clerk_id="user_test", email="t@example.com")


# --------------------------------------------------------------------- premium


def test_no_subscription_row_is_free_tier_not_an_error() -> None:
    """The ordinary state of everyone who never opened checkout."""
    assert is_premium(None) is False


def test_customer_without_a_subscription_is_not_premium() -> None:
    """Opening checkout and abandoning it creates a row with a NULL status."""
    assert is_premium(_subscription(None)) is False


@pytest.mark.parametrize("status", ["active", "trialing"])
def test_paying_and_trialing_users_are_premium(status: str) -> None:
    assert is_premium(_subscription(status)) is True


def test_past_due_keeps_access() -> None:
    """The judgement call, asserted so it cannot be "tidied" without a decision.

    `past_due` means a renewal failed and Stripe is still retrying — for days.
    Revoking here would lock a paying customer out of their own training history
    over an expired card that Stripe is likely about to charge successfully.
    """
    assert is_premium(_subscription("past_due")) is True


@pytest.mark.parametrize(
    "status", ["incomplete", "incomplete_expired", "canceled", "unpaid", "paused"]
)
def test_known_non_paying_statuses_are_not_premium(status: str) -> None:
    assert is_premium(_subscription(status)) is False


def test_unknown_status_is_not_premium_and_says_so_loudly(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Stripe can add statuses. Refusing to guess is the honest response.

    The warning is the load-bearing half: it is what turns "a customer insists
    they paid" into a one-line fix instead of an investigation.
    """
    with caplog.at_level(logging.WARNING):
        assert is_premium(_subscription("some_new_stripe_status")) is False

    assert "some_new_stripe_status" in caplog.text
    assert "PREMIUM_STATUSES" in caplog.text


def test_decided_statuses_do_not_warn(caplog: pytest.LogCaptureFixture) -> None:
    """Only genuinely unrecognised values are worth waking someone for."""
    with caplog.at_level(logging.WARNING):
        is_premium(_subscription("canceled"))
    assert caplog.text == ""


# ------------------------------------------------------------------ quota maths


def test_remaining_counts_down_and_floors_at_zero() -> None:
    assert QuotaState(False, 3, 0, None).remaining == 3
    assert QuotaState(False, 3, 2, None).remaining == 1
    # Over-count is possible if the limit is lowered while someone is mid-window.
    assert QuotaState(False, 3, 9, None).remaining == 0


def test_premium_remaining_is_the_unlimited_sentinel() -> None:
    assert QuotaState(True, 3, 0, None).remaining == -1
    assert QuotaState(True, 3, 0, None).unlimited is True


def test_exceeded_only_at_the_limit() -> None:
    assert QuotaState(False, 3, 2, None).exceeded is False
    assert QuotaState(False, 3, 3, None).exceeded is True


def test_premium_is_never_exceeded() -> None:
    assert QuotaState(True, 3, 999, None).exceeded is False


# ----------------------------------------------------------------- quota_state


@pytest.fixture
def stub_crud(monkeypatch: pytest.MonkeyPatch):
    """Substitute the data-access calls the entitlement checks make.

    Four now rather than two: `require_ai_quota` consults the rate limits before
    the quota, and those read a global count as well as a per-user one. The
    global default of zero keeps every quota test reading as it did — the
    ceiling is not what those tests are about, and a rate limit that fired
    during them would mask the thing they assert.
    """

    calls = {"count": 0, "global_count": 0}

    def configure(
        *,
        subscription: Subscription | None,
        used: int,
        oldest=None,
        global_used: int = 0,
        global_oldest=None,
        hourly_used: int | None = None,
    ):
        async def fake_get_by_user_id(db, *, user_id):
            return subscription

        async def fake_count_since(db, *, user_id, since):
            # One crud function, two callers asking about two different windows:
            # the rate limit over an hour, the quota over a day. `hourly_used`
            # lets a test set them apart — a premium account can be far over the
            # day's count and perfectly well behaved this minute, which is the
            # exact case that separates the two rules.
            calls["count"] += 1
            if hourly_used is not None and (
                datetime.now(timezone.utc) - since < entitlements.QUOTA_WINDOW
            ):
                return hourly_used
            return used

        async def fake_oldest(db, *, user_id, since):
            return oldest

        async def fake_count_all_since(db, *, since):
            calls["global_count"] += 1
            return global_used

        async def fake_oldest_all(db, *, since):
            return global_oldest

        monkeypatch.setattr(
            entitlements.subscription_crud, "get_by_user_id", fake_get_by_user_id
        )
        monkeypatch.setattr(
            entitlements.analysis_crud, "count_since", fake_count_since
        )
        monkeypatch.setattr(
            entitlements.analysis_crud, "oldest_created_at_since", fake_oldest
        )
        monkeypatch.setattr(
            entitlements.analysis_crud, "count_all_since", fake_count_all_since
        )
        monkeypatch.setattr(
            entitlements.analysis_crud,
            "oldest_created_at_all_since",
            fake_oldest_all,
        )
        return calls

    return configure


async def test_free_user_under_the_limit_may_run(stub_crud) -> None:
    stub_crud(subscription=None, used=1)
    state = await quota_state(None, user=_user())

    assert state.premium is False
    assert state.used == 1
    assert state.exceeded is False
    assert state.resets_at is None


async def test_premium_short_circuits_before_counting(stub_crud) -> None:
    """An unlimited plan makes the count irrelevant — so it is not paid for."""
    calls = stub_crud(subscription=_subscription("active"), used=99)
    state = await quota_state(None, user=_user())

    assert state.premium is True
    assert state.exceeded is False
    assert calls["count"] == 0, "counted analyses for a user with no limit"


async def test_reset_time_comes_from_the_oldest_run_in_the_window(stub_crud) -> None:
    """The oldest run is the one whose expiry frees the next slot."""
    oldest = datetime.now(timezone.utc) - timedelta(hours=20)
    stub_crud(subscription=None, used=3, oldest=oldest)

    state = await quota_state(None, user=_user())

    assert state.exceeded is True
    assert state.resets_at == oldest + timedelta(days=1)


async def test_reset_time_is_not_computed_below_the_limit(stub_crud) -> None:
    """Nothing to reset yet, so nothing to explain — and one less query."""
    stub_crud(subscription=None, used=1, oldest=datetime.now(timezone.utc))
    state = await quota_state(None, user=_user())
    assert state.resets_at is None


# ------------------------------------------------------------ require_ai_quota


async def test_dependency_returns_the_user_when_allowed(stub_crud) -> None:
    """It stands in for `get_current_user`, so it must hand back the same row."""
    stub_crud(subscription=None, used=0)
    user = _user()

    assert await require_ai_quota(current_user=user, db=None) is user


async def test_dependency_refuses_with_402_and_a_machine_readable_body(
    stub_crud,
) -> None:
    """402 not 429: the remedy is to pay, not to wait.

    The body is a dict so the frontend can branch on `code` rather than parse
    prose — the copy has to be reworded eventually, the contract should not be.
    """
    oldest = datetime.now(timezone.utc) - timedelta(hours=6)
    stub_crud(subscription=None, used=3, oldest=oldest)

    with pytest.raises(HTTPException) as exc_info:
        await require_ai_quota(current_user=_user(), db=None)

    assert exc_info.value.status_code == 402
    detail = exc_info.value.detail
    assert detail["code"] == entitlements.QUOTA_ERROR_CODE
    assert detail["limit"] == settings.free_daily_ai_analyses
    assert detail["used"] == 3
    assert detail["resets_at"] == (oldest + timedelta(days=1)).isoformat()


async def test_premium_user_is_never_refused_by_the_quota(stub_crud) -> None:
    """"Unlimited" means the allowance does not apply, at any count.

    `hourly_used=0` isolates that claim. Ten thousand runs in a day is over every
    threshold in the file, and a premium account is still owed a yes from the
    *quota* — which is a different question from whether it may have them all in
    the next sixty seconds. The test below is that question.
    """
    stub_crud(subscription=_subscription("active"), used=10_000, hourly_used=0)
    user = _user()
    assert await require_ai_quota(current_user=user, db=None) is user


async def test_a_zero_limit_makes_the_coach_premium_only(
    stub_crud, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`FREE_DAILY_AI_ANALYSES=0` is documented in .env.example as the way to put
    the coach entirely behind the paywall. Asserted so the documentation stays
    true — an off-by-one here would silently hand out one free run."""
    monkeypatch.setattr(settings, "free_daily_ai_analyses", 0)
    stub_crud(subscription=None, used=0)

    with pytest.raises(HTTPException) as exc_info:
        await require_ai_quota(current_user=_user(), db=None)

    assert exc_info.value.status_code == 402


# ------------------------------------------------------------------ rate limits
#
# The coach is the only endpoint here that spends money per call, and the quota
# above cannot bound that spend: signing up is free, so an attacker never needs
# to exceed anyone's allowance — they need more accounts, and each arrives with
# a fresh one. These limits are the part that does not scale with account count.


async def test_a_premium_user_is_still_rate_limited(stub_crud) -> None:
    """The security property the whole change exists for.

    Premium is exempt from the quota because the quota is pricing. It is not
    exempt from a rate limit, because that is cost control — and an unlimited
    plan is a promise about a day's work, not a licence to run a paid endpoint
    in a loop. A regression here reads as a generous feature rather than a bug,
    which is why it is pinned rather than left to the shape of the code.
    """
    stub_crud(
        subscription=_subscription("active"),
        used=0,
        hourly_used=settings.ai_rate_limit_per_user_hourly,
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_ai_quota(current_user=_user(), db=None)

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == entitlements.RATE_LIMIT_ERROR_CODE


async def test_the_global_ceiling_refuses_a_user_who_is_well_within_quota(
    stub_crud,
) -> None:
    """The limit an attacker cannot widen by making more accounts.

    This user has run nothing and has their whole allowance. They are refused
    anyway, because the deployment has spent its day's model calls — which is
    the only framing that bounds the bill.
    """
    stub_crud(
        subscription=None,
        used=0,
        global_used=settings.ai_rate_limit_global_daily,
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_ai_quota(current_user=_user(), db=None)

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == entitlements.CAPACITY_ERROR_CODE


async def test_the_ceiling_is_checked_before_the_quota(stub_crud) -> None:
    """A free user over their allowance, while the deployment is also at its
    ceiling, is told to wait rather than to pay.

    Selling an upgrade for a call that the ceiling would refuse anyway is the
    wrong answer in the most expensive possible way — it takes money for
    something that does not work.
    """
    stub_crud(
        subscription=None,
        used=settings.free_daily_ai_analyses,
        global_used=settings.ai_rate_limit_global_daily,
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_ai_quota(current_user=_user(), db=None)

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == entitlements.CAPACITY_ERROR_CODE


async def test_a_refusal_carries_a_retry_after_a_client_can_act_on(
    stub_crud,
) -> None:
    """Both halves: the header a machine reads, and the number a human is shown.

    Without a `Retry-After` a client that retries has no basis for choosing
    when, and the usual choice is immediately — turning one refused request into
    a hot loop against the endpoint the limit is protecting.
    """
    oldest = datetime.now(timezone.utc) - timedelta(minutes=20)
    stub_crud(
        subscription=_subscription("active"),
        used=0,
        hourly_used=settings.ai_rate_limit_per_user_hourly,
        oldest=oldest,
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_ai_quota(current_user=_user(), db=None)

    retry_after = int(exc_info.value.headers["Retry-After"])
    # The oldest run ages out of the hour-long window forty minutes from now.
    assert 2340 <= retry_after <= 2400
    assert exc_info.value.detail["retry_after_seconds"] == retry_after


async def test_the_ceiling_costs_one_query_not_three(stub_crud) -> None:
    """A refusal is the cheap path on purpose.

    The global check describes the deployment, not the caller, so once it is
    full there is nothing a per-user count could add — and the requests most
    likely to hit it are the ones there are most of.
    """
    calls = stub_crud(
        subscription=None,
        used=0,
        global_used=settings.ai_rate_limit_global_daily,
    )

    with pytest.raises(HTTPException):
        await require_ai_quota(current_user=_user(), db=None)

    assert calls["global_count"] == 1
    assert calls["count"] == 0, "counted one user's runs after refusing everyone"


async def test_an_ordinary_run_passes_every_control(stub_crud) -> None:
    """The case that must keep working: nothing is over anything."""
    user = _user()
    stub_crud(subscription=None, used=1, hourly_used=1, global_used=5)
    assert await require_ai_quota(current_user=user, db=None) is user


async def test_the_ceiling_is_logged_loudly_enough_to_find(
    stub_crud, caplog: pytest.LogCaptureFixture
) -> None:
    """On a healthy deployment this never fires. When it does it is either an
    attack or a ceiling that has outgrown real traffic, and both are things you
    want to discover from a log rather than from a user."""
    stub_crud(
        subscription=None,
        used=0,
        global_used=settings.ai_rate_limit_global_daily,
    )

    with caplog.at_level(logging.WARNING, logger="app.core.entitlements"):
        with pytest.raises(HTTPException):
            await require_ai_quota(current_user=_user(), db=None)

    assert any(
        "AI_RATE_LIMIT_GLOBAL_DAILY" in record.message for record in caplog.records
    ), "the log line does not name the setting that fixes it"
