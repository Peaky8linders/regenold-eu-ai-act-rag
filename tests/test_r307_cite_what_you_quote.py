"""R307 — two defects found by the R306 deep review, both measured live.

DEFECT 1 — cite-and-mismatch on the extractive composer.

    Q "What are the deployer obligations under Art 50"
      select_answer_sentence(Q, 'Art. 50') -> None   (confidence gate)
      select_answer_sentence(Q, 'Art. 26') -> "Where applicable, deployers
         of high-risk AI systems shall use the information provided under
         Article 13 ... data protection impact assessment under Article 35
         of Regulation (EU) 2016/679 ..."
    That Article 26(9) sentence shipped as the answer while
    ``_prune_non_anchor_refs`` collapsed references to ['Article 50'].
    The wire quoted one provision and cited another — a confidently-wrong
    attribution (hard rule #4).

    The loop walks the engine's top citations and returns the FIRST that
    yields a sentence, so it silently borrows a later article's prose.
    Nothing ties the provision that SOURCED the answer to the provisions
    that end up cited: ``answer_text`` is frozen early while
    ``references`` keeps being rewritten by ~25 later passes.

DEFECT 2 — the two most canonical questions in the domain hit the
zero-retrieval floor.

    "What obligations does a provider have?"  -> ['Article 1','Article 2',
        'Article 3.3'], retrieval_path="zero_retrieval_fallback",
        engine_confidence 0.0
    "What obligations does a deployer have?"  -> ['Article 1','Article 2',
        'Article 3.4'], same path, same 0.0
    Both returned byte-identical Article 1/2 purpose-and-scope boilerplate.
"""

from __future__ import annotations

import pytest

from app.data.article_existence import ARTICLE_EXISTENCE
from app.engines.zero_retrieval_fallback import (
    _role_duty_seeds,
    zero_retrieval_fallback,
)
from app.routes.regenold import (
    _extract_cited_only_enabled,
    _live_explicit_anchor_sets,
    _ref_matches_anchor_sets,
)

# ── Fix A — cite what you quote ──────────────────────────────────────

Q_ART50 = "What are the deployer obligations under Art 50"


class TestExplicitAnchorExtraction:
    def test_extracts_article_number(self):
        nums, annexes = _live_explicit_anchor_sets(Q_ART50)
        assert nums == {"50"}
        assert annexes == set()

    @pytest.mark.parametrize(
        "q,expected",
        [
            ("What does Article 13 require?", {"13"}),
            ("What does Art. 13 require?", {"13"}),
            ("What does Art 13 require?", {"13"}),
            ("Was verlangt Artikel 13?", {"13"}),
            ("Compare Article 16 and Article 26.", {"16", "26"}),
        ],
    )
    def test_article_forms(self, q, expected):
        assert _live_explicit_anchor_sets(q)[0] == expected

    def test_extracts_annex_roman(self):
        nums, annexes = _live_explicit_anchor_sets("What must be in Annex IV?")
        assert annexes == {"IV"}
        assert nums == set()

    def test_conceptual_question_has_no_anchor(self):
        """No anchors -> the guard must not fire at all."""
        nums, annexes = _live_explicit_anchor_sets(
            "What obligations does a provider have?"
        )
        assert not nums and not annexes

    def test_reads_only_the_live_turn(self):
        """Mirrors _prune_non_anchor_refs: a prior turn must not anchor."""
        flattened = (
            "Conversation so far:\nuser: What does Article 13 require?\n\n"
            "Latest question:\nWhat about deployers?"
        )
        nums, _ = _live_explicit_anchor_sets(flattened)
        assert nums == set()

    def test_fail_soft(self):
        assert _live_explicit_anchor_sets("") == (set(), set())
        assert _live_explicit_anchor_sets(None) == (set(), set())  # type: ignore[arg-type]


