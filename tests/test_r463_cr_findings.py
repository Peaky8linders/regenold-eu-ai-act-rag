"""R463 — the CR-SKILL deep review's verified findings, and their fixes.

Every test here fails on the pre-R463 code and asserts on a real path (the
dispatched request, the returned record, the computed key), never on source
text. The findings that were reported as DELIBERATE designs were verified and
are deliberately NOT changed (see the round report): ``llm_ok`` staying green on
zero fallback attempts (pinned by ``tests/test_r361_instrument_fidelity.py``)
and the ``CF_ACCESS_HOSTNAME`` pin arming the host it names.
"""
from __future__ import annotations

import hashlib

import httpx
import pytest

from app.llm.openai_wrapper_provider import (
    OpenAIWrapperRequest,
    _cf_access_denial_note,
    _OpenAIWrapperProvider,
    _token_count,
)

WRAPPER = "https://wrapper.antifragile-ai.net/v1"

ACCESS_HTML = (
    "<!doctype html><html><head><title>Error \u2013 Cloudflare Access</title>"
    "</head><body>Unauthorized You don't have permission to view this. "
    "Please contact your system administrator.</body></html>"
)


def _resp(status: int, body: str, **headers: str) -> httpx.Response:
    return httpx.Response(status, content=body.encode(), headers=headers)


class _StubClient:
    """Minimal stand-in for the pooled ``httpx.Client``."""

    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    def post(self, url: str, **kwargs: object) -> httpx.Response:
        return self._response

    def close(self) -> None:
        pass


def _provider(response: httpx.Response) -> _OpenAIWrapperProvider:
    prov = _OpenAIWrapperProvider(base_url=WRAPPER, api_key="dummy")
    prov._client = _StubClient(response)  # type: ignore[assignment]
    return prov


def _req() -> OpenAIWrapperRequest:
    return OpenAIWrapperRequest(
        model="claude-sonnet-4-6",
        user="r463",
        messages=[{"role": "user", "content": "ok"}],
        max_tokens=4,
    )


class TestCacheKeyIdentity:
    """Invariant #4: every runtime flag that can change the response is keyed."""

    def test_the_deadline_fallback_knob_flips_the_engine_cache_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R463 — ``_stage2_wrapper_timeout_s`` falls back to
        ``OPENAI_TIMEOUT_SECONDS`` when the dedicated knob is unset, and that
        deadline decides whether the primary dial lands. A read timeout is a
        leg FAILURE, so an unkeyed flip served arm A's cached answer to arm B
        and read as "the deadline does not matter"."""
        from app.routes.regenold import _engine_cache_key

        monkeypatch.delenv("REGENOLD_STAGE2_WRAPPER_TIMEOUT_S", raising=False)
        monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "60")
        sixty = _engine_cache_key("What must importers do?", None)
        monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "150")
        one_fifty = _engine_cache_key("What must importers do?", None)

        assert sixty != one_fifty

    def test_the_dedicated_knob_still_flips_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The positive control: the knob the key already carried."""
        from app.routes.regenold import _engine_cache_key

        monkeypatch.delenv("OPENAI_TIMEOUT_SECONDS", raising=False)
        monkeypatch.setenv("REGENOLD_STAGE2_WRAPPER_TIMEOUT_S", "30")
        thirty = _engine_cache_key("What must importers do?", None)
        monkeypatch.setenv("REGENOLD_STAGE2_WRAPPER_TIMEOUT_S", "90")
        ninety = _engine_cache_key("What must importers do?", None)

        assert thirty != ninety


