"""R310 — structural strip of retrieval meta-commentary.

Every positive case below is a VERBATIM sentence from the r309 live batch
(sidecar july7-r309-ALL.ckpt.jsonl), not a paraphrase. R305 shipped a
detector whose unit test used a TRUNCATED copy of its own target question,
so the test passed 7/7 while production was broken — these use the real
strings so that cannot happen again.

The negative cases matter as much: the Regulation's own prose says "the
information provided under Article 13" and "instructions for use provided by
the provider", which are legitimate legal content and must survive.
"""
from __future__ import annotations

import re

import pytest

from app.integrations.regenold.answer_normaliser import strip_retrieval_meta

# ── verbatim live leaks (july7-125 / 151 / 281 / 086) ───────────────────
LIVE_125 = (
    "Not prohibited, and not high-risk, so long as the sole purpose remains "
    "verification. Such a system infers none of those protected characteristics, "
    "so no prohibited practice under Article 5 arises. That conclusion depends "
    "entirely on the sole-purpose limitation holding in practice. The references "
    "supplied here contain Article 5 but not the classification provisions "
    "themselves, so the high-risk limb of this answer rests on the verification "
    "carve-out as stated rather than on provision text quoted above."
)
LIVE_151 = (
    "Not as a standing entitlement on the provisions supplied here. What those "
    "provisions establish is access on request rather than remote access. "
    "Providers of high-risk AI systems must keep the technical documentation at "
    "the disposal of the national competent authorities under Article 18. The "
    "references provided do not settle whether a market surveillance authority "
    "may require remote access to that documentation or to those data sets, so "
    "that question cannot be answered on this material."
)
LIVE_281 = (
    "Not high-risk on the facts stated. A conversational speech interface that "
    "captures a caller's consent to call recording performs an input-capture "
    "function rather than any of the functions the Act treats as high-risk. The "
    "classification provisions themselves were not among the references supplied "
    "to me, so treat this as an assessment on the stated facts rather than a "
    "formal Annex III screen, and confirm it against the provider's stated "
    "intended purpose. Should the system in fact be a high-risk system listed in "
    "Annex III, the operator's duties would include the fundamental rights "
    "impact assessment required by Article 27 before first use, which applies to "
    "deployers of the systems in points 5(b) and (c) of Annex III."
)

_CIT = re.compile(r"Article \d+|Annex [IVXL]+")


class TestStripsRealLiveLeaks:
    @pytest.mark.parametrize("text", [LIVE_125, LIVE_151, LIVE_281])
    def test_meta_removed(self, text: str) -> None:
        out = strip_retrieval_meta(text)
        assert out != text, "the live leak was not stripped"
        low = out.lower()
        assert "references supplied" not in low
        assert "references provided" not in low
        assert "provisions supplied" not in low
        assert "not among the references" not in low
        assert "on this material" not in low

    @pytest.mark.parametrize("text", [LIVE_125, LIVE_151, LIVE_281])
    def test_no_citation_is_lost(self, text: str) -> None:
        out = strip_retrieval_meta(text)
        assert not (set(_CIT.findall(text)) - set(_CIT.findall(out)))

    @pytest.mark.parametrize("text", [LIVE_125, LIVE_151, LIVE_281])
    def test_idempotent(self, text: str) -> None:
        once = strip_retrieval_meta(text)
        assert strip_retrieval_meta(once) == once

    def test_entangled_verdict_survives_clause_excision(self) -> None:
        """july7-151 opens 'Not as a standing entitlement ON THE PROVISIONS
        SUPPLIED HERE.' — the verdict and the meta share one sentence. A blunt
        sentence-drop would delete the answer; the clause-level pass must keep
        the verdict and excise only the qualifier."""
        out = strip_retrieval_meta(LIVE_151)
        assert out.startswith("Not as a standing entitlement")
        assert "supplied here" not in out.lower()


class TestDoesNotTouchLegitimateProse:
    """The Act's own wording uses 'provided' constantly. None of this is
    meta-commentary and none of it may be stripped."""

    @pytest.mark.parametrize(
        "text",
        [
            "Deployers shall use the information provided under Article 13 and "
            "assign human oversight to natural persons with the necessary "
            "competence, as Article 26 requires of every deployer of a high-risk "
            "AI system placed on the Union market.",
            "Providers must draw up the instructions for use provided to "
            "deployers under Article 13, and keep the technical documentation "
            "referred to in Annex IV for ten years after the system is placed on "
            "the market or put into service.",
            "The provider shall ensure that the information provided to the "
            "notified body is complete, and that the declaration of conformity "
            "drawn up under Article 47 is kept for the period Article 18 sets.",
        ],
    )
    def test_legitimate_provided_survives(self, text: str) -> None:
        assert strip_retrieval_meta(text) == text


class TestSafety:
    def test_empty_and_none_safe(self) -> None:
        assert strip_retrieval_meta("") == ""
        assert strip_retrieval_meta("   ") == "   "

    def test_single_sentence_untouched(self) -> None:
        one = "The references supplied here contain Article 5."
        assert strip_retrieval_meta(one) == one

    def test_never_empties(self) -> None:
        for t in (LIVE_125, LIVE_151, LIVE_281):
            assert strip_retrieval_meta(t).strip()

    def test_below_floor_returns_original(self) -> None:
        """If stripping would leave under the substance floor, keep the input."""
        thin = "No. The references supplied here do not settle it."
        assert strip_retrieval_meta(thin) == thin

    def test_env_off_switch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REGENOLD_STRIP_RETRIEVAL_META", "0")
        assert strip_retrieval_meta(LIVE_125) == LIVE_125

    def test_default_is_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REGENOLD_STRIP_RETRIEVAL_META", raising=False)
        assert strip_retrieval_meta(LIVE_125) != LIVE_125


class TestWiredIntoTheWire:
    def test_normaliser_applies_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.integrations.regenold.models import normalise_answer_for_regenold

        monkeypatch.delenv("REGENOLD_STRIP_RETRIEVAL_META", raising=False)
        monkeypatch.setenv("REGENOLD_MAX_ANSWER_SENTENCES", "0")
        out = normalise_answer_for_regenold(LIVE_125)
        assert "references supplied here" not in out.lower()


class TestPromptNoLongerInvitesIt:
    """The leak was partly self-inflicted: the delivered Stage-2 user clause
    ended 'If it does not settle a point, say so plainly', and july7-151
    complied almost verbatim ('The references provided do not settle
    whether ...'). The clause must now direct that limitation to the LAW."""

    def test_clause_forbids_source_commentary(self) -> None:
        from app.data.graph_rag_prompts import USER_ANSWER_COVERAGE_CLAUSE

        low = USER_ANSWER_COVERAGE_CLAUSE.lower()
        assert "as a matter of law" in low
        assert "do not mention the references" in low
        assert "say so plainly." not in low
