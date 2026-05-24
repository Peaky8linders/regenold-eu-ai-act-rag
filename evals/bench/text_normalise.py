"""Canonical text normaliser for scoring-side evaluation only.

This module is the single source of truth for Unicode + abbreviation
folding used by ``evals/bench/metrics.py``. It maps gold + pred onto
the same token space so the SQuAD-F1 / ROUGE-precedent token-overlap
scorers can compare them fairly.

It is INTENTIONALLY more aggressive than
``app/integrations/regenold/text_normalize.py`` (request-time,
length-preserving, semantics-preserving): this one is scoring-time and
lossy by design — diacritics stripped, case folded, abbreviations
expanded.

DO NOT IMPORT THIS FROM ``app/`` — it is for ``evals/`` only.
Aggressive normalisation must never run on production prose.

Why each rule exists (each is grounded in a measured davidath bias):

  * U+2011 non-breaking hyphen → ASCII '-': 42% of davidath QA gold
    answers carry it; the engine writes ASCII '-' throughout.
  * Smart quotes → ASCII apostrophe: davidath uses U+2018/U+2019
    throughout ("provider’s").
  * "Art. N" / "Arts. N" → "Article N": davidath gold writes "Article"
    in prose (5/137 QA); engine writes "Art." in 21/100 live preds.
  * "Ann. N" → "Annex N": symmetric to Art.
  * Diacritic strip: French / German / Czech regulator-text vocabulary
    occasionally appears ("équivalent", "Wörterbuch"). Stripping
    unifies surface forms; SQuAD-F1 / ROUGE precedent.
  * Lowercase: SQuAD-F1 standard.

Order matters in :func:`normalise_for_scoring`:

  1. NFKC first so fullwidth digits / ligatures collapse to ASCII
     equivalents before any regex operates.
  2. Dash + apostrophe folding before NFKD so the dash codepoints are
     ASCII before decomposition (NFKD can decompose some dashes into
     surprising sequences).
  3. ``Art.`` / ``Ann.`` expansion BEFORE case fold so the word-boundary
     regex sees the original capitalisation pattern.
  4. NFKD diacritic strip after the regex work, so diacritics in the
     INPUT (not in the rewritten output) get stripped.
  5. Lowercase last.
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

# ``Art.`` or ``Arts.`` followed by optional whitespace → ``Article ``.
# Word boundary on the LEFT prevents matching "Smart." or "Apart.".
_ART_ABBREV_RE = re.compile(r"\bArts?\.\s*", flags=re.IGNORECASE)

# ``Ann.`` followed by optional whitespace → ``Annex ``.
_ANN_ABBREV_RE = re.compile(r"\bAnn\.\s*", flags=re.IGNORECASE)


def normalise_for_scoring(text: str | None) -> str:
    """Map text onto the canonical scoring token-space.

    Pure, idempotent, stdlib-only. Returns ``""`` for None / empty input
    (the empty-string sentinel is friendlier for downstream regex than
    a NoneType propagation).
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
