"""R82-A — regression tests for the scoring-side text normaliser.

The normaliser is the canonical Unicode + abbreviation folding step
used by ``evals/bench/metrics.py`` to map gold + pred onto the same
token space for SQuAD-F1 / ROUGE-precedent token-overlap scoring. It
is INTENTIONALLY more aggressive than
``app/integrations/regenold/text_normalize.py`` (which is request-time
and length-preserving): this one is scoring-time and lossy by design.
"""
from __future__ import annotations

from evals.bench.text_normalise import normalise_for_scoring


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
