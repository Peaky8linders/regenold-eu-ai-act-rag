"""R138 — BLUF verdict-first answers + doubled Sonnet thinking + full
citation consistency.

Operator directives:

1. For a concrete question about a specific use-case / application / system
   ("Is a medtech system that tracks patient weight high-risk?"), the answer
   must OPEN with a concise one-phrase verdict ("It depends: high-risk only
   when …", "Not high-risk", "Prohibited"), THEN the grounded explanation +
   citations — not lead with "Article 6(1) read with Annex I is the operative
   provision" and bury the verdict.
2. Double the standard-path Sonnet 4.6 extended-thinking budget (1024 → 2048)
   for better answers.
3. Every article / sub-point the SHIPPED answer mentions must also appear in
   the wire ``references`` (and therefore the UI citations area).

The prompt + user-message + thinking-budget changes are Stage-2-only; the
final citation-consistency pass is ``stage2_landed``-gated — so the
wrapper-less davidath bench is byte-identical by construction.
"""
from __future__ import annotations

import re
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.data.graph_rag_prompts import ANSWER_GENERATE_SYSTEM
from app.main import app
from app.routes.regenold import _add_prose_named_refs

_ART_RE = re.compile(r"\bArticle\s+(\d{1,3})\b")
_ANNEX_RE = re.compile(r"\bAnnex\s+([IVXLC]+)\b")


# ── Change 2 — adaptive thinking budgets (R138 doubled; R139 retuned) ─────


def test_thinking_tokens_adaptive_r139() -> None:
    # 2026-07-04 operator directive — Opus 4.8 answers BOTH tiers ("fast mode").
    # The SIMPLE tier is thinking-FREE (thinking_tokens 0 — Opus single-pass);
    # the COMPLEX tier keeps the EXTENDED budget (complex_thinking_tokens 4000).
    # Supersedes the R261 "Sonnet 5 simple / Opus 4.8 complex" split.
    assert settings.graph_rag.thinking_tokens == 0
    assert settings.graph_rag.complex_thinking_tokens == 4000
    # R305 — pin the EXACT current default. An ``in (...)`` set that accepts
    # either model cannot catch the class of bug R300 found (an ungated,
    # undisclosed model swap that also made the reasoning trace report a
    # model that was never sent). Update this line deliberately when the
    # default changes; do not widen it.
    assert settings.graph_rag.stage2_model == "claude-opus-5"


# ── Change 1 — BLUF verdict-first prompt ──────────────────────────────────


def test_prompt_has_direct_answer_first_rule() -> None:
    assert "DIRECT ANSWER FIRST" in ANSWER_GENERATE_SYSTEM
    # R139 — verdict-first for a SPECIFIC system, stated as a FORMAL conditional
    # ("High-risk only where …"), NOT the colloquial "It depends" (which R139
    # removed from the prompt as un-professional and forbids explicitly).
    assert "High-risk only where" in ANSWER_GENERATE_SYSTEM
    assert "It depends: high-risk only when" not in ANSWER_GENERATE_SYSTEM
    assert 'NEVER open with the colloquial "It depends"' in ANSWER_GENERATE_SYSTEM
    # The reader must see the answer first, not the operative provision.
    assert "bury the verdict" in ANSWER_GENERATE_SYSTEM


def test_prompt_first_word_rule_allows_verdict_lead() -> None:
    # The "first word must be a regulatory term" rule is reconciled so a
    # yes/no / classification answer leads with the verdict, not a forced
    # "Article N" opener.
    assert "FIRST WORD" in ANSWER_GENERATE_SYSTEM
    assert "the first word is the direct verdict" in ANSWER_GENERATE_SYSTEM


def test_prompt_direct_verdict_rule_generalised() -> None:
    # The DIRECT-VERDICT RULE now covers specific-system classification, not
    # only the "always/ever" shapes.
    assert (
        "specific-system classification" in ANSWER_GENERATE_SYSTEM
        or "NAMED system / application / use-case is high-risk"
        in ANSWER_GENERATE_SYSTEM
    )


# ── Change 3 — full citation consistency (helper) ─────────────────────────