class TestCompletionIsFailSoft:
    """``complete()`` must return an error string, never raise."""

    @pytest.mark.parametrize(
        "body,expect_error,expect_text,expect_prompt",
        [
            # ``message`` is null (content filter / upstream error).
            ('{"choices":[{"message":null}]}', True, "", None),
            # ``message`` is a bare string.
            ('{"choices":[{"message":"boom"}]}', True, "", None),
            # ``usage`` is a non-dict truthy value.
            ('{"choices":[{"message":{"content":"ok"}}],"usage":[]}', False, "ok", 0),
            ('{"choices":[{"message":{"content":"ok"}}],"usage":"n/a"}', False, "ok", 0),
            # ``prompt_tokens`` is a non-numeric / null field.
            (
                '{"choices":[{"message":{"content":"ok"}}],'
                '"usage":{"prompt_tokens":"n/a","completion_tokens":null}}',
                False,
                "ok",
                0,
            ),
            # The content-parts variant of the same field.
            (
                '{"choices":[{"message":{"content":['
                '{"type":"text","text":"par"},{"type":"text","text":"ts"}]}}]}',
                False,
                "parts",
                0,
            ),
            # Positive control: a well-formed body is untouched.
            (
                '{"choices":[{"message":{"content":"real"},"finish_reason":"stop"}],'
                '"usage":{"prompt_tokens":7,"completion_tokens":2}}',
                False,
                "real",
                7,
            ),
        ],
    )
    def test_a_malformed_completion_never_raises(
        self,
        body: str,
        expect_error: bool,
        expect_text: str,
        expect_prompt: int | None,
    ) -> None:
        result = _provider(_resp(200, body)).complete(_req())

        assert (result.error is not None) is expect_error
        if expect_error:
            assert result.error is not None
            assert result.error.startswith("decode_error")
            return
        assert result.error is None
        assert result.text == expect_text
        if expect_prompt is not None:
            assert result.prompt_tokens == expect_prompt

    @pytest.mark.parametrize(
        "value,expected", [(7, 7), (None, 0), ("n/a", 0), ("9", 9), (-3, 0), (2.7, 2)]
    )
    def test_the_token_count_helper_never_raises(self, value: object, expected: int) -> None:
        assert _token_count(value) == expected


class TestAccessDenialNoteIsCaseFolded:
    """The sentinel scan must not be decided by the page's capitalisation."""

    def test_a_lowercased_block_page_still_names_the_remedy(self) -> None:
        note = _cf_access_denial_note(_resp(401, ACCESS_HTML.lower()), token_attached=True)
        assert "cf_access_denied" in note

    def test_the_exact_page_still_names_it(self) -> None:
        """The regression control for the case-fold."""
        assert "cf_access_denied" in _cf_access_denial_note(
            _resp(401, ACCESS_HTML), token_attached=True
        )

    @pytest.mark.parametrize(
        "status,body",
        [
            (401, '{"detail":"Not authenticated"}'),
            (403, '{"detail":"forbidden"}'),
            (500, '{"error":"boom"}'),
            (401, ""),
        ],
    )
    def test_an_ordinary_failure_gains_nothing(self, status: int, body: str) -> None:
        assert _cf_access_denial_note(_resp(status, body), token_attached=True) == ""


def _stub_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Put a stand-in ``anthropic`` module on the path.

    The anthropic arm imports the SDK BEFORE it reads the probe flag, so an
    ``importorskip`` would make the flag assertions below vacuous on every
    machine without the SDK installed (which is most of them, including CI).
    The disabled branch returns before it touches the module, so a bare module
    object is all it needs.
    """
    import sys as _sys
    import types as _types

    monkeypatch.setitem(_sys.modules, "anthropic", _types.ModuleType("anthropic"))


class TestProbeKnobsAreBounded:
    """``/healthz/llm`` must not hang, and must fail toward NOT spending."""

    @pytest.fixture()
    def client(self, monkeypatch: pytest.MonkeyPatch):
        from fastapi.testclient import TestClient

        monkeypatch.setenv("REGENOLD_SKIP_STARTUP_LOG", "1")
        from app.main import app

        return TestClient(app)

    @staticmethod
    def _capture(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
        from app.llm import openai_wrapper_provider

        captured: dict[str, object] = {}

        def _handler(req: httpx.Request) -> httpx.Response:
            captured["timeout"] = req.extensions.get("timeout")
            return httpx.Response(
                200,
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "choices": [{"message": {"content": "OK"}}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 1},
                },
            )

        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
        monkeypatch.setenv("OPENAI_API_BASE", "https://api.test.invalid")
        monkeypatch.setenv("OPENAI_API_KEY", "dummy")
        openai_wrapper_provider._SINGLETON = None
        prov = openai_wrapper_provider.get_openai_wrapper_provider()
        prov._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://api.test.invalid",
        )
        return captured

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("inf", 30.0),
            ("-inf", 30.0),
            ("nan", 30.0),
            ("0", 30.0),
            ("-5", 30.0),
            ("abc", 30.0),
            ("", 30.0),
            ("45", 45.0),
        ],
    )
    def test_an_unusable_probe_timeout_falls_back_to_the_default(
        self,
        client,
        monkeypatch: pytest.MonkeyPatch,
        raw: str,
        expected: float,
    ) -> None:
        """R463 — ``float()`` accepts ``inf``/``nan`` and only ValueError was
        caught, so ``=inf`` gave the probe an infinite deadline and ``=nan``
        disarmed the R461 wall-clock guard."""
        from app.llm import openai_wrapper_provider

        monkeypatch.setenv("REGENOLD_HEALTHZ_PROBE_TIMEOUT", raw)
        captured = self._capture(monkeypatch)
        try:
            r = client.get("/healthz/llm")
        finally:
            openai_wrapper_provider._SINGLETON = None

        assert r.status_code == 200
        timeout = captured.get("timeout")
        assert isinstance(timeout, dict), f"expected an httpx timeout dict, got {timeout!r}"
        assert timeout.get("read") == expected

    def test_the_live_anthropic_probe_honours_the_conventional_falsy_spellings(
        self, client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``REGENOLD_HEALTHZ_PROBE_ANTHROPIC`` was matched against the literal
        ``"0"``, so ``false``/``no``/``off`` left the live (billable) probe ON."""
        from pydantic import SecretStr

        from app.config import settings

        _stub_anthropic(monkeypatch)
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "anthropic")
        monkeypatch.setenv("REGENOLD_HEALTHZ_PROBE_ANTHROPIC", "false")
        monkeypatch.setattr(settings.graph_rag, "api_key", SecretStr("sk-ant-fake"), raising=True)
        try:
            body = client.get("/healthz/llm").json()
        finally:
            monkeypatch.setattr(settings.graph_rag, "api_key", None, raising=True)

        assert body["provider"] == "anthropic"
        assert "not probed live" in body["detail"]

    def test_zero_still_disables_it(self, client, monkeypatch: pytest.MonkeyPatch) -> None:
        """The spelling the old check accepted must keep working."""
        from pydantic import SecretStr

        from app.config import settings

        _stub_anthropic(monkeypatch)
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "anthropic")
        monkeypatch.setenv("REGENOLD_HEALTHZ_PROBE_ANTHROPIC", "0")
        monkeypatch.setattr(settings.graph_rag, "api_key", SecretStr("sk-ant-fake"), raising=True)
        try:
            body = client.get("/healthz/llm").json()
        finally:
            monkeypatch.setattr(settings.graph_rag, "api_key", None, raising=True)

        assert "not probed live" in body["detail"]


