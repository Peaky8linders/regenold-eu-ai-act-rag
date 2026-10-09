"""R462 — a Cloudflare Access edge denial is NAMED in the wrapper error string.

Measured 2026-10-08 in production: every Stage-2 dial returned

    api_status_401: {"message":"Unauthorized. You don't have permission to
    view this. Please contact you

— truncated exactly one character past the point where it becomes legible, and
saying nothing about WHICH edge refused. Two different bugs hide behind it:

  * the Cloudflare Access edge refusing the service token (console/credential
    action), and
  * the wrapper app itself returning 401 (wrapper-side action).

R277 already reports ``cf_access.headers_attached`` on /healthz/llm, but the
error string is what lands in the logs, the stage-2 counters and every captured
row. These tests pin the note AND the backward-compatibility contract that made
it safe to add: ``api_status_401`` must stay at the start of the string, because
``app/engines/_graph_rag_impl.py`` keys the loud provider-outage branch off
``"api_status_401" in _err_low``. A named error that silently stopped matching
that branch would trade an unreadable outage for a silent one.
"""
from __future__ import annotations

import httpx
import pytest

from app.llm.openai_wrapper_provider import (
    OpenAIWrapperRequest,
    _cf_access_denial_note,
    _OpenAIWrapperProvider,
)

WRAPPER = "https://wrapper.antifragile-ai.net/v1"

# The real block page, abbreviated: <title> is Cloudflare's, and the visible
# body carries the sentence an operator pastes into a search box.
ACCESS_HTML = (
    "<!doctype html><html><head><title>Error \u2013 Cloudflare Access</title>"
    "</head><body>Unauthorized You don't have permission to view this. "
    "Please contact your system administrator. Status code: 401 "
    "App AUD: 9bb8182c1d75191d35338987fc8e24db3191376290337de0b709e2cc496e4e9c"
    " MTLS Status: NONE</body></html>"
)

# The Access edge answers a JSON Accept with a JSON body and no HTML at all.
ACCESS_JSON = (
    '{"message":"Unauthorized. You don\'t have permission to view this. '
    'Please contact your administrator."}'
)


def _resp(status: int, body: str, **headers: str) -> httpx.Response:
    return httpx.Response(status, content=body.encode(), headers=headers)


class TestNoteClassification:
    def test_html_block_page_with_token_names_the_rotation_remedy(self) -> None:
        note = _cf_access_denial_note(_resp(401, ACCESS_HTML), token_attached=True)
        assert "cf_access_denied" in note
        assert "EDGE" in note
        # The remedy must be the credential one, not the missing-env one.
        assert "Service Auth principal" in note
        assert "CF_ACCESS_CLIENT_ID + CF_ACCESS_CLIENT_SECRET" in note

    def test_html_block_page_without_token_names_the_env_remedy(self) -> None:
        note = _cf_access_denial_note(_resp(401, ACCESS_HTML), token_attached=False)
        assert "cf_access_denied" in note
        assert "CF-Access-* service token reached this host" in note
        assert "Service Auth principal" not in note

    def test_json_block_page_is_detected_too(self) -> None:
        """The edge serves JSON for a JSON Accept — the note cannot be HTML-only."""
        note = _cf_access_denial_note(_resp(401, ACCESS_JSON), token_attached=True)
        assert "cf_access_denied" in note

    def test_cf_access_aud_header_alone_is_enough(self) -> None:
        note = _cf_access_denial_note(
            _resp(403, '{"detail":"nope"}', **{"Cf-Access-Aud": "9bb8182c"}),
            token_attached=True,
        )
        assert "cf_access_denied" in note

    @pytest.mark.parametrize(
        "body",
        [
            '{"error":{"message":"invalid api key","type":"api_error"}}',
            '{"detail":"Not authenticated"}',
            "",
            "Internal Server Error",
        ],
    )
    def test_an_ordinary_wrapper_error_is_left_byte_identical(self, body: str) -> None:
        """A wrapper-side 401/500 must NOT acquire a Cloudflare story."""
        for status in (401, 403, 500):
            assert _cf_access_denial_note(_resp(status, body), token_attached=True) == ""

    def test_a_successful_response_is_never_annotated(self) -> None:
        assert _cf_access_denial_note(_resp(200, '{"choices":[]}'), True) == ""


class _StubClient:
    """Minimal stand-in for the pooled ``httpx.Client``."""

    def __init__(self, response: httpx.Response) -> None:
        self._response = response
        self.posted_urls: list[str] = []

    def post(self, url: str, **kwargs: object) -> httpx.Response:
        self.posted_urls.append(url)
        return self._response

    def close(self) -> None:  # called from the provider's atexit hook
        pass


