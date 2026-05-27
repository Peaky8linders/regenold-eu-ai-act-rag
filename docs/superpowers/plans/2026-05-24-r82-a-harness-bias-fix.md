# R82-A — Harness bias fix implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the biased Loose/Strict tokenizer in `evals/bench/metrics.py` with a SQuAD-F1 / ROUGE-precedent normaliser + stemmer, preserve legacy axes alongside, add a third `ans_keyword_recall` axis against curated keyword lists, and re-score every historical sidecar so the corrected baseline is public.

**Architecture:** New `evals/bench/text_normalise.py` module exports a pure-stdlib `normalise_for_scoring(text)` + `_stem(token)`. `evals/bench/metrics.py` swaps `_tokens` to use them; legacy `_tokens_legacy` is preserved so `*_legacy` axes still reproduce pre-R82 numbers byte-identically. `RowScore` carries both new and legacy axes plus an optional `answer_keyword_recall`. `score_row()` gains an optional `expected_keywords` kwarg; runners that have curated keywords pass them through. `scripts/rescore_sidecars.py` walks `evals/bench/results/*.json`, recomputes the axes per-row, and writes sibling `<label>.rescored.json` files. The scorecard delta is published in `docs/r82-rescored-history.md`.

**Tech Stack:** Python 3.12, stdlib only for the new module (re + unicodedata). pytest. No new dependencies.

---

## File map

**Created:**
- `evals/bench/text_normalise.py` — canonical normaliser + stemmer
- `tests/test_evals_text_normalise.py` — normaliser + stemmer regression tests
- `tests/test_metrics_unbiased.py` — corrected-tokenizer + alignment regression tests
- `tests/test_metrics_no_overshoot.py` — guards against false-positive credit
- `tests/test_metrics_legacy_preservation.py` — legacy axes byte-identical to pre-R82
- `scripts/rescore_sidecars.py` — historical sidecar rescore walker
- `tests/test_rescore_sidecars.py` — golden tests for the rescorer
- `docs/r82-rescored-history.md` — published corrected scorecard delta

**Modified:**
- `evals/bench/metrics.py` — corrected `_tokens` + `_STOPWORDS_V2` + new fields on `RowScore` / `score_row` / `aggregate`
- `evals/bench/runner.py` — pass `expected_keywords=None` (davidath has none) to keep typing strict
- `evals/bench/representative_100.py` — pass `expected_keywords=row["expected_keywords"]` when present
- `evals/bench/unbiased_runner.py` — same as above where applicable
- `CLAUDE.md` — add R82-A round entry to the eval scorecard table

**Untouched (out of scope for R82-A — these are R82-B work):**
- `app/` — no engine changes
- `app/integrations/regenold/text_normalize.py` — different contract (request-time, length-preserving). Do NOT touch.
- `evals/judge/` — separate axis, separate round

---

## Pre-flight: isolated worktree

This plan ships as one atomic PR. Recommend creating a worktree first via the `superpowers:using-git-worktrees` skill so concurrent main-branch work isn't disturbed.

If skipping the worktree, ensure no uncommitted changes in `evals/bench/` before starting.

---

## Task 1: Create the scoring normaliser module

**Files:**
- Create: `evals/bench/text_normalise.py`
- Test: `tests/test_evals_text_normalise.py`

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```
.venv/Scripts/python.exe -m pytest tests/test_evals_text_normalise.py -v
```

Expected: every test fails with `ModuleNotFoundError: No module named 'evals.bench.text_normalise'`.

- [ ] **Step 3: Write the minimal implementation**

```python
# evals/bench/text_normalise.py
"""Canonical text normaliser for scoring-side evaluation only.

This module is the single source of truth for Unicode + abbreviation
folding used by `evals/bench/metrics.py`. It maps gold + pred onto the
same token space so the SQuAD-F1 / ROUGE-precedent token-overlap
scorers can compare them fairly.

It is INTENTIONALLY more aggressive than `app/integrations/regenold/
text_normalize.py` (request-time, length-preserving, semantics-
preserving): this one is scoring-time and lossy by design — diacritics
stripped, case folded, abbreviations expanded.

DO NOT IMPORT THIS FROM `app/` — it is for `evals/` only. Aggressive
normalisation must never run on production prose.

Why each rule exists (each is grounded in a measured davidath bias):

  * U+2011 non-breaking hyphen → ASCII '-': 42% of davidath QA gold
    answers carry it; engine writes ASCII '-'.
  * Smart quotes → ASCII apostrophe: davidath uses U+2018/U+2019
    throughout ("provider’s").
  * "Art. N" / "Arts. N" → "Article N": davidath gold writes "Article"
    in 5/137 QA prose, never "Art." — engine writes "Art." in 21/100
    live preds.
  * "Ann. N" → "Annex N": symmetric to Art.
  * Diacritic strip: French / German / Czech regulator-text vocabulary
    occasionally appears in cross-reference prose ("équivalent",
    "Wörterbuch") — stripping unifies surface forms.
  * Lowercase: SQuAD-F1 standard.
"""
from __future__ import annotations

import re
import unicodedata

# 6 dash codepoints + minus sign → ASCII '-'
_DASH_RE = re.compile(r"[‐‑‒–—−]")

# Curly + low + modifier apostrophes → ASCII "'"
_APOS_RE = re.compile(r"[‘’‚ʼʻ]")

# Curly double quotes → ASCII '"'
_DQUOT_RE = re.compile(r"[“”„]")

# `Art.` or `Arts.` followed by optional whitespace → `Article `.
# Word boundary on the LEFT prevents matching "Smart." or "Apart.".
_ART_ABBREV_RE = re.compile(r"\bArts?\.\s*", flags=re.IGNORECASE)

# `Ann.` followed by optional whitespace → `Annex `.
_ANN_ABBREV_RE = re.compile(r"\bAnn\.\s*", flags=re.IGNORECASE)


def normalise_for_scoring(text: str | None) -> str:
    """Map text onto the canonical scoring token-space.

    Pipeline (order matters — abbreviation expansion runs before case
    fold so the word-boundary regex sees the original capitalisation;
    diacritic strip runs after dash + apostrophe folding so the dash
    codepoints are unambiguously ASCII before decomposition):

      1. NFKC Unicode normalize (fullwidth → ASCII, ligatures → letters)
      2. Dash codepoints → ASCII '-'
      3. Apostrophe codepoints → ASCII "'"
      4. Double-quote codepoints → ASCII '"'
      5. `Art.` / `Arts.` → `Article `
      6. `Ann.` → `Annex `
      7. NFKD decompose + drop combining marks (strip diacritics)
      8. Lowercase

    Pure, idempotent, stdlib-only. Returns "" for None / empty input.
    """
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = _DASH_RE.sub("-", t)
    t = _APOS_RE.sub("'", t)
    t = _DQUOT_RE.sub('"', t)
    t = _ART_ABBREV_RE.sub("Article ", t)
    t = _ANN_ABBREV_RE.sub("Annex ", t)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t.lower()


__all__ = ["normalise_for_scoring"]
```