class TestOntologyCatalogueLegsAreNotVacuous:
    """Both existence checks had a second leg that was False for every input."""

    def test_anchor_exists_keeps_its_catalogue_leg(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``candidate`` is wire form while ARTICLE_EXISTENCE is keyed internally,
        so the "tolerating the short form" tolerance never existed."""
        from app.data import ontology_browse as ob

        monkeypatch.setattr(ob, "coordinate_exists", lambda ref: False)

        assert ob.anchor_exists("Article 26") is True
        assert ob.anchor_exists("Annex III") is True
        assert ob.anchor_exists("Article 999") is False

    def test_fabricated_targets_keeps_its_catalogue_leg(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.data import ontology_ledger as ol
        from app.data import provision_coordinates as pc

        monkeypatch.setattr(pc, "coordinate_exists", lambda ref: False)
        proposal = ol.OntologyPatchProposal(
            proposal_id="prop:r463",
            parent_snapshot="kb:test",
            target_ids=("Article 26", "Article 999"),
            layer="content",  # type: ignore[arg-type]
            hypothesis="h",
            evidence=(
                ol.evidence_record(source_id="s", source_version="v", locator="l", quote="q"),
            ),
        )

        assert ol.fabricated_targets(proposal) == ("Article 999",)

    def test_every_resolve_exit_is_counted(self) -> None:
        """Five of ``resolve_concept``'s seven exits skipped the bookkeeping, so
        ShadowTrace under-counted exactly the lookups that MISS."""
        from app.data import ontology_browse as ob

        ob.reset_shadow_trace()
        ids = (
            f"{ob.KIND_PRACTICE}:no_such_practice",
            f"{ob.KIND_ANNEX_III}:99",
            f"{ob.KIND_PHASE}:no_such_phase",
            f"{ob.KIND_RISK}:no_such_risk",
            f"{ob.KIND_ROLE}:no_such_role",
            f"{ob.KIND_ROLE}:provider:limited_risk",  # the success path
            "not-a-concept-id",  # the malformed path
        )
        for concept_id in ids:
            ob.resolve_concept(concept_id)

        trace = ob.shadow_trace()
        assert trace.calls == len(ids)
        assert "no_such_practice" not in trace.resolved
        assert trace.elapsed_ms > 0.0


class TestEvidenceHashesVerifyTheirOwnRecord:
    """One recipe, over the bytes that are STORED."""

    def test_the_shared_helper_hashes_the_stored_prefix(self) -> None:
        from app.data.ontology_evidence import EVIDENCE_QUOTE_CAP, content_hash_for

        long_quote = "Article 6 shall apply. " * 40
        stored, digest = content_hash_for(long_quote)

        assert stored == long_quote[:EVIDENCE_QUOTE_CAP]
        assert len(stored) < len(long_quote)
        assert digest == hashlib.sha256(stored.encode("utf-8")).hexdigest()

    def test_the_ledger_producer_hashes_what_it_stores(self) -> None:
        from app.data.ontology_ledger import evidence_record

        quote = "x" * 900
        record = evidence_record(source_id="s", source_version="v", locator="l", quote=quote)

        assert record.quote == quote[:400]
        assert record.content_hash == hashlib.sha256(record.quote.encode("utf-8")).hexdigest()

    def test_the_browse_producer_hashes_what_it_stores(self) -> None:
        from app.data import ontology_browse as ob

        record = ob._evidence_for("Article 6")

        assert record is not None
        assert record.content_hash == hashlib.sha256(record.quote.encode("utf-8")).hexdigest()


class TestEvidenceCensusCanProveLevelTwoFired:
    """``stats()`` must expose the member-line drop, not just the header count."""

    HEADER = "STRUCTURE of Article 6 NOT ENGAGED by this question (2 members)"

    @staticmethod
    def _bundle(*lines: str):
        from app.engines.evidence_bundle import EvidenceBundle

        return EvidenceBundle(raw="\n".join(lines), lines=lines, items=(), sections=())

    def test_the_member_drop_is_reported_next_to_the_header_count(self) -> None:
        bundle = self._bundle(
            "REFERENCES", self.HEADER, "    Article 6", "    Article 7", "ANSWER CONTRACT"
        )

        stats = bundle.stats()
        assert stats["non_engaged_blocks"] == 1
        assert stats["non_engaged_member_lines"] == 2

    def test_a_header_with_no_members_is_distinguishable(self) -> None:
        """The R463 point: 1 header and 0 dropped characters must be readable,
        because level 2 acting on nothing still reports as applied."""
        bundle = self._bundle("REFERENCES", self.HEADER, "Article 6", "ANSWER CONTRACT")

        stats = bundle.stats()
        assert stats["non_engaged_blocks"] == 1
        assert stats["non_engaged_member_lines"] == 0

    @pytest.mark.parametrize("indent,expected", [("    ", 2), ("  ", 0), ("\t", 0)])
    def test_only_the_four_space_member_contract_is_a_member(
        self, indent: str, expected: int
    ) -> None:
        """The four-space contract is DELIBERATE: the live block indents its
        verbatim quotes by two, and widening the test to any indentation deleted
        them (pinned by ``tests/test_r460_evidence_bundle``). The R463 fix is
        that a mismatch is now VISIBLE — a header count with a zero drop."""
        bundle = self._bundle(
            "REFERENCES",
            self.HEADER,
            f"{indent}Article 6",
            f"{indent}Article 7",
            "ANSWER CONTRACT",
        )

        assert bundle.stats()["non_engaged_member_lines"] == expected

    def test_a_blank_line_still_ends_the_member_list(self) -> None:
        """The BOUNDARY is load-bearing, and relaxing it was a measured
        regression: the live block separates an indented heading from its member
        list with a blank line, so swallowing that line deleted prompt content
        this lever does not own (``tests/test_r460_evidence_bundle`` pins it)."""
        bundle = self._bundle(
            "REFERENCES",
            self.HEADER,
            "    Article 6",
            "    Article 7",
            "",
            "    VERBATIM (question-relevant) Article 6",
            "ANSWER CONTRACT",
        )

        assert bundle.stats()["non_engaged_member_lines"] == 2
        assert "VERBATIM (question-relevant)" in bundle.minified(level=2)

    def test_level_two_removes_exactly_those_lines(self) -> None:
        bundle = self._bundle(
            "REFERENCES",
            self.HEADER,
            "    Article 6",
            "    Article 7",
            "ANSWER CONTRACT",
        )

        minified = bundle.minified(level=2)

        assert minified != bundle.raw
        # The MEMBER lines go; the heading (which carries the member count and
        # the do-not-enumerate instruction) stays.
        assert "    Article 6" not in minified
        assert "    Article 7" not in minified
        assert self.HEADER in minified
        assert bundle.minified(level=1) == bundle.raw