class TestErrorStringContract:
    """Drive the real ``complete()`` so the note is pinned where it is emitted."""

    def _provider(self, response: httpx.Response) -> _OpenAIWrapperProvider:
        prov = _OpenAIWrapperProvider(base_url=WRAPPER, api_key="dummy")
        prov._client = _StubClient(response)  # type: ignore[assignment]
        return prov

    def _req(self) -> OpenAIWrapperRequest:
        return OpenAIWrapperRequest(
            model="claude-sonnet-4-6",
            user="r462",
            messages=[{"role": "user", "content": "ok"}],
            max_tokens=4,
        )

    def _complete(self, response: httpx.Response, *, token: bool, monkeypatch) -> str:
        if token:
            monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "id.access")
            monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "secret")
        else:
            monkeypatch.delenv("CF_ACCESS_CLIENT_ID", raising=False)
            monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("CF_ACCESS_HOSTNAME", raising=False)
        monkeypatch.setenv("OPENAI_API_BASE", WRAPPER)
        result = self._provider(response).complete(self._req())
        assert result.error is not None
        return result.error

    def test_legacy_prefix_survives_so_the_outage_branch_still_fires(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The exact matcher in ``_graph_rag_impl`` must still match."""
        err = self._complete(_resp(401, ACCESS_HTML), token=True, monkeypatch=monkeypatch)
        assert err.startswith("api_status_401")
        assert "api_status_401" in err.lower()  # the loud outage branch's test

    def test_token_attached_is_reported_as_a_policy_fact(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        err = self._complete(_resp(401, ACCESS_HTML), token=True, monkeypatch=monkeypatch)
        assert "cf_access_denied" in err
        assert "Service Auth principal" in err

    def test_no_token_is_reported_as_configuration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        err = self._complete(_resp(401, ACCESS_HTML), token=False, monkeypatch=monkeypatch)
        assert "cf_access_denied" in err
        assert "CF-Access-* service token reached this host" in err

    def test_ordinary_wrapper_401_gains_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        err = self._complete(
            _resp(401, '{"detail":"Not authenticated"}'), token=True, monkeypatch=monkeypatch
        )
        assert err.startswith("api_status_401")
        assert "cf_access_denied" not in err

    def test_the_secret_never_reaches_the_error_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "super-secret-value")
        monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "id.access")
        monkeypatch.delenv("CF_ACCESS_HOSTNAME", raising=False)
        monkeypatch.setenv("OPENAI_API_BASE", WRAPPER)
        err = self._provider(_resp(401, ACCESS_HTML)).complete(self._req()).error or ""
        assert "super-secret-value" not in err


def test_a_provider_built_without_init_degrades_instead_of_raising() -> None:
    """The failure path must not depend on ``__init__`` having run.

    ``tests/test_llm_round37_hardening.py`` (and its 429-skip test) builds the
    provider without ``__init__``, so ``_cf_access_headers`` need not exist. The
    first cut of this round read it directly and turned every such 401 into
    ``AttributeError`` — a crash where there used to be a diagnosable error.
    This pins the reading as an absence of evidence, not an exception: no token
    is *known* to have been sent, so the note picks the unspecified remedy and
    the status prefix is still exact.
    """
    prov = object.__new__(_OpenAIWrapperProvider)
    prov._client = _StubClient(_resp(401, ACCESS_HTML))  # type: ignore[attr-defined]
    prov._api_key = "dummy"  # type: ignore[attr-defined]
    prov._timeout = 60.0  # type: ignore[attr-defined]

    result = prov.complete(
        OpenAIWrapperRequest(
            model="claude-sonnet-4-6",
            user="r462",
            messages=[{"role": "user", "content": "ok"}],
            max_tokens=4,
        )
    )

    assert result.error is not None
    assert result.error.startswith("api_status_401")
    assert "cf_access_denied" in result.error


class TestTheNoteSurvivesTheHealthBudget:
    """The note must reach ``/healthz/llm``, which is where an operator looks.

    Measured live on 07f8cc0, minutes after R462 first shipped: the note was in
    the error string and **absent from the health detail**, because
    ``_degraded_to_bedrock`` slices the error to 100/120/150 chars and the note
    sits past the 200-char body. A fix that is real everywhere an operator does
    not look is not a fix.
    """

    def _long_error(self) -> str:
        """A realistic provider error: body capped at 200, then the note."""
        body = (
            '{"message":"Unauthorized. You don\'t have permission to view this. '
            'Please contact your system administrator.","status_code":401,'
            '"aud":"9bb8182c1d75191d35338987fc8e24db3191376290337de0b709e2cc496e4e9c"}'
        )
        return (
            f"api_status_401: {body[:200]}"
            + _cf_access_denial_note(_resp(401, ACCESS_HTML), token_attached=True)
        )

    def test_marker_is_extracted_from_an_error(self) -> None:
        from app.main import _named_error_marker

        note = _named_error_marker(self._long_error())
        assert note.startswith(" [cf_access_denied: ")
        assert note.endswith("]")

    def test_marker_is_empty_for_an_unnamed_error(self) -> None:
        from app.main import _named_error_marker

        assert _named_error_marker('api_status_500: {"error":"boom"}') == ""
        assert _named_error_marker("") == ""

    def test_marker_respects_its_own_bound(self) -> None:
        from app.main import _named_error_marker

        assert len(_named_error_marker(self._long_error(), limit=40)) <= 42

    @pytest.mark.parametrize("attempts,expect_failing", [(0, False), (3, True)])
    def test_health_detail_keeps_the_marker_past_the_slice(
        self,
        monkeypatch: pytest.MonkeyPatch,
        attempts: int,
        expect_failing: bool,
    ) -> None:
        """Both ``armed`` arms slice the body — neither may cut the marker."""
        from app import main as app_main
        from app.llm import bedrock_client, stage2_policy

        monkeypatch.setattr(bedrock_client, "is_bedrock_provider_enabled", lambda: True)
        monkeypatch.setattr(
            stage2_policy,
            "transport_stats",
            lambda: {"fallback_attempts": attempts, "fallback_ok": 0},
        )

        out = app_main._degraded_to_bedrock({}, self._long_error())
        detail = str(out["detail"])

        assert "cf_access_denied" in detail
        # The status prefix must still be there, and the body still sliced.
        assert "api_status_401" in detail
        if expect_failing:
            assert "(bedrock fallback FAILING)" in str(out["provider"])
        else:
            # R463 — this arm used to read `... or expect_failing is False`,
            # which made the whole statement assert the literal True whenever
            # expect_failing was False: half of the parametrization was never
            # checked. Assert the negative explicitly instead.
            assert "FAILING" not in str(out["provider"])
        assert out["llm_ok"] is (not expect_failing)
