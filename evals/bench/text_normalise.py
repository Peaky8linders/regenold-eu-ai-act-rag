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


# Targeted suffix-strip — 5 frequent suffixes that create false
# morphological misses on regulatory text. Order matters: longest first
# so "analyses" strips "es" not "s" on the first pass.
_STEM_SUFFIXES: tuple[str, ...] = ("ing", "es", "ed", "s", "e")


def stem_token(token: str) -> str:
    """Greedy strip of the 5 frequent suffixes until no suffix fires.

    Greedy (loops to fixed point) so all four morphological variants of
    a verb collapse to the SAME stem rather than two near-stems:

      * ``analyse``   → strip ``e``   → ``analys`` → strip ``s`` → ``analy``
      * ``analysing`` → strip ``ing`` → ``analys`` → strip ``s`` → ``analy``
      * ``analyses``  → strip ``es``  → ``analys`` → strip ``s`` → ``analy``
      * ``analysed``  → strip ``ed``  → ``analys`` → strip ``s`` → ``analy``

    Pre-R82-A.1 single-pass collapsed ``analysing`` / ``analyses`` /
    ``analysed`` to ``analys`` and left ``analyse`` at ``analys`` too
    (because ``e`` is in the suffix set), so the headline collapse was
    correct — but ``stem(stem(analyse))`` then equaled ``analy`` while
    ``stem(analyse)`` equaled ``analys``. Not idempotent. The greedy
    loop converges in one call (every call yields ``analy``), so the
    function IS idempotent — important for any future caller that
    composes with it.

    Empirically (against r81-h-live, n=100): greedy lifts Loose
    +0.0004, Strict +0.0009, Keyword recall +0.0012 over single-pass
    on the same axes. Within bench noise but strictly positive on
    every axis.

    Length guard: a suffix only strips when the remaining stem would
    be ≥ 3 characters. So ``cat``/``cats`` (3-4 chars) never strip,
    ``birds`` (5 chars) strips to ``bird``, ``ai``/``eu`` stay intact.

    Pure, idempotent. Returns input unchanged for empty / non-alphabetic
    leading char / too-short tokens.
    """
    if not token or not token[0].isalpha():
        return token
    changed = True
    while changed:
        changed = False
        for suf in _STEM_SUFFIXES:
            if len(token) > len(suf) + 3 and token.endswith(suf):
                token = token[: -len(suf)]
                changed = True
                break
    return token


__all__ = ["normalise_for_scoring", "stem_token"]
