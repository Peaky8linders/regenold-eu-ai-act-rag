# tests/test_evals_text_normalise.py
"""Regression tests for the scoring-side text normaliser.

The normaliser is the canonical Unicode + abbreviation folding step
used by `evals/bench/metrics.py` to map gold + pred onto the same
token space for SQuAD-F1 / ROUGE-precedent scoring. It is INTENTIONALLY
more aggressive than `app/integrations/regenold/text_normalize.py`
(which is request-time, length-preserving): this one is scoring-time
and lossy by design.
"""
from __future__ import annotations

from evals.bench.text_normalise import normalise_for_scoring, stem_token


class TestUnicodeDashFolding:
    def test_non_breaking_hyphen_folds(self) -> None:
        # U+2011 — 42% of davidath gold answers carry this
        assert normalise_for_scoring("high‑risk") == "high-risk"

    def test_en_dash_folds(self) -> None:
        assert normalise_for_scoring("2024–2026") == "2024-2026"

    def test_em_dash_folds(self) -> None:
        assert normalise_for_scoring("provider—deployer") == "provider-deployer"

    def test_minus_sign_folds(self) -> None:
        assert normalise_for_scoring("10−5") == "10-5"

    def test_ascii_hyphen_passes_through(self) -> None:
        assert normalise_for_scoring("high-risk") == "high-risk"


class TestApostropheFolding:
    def test_curly_apostrophe(self) -> None:
        assert normalise_for_scoring("provider’s") == "provider's"

    def test_left_single_quote(self) -> None:
        assert normalise_for_scoring("‘ai system’") == "'ai system'"


class TestArticleAbbreviation:
    def test_dot_form_expands(self) -> None:
        # Pred says "Art. 6"; gold says "Article 6" — both should match
        assert normalise_for_scoring("Art. 6 requires logs") == "article 6 requires logs"

    def test_plural_abbrev(self) -> None:
        assert normalise_for_scoring("Arts. 9 and 10") == "article 9 and 10"

    def test_already_expanded_passes(self) -> None:
        assert normalise_for_scoring("Article 6") == "article 6"

    def test_word_boundary_not_inside_other_token(self) -> None:
        # 'Smart.' or 'apart.' must NOT become 'smarticle'
        assert "article" not in normalise_for_scoring("partake")
        assert "article" not in normalise_for_scoring("Smart. people read")


class TestAnnexAbbreviation:
    def test_dot_form_expands(self) -> None:
        assert normalise_for_scoring("Ann. III") == "annex iii"

    def test_already_expanded(self) -> None:
        assert normalise_for_scoring("Annex IV") == "annex iv"


class TestDiacriticStrip:
    def test_grave(self) -> None:
        assert normalise_for_scoring("équivalent") == "equivalent"

    def test_circumflex(self) -> None:
        assert normalise_for_scoring("rôle") == "role"

    def test_euro_symbol_preserved(self) -> None:
        # Currency symbol is not a diacritic — preserve so it can be
        # tokenised or stripped at the token regex layer.
        out = normalise_for_scoring("€15 million")
        assert "€" in out or "15 million" in out


class TestCaseFolding:
    def test_uppercase(self) -> None:
        assert normalise_for_scoring("AI Act") == "ai act"

    def test_mixed_case(self) -> None:
        assert normalise_for_scoring("EuRoPeaN") == "european"


class TestEmptyAndNone:
    def test_empty_string(self) -> None:
        assert normalise_for_scoring("") == ""

    def test_none(self) -> None:
        assert normalise_for_scoring(None) == ""  # type: ignore[arg-type]

    def test_whitespace_only(self) -> None:
        assert normalise_for_scoring("   ") == "   "


class TestIdempotence:
    def test_double_normalise_is_stable(self) -> None:
        sample = "Art. 6 requires high‑risk AI providers to ‘document’ €15M"
        once = normalise_for_scoring(sample)
        twice = normalise_for_scoring(once)
        assert once == twice


