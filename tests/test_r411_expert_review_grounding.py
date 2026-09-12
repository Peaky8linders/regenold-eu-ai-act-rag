"""R411 — statutory corrections sourced from the expert EU AI Act review.

Two defects, both found by reading `Antifragile AI expert review.txt` against our
OWN statutory corpus rather than against a paraphrase. Each is a paragraph-level
mis-attribution, which is the failure mode the official **Ref. Correctness
(Strict)** axis scores — a right article with the wrong paragraph scores zero.

1. **Art. 6(3) vs Art. 6(4).** The live prompt told the model that a provider who
   relies on the Article 6(3) derogation "must document their self-assessment
   ... and register it in the EU database under Article 49(2)". Article 6(3) is
   the derogation *condition*; the documentation duty and the Article 49(2)
   registration obligation sit in **Article 6(4)**, which the prompt never named.
   Verbatim from our corpus: "4. A provider who considers that an AI system
   referred to in Annex III is not high-risk shall document its assessment before
   that system is placed on the market or put into service. Such provider shall be
   subject to the registration obligation set out in Article 49(2)."

2. **Art. 5(1)(c) social scoring.** `PROPORTIONALITY[0]['applies_to']` still
   asserted "social scoring by public authorities". The limitation existed only in
   the Commission proposal and was removed from the final Regulation — our own
   Art. 5(1)(c) text carries no such qualifier, and
   `graph_rag_prompt_templates` already forbids the phrase. The metadata
   contradicted both the statute and our prompt rule. It is dead data (no reader),
   so this is latent-trap maintenance, not a live-behaviour fix.

The tests assert against the CORPUS where the corpus is the authority, so they
cannot drift with a paraphrase.
"""

from __future__ import annotations

import re

from app.data import graph_rag_prompt_templates as tpl
from app.data.eu_ai_act_corpus import PROPORTIONALITY
from app.data.provision_text import get_provision_text


def _corpus_article_6() -> str:
    return get_provision_text("Article 6") or ""


def test_corpus_confirms_6_4_is_the_documentation_paragraph() -> None:
    """The authority for the fix — assert the statute, not our summary of it."""
    text = _corpus_article_6()
    assert "shall document its assessment" in text
    assert "registration obligation set out in Article 49(2)" in text
    # 6(4) sits after the 6(3) profiling subparagraph.
    assert text.index("shall always be considered to be high-risk") < text.index(
        "shall document its assessment"
    )


def test_stage2_rules_attribute_the_documentation_duty_to_6_4() -> None:
    """Every live rules string that names the duty must name Art. 6(4) for it."""
    src = open(tpl.__file__, encoding="utf-8").read()
    offenders = []
    for line in src.splitlines():
        if "Article 49(2)" not in line:
            continue
        # The 6(4) attribution must appear in the same sentence as 49(2).
        window = line[max(0, line.find("Article 49(2)") - 400) : line.find("Article 49(2)") + 200]
        if "Article 6(4)" not in window:
            offenders.append(line[:160])
    assert not offenders, (
        "the Art. 49(2) registration duty is attributed without naming Art. 6(4) "
        "in the same sentence:\n" + "\n".join(offenders)
    )


def test_no_live_string_limits_social_scoring_to_public_authorities() -> None:
    """Art. 5(1)(c) has no public-authority qualifier in the final Regulation."""
    for path in (tpl.__file__,):
        src = open(path, encoding="utf-8").read()
        for line in src.splitlines():
            if "social scoring" not in line:
                continue
            # The prompt rule that FORBIDS the phrase is allowed to quote it.
            if "Never write" in line or "NOT limited to" in line:
                continue
            assert not re.search(
                r"social scoring[^.]{0,60}by public authorities", line, re.IGNORECASE
            ), f"live string still qualifies social scoring by public authorities: {line[:160]}"


def test_corpus_proportionality_metadata_is_statute_accurate() -> None:
    prohibited = [entry for entry in PROPORTIONALITY if entry["name"] == "prohibited"][0]
    assert "by public authorities" not in prohibited["applies_to"]

    annex_iii = [entry for entry in PROPORTIONALITY if entry["name"] == "high_risk_annex_III"][0]
    assert "6(4)" in annex_iii["key_articles"], "the Art. 6(4) duty is a key article of this tier"
    assert "no significant risk of harm" in annex_iii["note"]
    # The significant-risk test is the 6(3) derogation, not a 6(2) precondition.
    assert "ONLY if they pose" not in annex_iii["applies_to"]


def test_corpus_confirms_5_1_c_carries_no_public_authority_qualifier() -> None:
    text = get_provision_text("Article 5") or ""
    idx = text.find("evaluation or classification of natural persons")
    assert idx > 0, "Art. 5(1)(c) text not found in the corpus"
    window = text[idx : idx + 400]
    assert "public authorities" not in window
    assert "social score" in window