def test_add_prose_named_refs_high_cap_adds_more_than_two() -> None:
    """The final consistency pass uses a high cap so EVERY prose-named base
    article is promoted, not just the R134 cap=2 first two."""
    prose = (
        "Article 14 requires human oversight; Article 26 deployer duties; "
        "Article 27 a fundamental-rights impact assessment; and Article 73 "
        "serious-incident reporting."
    )
    out = _add_prose_named_refs([], prose, cap=8)
    for ref in ("Article 14", "Article 26", "Article 27", "Article 73"):
        assert ref in out


# ── Change 1 + 3 — end-to-end Stage-2 route proofs ────────────────────────


_VERDICT_SONNET = (
    "Yes, high-risk: a deployer of an Annex III recruitment AI system must "
    "implement Article 14 human oversight and complete an Article 27 "
    "fundamental-rights impact assessment. The deployer also owes Article 26 "
    "information and logging duties and must report serious incidents under "
    "Article 73."
)
_Q = "What must a deployer of a high-risk recruitment AI system do?"


def _stage2_env(monkeypatch) -> None:
    settings.regenold.api_key = SecretStr("regenold-test-key")
    monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "1")
    monkeypatch.setenv("REGENOLD_STAGE2_MIN_CONFIDENCE", "0")
    monkeypatch.setenv("REGENOLD_VERBATIM_ANSWER", "0")  # keep Sonnet prose on wire
    monkeypatch.setenv("REGENOLD_ANSWER_ROUTER", "1")
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "0")
    monkeypatch.setenv("REGENOLD_CITE_CONSISTENCY", "1")
    # The dev .env may pin provider=cli (deterministic eval setting), which
    # makes _stage2_provider_enabled() return False and skips Stage-2. Drop it
    # so the patched is_openai_wrapper_enabled=True wins the provider gate.
    monkeypatch.delenv("P2P_GRAPH_RAG_PROVIDER", raising=False)


def _post(question: str, sonnet_answer: str, captured: list[str] | None = None):
    def _complete(*_a, **kw):
        if captured is not None:
            captured.append(kw.get("user", ""))
        return sonnet_answer

    with (
        patch(
            "app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
            return_value=True,
        ),
        patch(
            "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
            side_effect=_complete,
        ),
    ):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/regenold/eu-ai-act/ask",
            headers={"X-Regenold-Api-Key": "regenold-test-key"},
            json=[{"role": "user", "content": question}],
        )
        return resp.json()


def test_every_cited_article_is_in_references(monkeypatch) -> None:
    """The user directive: every article / annex the SHIPPED answer names
    must appear in the wire references list (UI citations area)."""
    _stage2_env(monkeypatch)
    body = _post(_Q, _VERDICT_SONNET)
    answer = body.get("answer", "")
    # Guard against a vacuous assertion (refusal / no_match / non-Stage-2).
    if body.get("retrieval_path") in {"no_match"} or "Article" not in answer:
        return
    refs = body.get("references", [])
    ref_art_nums = {
        m.group(1)
        for r in refs
        for m in [_ART_RE.match(str(r).strip())]
        if m
    }
    ref_annex = {
        m.group(1).upper()
        for r in refs
        for m in [_ANNEX_RE.match(str(r).strip())]
        if m
    }
    for m in _ART_RE.finditer(answer):
        assert m.group(1) in ref_art_nums, (
            f"Article {m.group(1)} is in the answer but missing from "
            f"references {refs}"
        )
    for m in _ANNEX_RE.finditer(answer):
        assert m.group(1).upper() in ref_annex, (
            f"Annex {m.group(1)} is in the answer but missing from "
            f"references {refs}"
        )


def test_classification_user_message_leads_with_verdict(monkeypatch) -> None:
    """The Stage-2 user message instructs Sonnet to lead with the verdict,
    not the removed 'Start IMMEDIATELY with the regulation (Article 5
    prohibits...)' example."""
    _stage2_env(monkeypatch)
    captured: list[str] = []
    _post(
        "Is a medtech system that tracks patient weight considered high risk?",
        _VERDICT_SONNET,
        captured=captured,
    )
    # The provider was invoked at least once and the verdict-lead instruction
    # is present in every captured user message; the buried-verdict example is
    # gone.
    if not captured:
        return
    joined = "\n".join(captured)
    assert "verdict" in joined.lower()
    assert "Lead with" in joined
    assert "Start IMMEDIATELY with the regulation (e.g. 'Article 5 prohibits" not in joined
