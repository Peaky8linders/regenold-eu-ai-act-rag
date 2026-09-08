"""R292 — pin the two statutory citations that have now been wrong TWICE.

History: R290 verified both against the pinned verbatim text and reverted them;
commit ``5c3287c`` then re-applied them under the framing "commit *missing*
statutory citations". The first R292 pass fixed only the PROSE and left the
``refs`` lists wrong, so the wire briefly shipped citations that contradicted
its own answer text.

These are hard-rule-#4 defects (a confidently-wrong statement of law) and they
are structurally invisible to the davidath regression guard — both verdicts fire
on 0 of the 476 davidath rows, so "davidath byte-identical" says nothing about
them. That is exactly why they need an explicit pin.

Each assertion is grounded in ``provision_text.get_provision_text`` rather than
a hardcoded expectation, so the test re-derives the ground truth from the pinned
Regulation on every run.
"""
from __future__ import annotations

import re

import pytest

from app.data.provision_text import get_provision_text


def _text(ref: str) -> str:
    return (get_provision_text(ref) or "").lower()


# ── ground truth, re-derived from the pinned Regulation ──────────────────────


def test_article_47_is_the_eu_declaration_of_conformity():
    """Art. 47 is the declaration; Art. 48 is CE marking. Not interchangeable."""
    assert "declaration of conformity" in _text("Article 47")
    assert "ce marking" in _text("Article 48")
    assert "declaration of conformity" not in _text("Article 48")[:400]


def test_article_49_2_is_the_article_6_3_registration_duty():
    """Art. 49(2) is the 6(3) duty; Art. 71(2) is entering Annex VIII data."""
    a49 = _text("Article 49(2)")
    assert "article 6(3)" in a49 and "register" in a49
    assert "annex viii" in _text("Article 71(2)")


# ── the engine's curated verdicts must agree with the above ─────────────────


# R394.1 — anchor on the verdict NAME rather than on prose wording.
# The former anchor "register it under Article" broke when the Article 6(3)
# answer was rewritten to fit the three-sentence budget, even though it still
# cites Article 49(2) in both prose and refs. A verdict name is stable across
# rewordings; a sentence fragment is not.
_ART_6_3_ANCHOR = '"name": "article_6_3_exception"'


def _verdict_block(anchor: str) -> str:
    """Return the source region of the curated verdict containing ``anchor``."""
    from pathlib import Path

    src = Path("app/engines/_graph_rag_impl.py").read_text(encoding="utf-8")
    idx = src.find(anchor)
    assert idx != -1, f"anchor not found in engine source: {anchor!r}"
    # R394.1 — span to the END of this verdict's refs list rather than a fixed
    # 600-char window. A fixed window silently stops covering the refs as soon
    # as an explanatory comment is added above the answer, which turns these
    # pins into false failures instead of real ones.
    end = src.find('"refs"', idx)
    assert end != -1, f"no refs list after anchor: {anchor!r}"
    close = src.find("]", end)
    assert close != -1, f"unterminated refs list after anchor: {anchor!r}"
    return src[idx : close + 1]


def test_record_retention_verdict_cites_article_47_not_48():
    block = _verdict_block("conformity (Article ")
    assert "Article 47" in block, "prose must cite Art. 47 (the declaration)"
    assert "Article 48" not in block, "Art. 48 is CE marking, not the declaration"
    refs = re.search(r'"refs":\s*\[([^\]]*)\]', block)
    assert refs, "refs list not found next to the record-retention prose"
    assert '"Art. 47"' in refs.group(1)
    assert '"Art. 48"' not in refs.group(1), (
        "the refs list must not contradict the prose — this is the exact "
        "half-fix that shipped mid-R292"
    )


def test_article_6_3_verdict_cites_article_49_2_not_71_2():
    block = _verdict_block(_ART_6_3_ANCHOR)
    assert "Article 49(2)" in block
    assert "Article 71(2)" not in block
    refs = re.search(r'"refs":\s*\[([^\]]*)\]', block)
    assert refs, "refs list not found next to the Art. 6(3) prose"
    assert '"Art. 49.2"' in refs.group(1)
    assert '"Art. 71.2"' not in refs.group(1)


@pytest.mark.parametrize(
    "anchor",
    ["conformity (Article ", _ART_6_3_ANCHOR],
)
def test_prose_and_refs_never_contradict(anchor: str):
    """Every Article N named in the prose must appear in that verdict's refs."""
    block = _verdict_block(anchor)
    refs = re.search(r'"refs":\s*\[([^\]]*)\]', block)
    assert refs
    ref_nums = set(re.findall(r"Art\.\s*(\d+)", refs.group(1)))
    prose = block[: block.find('"refs"')]
    prose_nums = set(re.findall(r"Article\s+(\d+)", prose))
    missing = prose_nums - ref_nums
    assert not missing, (
        f"prose cites Article(s) {sorted(missing)} that the refs list omits — "
        "the grounded judge penalises exactly this on citation faithfulness"
    )
