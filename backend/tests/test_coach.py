"""AI coach tests — everything except the model call itself.

No network, no API key, no mocking of the Anthropic client: what is worth testing
here is the boundary around the model, not the model. Specifically that findings
reach it as finished sentences, that a narrative referencing something it was
never given is rejected, and that every unavailable-model path degrades to
findings rather than raising.
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