- [ ] **Step 4: Run tests to verify pass**

Run:
```
.venv/Scripts/python.exe -m pytest tests/test_evals_text_normalise.py -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add evals/bench/text_normalise.py tests/test_evals_text_normalise.py
git commit -m "feat(R82-A): scoring-side text normaliser (NFKC + dashes + Art./Article + diacritic strip)"
```

---

## Task 2: Add Porter-light stemmer to the normaliser module

**Files:**
- Modify: `evals/bench/text_normalise.py`
- Modify: `tests/test_evals_text_normalise.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_evals_text_normalise.py`:

```python
from evals.bench.text_normalise import stem_token


class TestStemmer:
    # Targeted suffix-strip — only the 4 frequent suffixes that create
    # false morphological misses on regulatory verbs/nouns.

    def test_ing_strips(self) -> None:
        assert stem_token("analysing") == "analys"

    def test_es_strips(self) -> None:
        assert stem_token("analyses") == "analys"

    def test_ed_strips(self) -> None:
        assert stem_token("analysed") == "analys"

    def test_s_strips(self) -> None:
        assert stem_token("systems") == "system"

    def test_short_tokens_pass_through(self) -> None:
        # 'cats' would stem to 'cat' (length 4) — but 'ai', 'eu' must
        # not be touched. Suffix only strips when token length > suf+3.
        assert stem_token("ai") == "ai"
        assert stem_function_invariant_short("eu")
        # `cat` is 3 chars; 's' suffix needs token length > 4 → no strip
        assert stem_token("cat") == "cat"
        # `cats` is 4 chars; 's' needs > 4 → no strip
        assert stem_token("cats") == "cats"
        # `birds` is 5 chars > 4 → 's' strips
        assert stem_token("birds") == "bird"

    def test_idempotent(self) -> None:
        assert stem_token(stem_token("analysing")) == "analys"

    def test_no_alpha_passes_through(self) -> None:
        assert stem_token("15") == "15"

    def test_empty(self) -> None:
        assert stem_token("") == ""


def stem_function_invariant_short(t: str) -> bool:
    """Helper — short tokens (≤ 4 chars) must never stem."""
    return stem_token(t) == t
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```
.venv/Scripts/python.exe -m pytest tests/test_evals_text_normalise.py::TestStemmer -v
```

Expected: `ImportError: cannot import name 'stem_token'`.

- [ ] **Step 3: Add the stemmer**

Append to `evals/bench/text_normalise.py`:

```python
# Targeted suffix-strip — only the 4 frequent suffixes that create
# false morphological misses on regulatory text. Order matters: longest
# first so "analyses" strips "es" not "s".
_STEM_SUFFIXES: tuple[str, ...] = ("ing", "es", "ed", "s")


def stem_token(token: str) -> str:
    """Strip one of 4 frequent suffixes IFF the resulting stem is ≥ 3 chars.

    Conservative — does not handle "y" → "i" or "-ies" → "-y" (would
    over-fire on tokens like "facilities" → "facilit", "facility"
    leaving a false split). For the davidath token space, the 4
    suffixes above cover the dominant morphological variation.

    Pure, idempotent. Returns the input unchanged for empty / digit-only
    / too-short tokens.
    """
    if not token or not token[0].isalpha():
        return token
    for suf in _STEM_SUFFIXES:
        if len(token) > len(suf) + 3 and token.endswith(suf):
            return token[: -len(suf)]
    return token


__all__ = ["normalise_for_scoring", "stem_token"]
```

- [ ] **Step 4: Run tests to verify pass**

Run:
```
.venv/Scripts/python.exe -m pytest tests/test_evals_text_normalise.py -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add evals/bench/text_normalise.py tests/test_evals_text_normalise.py
git commit -m "feat(R82-A): add Porter-light stemmer (ing/es/ed/s, length-gated)"
```

---

## Task 3: Corrected tokenizer in metrics.py — with legacy preserved

**Files:**
- Modify: `evals/bench/metrics.py` (the `_STOPWORDS`, `_TOKEN_RE`, `_tokens` block at lines 36-57)
- Test: `tests/test_metrics_unbiased.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_metrics_unbiased.py
"""R82-A — corrected-tokenizer alignment + bias-removal regression."""
from __future__ import annotations

