"""CORS — the allow-list, and the preview-origin pattern beside it.

Phase 9 shipped CORS with no test at all, which is a strange gap for the one
setting whose failure mode is "the deployed app cannot talk to its own API".
Both directions matter and only one of them is visible in normal use: an
allow-list that is too narrow breaks the app loudly on the first request, while
one that is too wide breaks nothing and hands another origin the ability to call
this API with a signed-in user's credentials.

`CORS_ORIGIN_REGEX` exists because Vercel generates a hostname per branch, so
preview deployments cannot be listed literally. It is also the setting most
likely to be written too broadly — `.*\\.vercel\\.app` looks scoped and is not —
which is why the validator gets more tests here than the middleware does.
"""

import re

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.main import app

# The pattern `config.py` and `docs/deployment.md` both recommend. Tested rather
# than merely written down: it is the thing a reader will copy, so if it does not
# actually match a Vercel preview origin, the documentation is the bug.
DOCUMENTED_PATTERN = r"^https://fitmind-git-[a-z0-9-]+-myteam\.vercel\.app$"

# A real preview origin's shape: project, `-git-`, the branch slug, the team.
PREVIEW_ORIGIN = "https://fitmind-git-feature-deployment-myteam.vercel.app"

# Origins that must never be allowed, whatever the pattern says.
#
# The third is the interesting one: a well-formed `vercel.app` subdomain that
# simply belongs to someone else. It is what `.*\.vercel\.app` lets in, and it
# is invisible to every probe aimed at obviously-hostile hostnames.
#
# The last is suffix confusion — a hostname ending in the attacker's domain that
# contains the one being allowed.
HOSTILE_ORIGINS = [
    "https://evil.example",
    "https://vercel.app",
    "https://someone-elses-app.vercel.app",
    "https://fitmind.vercel.app.evil.example",
]


def _settings(**overrides) -> Settings:
    """Build a Settings with the required database URL already supplied."""
    return Settings(database_url="postgresql://u:p@127.0.0.1:5432/db", **overrides)


# --------------------------------------------------------------- the allow-list


async def test_a_listed_origin_is_allowed(client) -> None:
    response = await client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


async def test_an_unlisted_origin_gets_no_allow_header(client) -> None:
    """The check that proves the allow-list is enforced rather than decorative.

    A browser refuses the response when this header is absent, which is the
    whole mechanism — the request still reaches the API and is still answered.
    """
    response = await client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


async def test_an_unlisted_origin_is_refused_at_the_preflight(client) -> None:
    """Preflight is where a real cross-origin POST is stopped, before the request
    with the user's token is ever sent."""
    response = await client.options(
        "/api/workouts",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in response.headers


async def test_a_refused_origin_gets_no_usable_grant(client) -> None:
    """Starlette sends `access-control-allow-credentials: true` on this response
    even though the origin is refused, which looks alarming and is not.

    The header grants nothing on its own. A browser only exposes a cross-origin
    response when `access-control-allow-origin` names the requesting origin, and
    with credentials in play it must name it exactly — a `*` is rejected outright.
    Absent that header the response is unreadable and the credentials header has
    nothing to apply to.

    Pinned as a test because the alternative is rediscovering it in a DevTools
    console during an incident and mistaking it for the hole it resembles.
    """
    response = await client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


# ------------------------------------------------------- the preview-origin regex


def test_the_documented_pattern_matches_a_real_preview_origin() -> None:
    """The example in config.py and docs/deployment.md, actually run."""
    assert re.fullmatch(DOCUMENTED_PATTERN, PREVIEW_ORIGIN)


@pytest.mark.parametrize("origin", HOSTILE_ORIGINS)
def test_the_documented_pattern_matches_nothing_hostile(origin: str) -> None:
    assert not re.fullmatch(DOCUMENTED_PATTERN, origin)


def test_the_documented_pattern_is_accepted_by_the_validator() -> None:
    """The guard must not reject the thing the docs tell you to write."""
    assert _settings(cors_origin_regex=DOCUMENTED_PATTERN).cors_origin_regex


def test_no_pattern_is_the_default_and_stays_valid() -> None:
    assert _settings().cors_origin_regex is None


@pytest.mark.parametrize(
    "pattern",
    [
        ".*",
        ".+",
        r".*\.vercel\.app",
        r"https://.*\.vercel\.app",
    ],
)
def test_an_overly_broad_pattern_is_refused_at_boot(pattern: str) -> None:
    """Each of these fullmatches, so anchoring does not save them.

    `.*\\.vercel\\.app` is the one worth naming: it reads as "our previews" and
    means "any deployment any Vercel user has ever created". Refusing at boot
    rather than at the first preflight is deliberate — a too-wide CORS rule
    produces no error, no failed request, and nothing to notice.
    """
    with pytest.raises(ValidationError, match="too broad"):
        _settings(cors_origin_regex=pattern)


def test_an_invalid_pattern_is_refused_at_boot() -> None:
    """An unparseable regex would otherwise raise inside the middleware on the
    first request that carried an Origin header."""
    with pytest.raises(ValidationError, match="not a valid regular expression"):
        _settings(cors_origin_regex="^https://fitmind-[a-z(.vercel\\.app$")


# ------------------------------------------------------------------- the wiring


def test_the_pattern_reaches_the_middleware() -> None:
    """The validator is only worth anything if the value it guards is the value
    Starlette actually matches against.

    Asserted on the app's middleware stack rather than through a request because
    the app is built once at import from the ambient settings; this reads the
    same wiring a request would use, without rebuilding it.
    """
    cors = next(m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware")
    assert cors.kwargs["allow_origin_regex"] == settings.cors_origin_regex
    assert cors.kwargs["allow_origins"] == settings.cors_origins_list
