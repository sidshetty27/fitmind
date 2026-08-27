"""AI coach tests — everything except the model call itself.

No network and no API key: what is worth testing here is the boundary around the
model, not the model. Specifically that findings reach it as finished sentences,
that a narrative referencing something it was never given is rejected, and that
every unavailable-model path degrades to findings rather than raising.

The last section is the one exception, and substitutes the client. Some of the
request's settings cannot be checked any other way, and getting them wrong fails
*silently* — down the same path as a missing API key, so nothing raises and the
page still renders. A test is the only thing that would notice.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.ai import coach
from app.ai.coach import CoachNarrative, CoachNote
from app.analysis.findings import Finding, FindingKind
from app.core.config import settings


def _finding(kind: FindingKind = FindingKind.PLATEAU, statement: str = "Squat stalled.") -> Finding:
    return Finding(kind, "Barbell Back Squat", statement, {"change_pct": "-3.13"})


# ------------------------------------------------------------------- the prompt


def test_prompt_carries_the_finished_sentence_not_raw_numbers() -> None:
    """The model reuses a sentence that is already correct; it never recombines
    figures into a new claim."""
    prompt = coach.build_prompt(
        [_finding(statement="Your squat is down 3.13% across 7 sessions.")]
    )
    assert "Your squat is down 3.13% across 7 sessions." in prompt
    assert "plateau" in prompt


def test_prompt_numbers_every_finding() -> None:
    prompt = coach.build_prompt(
        [
            _finding(FindingKind.STALE_MUSCLE_GROUP, "You haven't trained calves in 40 days."),
            _finding(FindingKind.PLATEAU, "Squat has stalled."),
        ]
    )
    assert "1. [stale_muscle_group]" in prompt
    assert "2. [plateau]" in prompt


def test_empty_findings_still_produce_a_usable_prompt() -> None:
    """A quiet week is a real answer, not a reason to skip the call."""
    prompt = coach.build_prompt([])
    assert "none" in prompt.lower()


def test_system_prompt_forbids_inventing_numbers_about_the_training() -> None:
    """The single most important line in this package — assert it exists so it
    cannot be edited away silently.

    Scoped to the athlete's *training* deliberately. The original wording forbade
    any number at all, which real narratives broke the moment they recommended a
    training frequency ("get them back in twice a week"). A rule that every output
    quietly violates teaches you to stop reading it; this one draws the line where
    the guarantee actually matters.
    """
    assert (
        "Never state a number about the athlete's training that does not appear "
        "in the findings" in coach.SYSTEM_PROMPT
    )


def test_system_prompt_leaves_recommendation_numbers_to_the_model() -> None:
    """The other half of that rule. Sets, reps and frequencies are advice rather
    than claims about what the athlete did, and no finding could support them —
    so forbidding them would forbid coaching."""
    assert "are yours to choose" in coach.SYSTEM_PROMPT


# -------------------------------------------------------------- the verifier


def test_narrative_referencing_only_given_findings_is_accepted() -> None:
    narrative = CoachNarrative(
        headline="Squat needs attention.",
        notes=[CoachNote(finding_kind="plateau", text="Drop the weight and rebuild.")],
    )
    assert coach._verify(narrative, [_finding(FindingKind.PLATEAU)]) is True


def test_narrative_inventing_a_finding_is_rejected() -> None:
    """The failure that matters: coaching about a pattern the athlete's data
    never showed."""
    narrative = CoachNarrative(
        headline="Good week.",
        notes=[CoachNote(finding_kind="ready_to_progress", text="Add 2.5 kg to your bench.")],
    )
    assert coach._verify(narrative, [_finding(FindingKind.PLATEAU)]) is False


def test_a_headline_with_no_notes_is_fine() -> None:
    """Nothing to reference means nothing to get wrong."""
    narrative = CoachNarrative(headline="Nothing notable this window.", notes=[])
    assert coach._verify(narrative, []) is True


def test_notes_are_capped_so_the_coach_stays_readable() -> None:
    with pytest.raises(ValueError):
        CoachNarrative(
            headline="Too much.",
            notes=[CoachNote(finding_kind="plateau", text=str(i)) for i in range(4)],
        )


# ------------------------------------------------------------------ rendering


def test_rendering_joins_headline_and_notes_as_prose() -> None:
    rendered = coach._render(
        CoachNarrative(
            headline="Squat is the story this week.",
            notes=[
                CoachNote(finding_kind="plateau", text="It's down across seven sessions."),
                CoachNote(finding_kind="plateau", text="Deload and rebuild."),
            ],
        )
    )
    assert rendered.startswith("Squat is the story this week.")
    assert "Deload and rebuild." in rendered
    assert "\n\n" in rendered


# ------------------------------------------------------------ graceful degrading


async def test_no_api_key_yields_no_narrative_rather_than_an_error(monkeypatch) -> None:
    """The whole reason findings are computed rather than generated: with no
    model configured the feature still works."""
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    assert await coach.generate_narrative([_finding()]) == (None, None)


async def test_summarise_returns_findings_even_with_no_model(monkeypatch) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    payload = await coach.summarise([_finding()])
    assert payload["narrative"] is None
    assert payload["model"] is None
    assert len(payload["findings"]) == 1
    # The finding still carries a complete sentence, so the UI has something to
    # render without any coaching voice.
    assert payload["findings"][0]["statement"]


async def test_summarise_of_nothing_is_still_a_valid_payload(monkeypatch) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    assert await coach.summarise([]) == {"findings": [], "narrative": None, "model": None}


# ------------------------------------------------------------ the request itself


class _Messages:
    """Records the request and answers happily, so the call runs to completion.

    `parse` is a coroutine, mirroring `AsyncAnthropic`. That is not cosmetic: if
    the code under test ever went back to calling it synchronously, it would get
    an un-awaited coroutine instead of an answer and the fixture would fail.
    """

    def __init__(self, captured: dict) -> None:
        self._captured = captured

    async def parse(self, **kwargs):
        self._captured.update(kwargs)
        return _Answer()


class _Client:
    def __init__(self, captured: dict) -> None:
        self.messages = _Messages(captured)
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _Answer:
    stop_reason = "end_turn"
    parsed_output = CoachNarrative(
        headline="Squat is the story this week.",
        notes=[CoachNote(finding_kind="plateau", text="Deload and rebuild.")],
    )


def _stand_in(monkeypatch, client: _Client) -> _Client:
    """Point the coach at `client`, and make the synchronous client a hard error.

    The second half is what keeps this suite hermetic. `AsyncAnthropic` is the
    only constructor stubbed, so code that built `anthropic.Anthropic` instead
    would sail past the stub and open a real connection to api.anthropic.com —
    turning a regression into a network call and a confusing 401 rather than the
    failure it actually is. ci.yml promises these tests need no network; this is
    the line that keeps that true when the code under test is wrong.
    """
    import anthropic

    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    monkeypatch.setattr(anthropic, "AsyncAnthropic", lambda **_: client)

    def _blocking_client(**_):
        raise AssertionError(
            "the coach built the synchronous Anthropic client — a model call on "
            "the event loop stalls every other request in the worker, /health "
            "included. Use anthropic.AsyncAnthropic and await the call."
        )

    monkeypatch.setattr(anthropic, "Anthropic", _blocking_client)
    return client


@pytest.fixture
async def request_kwargs(monkeypatch) -> dict:
    """Run `generate_narrative` against a stand-in client, return what it sent."""
    captured: dict = {}
    _stand_in(monkeypatch, _Client(captured))

    narrative, model = await coach.generate_narrative([_finding()])
    # If this fails the fixture is broken, not the thing under test.
    assert narrative and model, "the stand-in answers, so a narrative must come back"
    return captured


def _thinking_is_off(request_kwargs: dict) -> bool:
    """Whether this request actually disables thinking.

    A *missing* `thinking` key is not "off" — omitting the argument is precisely
    what leaves thinking on, so it has to read as on here or these tests would
    wave through the exact regression they exist to catch.
    """
    return request_kwargs.get("thinking", {}).get("type") == "disabled"


def test_thinking_is_off_so_the_budget_is_the_narrative_s_alone(request_kwargs) -> None:
    """`max_tokens` caps thinking *and* response text together, and thinking is on
    by default when the argument is omitted. Left on, it takes a share of a budget
    sized for prose."""
    assert _thinking_is_off(request_kwargs), (
        "the request does not disable thinking — an omitted `thinking` argument "
        "leaves it on, sharing MAX_TOKENS with the narrative"
    )


def test_the_budget_and_the_thinking_setting_stay_in_step(request_kwargs) -> None:
    """The regression worth catching: thinking turned back on without raising the
    budget it now shares. A run that spends the budget reasoning fails to parse and
    returns no narrative — through the same path as an unset API key, so nothing
    raises and it reads as "the key isn't working"."""
    if not _thinking_is_off(request_kwargs):
        assert request_kwargs["max_tokens"] >= 8000, (
            "thinking now shares max_tokens with the response; 2000 is a "
            "prose-sized budget, not a thinking-sized one"
        )


def test_effort_stays_low_enough_to_disable_thinking(request_kwargs) -> None:
    """Disabling thinking is only accepted at effort `high` or below — pairing it
    with `xhigh` or `max` is rejected at request time, which every other test here
    is too far from the wire to see."""
    if _thinking_is_off(request_kwargs):
        assert request_kwargs["output_config"]["effort"] in {"low", "medium", "high"}


# --------------------------------------------------------- not on the event loop


async def test_the_model_call_never_blocks_the_event_loop(monkeypatch) -> None:
    """The regression that gets a healthy container killed.

    The API serves on one uvicorn worker, so a synchronous client here does not
    block a thread — it blocks the *event loop*, queueing every other request in
    the process behind a model call that takes seconds. Render's `/health` probe
    is one of those requests, and its timeout is what decides whether the
    container is restarted. `health.py` keeps that probe free of database I/O for
    exactly this reason; a blocking call here defeats it from the other side.

    Constructing `anthropic.Anthropic` is the whole of the regression, so that is
    what this catches — directly, rather than by timing something flaky.
    """
    _stand_in(monkeypatch, _Client({}))

    narrative, model = await coach.generate_narrative([_finding()])
    assert narrative and model


async def test_the_client_is_closed_so_connection_pools_do_not_accumulate(
    monkeypatch,
) -> None:
    """Each call builds its own client, and each client owns an httpx pool. Left
    unclosed they pile up for the life of the process — a slow leak on a 512MB
    instance rather than an untidiness."""
    client = _stand_in(monkeypatch, _Client({}))

    await coach.generate_narrative([_finding()])
    assert client.closed, "the Anthropic client was never closed"


# ------------------------------------------------------------------- settings


def test_ai_disabled_without_a_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    assert settings.ai_enabled is False


def test_ai_enabled_with_a_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    assert settings.ai_enabled is True


def test_the_model_is_pinned_in_config_not_hardcoded() -> None:
    """`ai_analyses.model` records which model wrote each note, so the id has to
    be configurable rather than buried in a call site."""
    assert settings.anthropic_model
    assert isinstance(settings.anthropic_model, str)


# --------------------------------------------------------------- the pay gate


def test_only_running_an_analysis_is_metered() -> None:
    """POST is gated, both GETs are not — asserted at the dependency, which is
    where the enforcement actually lives.

    A free user who has spent today's allowance must still be able to open the
    Coach page and read every analysis they have already run. Metering a GET
    would take away something already paid for, which is a different and much
    worse thing than declining to give more.

    Checked by inspecting the resolved dependencies rather than by calling the
    routes, because the failure this guards against is someone adding
    `require_ai_quota` to a read path — or dropping it from the write path —
    and nothing else noticing.
    """
    from app.core.entitlements import require_ai_quota
    from app.main import app

    gated = {}
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/coach"):
            continue
        calls = {d.call for d in route.dependant.dependencies}
        for method in route.methods:
            gated[(method, path)] = require_ai_quota in calls

    assert gated[("POST", "/api/coach/analyses")] is True, "the paid action is free"
    assert gated[("GET", "/api/coach/analyses")] is False, "reading history is metered"
    assert (
        gated[("GET", "/api/coach/analyses/{analysis_id}")] is False
    ), "reading one past analysis is metered"


# ------------------------------------------------------- the refusal on the wire


@pytest.fixture
def rate_limited_app(monkeypatch):
    """The coach endpoint with a full capacity ceiling and no database.

    Overrides only the two edges — who is calling, and the session — and lets
    `require_ai_quota` run for real against stubbed counts. The point is to
    exercise the path a client actually meets, which the policy tests deliberately
    do not: they call the dependency as a function, where a response header does
    not exist yet.
    """
    import uuid

    from app.core import entitlements
    from app.core.auth import get_current_user
    from app.core.config import settings
    from app.db.session import get_db
    from app.main import app
    from app.models.user import User

    user = User(id=uuid.uuid4(), clerk_id="user_test", email="t@example.com")

    async def _count_all_since(db, *, since):
        return settings.ai_rate_limit_global_daily

    async def _oldest_all(db, *, since):
        # Twenty minutes into a day-long window, so Retry-After is a real
        # interval rather than the window's full length.
        from datetime import datetime, timedelta, timezone

        return datetime.now(timezone.utc) - timedelta(minutes=20)

    monkeypatch.setattr(entitlements.analysis_crud, "count_all_since", _count_all_since)
    monkeypatch.setattr(
        entitlements.analysis_crud, "oldest_created_at_all_since", _oldest_all
    )

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: None
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


async def test_a_rate_limited_run_answers_429_with_a_usable_retry_after(
    client, rate_limited_app
) -> None:
    """`HTTPException(headers=...)` reaching the wire is the part worth proving.

    A Retry-After the dependency sets and the framework drops would leave the
    limiter looking correct in every unit test and still teaching clients to
    retry immediately — which is the failure the header exists to prevent.
    """
    response = await client.post("/api/coach/analyses")

    assert response.status_code == 429
    assert "retry-after" in response.headers, "the header never reached the client"

    retry_after = int(response.headers["retry-after"])
    assert retry_after > 0

    detail = response.json()["detail"]
    assert detail["code"] == "ai_capacity_reached"
    assert detail["retry_after_seconds"] == retry_after
    # A refusal that names the deployment's ceiling must not read as a billing
    # problem — nothing this user can buy would change the answer.
    assert "upgrade" not in detail["message"].lower()
