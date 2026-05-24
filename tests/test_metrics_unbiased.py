"""R82-A — corrected-tokenizer alignment + bias-removal regression tests."""
from __future__ import annotations

from evals.bench.metrics import (
    _tokens,
    _tokens_legacy,
    answer_correctness_loose,
    answer_correctness_strict,
)


class TestNBHAlignment:
    """U+2011 in gold should yield the same tokens as ASCII '-' in pred.

    42% of davidath QA gold answers ship NBH; engine writes ASCII.
    """

    def test_high_risk_aligns(self) -> None:
        g = _tokens("high‑risk AI system")
        p = _tokens("high-risk AI system")
        assert g == p

    def test_general_purpose_aligns(self) -> None:
        g = _tokens("general‑purpose model")
        p = _tokens("general-purpose model")
        assert g == p


class TestArtArticleAlignment:
    def test_dot_form_aligns_with_full(self) -> None:
        g = _tokens("Article 9 requires logs")
        p = _tokens("Art. 9 requires logs")
        # After normalisation both → "article 9 requires logs"; "9" is
        # length 1 → filtered; both produce
        # {"article", "requir", "log"} (after stemming).
        assert g == p


class TestTwoCharTokensAccepted:
    def test_ai_token_kept(self) -> None:
        toks = _tokens("AI system")
        assert "ai" in toks

    def test_eu_token_kept(self) -> None:
        toks = _tokens("EU regulator")
        assert "eu" in toks

    def test_single_char_dropped(self) -> None:
        # 'a' is filtered by both stopword + 2-char-min — stays out.
        toks = _tokens("a system")
        assert "a" not in toks

    def test_one_char_digit_dropped(self) -> None:
        # `3` is one char, fails 2-char min.
        toks = _tokens("3 %")
        assert "3" not in toks

    def test_two_char_digit_kept(self) -> None:
        # `15` survives — has length 2, regex accepts digit-led tokens.
        toks = _tokens("15 million")
        assert "15" in toks


class TestModalVerbsScored:
    """Regulatory modals are load-bearing; not stopwords any more."""

    def test_must_in_tokens(self) -> None:
        assert "must" in _tokens("Providers must document")

    def test_shall_in_tokens(self) -> None:
        # 'shall' stems? len 5 > 4, doesn't end with any suffix — stays 'shall'
        assert "shall" in _tokens("Deployers shall maintain logs")


class TestStemmerInTokens:
    def test_analysing_collapses_with_analysed(self) -> None:
        # 'analysing' → 'analys' → 'analy'
        # 'analysed'  → 'analys' → 'analy'
        # (The base 'analyse' does NOT collapse — we don't strip -e
        # because that would mis-collapse 'compliance' ≠ 'compliant'.
        # This is acceptable: the dominant davidath morphological
        # variation is -ing / -ed / -es, not bare -e.)
        a = _tokens("analysing the system")
        b = _tokens("analysed the system")
        assert a == b

    def test_analyses_collapses_with_analysed(self) -> None:
        a = _tokens("analyses the data")
        b = _tokens("analysed the data")
        assert a == b

    def test_systems_collapses_with_system(self) -> None:
        # 'systems' (7 chars) → strip 's' → 'system' (6 chars, stable)
        # 'system' (6 chars) → no strip
        a = _tokens("the system")
        b = _tokens("the systems")
        assert a == b

    def test_documents_collapses_with_documented(self) -> None:
        # 'documents' → strip 's' → 'document'
        # 'documented' → strip 'ed' → 'document'
        a = _tokens("documents the risk")
        b = _tokens("documented the risk")
        assert a == b


class TestLegacyTokenizerPreserved:
    """`_tokens_legacy` reproduces the pre-R82 shipped behaviour byte-identically."""

    def test_legacy_drops_two_char(self) -> None:
        assert "ai" not in _tokens_legacy("AI system")

    def test_legacy_treats_nbh_as_split(self) -> None:
        g = _tokens_legacy("high‑risk")
        p = _tokens_legacy("high-risk")
        # Pre-R82 these DON'T align — gold splits into {"high", "risk"},
        # pred is {"high-risk"}.
        assert g != p

    def test_legacy_drops_modals(self) -> None:
        assert "must" not in _tokens_legacy("must document")
        assert "shall" not in _tokens_legacy("shall maintain")


class TestCorrectnessFormulasUseNewTokenizer:
    """End-to-end check: a pair that differs ONLY by harness-bias dims scores 1.0."""

    def test_high_risk_pair_loose_1(self) -> None:
        # Gold uses NBH, pred uses ASCII. Same modals, same stems, same
        # case. After normalisation both tokenise identically.
        gold = "High‑risk AI must conduct assessment"
        pred = "high-risk ai must conduct assessment"
        assert answer_correctness_loose(pred, gold) == 1.0

    def test_high_risk_pair_strict_1(self) -> None:
        gold = "High‑risk AI must conduct assessment"
        pred = "high-risk ai must conduct assessment"
        assert answer_correctness_strict(pred, gold) == 1.0
