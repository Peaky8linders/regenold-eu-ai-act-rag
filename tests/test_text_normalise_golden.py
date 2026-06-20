"""R138 — golden regression for the davidath scorer's custom stemmer.

The R82-A tokenizer (``evals/bench/text_normalise.stem_token``) is a custom
greedy 5-suffix loop, NOT standard Porter (no y→i), self-documented as
"within-noise but unvalidated against morphological edge cases". This is the
one residual metric risk in the regression-guard's OWN scorer. These tests pin
its behaviour so a future edit can't silently drift the davidath token-overlap
axes.

Strategy: assert morphological-FAMILY COLLAPSE (the property the metric relies
on — plural/verb variants of a load-bearing EU-AI-Act term score as the same
token) rather than hard-coding the exact greedy stem, plus a few known-correct
exact stems and the non-mutation invariants.
"""
from __future__ import annotations

import pytest

from evals.bench.text_normalise import stem_token

# Each family: variants that MUST collapse to one stem (so token-overlap
# scoring treats them as the same gold token). EU-AI-Act load-bearing terms.
_FAMILIES: tuple[tuple[str, ...], ...] = (
    ("obligation", "obligations"),
    ("provider", "providers"),
    ("deployer", "deployers"),
    ("importer", "importers"),
    ("distributor", "distributors"),
    ("definition", "definitions"),
    ("requirement", "requirements"),
    ("system", "systems"),
    ("model", "models"),
    ("prohibition", "prohibitions"),
    ("transparency", "transparency"),  # no variant — must be stable
    ("annex", "annexes"),
)


@pytest.mark.parametrize("family", _FAMILIES, ids=[f[0] for f in _FAMILIES])
def test_morphological_family_collapses(family):
    stems = {stem_token(v) for v in family}
    assert len(stems) == 1, (
        f"variants {family} stemmed to {stems}; the davidath token-overlap "
        f"axes need them to collapse to one token"
    )


def test_stem_is_idempotent():
    for w in ("obligations", "providers", "analysed", "facilities", "marking"):
        assert stem_token(stem_token(w)) == stem_token(w)


def test_stem_never_empties_a_real_word():
    for w in ("ai", "eu", "risk", "data", "logs", "use", "must", "shall"):
        assert stem_token(w), f"stem_token({w!r}) collapsed to empty"


def test_short_function_words_stable():
    # 2-char tokens the V2 tokenizer keeps must survive stemming intact.
    for w in ("ai", "eu"):
        assert stem_token(w) == w
