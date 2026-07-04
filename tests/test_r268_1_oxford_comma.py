"""R268.1 — Oxford-comma multi-article / multi-annex capture.

R268 widened the explicit-reference regex to capture LISTS ("Articles 13 and
50" -> [13, 50]). But the separator matched only ONE connector, so the
Oxford-comma shape "Articles 9, 10, and 15" — where the connector before the
last item is a comma FOLLOWED by "and" (", and") — broke the list and silently
dropped the trailing "15". That is the commonest legal-list phrasing, so R268
defeated its own goal on it.

R268.1 makes the separator a ONE-OR-MORE run ``(?:sep)+`` so ", and" / ", or"
is consumed as a single separator and the trailing item is captured. These
tests pin the fix, its ReDoS-safety, no cross-contamination between the article
and annex tokens, and the (inert) over-capture behaviour left as-is.

davidath byte-identical: a diff of the pre- vs post-R268.1 regex over all 6358
davidath string values yields 0 deltas (its lists never use an Oxford comma).
"""
from __future__ import annotations

import os
import time

import pytest

from app.engines.graph_rag import (
    _MULTI_ANNEX_MENTION_RE,
    _MULTI_ARTICLE_MENTION_RE,
    _deterministic_parse,
    _retrieve_from_kb,
)


def _entities(question: str, *, gate: str = "1") -> list[str]:
    prev = os.environ.get("REGENOLD_MULTI_ARTICLE_ENTITIES")
    os.environ["REGENOLD_MULTI_ARTICLE_ENTITIES"] = gate
    try:
        return _deterministic_parse(question).entities
    finally:
        if prev is None:
            os.environ.pop("REGENOLD_MULTI_ARTICLE_ENTITIES", None)
        else:
            os.environ["REGENOLD_MULTI_ARTICLE_ENTITIES"] = prev


# ── Oxford-comma ARTICLE lists (the R268.1 defect) ───────────────────────────

@pytest.mark.parametrize(
    "question,expected",
    [
        ("Explain obligations under Articles 9, 10, and 15.",
         ["Art. 9", "Art. 10", "Art. 15"]),
        ("penalties under Articles 99, 100, or 101",
         ["Art. 99", "Art. 100", "Art. 101"]),
        ("duties in Articles 5, 6, 9, 10, 11, 13, 14, and 15",
         ["Art. 5", "Art. 6", "Art. 9", "Art. 10",
          "Art. 11", "Art. 13", "Art. 14", "Art. 15"]),
    ],
)
def test_oxford_comma_article_list_captures_trailing_item(question, expected):
    ents = _entities(question)
    for e in expected:
        assert e in ents, f"{e!r} missing from {ents!r} for {question!r}"


# ── Oxford-comma ANNEX lists (symmetric) ─────────────────────────────────────

def test_oxford_comma_annex_list_captures_trailing_item():
    ents = _entities("Compare Annexes XI, XII, or XIII.")
    for e in ("Annex XI", "Annex XII", "Annex XIII"):
        assert e in ents, f"{e!r} missing from {ents!r}"


# ── The pre-R268.1 gap this fixes (regression witness) ───────────────────────

def test_trailing_oxford_item_was_the_gap():
    # The whole point: the LAST item after ", and" must now be present.
    assert "Art. 15" in _entities("obligations under Articles 9, 10, and 15?")


# ── No cross-contamination between the two tokens ────────────────────────────

def test_article_and_annex_do_not_bleed():
    ents = _entities("Article 9 and Annex III obligations")
    assert "Art. 9" in ents
    assert "Annex III" in ents
    assert "Art. 3" not in ents  # "III" must not be mis-read as article 3
    # The article token must not swallow the annex clause, nor vice-versa.
    assert _MULTI_ARTICLE_MENTION_RE.findall("Article 9 and Annex III") == ["9"]
    assert _MULTI_ANNEX_MENTION_RE.findall("Article 9 and Annex III") == ["III"]


# ── ReDoS-safety: bounded {0,8} + required-progress groups ───────────────────

def test_no_catastrophic_backtracking_on_pathological_input():
    pathological = "Articles " + ", ".join(["9"] * 600) + " and " + "x" * 400
    start = time.perf_counter()
    _MULTI_ARTICLE_MENTION_RE.findall(pathological)
    _MULTI_ANNEX_MENTION_RE.findall("Annex " + ", ".join(["III"] * 600))
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5, f"regex took {elapsed:.3f}s — possible ReDoS"


# ── F2 (review): the annex over-capture is inert, never a wire citation ──────

def test_over_captured_bogus_annex_surfaces_no_obligation():
    # An UPPERCASE Roman-letter word after a connector ("CE marking" -> "C")
    # over-captures a bogus "Annex C" at the entity layer. It has no
    # EC_CHECKER_OBLIGATION_MAP entry, so retrieval surfaces no obligation for
    # it and it can never become a wire citation. This pins that inertness so a
    # future change that consumes query.entities less carefully can't leak it.
    query = _deterministic_parse(
        "What must a provider do under Annex III, CE marking, and Annex I?"
    )
    assert "Annex C" in query.entities  # documents the known over-capture
    ctx = _retrieve_from_kb(query)
    surfaced = {o.get("article") for o in ctx.obligations}
    assert "Annex C" not in surfaced
    assert not any(a and a.startswith("Annex C") for a in surfaced)


# ── davidath byte-identity witness (the ", and"/", or" shape is the only Δ) ──

def test_plain_lists_unchanged_by_the_run_separator():
    # Non-Oxford lists behave exactly as R268 did (the shapes davidath uses).
    assert _MULTI_ARTICLE_MENTION_RE.findall("Articles 13 and 50") == ["13 and 50"]
    assert _MULTI_ARTICLE_MENTION_RE.findall("Articles 6, 9 and 13") == [
        "6, 9 and 13"
    ]
    assert _MULTI_ANNEX_MENTION_RE.findall("Annexes III and IV") == ["III and IV"]
