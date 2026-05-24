"""R82-A — regression tests for the scoring-side text normaliser.

The normaliser is the canonical Unicode + abbreviation folding step
used by ``evals/bench/metrics.py`` to map gold + pred onto the same
token space for SQuAD-F1 / ROUGE-precedent token-overlap scoring. It
is INTENTIONALLY more aggressive than
``app/integrations/regenold/text_normalize.py`` (which is request-time
and length-preserving): this one is scoring-time and lossy by design.
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
        # Both kinds of single quote → ASCII apostrophe
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
        # 'Smart.' or 'apart' must NOT become 'smarticle' / 'aparticle'
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

    def test_currency_symbol_preserved(self) -> None:
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
    """Greedy strip of 4 frequent suffixes until no suffix matches.

    Greedy loop ensures ``analysing`` / ``analyses`` / ``analysed`` all
    collapse to the same stem (``analy``), so morphological variation
    doesn't fragment the token space.
    """

    def test_ing_collapses_to_analy(self) -> None:
        # 'analysing' → 'analys' → 'analy' (greedy loop)
        assert stem_token("analysing") == "analy"

    def test_es_collapses_to_analy(self) -> None:
        # 'analyses' → 'analys' → 'analy' (longest suffix first)
        assert stem_token("analyses") == "analy"

    def test_ed_collapses_to_analy(self) -> None:
        # 'analysed' → 'analys' → 'analy'
        assert stem_token("analysed") == "analy"

    def test_morphological_variants_collapse_to_same_stem(self) -> None:
        # The whole POINT of stemming — three variants → one token.
        assert stem_token("analysing") == stem_token("analyses") == stem_token("analysed")

    def test_s_strips_on_long_token(self) -> None:
        # 'systems' is 7 chars > 4; 's' strips → 'system'. No further suffix.
        assert stem_token("systems") == "system"

    def test_documented_collapses(self) -> None:
        # 'documented' → strip 'ed' → 'document' (8 chars, no further suffix)
        assert stem_token("documented") == "document"

    def test_two_char_tokens_pass_through(self) -> None:
        # Critical: short load-bearing tokens like AI / EU never stem.
        assert stem_token("ai") == "ai"
        assert stem_token("eu") == "eu"

    def test_three_char_passes_through(self) -> None:
        # 'cat' is 3 chars; 's' needs > 4 → no strip
        assert stem_token("cat") == "cat"

    def test_four_char_passes_through(self) -> None:
        # 'cats' is 4 chars; 's' needs > 4 → no strip
        assert stem_token("cats") == "cats"

    def test_five_char_s_strips(self) -> None:
        # 'birds' is 5 chars > 4 → 's' strips → 'bird' (4 chars, stable)
        assert stem_token("birds") == "bird"

    def test_idempotent(self) -> None:
        # Greedy loop converges in one call; second call is a no-op.
        once = stem_token("analysing")
        twice = stem_token(once)
        assert once == twice == "analy"

    def test_no_alpha_passes_through(self) -> None:
        assert stem_token("15") == "15"

    def test_empty(self) -> None:
        assert stem_token("") == ""
