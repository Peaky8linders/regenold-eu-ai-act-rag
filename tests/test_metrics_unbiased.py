from evals.bench.metrics import (
    _tokens,
    _tokens_legacy,
    answer_correctness_loose,
    answer_correctness_strict,
    answer_keyword_recall,
)


class TestNBHAlignment:
    """U+2011 in gold should yield the same tokens as ASCII '-' in pred."""

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
        # a digit-only token (length 1) → filtered; both produce
        # {"article", "requires", "logs"}.
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
        assert "shall" in _tokens("Deployers shall maintain logs")


class TestStemmerInTokens:
    def test_analysing_collapses_with_analyse(self) -> None:
        a = _tokens("analyse the system")
        b = _tokens("analysing the system")
        assert a == b

    def test_systems_collapses_with_system(self) -> None:
        a = _tokens("the system")
        b = _tokens("the systems")
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
    """End-to-end check: NBH-only-difference scores 1.0 Strict + 1.0 Loose."""

    def test_high_risk_pair_loose_1(self) -> None:
        # Gold uses NBH, pred uses ASCII hyphen. Otherwise identical tokens.
        gold = "High‑risk AI must conduct assessment"
        pred = "high-risk ai must conduct assessment"
        assert answer_correctness_loose(pred, gold) == 1.0

    def test_high_risk_pair_strict_1(self) -> None:
        gold = "High‑risk AI must conduct assessment"
        pred = "high-risk ai must conduct assessment"
        assert answer_correctness_strict(pred, gold) == 1.0


class TestAnswerKeywordRecall:
    """Curated keyword recall — closer to what an LLM judge will see."""

    def test_all_keywords_present(self) -> None:
        pred = "Providers must document and maintain a risk management system."
        keywords = ["document", "maintain", "risk", "management"]
        assert answer_keyword_recall(pred, keywords) == 1.0

    def test_half_keywords_present(self) -> None:
        pred = "Providers must document the system."
        keywords = ["document", "maintain", "risk", "management"]
        # only 'document' matches → 1/4 = 0.25
        assert answer_keyword_recall(pred, keywords) == 0.25

    def test_normalisation_applies(self) -> None:
        # Gold keyword carries NBH; pred has ASCII hyphen
        pred = "high-risk classification"
        keywords = ["high‑risk", "classification"]
        assert answer_keyword_recall(pred, keywords) == 1.0

    def test_stem_helps(self) -> None:
        pred = "analysing the system documented the risks"
        keywords = ["analyse", "document", "risk"]
        # All three stem-match: 'analys', 'document', 'risk'
        assert answer_keyword_recall(pred, keywords) == 1.0

    def test_empty_keywords_returns_none_sentinel(self) -> None:
        # Caller convention: empty keyword list → axis not applicable
        # → return None (so aggregate can skip the row).
        assert answer_keyword_recall("anything", []) is None

    def test_none_keywords_returns_none(self) -> None:
        assert answer_keyword_recall("anything", None) is None

    def test_empty_pred_zero(self) -> None:
        assert answer_keyword_recall("", ["a", "b"]) == 0.0
