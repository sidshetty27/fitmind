"""Turn verified findings into coaching prose.

The model's whole job is prioritisation and voice. It receives findings that are
already true — each one computed by `app.analysis.findings` from the user's own
logged sets — and is told, explicitly, that it may not compute anything new.

**Why the output is schema-constrained.** `client.messages.parse()` with a
Pydantic model means the response either validates or raises; there is no
half-parsed prose to sanitise and no free-text field where a hallucinated number
can hide unnoticed. The `headline` and `notes` are checked against the findings
they claim to reference before anything is stored.

**Why every failure path returns rather than raises.** A coaching narrative is a
nice-to-have on top of findings that already stand on their own. A missing API
key, a rate limit, a refusal, or a network blip should cost the user their
coaching *voice*, not their analysis — so `generate_narrative` returns `None` and
the caller stores the findings with `narrative = NULL`.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.analysis.findings import Finding
from app.core.config import settings

logger = logging.getLogger(__name__)

# Comfortably above any narrative this prompt can produce, and far below the
# model's ceiling — the cost control here is the small input, not a tight cap
# that would truncate a note mid-sentence.
MAX_TOKENS = 2000

# The findings are already ordered by priority and bounded in number, so there is
# no long-horizon reasoning to fund. `low` keeps latency and cost down on what is
# fundamentally a rewriting task.
EFFORT = "low"

SYSTEM_PROMPT = """\
You are a strength coach reviewing one athlete's recent training.

You will be given a list of FINDINGS. Each was computed directly from the \
athlete's logged workouts and is already true. Your job is to turn them into \
short, direct coaching — nothing else.

Rules, in order of importance:

1. Never state a number that does not appear in the findings. Do not compute, \
estimate, convert, or infer any figure. If you want to say something you cannot \
support from a finding, leave it out.
2. Never contradict a finding, and never soften one. A decline is a decline.
3. Prioritise. Lead with whatever most deserves the athlete's attention this \
week. You may leave a minor finding out entirely; you may not invent one.
4. Write like a coach talking to a lifter — plain, specific, second person. No \
preamble, no headings, no bullet characters, no emoji, no sign-off.
5. If the findings list is empty, say plainly that there is nothing notable in \
this window and that more sessions will give you something to work with.

Keep the headline under 100 characters. Write at most three notes, each one or \
two sentences.\
"""


class CoachNote(BaseModel):
    """One piece of advice, tied back to the finding that justifies it."""

    # Constrains the model to reference a finding it was actually given. A note
    # citing a `kind` outside the input is the clearest possible signal that it
    # drifted, and `_verify` rejects the whole narrative when it happens.
    finding_kind: str = Field(description="The `kind` of the finding this note is about.")
    text: str = Field(description="One or two sentences of direct coaching.")


class CoachNarrative(BaseModel):
    """The model's full output. Validated on arrival by the SDK."""

    headline: str = Field(description="A single short sentence summarising the week.")
    notes: list[CoachNote] = Field(default_factory=list, max_length=3)


def build_prompt(findings: list[Finding]) -> str:
    """Render findings as the model's entire factual world.

    Numbers are passed inside the pre-written `statement` rather than as loose
    figures for the model to recombine — the sentence is already correct, so the
    lowest-risk thing the model can do is reuse it.
    """
    if not findings:
        return "FINDINGS: (none — this athlete has no notable patterns in the window)"

    lines = ["FINDINGS:"]
    for index, finding in enumerate(findings, start=1):
        lines.append(f"{index}. [{finding.kind.value}] {finding.statement}")
    return "\n".join(lines)


def _verify(narrative: CoachNarrative, findings: list[Finding]) -> bool:
    """Reject a narrative that references a finding it was not given.

    Cheap, and it catches the failure mode that matters: a note invented about a
    movement or pattern that never appeared in the input. It cannot catch every
    fabricated number, which is exactly why the prompt hands over finished
    sentences rather than raw figures.
    """
    allowed = {finding.kind.value for finding in findings}
    unknown = {note.finding_kind for note in narrative.notes} - allowed
    if unknown:
        logger.warning("Coach narrative referenced unknown findings: %s", sorted(unknown))
        return False
    return True


def generate_narrative(findings: list[Finding]) -> tuple[str | None, str | None]:
    """Return `(narrative, model)`, or `(None, None)` when unavailable.

    Never raises. Callers store what they get: findings with a narrative when the
    model answered, findings alone when it did not.
    """
    if not settings.ai_enabled:
        return None, None

    try:
        import anthropic
    except ImportError:  # pragma: no cover - dependency is declared, not optional
        logger.warning("anthropic package is not installed; skipping narrative")
        return None, None

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    try:
        response = client.messages.parse(
            model=settings.anthropic_model,
            max_tokens=MAX_TOKENS,
            output_config={"effort": EFFORT},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_prompt(findings)}],
            output_format=CoachNarrative,
        )
    except anthropic.APIStatusError as exc:
        # Covers rate limits, auth failures, and server errors alike: none of
        # them should surface to a user who asked for their training summary.
        logger.warning("Coach model call failed (%s): %s", exc.status_code, exc.message)
        return None, None
    except anthropic.APIConnectionError:
        logger.warning("Coach model unreachable; returning findings only")
        return None, None

    # A safety decline arrives as a normal 200 with an empty or partial body, so
    # this has to be checked before touching the parsed output.
    if response.stop_reason == "refusal":
        logger.warning("Coach model declined to respond")
        return None, None

    narrative = response.parsed_output
    if narrative is None or not _verify(narrative, findings):
        return None, None

    return _render(narrative), settings.anthropic_model


def _render(narrative: CoachNarrative) -> str:
    """Flatten the structured narrative into the text stored on the analysis.

    Stored as prose rather than JSON because that is what the UI shows and what a
    user would quote back. The structure did its job at the boundary — forcing a
    shape the model had to fill and could be checked against.
    """
    parts = [narrative.headline.strip()]
    parts.extend(note.text.strip() for note in narrative.notes)
    return "\n\n".join(part for part in parts if part)


def summarise(findings: list[Finding]) -> dict[str, Any]:
    """One call for the route: findings as stored, plus a narrative if available."""
    narrative, model = generate_narrative(findings)
    return {
        "findings": [finding.as_dict() for finding in findings],
        "narrative": narrative,
        "model": model,
    }


__all__ = [
    "CoachNarrative",
    "CoachNote",
    "EFFORT",
    "MAX_TOKENS",
    "SYSTEM_PROMPT",
    "build_prompt",
    "generate_narrative",
    "summarise",
]