from evals.bench.metrics import (
    _tokens,
    _tokens_legacy,
    answer_correctness_loose,
    answer_correctness_strict,
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```
.venv/Scripts/python.exe -m pytest tests/test_metrics_unbiased.py -v
```

Expected: ImportError on `_tokens_legacy`, plus failures on the alignment tests.

- [ ] **Step 3: Modify `evals/bench/metrics.py` — corrected tokenizer + legacy preserved**

Replace the `_STOPWORDS`, `_TOKEN_RE`, `_tokens` block (lines 36-57) with:

```python
from evals.bench.text_normalise import normalise_for_scoring, stem_token

# Pre-R82 stopword set — kept for `_tokens_legacy` only.
_STOPWORDS_LEGACY = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "if", "of", "to", "in",
        "on", "for", "with", "as", "by", "is", "are", "was", "were", "be",
        "been", "being", "this", "that", "these", "those", "it", "its",
        "must", "shall", "should", "would", "can", "may", "from", "at",
        "any", "all", "such", "which", "who", "what", "when", "where",
        "their", "they", "them", "his", "her", "he", "she", "you", "we",
        "i", "us", "our", "your", "my", "do", "does", "did", "have", "has",
        "had", "not", "no", "yes",
    }
)

# R82-A: drop regulatory modal verbs from stopwords. The whole
# regulation is "must / shall / should" — discarding them under-counts
# rubric-relevant tokens.
_STOPWORDS_V2 = _STOPWORDS_LEGACY - {
    "must", "shall", "should", "would", "may", "can",
}

# Pre-R82 token regex — must start with letter, accepts ASCII '-'.
_TOKEN_RE_LEGACY = re.compile(r"[A-Za-z][A-Za-z0-9'\-]+")

# R82-A: accept digit-led tokens so `15` / `10` / `2024` survive when
# they carry meaning (penalty amounts, FLOPs scales, year markers).
_TOKEN_RE_V2 = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-]+")


def _tokens_legacy(text: str) -> set[str]:
    """Pre-R82 tokenizer — reproduces shipped behaviour byte-identically.

    Preserved so `*_legacy` axes in the rescored history remain
    reproducible across the R23-R81 round trajectory. Do NOT modify.
    """
    if not text:
        return set()
    raw = _TOKEN_RE_LEGACY.findall(text.lower())
    return {t for t in raw if len(t) >= 3 and t not in _STOPWORDS_LEGACY}


def _tokens(text: str) -> set[str]:
    """R82-A corrected tokenizer.

    Pipeline:
      1. `normalise_for_scoring` (NFKC + dash fold + Art. → Article +
         diacritic strip + lowercase).
      2. Token regex `[A-Za-z0-9][A-Za-z0-9'\\-]+` (digit-led OK).
      3. Filter: len ≥ 2 AND not in `_STOPWORDS_V2`.
      4. Stem each survivor.

    Returns a set (deduped). See `evals/bench/text_normalise.py` for the
    per-rule rationale grounded in measured davidath biases.
    """
    if not text:
        return set()
    norm = normalise_for_scoring(text)
    raw = _TOKEN_RE_V2.findall(norm)
    return {stem_token(t) for t in raw if len(t) >= 2 and t not in _STOPWORDS_V2}
```

(Keep the rest of the file as-is for now — the `_legacy` correctness functions are Task 4.)

- [ ] **Step 4: Run tests to verify pass**

Run:
```
.venv/Scripts/python.exe -m pytest tests/test_metrics_unbiased.py -v
```

Expected: all green.

- [ ] **Step 5: Verify the existing metrics suite still passes**

Run:
```
.venv/Scripts/python.exe -m pytest tests/test_bench_metrics.py -v
```

Expected: any tests that depended on the SHIPPED behaviour will now fail. **Do NOT "fix" these by changing the test expectations**. Instead: every test that was pinning a specific number against the pre-R82 tokenizer must be split into a `_legacy` variant (pinning `_tokens_legacy` + the legacy correctness functions, untouched) AND a `_v2` variant (the new expected value). If a test was checking ROUND NUMBERS like "0.34 for this pair", regenerate the expected value against the new tokenizer and document the change in the test.

Catalogue every failing test; fix them in this same task by either:
1. Renaming to `..._legacy` and pinning `_tokens_legacy` instead.
2. Updating the expected value to the new tokenizer output, with a comment line `# R82-A — value regenerated against corrected tokenizer`.

- [ ] **Step 6: Commit**

```bash
git add evals/bench/metrics.py tests/test_metrics_unbiased.py tests/test_bench_metrics.py
git commit -m "feat(R82-A): corrected tokenizer with NBH+Art+2-char+modals+stem (legacy preserved)"
```

---

## Task 4: Add `*_legacy` correctness functions

**Files:**
- Modify: `evals/bench/metrics.py`
- Test: `tests/test_metrics_legacy_preservation.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_metrics_legacy_preservation.py
"""R82-A — legacy correctness axes must byte-reproduce pre-R82 behaviour."""
from __future__ import annotations

from evals.bench.metrics import (
    answer_correctness_loose_legacy,
    answer_correctness_strict_legacy,
)


class TestLegacyLooseReproducesPreR82:
    def test_nbh_misses_in_legacy(self) -> None:
        # Pre-R82: NBH → 'high','risk'; ASCII pred → 'high-risk'. They miss.
        gold = "high‑risk system"
        pred = "high-risk system"
        # gold tokens (legacy): {'high', 'risk', 'system'}
        # pred tokens (legacy): {'high-risk', 'system'}
        # intersection: {'system'}; union: {'high', 'risk', 'system', 'high-risk'}
        # Jaccard = 1/4 = 0.25
        assert answer_correctness_loose_legacy(pred, gold) == 0.25

    def test_ai_dropped_in_legacy_strict(self) -> None:
        # Pre-R82: 'AI' is < 3 chars → dropped.
        gold = "AI system"   # legacy tokens: {'system'} only
        pred = "ai system"   # legacy tokens: {'system'} only
        # Strict = recall = |intersection|/|gold| = 1/1 = 1.0
        assert answer_correctness_strict_legacy(pred, gold) == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```
.venv/Scripts/python.exe -m pytest tests/test_metrics_legacy_preservation.py -v
```

Expected: ImportError on the `*_legacy` symbols.

- [ ] **Step 3: Add the legacy correctness functions to `metrics.py`**

Insert after the existing `answer_correctness_loose` / `answer_correctness_strict` definitions (around line 124):

```python
def answer_correctness_loose_legacy(pred: str, gold: str) -> float:
    """Pre-R82 token-Jaccard. Preserved for back-compat / history rescore."""
    pt = _tokens_legacy(pred)
    gt = _tokens_legacy(gold)
    if not gt or not pt:
        return 0.0
    overlap = len(pt & gt)
    union = len(pt | gt)
    return overlap / union if union else 0.0


def answer_correctness_strict_legacy(pred: str, gold: str) -> float:
    """Pre-R82 gold-recall. Preserved for back-compat / history rescore."""
    pt = _tokens_legacy(pred)
    gt = _tokens_legacy(gold)
    if not gt:
        return 0.0
    return len(pt & gt) / len(gt)
```

- [ ] **Step 4: Run tests to verify pass**

Run:
```
.venv/Scripts/python.exe -m pytest tests/test_metrics_legacy_preservation.py -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add evals/bench/metrics.py tests/test_metrics_legacy_preservation.py
git commit -m "feat(R82-A): preserve answer_correctness_*_legacy for byte-identical historical reproduction"
```

---

## Task 5: Add `answer_keyword_recall` against curated keyword list

**Files:**
- Modify: `evals/bench/metrics.py`
- Test: `tests/test_metrics_unbiased.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_metrics_unbiased.py`:

```python
from evals.bench.metrics import answer_keyword_recall


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```
.venv/Scripts/python.exe -m pytest tests/test_metrics_unbiased.py::TestAnswerKeywordRecall -v
```

Expected: `ImportError: cannot import name 'answer_keyword_recall'`.

- [ ] **Step 3: Implement**

Add to `evals/bench/metrics.py` after the legacy correctness functions:

```python
def answer_keyword_recall(
    pred: str, expected_keywords: list[str] | None
) -> float | None:
    """Fraction of curated keywords (normalised + stemmed) present in pred.

    Designed for sidecars that carry an `expected_keywords` field (V2 /
    representative-100). Mirrors what an LLM judge looks for: "are the
    load-bearing domain tokens for this question surfaced in the
    answer?". Robust to pred verbosity (recall, not Jaccard) and uses a
    curated subset rather than the full gold answer's incidental
    tokens.

    Returns `None` when `expected_keywords` is None or empty — caller
    convention: the axis is not applicable for this row, skip from
    aggregation. Returns 0.0 when pred is empty.
    """
    if not expected_keywords:
        return None
    pred_tokens = _tokens(pred)
    if not pred_tokens:
        return 0.0
    # Each keyword goes through the same normalise + tokenise pipeline
    # the predicate side did — collect all keyword stems.
    keyword_stems: set[str] = set()
    for kw in expected_keywords:
        keyword_stems |= _tokens(kw)
    if not keyword_stems:
        return None
    return len(pred_tokens & keyword_stems) / len(keyword_stems)
```

- [ ] **Step 4: Run tests to verify pass**

Run:
```
.venv/Scripts/python.exe -m pytest tests/test_metrics_unbiased.py::TestAnswerKeywordRecall -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add evals/bench/metrics.py tests/test_metrics_unbiased.py
git commit -m "feat(R82-A): add answer_keyword_recall against curated keyword lists"
```

---

## Task 6: Extend `RowScore` + `score_row` + `aggregate`

**Files:**
- Modify: `evals/bench/metrics.py` (`RowScore` dataclass + `score_row` + `aggregate`)
- Test: `tests/test_metrics_unbiased.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_metrics_unbiased.py`:

```python
from evals.bench.metrics import RowScore, aggregate, score_row


class TestScoreRowEmitsBothAxes:
    def test_score_row_carries_legacy_fields(self) -> None:
        s = score_row(
            pred_answer="high-risk providers must document",
            pred_refs=["Article 9"],
            gold_answer="high‑risk providers must document",
            gold_articles=9,
            latency_ms=42.0,
        )
        d = s.to_dict()
        # New corrected axes present
        assert "ans_correctness_loose" in d
        assert "ans_correctness_strict" in d
        # Legacy axes present
        assert "ans_correctness_loose_legacy" in d
        assert "ans_correctness_strict_legacy" in d
        # Loose-v2 > Loose-legacy on this NBH-vs-ASCII pair
        assert d["ans_correctness_loose"] > d["ans_correctness_loose_legacy"]

    def test_score_row_accepts_expected_keywords(self) -> None:
        s = score_row(
            pred_answer="providers must document risk",
            pred_refs=["Article 9"],
            gold_answer="anything",
            gold_articles=9,
            latency_ms=10.0,
            expected_keywords=["document", "risk", "providers"],
        )
        d = s.to_dict()
        assert d["ans_keyword_recall"] == 1.0

    def test_score_row_without_keywords_emits_none(self) -> None:
        s = score_row(
            pred_answer="anything",
            pred_refs=["Article 9"],
            gold_answer="anything",
            gold_articles=9,
            latency_ms=10.0,
        )
        d = s.to_dict()
        assert d["ans_keyword_recall"] is None


class TestAggregateSkipsNoneKeywordRecall:
    def test_aggregate_excludes_none(self) -> None:
        rows = [
            score_row("hello", ["Article 1"], "hello", 1, 1.0,
                      expected_keywords=["hello"]),
            score_row("hello", ["Article 1"], "hello", 1, 1.0,
                      expected_keywords=None),
        ]
        agg = aggregate(rows)
        # 1 row had None → averaged over 1, not 2
        assert "ans_keyword_recall" in agg
        assert agg["ans_keyword_recall"] == 1.0
        # n_keyword_recall surfaces the denominator
        assert agg["n_keyword_recall"] == 1

    def test_aggregate_emits_legacy_axes(self) -> None:
        rows = [
            score_row("hello", ["Article 1"], "hello", 1, 1.0)
        ]
        agg = aggregate(rows)
        assert "ans_correctness_loose" in agg
        assert "ans_correctness_loose_legacy" in agg
        assert "ans_correctness_strict_legacy" in agg
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```
.venv/Scripts/python.exe -m pytest tests/test_metrics_unbiased.py::TestScoreRowEmitsBothAxes tests/test_metrics_unbiased.py::TestAggregateSkipsNoneKeywordRecall -v
```

Expected: failures on missing fields / TypeError on `expected_keywords` kwarg.

- [ ] **Step 3: Update `RowScore`, `score_row`, `aggregate` in `evals/bench/metrics.py`**

Replace the `RowScore` dataclass + `score_row` + `aggregate` block (lines 302-396) with:

```python
@dataclass
class RowScore:
    """Eight-axis score for a single QA / scenario row.

    R82-A: extended with legacy variants (`*_legacy`) for back-compat
    and `answer_keyword_recall` for curated-keyword scoring on sidecars
    that carry an `expected_keywords` field.
    """

    answer_correctness_loose: float
    answer_correctness_strict: float
    answer_conciseness: float
    reference_correctness_loose: float
    reference_correctness_strict: float
    reference_conciseness: float
    latency_ms: float
    regulatory_tone: float
    # R82-A additions
    answer_correctness_loose_legacy: float
    answer_correctness_strict_legacy: float
    answer_keyword_recall: float | None  # None = N/A (no curated keywords)

    def to_dict(self) -> dict[str, float | None]:
        out: dict[str, float | None] = {
            "ans_correctness_loose": round(self.answer_correctness_loose, 4),
            "ans_correctness_strict": round(self.answer_correctness_strict, 4),
            "ans_conciseness": round(self.answer_conciseness, 4),
            "ref_correctness_loose": round(self.reference_correctness_loose, 4),
            "ref_correctness_strict": round(self.reference_correctness_strict, 4),
            "ref_conciseness": round(self.reference_conciseness, 4),
            "latency_ms": round(self.latency_ms, 2),
            "regulatory_tone": round(self.regulatory_tone, 4),
            "ans_correctness_loose_legacy": round(
                self.answer_correctness_loose_legacy, 4
            ),
            "ans_correctness_strict_legacy": round(
                self.answer_correctness_strict_legacy, 4
            ),
        }
        if self.answer_keyword_recall is None:
            out["ans_keyword_recall"] = None
        else:
            out["ans_keyword_recall"] = round(self.answer_keyword_recall, 4)
        return out


def score_row(
    pred_answer: str,
    pred_refs: list[str],
    gold_answer: str,
    gold_articles: int | list[int] | None,
    latency_ms: float,
    expected_keywords: list[str] | None = None,
) -> RowScore:
    """Compute every metric for one row in one call.

    R82-A: `expected_keywords` is optional. Sidecars from the
    representative-100 / V2 runners carry it; the in-process davidath
    bench runner does not (gold answers come from the corpus only).
    """
    return RowScore(
        answer_correctness_loose=answer_correctness_loose(pred_answer, gold_answer),
        answer_correctness_strict=answer_correctness_strict(pred_answer, gold_answer),
        answer_conciseness=answer_conciseness(pred_answer, gold_answer),
        reference_correctness_loose=reference_correctness_loose(
            pred_refs, gold_articles
        ),
        reference_correctness_strict=reference_correctness_strict(
            pred_refs, gold_articles
        ),
        reference_conciseness=reference_conciseness(pred_refs, gold_articles),
        latency_ms=latency_ms,
        regulatory_tone=regulatory_tone(pred_answer),
        answer_correctness_loose_legacy=answer_correctness_loose_legacy(
            pred_answer, gold_answer
        ),
        answer_correctness_strict_legacy=answer_correctness_strict_legacy(
            pred_answer, gold_answer
        ),
        answer_keyword_recall=answer_keyword_recall(pred_answer, expected_keywords),
    )


def aggregate(rows: list[RowScore]) -> dict[str, float | int]:
    """Mean per axis + latency percentiles.

    R82-A: `answer_keyword_recall` averages over rows where it is not
    None (denominator surfaced as `n_keyword_recall`); other axes
    average over the full set of rows.
    """
    if not rows:
        return {}
    n = len(rows)
    latencies = [r.latency_ms for r in rows]
    # Axes that always apply: simple mean
    def mn(attr: str) -> float:
        return sum(getattr(r, attr) for r in rows) / n

    # Keyword recall: skip None
    kw_values = [
        r.answer_keyword_recall for r in rows if r.answer_keyword_recall is not None
    ]
    agg: dict[str, float | int] = {
        "n": n,
        "ans_correctness_loose": round(mn("answer_correctness_loose"), 4),
        "ans_correctness_strict": round(mn("answer_correctness_strict"), 4),
        "ans_conciseness": round(mn("answer_conciseness"), 4),
        "ref_correctness_loose": round(mn("reference_correctness_loose"), 4),
        "ref_correctness_strict": round(mn("reference_correctness_strict"), 4),
        "ref_conciseness": round(mn("reference_conciseness"), 4),
        "regulatory_tone": round(mn("regulatory_tone"), 4),
        "latency_p50_ms": round(percentile(latencies, 50), 2),
        "latency_p95_ms": round(percentile(latencies, 95), 2),
        "latency_max_ms": round(max(latencies) if latencies else 0.0, 2),
        "latency_mean_ms": round(sum(latencies) / n, 2),
        "ans_correctness_loose_legacy": round(
            mn("answer_correctness_loose_legacy"), 4
        ),
        "ans_correctness_strict_legacy": round(
            mn("answer_correctness_strict_legacy"), 4
        ),
        "n_keyword_recall": len(kw_values),
    }
    if kw_values:
        agg["ans_keyword_recall"] = round(sum(kw_values) / len(kw_values), 4)
    else:
        agg["ans_keyword_recall"] = None  # type: ignore[assignment]
    return agg
```

- [ ] **Step 4: Run tests to verify pass**

Run:
```
.venv/Scripts/python.exe -m pytest tests/test_metrics_unbiased.py -v tests/test_metrics_legacy_preservation.py -v
```

Expected: all green.

- [ ] **Step 5: Smoke-test that the existing bench runner still works**

Run:
```
.venv/Scripts/python.exe -m evals.bench.runner --label r82a-smoke --limit 10
```

Expected: completes without errors; sidecar at `evals/bench/results/r82a-smoke.json` carries new fields including `ans_correctness_loose_legacy`. Compare any pre-R82 sidecar's legacy field to its current shipped value — should be byte-identical.

- [ ] **Step 6: Commit**

```bash
git add evals/bench/metrics.py tests/test_metrics_unbiased.py
git commit -m "feat(R82-A): extend RowScore + score_row + aggregate with legacy + keyword-recall axes"
```

---

## Task 7: Wire `expected_keywords` through the runners

**Files:**
- Modify: `evals/bench/representative_100.py` (the call to `score_row`)
- Modify: `evals/bench/unbiased_runner.py` (if it calls `score_row` — verify)
- Modify: `evals/bench/runner.py` (no-op — davidath has no keywords; explicit `expected_keywords=None`)

- [ ] **Step 1: Locate every `score_row` call site**

Run:
```
.venv/Scripts/python.exe -c "
import subprocess
r = subprocess.run(['grep','-rn','score_row','evals/','--include=*.py'], capture_output=True, text=True)
print(r.stdout)
"
```

Expected: lists every call site. Catalogue each — the rep-100 runner is the load-bearing one (its rows carry `expected_keywords`).

- [ ] **Step 2: Update `representative_100.py`**

Find the `score_row(...)` call (likely in a per-row scoring loop). Pass the row's `expected_keywords` field through:

```python
# Before:
score = metrics.score_row(
    pred_answer=pred_answer,
    pred_refs=pred_refs,
    gold_answer=row["gold_answer"],
    gold_articles=row["gold_articles"],
    latency_ms=latency_ms,
)

# After:
score = metrics.score_row(
    pred_answer=pred_answer,
    pred_refs=pred_refs,
    gold_answer=row["gold_answer"],
    gold_articles=row["gold_articles"],
    latency_ms=latency_ms,
    expected_keywords=row.get("expected_keywords"),
)
```

- [ ] **Step 3: Update `unbiased_runner.py` similarly if applicable**

If the unbiased runner constructs rows from any source that includes `expected_keywords`, pass it through. If not (it works against davidath / AIReg-Bench / Regenold probe, which don't have curated keywords), leave the call as-is — `expected_keywords` defaults to None.

- [ ] **Step 4: Re-run the rep-100 smoke**

Run:
```
.venv/Scripts/python.exe -m evals.bench.representative_100 --label r82a-rep-smoke --limit 5
```

Expected: completes; sidecar's `rows[i]["ans_keyword_recall"]` is a float (not None) for rows whose `expected_keywords` was populated.

- [ ] **Step 5: Commit**

```bash
git add evals/bench/representative_100.py evals/bench/unbiased_runner.py
git commit -m "feat(R82-A): wire expected_keywords through scoring call sites"
```

---

## Task 8: Build the historical sidecar rescorer

**Files:**
- Create: `scripts/rescore_sidecars.py`
- Test: `tests/test_rescore_sidecars.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rescore_sidecars.py
"""R82-A — rescore historical sidecars in place (write siblings)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.rescore_sidecars import (
    iter_sidecars,
    rescore_row,
    rescore_sidecar,
)


@pytest.fixture
def fake_sidecar(tmp_path: Path) -> Path:
    """A minimal sidecar with one QA row and one rep-100-style row."""
    p = tmp_path / "results" / "fake.json"
    p.parent.mkdir(parents=True)
    payload = {
        "label": "fake",
        "rows": [
            {
                "id": "fake_qa_1",
                "kind": "qa",
                "gold_answer": "high‑risk providers must document",
                "gold_articles": [9],
                "predicted_answer": "high-risk providers must document",
                "pred_refs": ["Article 9"],
                "latency_ms": 100.0,
                # No expected_keywords field — davidath-style row.
            },
            {
                "id": "fake_rep_1",
                "kind": "multiturn",
                "gold_answer": "providers must conduct risk assessment",
                "gold_articles": [9, 27],
                "predicted_answer": "the provider must perform a risk assessment",
                "pred_refs": ["Article 9", "Article 27"],
                "expected_keywords": ["risk", "assessment"],
                "latency_ms": 200.0,
            },
        ],
    }
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_iter_sidecars_finds_label_rows(fake_sidecar: Path) -> None:
    found = list(iter_sidecars(fake_sidecar.parent))
    assert len(found) == 1
    assert found[0].name == "fake.json"


def test_rescore_row_qa_row_emits_legacy_and_corrected(fake_sidecar: Path) -> None:
    payload = json.loads(fake_sidecar.read_text(encoding="utf-8"))
    row = payload["rows"][0]
    out = rescore_row(row)
    # New axes
    assert "ans_correctness_loose" in out
    assert "ans_correctness_strict" in out
    # Legacy axes
    assert "ans_correctness_loose_legacy" in out
    assert "ans_correctness_strict_legacy" in out
    # NBH-vs-ASCII pair: corrected Loose strictly higher than legacy
    assert out["ans_correctness_loose"] > out["ans_correctness_loose_legacy"]
    # No keyword recall for davidath-style row
    assert out["ans_keyword_recall"] is None


def test_rescore_row_rep100_emits_keyword_recall(fake_sidecar: Path) -> None:
    payload = json.loads(fake_sidecar.read_text(encoding="utf-8"))
    row = payload["rows"][1]
    out = rescore_row(row)
    # Curated keyword list present → recall computed
    assert isinstance(out["ans_keyword_recall"], float)
    assert out["ans_keyword_recall"] > 0


def test_rescore_sidecar_writes_sibling_file(fake_sidecar: Path) -> None:
    sibling = rescore_sidecar(fake_sidecar)
    assert sibling.name == "fake.rescored.json"
    assert sibling.exists()
    # Original untouched
    payload = json.loads(fake_sidecar.read_text(encoding="utf-8"))
    assert "rescored_aggregate" not in payload


def test_rescore_sidecar_aggregate_present(fake_sidecar: Path) -> None:
    sibling = rescore_sidecar(fake_sidecar)
    rescored = json.loads(sibling.read_text(encoding="utf-8"))
    assert "rescored_aggregate" in rescored
    assert "ans_correctness_loose" in rescored["rescored_aggregate"]
    assert "ans_correctness_loose_legacy" in rescored["rescored_aggregate"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```
.venv/Scripts/python.exe -m pytest tests/test_rescore_sidecars.py -v
```

Expected: ImportError on `scripts.rescore_sidecars`.

- [ ] **Step 3: Implement**

```python
# scripts/rescore_sidecars.py
"""R82-A — rescore historical sidecars with the corrected tokenizer.

Walks `evals/bench/results/*.json`, recomputes the answer-correctness
axes from each row's `gold_answer` + `predicted_answer` (+
`expected_keywords` when present), and writes a sibling
`<label>.rescored.json` carrying:

  * `rescored_at`: ISO timestamp
  * `metrics_version`: 'r82-a'
  * `rows`: every original row plus `rescored_axes` field
  * `rescored_aggregate`: aggregate dict from `metrics.aggregate`

The ORIGINAL sidecar is never mutated. Re-runs are idempotent — if
`<label>.rescored.json` already exists with the same row count + same
metrics_version, the rescore is skipped (use `--force` to override).

Usage:
    .venv/Scripts/python.exe -m scripts.rescore_sidecars
    .venv/Scripts/python.exe -m scripts.rescore_sidecars --force
    .venv/Scripts/python.exe -m scripts.rescore_sidecars --pattern 'representative-100-*.json'
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from evals.bench import metrics

_METRICS_VERSION = "r82-a"
_RESULTS_DIR = Path(__file__).parent.parent / "evals" / "bench" / "results"


def iter_sidecars(directory: Path, pattern: str = "*.json") -> Iterable[Path]:
    """Yield every sidecar (not already-rescored)."""
    for p in sorted(directory.glob(pattern)):
        if p.name.endswith(".rescored.json"):
            continue
        yield p


def _read_payload(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def rescore_row(row: dict[str, Any]) -> dict[str, float | None]:
    """Recompute every R82-A axis for a single row.

    Robust to missing fields — returns 0.0 for any axis whose inputs
    are absent (so a malformed sidecar doesn't crash the walker).
    """
    pred_answer = row.get("predicted_answer") or row.get("answer") or ""
    pred_refs = row.get("pred_refs") or row.get("references") or []
    gold_answer = row.get("gold_answer") or row.get("answer_gold") or ""
    gold_articles = row.get("gold_articles") or row.get("relevant_article")
    latency_ms = float(row.get("latency_ms") or 0.0)
    expected_keywords = row.get("expected_keywords")  # may be None

    score = metrics.score_row(
        pred_answer=pred_answer,
        pred_refs=list(pred_refs),
        gold_answer=gold_answer,
        gold_articles=gold_articles,
        latency_ms=latency_ms,
        expected_keywords=expected_keywords,
    )
    return score.to_dict()


def rescore_sidecar(path: Path, *, force: bool = False) -> Path:
    """Rescore one sidecar; write its sibling `.rescored.json`.

    Idempotent: returns the sibling path without rewriting if it
    already exists and carries the same metrics_version + row count.
    """
    payload = _read_payload(path)
    if payload is None:
        raise RuntimeError(f"Could not load sidecar {path}")
    rows = payload.get("rows") or []
    sibling = path.with_suffix(".rescored.json")
    if sibling.exists() and not force:
        existing = _read_payload(sibling)
        if (
            existing is not None
            and existing.get("metrics_version") == _METRICS_VERSION
            and len(existing.get("rows") or []) == len(rows)
        ):
            return sibling
    # Build the rescored payload — copy the row, attach `rescored_axes`
    new_rows: list[dict[str, Any]] = []
    row_scores: list[metrics.RowScore] = []
    for row in rows:
        axes = rescore_row(row)
        new_row = dict(row)
        new_row["rescored_axes"] = axes
        new_rows.append(new_row)
        # Build a RowScore for aggregation
        row_scores.append(
            metrics.score_row(
                pred_answer=row.get("predicted_answer") or row.get("answer") or "",
                pred_refs=list(row.get("pred_refs") or row.get("references") or []),
                gold_answer=row.get("gold_answer") or row.get("answer_gold") or "",
                gold_articles=row.get("gold_articles") or row.get("relevant_article"),
                latency_ms=float(row.get("latency_ms") or 0.0),
                expected_keywords=row.get("expected_keywords"),
            )
        )
    new_payload = dict(payload)
    new_payload["rows"] = new_rows
    new_payload["rescored_at"] = (
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    new_payload["metrics_version"] = _METRICS_VERSION
    new_payload["rescored_aggregate"] = metrics.aggregate(row_scores)
    sibling.write_text(
        json.dumps(new_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return sibling


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rescore_sidecars")
    parser.add_argument("--pattern", default="*.json")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--results-dir", type=Path, default=_RESULTS_DIR)
    args = parser.parse_args(argv)

    n = 0
    for path in iter_sidecars(args.results_dir, args.pattern):
        try:
            sibling = rescore_sidecar(path, force=args.force)
            n += 1
            print(f"rescored {path.name} -> {sibling.name}")
        except Exception as exc:  # noqa: BLE001
            print(f"SKIP {path.name}: {exc}", file=sys.stderr)
    print(f"\n{n} sidecars rescored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify pass**

Run:
```
.venv/Scripts/python.exe -m pytest tests/test_rescore_sidecars.py -v
```

Expected: all green.

- [ ] **Step 5: Smoke-rescore a known historical sidecar**

Run:
```
.venv/Scripts/python.exe -m scripts.rescore_sidecars --pattern 'representative-100-r81-h-live.json'
```

Expected output: `rescored representative-100-r81-h-live.json -> representative-100-r81-h-live.rescored.json` plus a count of 1. Open the rescored file and verify `rescored_aggregate.ans_correctness_loose` > `rescored_aggregate.ans_correctness_loose_legacy`.

- [ ] **Step 6: Commit**

```bash
git add scripts/rescore_sidecars.py tests/test_rescore_sidecars.py
git commit -m "feat(R82-A): scripts/rescore_sidecars.py for historical re-baseline"
```

---

## Task 9: Rescore every historical sidecar + publish the delta table

**Files:**
- Create: `docs/r82-rescored-history.md`

- [ ] **Step 1: Rescore every sidecar**

Run:
```
.venv/Scripts/python.exe -m scripts.rescore_sidecars
```

Expected: every `representative-100-*.json` + `r66-*.json` + `r67-*.json` + `r68-*.json` + `r69-*.json` + `r70-*.json` + `r71-*.json` + `r72-*.json` + `r76-*.json` + `r80-*.json` + `r81-*.json` produces a sibling `*.rescored.json`. A few sidecars from older rounds may fail with `SKIP <name>: ...` because they don't have the expected `rows` schema — that's fine, log them.

- [ ] **Step 2: Generate the delta table**

```python
# scripts/build_rescored_history.py (one-off helper — do NOT commit this; it just emits stdout)
import json
from pathlib import Path

results = Path("evals/bench/results")
rows = []
for p in sorted(results.glob("*.rescored.json")):
    payload = json.loads(p.read_text(encoding="utf-8"))
    agg = payload.get("rescored_aggregate", {})
    rows.append((
        p.name.replace(".rescored.json", ""),
        agg.get("n"),
        agg.get("ans_correctness_loose_legacy"),
        agg.get("ans_correctness_loose"),
        agg.get("ans_correctness_strict_legacy"),
        agg.get("ans_correctness_strict"),
        agg.get("ans_keyword_recall"),
    ))

print("| Label | n | Loose (legacy) | Loose (R82-A) | Strict (legacy) | Strict (R82-A) | Keyword recall |")
print("| ----- | - | -------------- | ------------- | --------------- | -------------- | -------------- |")
for r in rows:
    print(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} |")
```

Run it:
```
.venv/Scripts/python.exe scripts/build_rescored_history.py > /tmp/r82_table.md
```

- [ ] **Step 3: Write the publication doc**

Create `docs/r82-rescored-history.md`:

```markdown
# R82-A — Re-baselined Ans Correctness history

The R82-A round audited the `evals/bench/metrics.py` tokenizer for
bias against our own preds and found four load-bearing defects (see
[`docs/superpowers/specs/2026-05-24-r82-unbiased-evals-answer-quality-design.md`](superpowers/specs/2026-05-24-r82-unbiased-evals-answer-quality-design.md)
for the full audit). The corrected tokenizer is SQuAD-F1 / ROUGE-L
precedent: Unicode normalisation + dash + `Art.`/`Article` alignment +
2-char alphanumeric tokens + Porter-light stemmer + modal verbs out of
stopwords.

Every historical sidecar from R66 onward has been rescored with the
new tokenizer. The legacy-formula axes are preserved alongside so the
pre-R82 trajectory remains reproducible. Files: `evals/bench/results/
*.rescored.json` (originals untouched).

## Per-round delta

[INSERT the table emitted by build_rescored_history.py]

## Reading the table

- `Loose (legacy)` / `Strict (legacy)` are byte-identical to what the
  pre-R82 harness reported — useful for verifying the rescore was
  faithful.
- `Loose (R82-A)` / `Strict (R82-A)` are the corrected numbers — what
  a fair external judge using the same normalisation would compute.
- `Keyword recall` is `None` for sidecars without an `expected_keywords`
  field (in-process davidath bench) and a 0-1 float for V2 / rep-100
  sidecars.

## Headline shifts

- R81-H-live Ans Strict: 0.2681 (legacy) → **~0.292** (R82-A
  corrected) — **+0.024 absolute** from harness-bias removal alone,
  no engine change.
- R81-H-live Ans Loose: 0.1258 (legacy) → **~0.133** (R82-A
  corrected) — **+0.007 absolute**.

## How to reproduce

```bash
.venv/Scripts/python.exe -m scripts.rescore_sidecars --force
```

Idempotent — re-running with no `--force` is a no-op.
```

Insert the table generated in Step 2.

- [ ] **Step 4: Update CLAUDE.md scorecard with the R82-A row**

Add to the eval scorecard table in `CLAUDE.md`:

```markdown
| **82-A** | 476 davidath | — | — | — | RefL **0.5776** / RefS **0.4654** / Ans Strict **<measured>** (legacy <legacy>) / Tone 1.0 / mt 20/20 / OOS 21/21 / +<N> R82-A tests pass | **Harness bias fix.** Audited evals/bench/metrics.py for bias against our own preds, found 4 load-bearing tokenizer defects (NBH U+2011, Art./Article, 2-char AI, modal verbs in stopwords) plus missing stemmer. Replaced `_tokens` with SQuAD-F1 / ROUGE precedent: normalise_for_scoring (NFKC + dashes + Art→Article + diacritic strip + lowercase) + V2 regex (digit-led OK) + 2-char minimum + drop modals from stopwords + Porter-light stemmer. Preserved `_tokens_legacy` + `answer_correctness_*_legacy` alongside so historical sidecars remain reproducible. Added `answer_keyword_recall` against V2 sidecars' curated keyword lists. Re-scored every historical sidecar (`scripts/rescore_sidecars.py`), published delta table at `docs/r82-rescored-history.md`. Davidath bench rerun: corrected Ans Strict +<delta> / Loose +<delta>. No engine changes — R82-B is the engine push. |
```

(Replace `<measured>` / `<legacy>` / `<delta>` / `<N>` with the actual numbers from Task 10's verification run.)

- [ ] **Step 5: Commit**

```bash
git add docs/r82-rescored-history.md CLAUDE.md evals/bench/results/*.rescored.json
git commit -m "docs(R82-A): rescored historical sidecars + R82-A scorecard row"
```

---

## Task 10: Full verification gates

**Files:**
- Run-only (no edits)

- [ ] **Step 1: Full pytest**

Run:
```
.venv/Scripts/python.exe -m pytest -q
```

Expected: `≥ 2,458 + 1 skip + <N> R82-A new tests pass`. No regressions in pre-existing tests except any that were intentionally renamed to `_legacy` in Task 3.

- [ ] **Step 2: Davidath bench full run**

Run:
```
.venv/Scripts/python.exe -m evals.bench.runner --label r82a-davidath
```

Expected: completes; the sidecar's aggregate carries both new + legacy axes. Compare:
- `ans_correctness_loose_legacy` against the most recent pre-R82 davidath run — should be IDENTICAL.
- `ref_correctness_*` / `ans_conciseness` / `regulatory_tone` / multi-turn coherence — IDENTICAL to pre-R82.
- `ans_correctness_loose` / `ans_correctness_strict` — measurable but small lift (the harness fix lands ~+0.01 Loose / ~+0.02 Strict on davidath).

- [ ] **Step 3: OOS probe**

Run:
```
.venv/Scripts/python.exe -m evals.regenold.runner_v2 --local --probe-oos
```

Expected: 21/21 PASS — the harness fix never touches the route, so this is purely a sanity gate.

- [ ] **Step 4: Rep-100 + judge runs (only if Anthropic credits available)**

This re-run is OPTIONAL for R82-A merge but RECOMMENDED so the round entry's "R82-A live" numbers are real:

```
.venv/Scripts/python.exe -m evals.bench.representative_100 --label r82a-live \
    --endpoint https://regenold-eu-ai-act-rag-production.up.railway.app/api/v1/regenold/eu-ai-act/ask \
    --api-key $REGENOLD_API_KEY
.venv/Scripts/python.exe -m evals.judge.runner --bench-sidecar evals/bench/results/representative-100-r82a-live.json --label r82a-live
```

Expected: a fresh sidecar where the aggregate carries both the new + legacy axes. The published R81-H baseline (Ans Loose 0.1258 / Strict 0.2681) should be reproduced exactly by the `*_legacy` columns; the new columns should show the bias-corrected lift.

- [ ] **Step 5: Fill in `<measured>` placeholders in CLAUDE.md**

Update the R82-A row in `CLAUDE.md` with the actual numbers from Steps 2 + 4.

- [ ] **Step 6: Final commit**

```bash
git add CLAUDE.md
git commit -m "docs(R82-A): fill in measured Ans Loose/Strict deltas for R82-A round"
```

---

## Task 11: Open the PR

- [ ] **Step 1: Push the branch**

```bash
git push -u origin <branch-name>
```

- [ ] **Step 2: Open the PR**

```bash
gh pr create --title "feat(R82-A): unbias evals harness + rescore history" --body "$(cat <<'EOF'
## Summary

- Replaced biased Loose/Strict tokenizer in `evals/bench/metrics.py` with SQuAD-F1 / ROUGE precedent: NFKC + Unicode-dash fold + `Art.`→`Article` + diacritic strip + 2-char alphanumeric tokens + modal verbs out of stopwords + Porter-light stemmer.
- Preserved `*_legacy` axes alongside so pre-R82 trajectory is byte-identically reproducible.
- Added `ans_keyword_recall` against V2 sidecars' curated `expected_keywords`.
- Re-scored every historical sidecar; delta table at `docs/r82-rescored-history.md`.
- No engine changes — R82-B (in design spec) is the engine push.

Spec: `docs/superpowers/specs/2026-05-24-r82-unbiased-evals-answer-quality-design.md`
Plan: `docs/superpowers/plans/2026-05-24-r82-a-harness-bias-fix.md`

## Test plan

- [x] `pytest -q` green (≥ 2,458 + 1 skip + R82-A new tests)
- [x] `evals.bench.runner` davidath: legacy axes byte-identical to pre-R82, corrected axes lift measurable
- [x] `evals.regenold.runner_v2 --local --probe-oos`: 21/21 PASS
- [x] Sidecar rescore idempotent, write-sibling, never mutates original

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes

**Spec coverage** — every A1-A7 item is implemented across Tasks 1-10:
- A1 `normalise_for_scoring` → Task 1.
- A2 corrected tokenizer + stopwords → Task 3.
- A2 stemmer → Task 2.
- A3 `answer_keyword_recall` → Task 5.
- A4 legacy axes preserved → Task 4.
- A5 sidecar rescorer → Task 8 + Task 9.
- A6 unit tests → present in every task.
- A7 verification gates → Task 10.

**Type consistency** — `_tokens` / `_tokens_legacy` / `_STOPWORDS_V2` / `_TOKEN_RE_V2` / `RowScore.answer_keyword_recall: float | None` are consistent across all tasks. `score_row(..., expected_keywords: list[str] | None = None)` is the unified call signature; runners that don't have keywords don't pass the kwarg.

**Placeholder check** — no TODO/TBD. Every code block is complete. The `<measured>` / `<delta>` / `<N>` placeholders in Task 9 Step 4 + Task 10 Step 5 are explicitly flagged as "fill in after the verification run" — they are the EXPECTED output, not gaps in the plan.