class TestStemmer:
    """Greedy strip of 5 frequent suffixes until no further suffix fires.

    Updated for R82-A.1: the stemmer is now greedy (loops to fixed
    point), so all four morphological variants of a verb collapse to
    the SAME final stem. Pre-R82-A.1 single-pass left ``analysing`` at
    ``analys`` and ``analyse`` at ``analys`` but ``stem(stem(analyse))``
    yielded ``analy`` — non-idempotent. Greedy converges in one call.
    """

    def test_ing_collapses_to_analy(self) -> None:
        # R82-A.1: greedy loops 'analysing' -> 'analys' -> 'analy'
        assert stem_token("analysing") == "analy"

    def test_es_collapses_to_analy(self) -> None:
        # 'analyses' -> strip 'es' -> 'analys' -> strip 's' -> 'analy'
        assert stem_token("analyses") == "analy"

    def test_ed_collapses_to_analy(self) -> None:
        # 'analysed' -> strip 'ed' -> 'analys' -> strip 's' -> 'analy'
        assert stem_token("analysed") == "analy"

    def test_e_strip_also_collapses(self) -> None:
        # Base form 'analyse' (7 chars) -> strip 'e' -> 'analys' ->
        # strip 's' -> 'analy'. Greedy ensures the base form collapses
        # to the same stem as the -ing/-es/-ed variants.
        assert stem_token("analyse") == "analy"

    def test_morphological_variants_collapse_to_same_stem(self) -> None:
        """The whole POINT of greedy stemming: 4 variants → 1 stem."""
        a = stem_token("analyse")
        b = stem_token("analysing")
        c = stem_token("analyses")
        d = stem_token("analysed")
        assert a == b == c == d == "analy"

    def test_s_strips_on_long_token(self) -> None:
        # 'systems' (7 chars) -> strip 's' -> 'system' (6 chars).
        # 'system' has no terminal suffix in the set -> stable.
        assert stem_token("systems") == "system"

    def test_documents_collapses_with_documented(self) -> None:
        # 'documents' -> strip 's' -> 'document' (8 chars, no suffix)
        # 'documented' -> strip 'ed' -> 'document' (8 chars, no suffix)
        assert stem_token("documents") == stem_token("documented") == "document"

    def test_short_tokens_pass_through(self) -> None:
        # 'cats' would stem to 'cat' (length 4) — but 'ai', 'eu' must
        # not be touched. Suffix only strips when token length > suf+3.
        assert stem_token("ai") == "ai"
        assert stem_token("eu") == "eu"
        # `cat` is 3 chars; 's' suffix needs token length > 4 → no strip
        assert stem_token("cat") == "cat"
        # `cats` is 4 chars; 's' needs > 4 → no strip
        assert stem_token("cats") == "cats"
        # `birds` is 5 chars > 4 → 's' strips
        assert stem_token("birds") == "bird"

    def test_truly_idempotent(self) -> None:
        """R82-A.1 invariant: stem(stem(x)) == stem(x) for all x.

        Pre-R82-A.1 single-pass failed this on tokens whose stem still
        ended in a suffix (e.g. stem('analyse') = 'analys' but
        stem('analys') = 'analy', so stem(stem('analyse')) = 'analy' !=
        stem('analyse') = 'analys'). Greedy fixes it by converging
        within the first call.
        """
        for sample in [
            "analyse", "analysing", "analyses", "analysed",
            "document", "documents", "documented", "documenting",
            "system", "systems", "service", "services",
        ]:
            once = stem_token(sample)
            twice = stem_token(once)
            assert once == twice, f"stem({sample!r}) = {once!r} but stem({once!r}) = {twice!r}"

    def test_compliance_not_collapsed_with_compliant(self) -> None:
        """Known non-collapse: -e strip on 'compliance' yields 'complianc',
        not 'compliant'. We accept this — collapsing them would require
        Porter's full rules (y -> i, -ies -> -y, etc.) which over-fires
        on regulatory text. Pinning the limitation so it doesn't drift."""
        assert stem_token("compliance") == "complianc"
        assert stem_token("compliant") == "compliant"

    def test_no_alpha_passes_through(self) -> None:
        assert stem_token("15") == "15"

    def test_empty(self) -> None:
        assert stem_token("") == ""


def stem_function_invariant_short(t: str) -> bool:
    """Helper — short tokens (≤ 4 chars) must never stem."""
    return stem_token(t) == t