class TestRefMatchesAnchors:
    @pytest.mark.parametrize(
        "ref,ok",
        [
            ("Art. 50", True),
            ("Article 50", True),
            ("Art. 50(3)", True),   # sub-point matches on its PARENT
            ("Art. 26", False),
            ("Art. 5", False),      # must not match on a numeric prefix
            ("Annex IV", False),
        ],
    )
    def test_article_matching(self, ref, ok):
        assert _ref_matches_anchor_sets(ref, {"50"}, set()) is ok

    def test_annex_matching(self):
        assert _ref_matches_anchor_sets("Annex IV", set(), {"IV"}) is True
        assert _ref_matches_anchor_sets("Annex III", set(), {"IV"}) is False

    def test_empty_and_garbage_are_safe(self):
        assert _ref_matches_anchor_sets("", {"50"}, set()) is False
        assert _ref_matches_anchor_sets("nonsense", {"50"}, set()) is False

    def test_gate_default_on(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_EXTRACT_CITED_ONLY", raising=False)
        assert _extract_cited_only_enabled() is True

    @pytest.mark.parametrize("v", ["0", "off", "false", "no"])
    def test_gate_off_switch(self, monkeypatch, v):
        monkeypatch.setenv("REGENOLD_EXTRACT_CITED_ONLY", v)
        assert _extract_cited_only_enabled() is False


# ── Fix B — role-duty rescue on the zero-retrieval path ──────────────


class TestRoleDutySeed:
    @pytest.mark.parametrize(
        "q,expected",
        [
            ("What obligations does a provider have?", ["Art. 16"]),
            ("What obligations does a deployer have?", ["Art. 26"]),
            ("What are the responsibilities of importers?", ["Art. 23"]),
            ("What must a distributor do to comply with the Act?", ["Art. 24"]),
            (
                "What are the obligations of an authorised representative?",
                ["Art. 22"],
            ),
            (
                "What are the obligations of an authorized representative?",
                ["Art. 22"],
            ),
        ],
    )
    def test_role_duty_questions_seed_their_article(self, q, expected):
        assert _role_duty_seeds(q) == expected

    @pytest.mark.parametrize(
        "q",
        [
            # Definitional — gold is the Article 3 definition, NOT the
            # role's obligation article.
            "What is a provider?",
            "What is a deployer under the EU AI Act?",
            "Who counts as an importer?",
            # No role noun at all.
            "What are the obligations for high-risk AI systems?",
            "What obligations apply to GPAI models?",
            # Role noun but no duty marker.
            "Is a hospital a deployer?",
        ],
    )
    def test_non_role_duty_questions_do_not_seed(self, q):
        assert _role_duty_seeds(q) == []

    def test_authorised_representative_wins_over_nothing_shorter(self):
        """Longest role phrase first — must not be read as a bare role."""
        out = _role_duty_seeds(
            "What are the duties of the authorised representative?"
        )
        assert out == ["Art. 22"]

    def test_every_seeded_ref_exists(self):
        from app.engines.zero_retrieval_fallback import _ROLE_DUTY_SEED_MAP

        for _phrases, ref in _ROLE_DUTY_SEED_MAP:
            assert ref in ARTICLE_EXISTENCE, ref

    def test_reads_only_the_live_turn(self):
        flattened = (
            "Conversation so far:\nuser: What obligations does a provider have?\n\n"
            "Latest question:\nAnd what about GPAI models?"
        )
        assert _role_duty_seeds(flattened) == []

    def test_gate_default_on(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_ROLE_DUTY_ZRF", raising=False)
        assert _role_duty_seeds("What obligations does a provider have?") == [
            "Art. 16"
        ]

    @pytest.mark.parametrize("v", ["0", "off", "false", "no"])
    def test_gate_off_switch(self, monkeypatch, v):
        monkeypatch.setenv("REGENOLD_ROLE_DUTY_ZRF", v)
        assert _role_duty_seeds("What obligations does a provider have?") == []

    def test_fail_soft(self):
        for bad in ("", None, 12345):
            assert _role_duty_seeds(bad) == []  # type: ignore[arg-type]


class TestZeroRetrievalFallbackComposition:
    def test_provider_duty_replaces_the_purpose_scope_floor(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_ROLE_DUTY_ZRF", raising=False)
        refs, prose = zero_retrieval_fallback(
            "What obligations does a provider have?"
        )
        assert refs == ["Art. 16"]
        assert "Art. 1" not in refs and "Art. 2" not in refs
        assert prose

    def test_deployer_is_not_answered_with_the_provider_article(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_ROLE_DUTY_ZRF", raising=False)
        refs, _ = zero_retrieval_fallback("What obligations does a deployer have?")
        assert refs == ["Art. 26"]

    def test_role_aware_unlike_the_intent_seed(self, monkeypatch):
        """The pre-existing role_obligations intent seed is deployer-centric.

        It would answer a PROVIDER question with Article 26. The
        deterministic role seed must not.
        """
        monkeypatch.delenv("REGENOLD_ROLE_DUTY_ZRF", raising=False)
        provider, _ = zero_retrieval_fallback(
            "What obligations does a provider have?"
        )
        deployer, _ = zero_retrieval_fallback(
            "What obligations does a deployer have?"
        )
        assert provider != deployer

    def test_default_floor_still_applies_without_any_signal(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_ROLE_DUTY_ZRF", raising=False)
        refs, _ = zero_retrieval_fallback("Tell me about this regulation")
        assert refs == ["Art. 1", "Art. 2", "Art. 3"]

    def test_explicit_anchor_still_leads(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_ROLE_DUTY_ZRF", raising=False)
        refs, _ = zero_retrieval_fallback(
            "What obligations does a provider have under Article 16?",
            explicit_anchors=("Art. 16",),
        )
        assert refs[0] == "Art. 16"

    def test_off_switch_restores_the_floor(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_ROLE_DUTY_ZRF", "0")
        refs, _ = zero_retrieval_fallback(
            "What obligations does a provider have?"
        )
        assert refs == ["Art. 1", "Art. 2", "Art. 3"]

    def test_every_returned_ref_exists(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_ROLE_DUTY_ZRF", raising=False)
        for q in (
            "What obligations does a provider have?",
            "What obligations does a deployer have?",
            "Tell me about this regulation",
        ):
            refs, _ = zero_retrieval_fallback(q)
            assert refs
            for r in refs:
                assert r in ARTICLE_EXISTENCE, r


# ── Fix C — plural citation abbreviations ────────────────────────────


class TestPluralCitationAbbreviations:
    """R307 — ``Art.`` was protected from the sentence splitter, ``Arts.`` was not.

    Surfaced by the live A/B for Fix B: with Article 16 correctly
    surfaced, its KB stub ("keep the technical documentation (Arts. 11
    and 18)") split after "(Arts." and the 3-sentence cap shipped an
    answer ending mid-citation:

        "...operate a quality-management system (Art. 17), keep the
         technical documentation (Arts."

    Same class as the R59 tone-guard Annex-lookbehind bug. Adding an
    abbreviation can only SUPPRESS a false split, never create one.
    """

    def test_plural_article_citation_does_not_split(self):
        from app.integrations.regenold.models import _split_sentences

        t = (
            "Providers must operate a quality-management system (Art. 17), "
            "keep the technical documentation (Arts. 11 and 18), and affix "
            "the CE marking (Art. 48)."
        )
        assert len(_split_sentences(t)) == 1

    def test_no_answer_ends_mid_citation(self):
        from app.integrations.regenold.models import _split_sentences

        t = (
            "Providers must operate a quality-management system (Art. 17), "
            "keep the technical documentation (Arts. 11 and 18)."
        )
        for s in _split_sentences(t):
            assert not s.rstrip().endswith(("(Arts.", "(Art.", "(Annexes", "Arts."))

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("See Annexes IV and V. Also see Arts. 9 to 15.", 2),
            ("Under Recitals 26 and 27 the principles apply.", 1),
            ("Refer to Secs. 2 and 3 of Chapter III.", 1),
            # Genuine boundaries must still be found.
            ("This is one sentence. This is a second sentence.", 2),
            (
                "Article 5 prohibits eight practices. "
                "Article 6 classifies high-risk systems.",
                2,
            ),
        ],
    )
    def test_splitting_still_correct(self, text, expected):
        from app.integrations.regenold.models import _split_sentences

        assert len(_split_sentences(text)) == expected

    def test_singular_forms_still_protected(self):
        from app.integrations.regenold.models import _split_sentences

        assert len(_split_sentences("See Art. 16 and para. 3 for detail.")) == 1
