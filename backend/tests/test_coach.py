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


def test_system_prompt_forbids_inventing_numbers() -> None:
    """The single most important line in this package — assert it exists so it
    cannot be edited away silently."""
    assert "Never state a number that does not appear in the findings" in coach.SYSTEM_PROMPT


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


def test_no_api_key_yields_no_narrative_rather_than_an_error(monkeypatch) -> None:
    """The whole reason findings are computed rather than generated: with no
    model configured the feature still works."""
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    assert coach.generate_narrative([_finding()]) == (None, None)


def test_summarise_returns_findings_even_with_no_model(monkeypatch) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    payload = coach.summarise([_finding()])
    assert payload["narrative"] is None
    assert payload["model"] is None
    assert len(payload["findings"]) == 1
    # The finding still carries a complete sentence, so the UI has something to
    # render without any coaching voice.
    assert payload["findings"][0]["statement"]


def test_summarise_of_nothing_is_still_a_valid_payload(monkeypatch) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    assert coach.summarise([]) == {"findings": [], "narrative": None, "model": None}


# ------------------------------------------------------------ the request itself


class _Messages:
    """Records the request and answers happily, so the call runs to completion."""

    def __init__(self, captured: dict) -> None:
        self._captured = captured

    def parse(self, **kwargs):
        self._captured.update(kwargs)
        return _Answer()


class _Client:
    def __init__(self, captured: dict) -> None:
        self.messages = _Messages(captured)


class _Answer:
    stop_reason = "end_turn"
    parsed_output = CoachNarrative(
        headline="Squat is the story this week.",
        notes=[CoachNote(finding_kind="plateau", text="Deload and rebuild.")],
    )


@pytest.fixture
def request_kwargs(monkeypatch) -> dict:
    """Run `generate_narrative` against a stand-in client, return what it sent."""
    import anthropic

    captured: dict = {}
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    monkeypatch.setattr(anthropic, "Anthropic", lambda **_: _Client(captured))

    narrative, model = coach.generate_narrative([_finding()])
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
