"""R94 — regression tests for the 3 engine bugs the R93 fresh-200 judge
run surfaced (all reproduce deterministically; the `references` list and
the deterministic answer prose are built without the wrapper).

Bug 1: spurious Article 52 on prohibited-practice "...Permitted?" questions
       (the high-IDF token "permitted" in the Art. 52 KB summary makes the
       BM25 fallback rank it).
Bug 2: Art. 5 real-time RBI mischaracterised as a Member-State opt-in /
       "stricter national laws" carve-out instead of a prohibition.
Bug 3: truncated / dangling answer sentences — `_first_clause` hard-cutting
       a stub mid-clause ("...register themselves and.") + run-on joins.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.main import app

_KEY = "regenold-test-key"


@pytest.fixture()
def client() -> TestClient:
    settings.regenold.api_key = SecretStr(_KEY)
    return TestClient(app)


def _refs(client: TestClient, question: str) -> list[str]:
    resp = client.post(
        "/api/v1/regenold/eu-ai-act/ask",
        json=[{"role": "user", "content": question}],
        headers={"X-Regenold-Api-Key": _KEY},
    )
    assert resp.status_code == 200, resp.text
    return resp.json().get("references", [])


def _answer(client: TestClient, question: str) -> str:
    resp = client.post(
        "/api/v1/regenold/eu-ai-act/ask",
        json=[{"role": "user", "content": question}],
        headers={"X-Regenold-Api-Key": _KEY},
    )
    assert resp.status_code == 200, resp.text
    return resp.json().get("answer", "") or ""


# ── Bug 1 — spurious Article 52 ────────────────────────────────────────────

_PERMITTED_PROHIBITION_QS = [
    "The city wants an AI that gives citizens a social score based on "
    "unrelated behaviour and then restricts services. Permitted?",
    "An AI gives citizens a social score based on unrelated behaviour. Permitted?",
    "An AI that restricts services. Permitted?",
]


def test_art52_summary_has_no_bare_permitted_token() -> None:
    """The Art. 52 KB summary must not carry the bare 'permitted' token —
    it is high-IDF and makes the BM25 fallback false-match every
    '...Permitted?' prohibited-practice question."""
    from app.data.kb import EC_CHECKER_OBLIGATION_MAP

    summary = EC_CHECKER_OBLIGATION_MAP["Art. 52"]["summary"].lower()
    assert "permitted" not in summary, (
        "Art. 52 summary still contains 'permitted' — BM25 will false-match "
        "'...Permitted?' questions and spuriously cite Article 52."
    )


@pytest.mark.parametrize("question", _PERMITTED_PROHIBITION_QS)
def test_art52_not_cited_on_permitted_prohibition_questions(
    client: TestClient, question: str
) -> None:
    """Article 52 (GPAI systemic-risk notification) must never surface on a
    prohibited-practice question — it is wholly unrelated to Article 5."""
    refs = _refs(client, question)
    assert "Article 52" not in refs, f"spurious Article 52 in refs={refs}"


def test_art52_bm25_score_for_permitted_token_is_zero() -> None:
    from app.data.kb_search import relevance_score

    assert relevance_score("permitted", "Art. 52") == 0.0


# ── Bug 2 — Art. 5 RBI mischaracterisation ─────────────────────────────────

def test_art5_stub_does_not_frame_rbi_as_member_state_optin() -> None:
    """The Art. 5 stub must not carry the misleading standalone sentence
    that frames real-time RBI as a Member-State 'stricter national laws'
    opt-in rather than a prohibition."""
    from app.data.kb import EC_CHECKER_OBLIGATION_MAP, _KBEntry

    entry = EC_CHECKER_OBLIGATION_MAP["Art. 5"]
    assert isinstance(entry, _KBEntry)
    blob = " ".join(entry.stubs).lower()
    assert "lets member states impose stricter national laws" not in blob, (
        "Art. 5 stub still frames RBI as a Member-State stricter-laws opt-in."
    )


_RBI_QUESTIONS = [
    "Is real-time remote biometric identification in publicly accessible "
    "spaces by law enforcement allowed under the EU AI Act?",
    "Police want an AI that predicts who will commit a crime purely from "
    "personality profiling. Is that prohibited?",
]


@pytest.mark.parametrize("question", _RBI_QUESTIONS)
def test_art5_answer_not_member_state_optin_framing(
    client: TestClient, question: str
) -> None:
    """The Art. 5 answer must not lead with / reduce to the 'Member States
    impose stricter national laws' framing — it must frame Article 5 as a
    prohibition."""
    ans = _answer(client, question).lower()
    assert "impose stricter national laws on remote biometric" not in ans, (
        f"answer mischaracterises Art. 5 as a Member-State opt-in: {ans!r}"
    )
    assert "prohibit" in ans, (
        f"answer does not frame Article 5 as a prohibition: {ans!r}"
    )


# ── Bug 3 — truncated / dangling answer sentences ──────────────────────────

_ART49_STUB = (
    "Requires providers (and deployers that are public authorities) to "
    "register themselves and their high-risk AI system in the EU "
    "database (Art. 71) before placing the system on the market or "
    "putting it into service."
)


def test_first_clause_no_dangling_conjunction(monkeypatch) -> None:
    """With the live fix ON, `_first_clause` must never return a clause that
    ends on a dangling conjunction / preposition
    ('...register themselves and.')."""
    monkeypatch.setenv("REGENOLD_CLAUSE_COMPLETE", "1")
    from app.integrations.regenold.grounded_prose import _first_clause

    out = _first_clause(_ART49_STUB, max_chars=90)
    stripped = out.rstrip(".").rstrip().lower()
    assert not stripped.endswith(
        (" and", " or", " to", " the", " of", " a", " with")
    ), f"_first_clause produced a dangling fragment: {out!r}"
    # And the clause is grammatically complete (ends with a terminator).
    assert out.rstrip()[-1] in ".!?"
    # Must NOT truncate mid-citation: the abbreviation-aware splitter must
    # not treat "Art. 71" as a sentence end ("...EU database (Art.").
    assert not out.rstrip().rstrip(".").lower().endswith("(art"), (
        f"_first_clause clipped mid-citation: {out!r}"
    )


def test_first_clause_default_is_clause_complete(monkeypatch) -> None:
    """Clause-complete is now ALWAYS-ON — `_clause_complete_enabled()` is
    hard-coded ``True`` ("per user directive to prevent mid-word character
    slicing"), so the pre-R94 flag-gated hard-cut path is unreachable. With
    the env unset, `_first_clause` produces the SAME clean-boundary clause as
    the flag-ON path: it never returns the raw mid-word hard-cut, never ends
    on a dangling connective, and always terminates cleanly."""
    monkeypatch.delenv("REGENOLD_CLAUSE_COMPLETE", raising=False)
    from app.integrations.regenold.grounded_prose import _first_clause

    out = _first_clause(_ART49_STUB, max_chars=90)
    # No longer the pre-R94 mid-word hard-cut.
    assert out != _ART49_STUB[:90].rstrip(",;: ") + "."
    # Clean clause-complete invariants (same as the flag-ON path).
    assert out.rstrip()[-1] in ".!?"
    assert not out.rstrip().rstrip(".").lower().endswith(
        (" and", " or", " to", " the", " of", " a", " with")
    ), f"_first_clause produced a dangling fragment: {out!r}"


def test_augmenter_no_runon_or_dangling(client: TestClient, monkeypatch) -> None:
    """With the live fix ON, the deterministic multi-article answer must not
    run on between cited articles, nor end mid-clause on a dangling
    conjunction."""
    monkeypatch.setenv("REGENOLD_CLAUSE_COMPLETE", "1")
    ans = _answer(
        client,
        "Police want an AI that predicts who will commit a crime purely "
        "from personality profiling. Is that prohibited?",
    )
    low = ans.rstrip().rstrip(".").lower()
    assert not low.endswith((" and", " or", " to", " the", " of")), (
        f"answer ends on a dangling fragment: {ans!r}"
    )
