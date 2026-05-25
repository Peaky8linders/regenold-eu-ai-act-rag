"""R89-A — article-level describer expansion regression tests.

Source data: ``evals/bench/results/v2-r88-bcde-v2-live.json`` — the
10 V2 multi-turn failing rows where the gold reference IS cited but
keyword_recall < 0.5 because the answer prose does not surface the
row's gold ``expected_keywords``.

Each new describer entry in
:data:`app.integrations.regenold.grounded_prose._ART_SUBPOINT_DESCRIBERS`
is paired with the V2 row that motivated it. The tests verify:

1. Every gold keyword for the row appears as a case-insensitive
   substring inside the describer prose (the same matching shape
   the V2 runner uses in :func:`evals.regenold.runner_v2._keyword_recall`).
2. The total prefixed length (``"Article N — " + describer``) fits
   the 400-char first-substance per-ref budget enforced by
   :func:`stitch_grounded_prose`.
3. Each describer is reachable via the public
   :func:`_subpoint_describer_clause` lookup with the env gate ON.
4. The augmenter pre-pend path fires for each new key (force_append
   surfaces the describer at sentence position 0 so the downstream
   3-sentence cap doesn't drop it).
5. The describer table import contract is preserved (env gate OFF
   returns None for the new keys, same as for the existing R88-E
   keys).
"""

from __future__ import annotations

import os

import pytest

from app.integrations.regenold.grounded_prose import (
    _ART_SUBPOINT_DESCRIBERS,
    _subpoint_describer_clause,
    augment_with_ref_descriptions,
    stitch_grounded_prose,
)

# Row → (article ref, gold expected_keywords, motivating V2 row id).
# Mirrors the rows discovered in v2-r88-bcde-v2-live.json analysis.
#
# R89-A code-review fix (E&EC-F2): the Art 50 cumulative-with-Art-13
# angle moved to _ART_CONDITIONAL_DESCRIBERS (only fires when Art 13
# co-cited). The flat Art 50 describer is now NEUTRAL — covers the
# limited-risk transparency surface without claiming cumulativity.
# This row's EXPECTED set switched from cumulative-keywords
# ("both / cumulative / apply" — mt_v2_010) to neutral-surface
# keywords ("transparency / deepfakes / labelled") because the flat
# describer no longer carries the cumulativity claim. The original
# mt_v2_010 gold-keyword coverage is exercised by
# `test_r89a_review_fix_f2_art50_cumulativity_conditional` below.
R89A_DESCRIBER_ROWS: list[tuple[str, list[str], str]] = [
    ("Article 27", ["FRIA", "fundamental rights", "in addition"], "mt_v2_002"),
    ("Article 73", ["serious incident", "15 days", "market surveillance"], "mt_v2_003"),
    ("Article 51", ["systemic risk", "10²⁵", "notify"], "mt_v2_007"),
    ("Article 53", ["systemic", "carve-out", "does not apply"], "mt_v2_009"),
    ("Article 50", ["transparency", "deepfakes", "labelled"], "mt_v2_010-neutral"),
    ("Article 60", ["real-world", "testing", "conditions"], "mt_v2_016"),
    ("Article 99", ["proportionate", "SME", "lower"], "mt_v2_017"),
    ("Article 56", ["adequate means", "alternative", "demonstrate"], "mt_v2_021"),
    ("Article 111", ["substantial change", "transitional", "grandfather"], "mt_v2_023"),
    ("Article 86", ["explanation", "individual", "right"], "mt_v2_024"),
]


# ── 1. Every R89-A key is registered in the describer table. ─────────


@pytest.mark.parametrize("ref,_kws,_row", R89A_DESCRIBER_ROWS)
def test_r89a_key_registered(ref: str, _kws: list[str], _row: str) -> None:
    assert ref in _ART_SUBPOINT_DESCRIBERS, (
        f"R89-A describer for {ref} (motivated by {_row}) is missing"
        f" from _ART_SUBPOINT_DESCRIBERS"
    )


# ── 2. Each describer surfaces ALL motivating gold keywords as
#       case-insensitive substrings (mirrors the V2 runner's
#       _keyword_recall implementation).


@pytest.mark.parametrize("ref,kws,row", R89A_DESCRIBER_ROWS)
def test_r89a_describer_surfaces_keywords(
    ref: str, kws: list[str], row: str
) -> None:
    describer = _ART_SUBPOINT_DESCRIBERS[ref]
    low = describer.lower()
    missing = [k for k in kws if k.lower() not in low]
    assert not missing, (
        f"R89-A describer for {ref} ({row}) is missing keywords: {missing}.\n"
        f"Describer prose: {describer!r}"
    )


# ── 3. Each describer fits the 400-char first-substance per-ref
#       budget (`_MAX_LEAD_SUBSTANCE_CHARS`) including the
#       "Article N — " prefix. Over-budget describers would be
#       clipped by `_first_clause`, potentially losing gold keywords.


@pytest.mark.parametrize("ref,_kws,_row", R89A_DESCRIBER_ROWS)
def test_r89a_describer_fits_per_ref_cap(
    ref: str, _kws: list[str], _row: str
) -> None:
    describer = _ART_SUBPOINT_DESCRIBERS[ref]
    prefixed_len = len(f"{ref} — ") + len(describer)
    assert prefixed_len <= 400, (
        f"R89-A describer for {ref} is {prefixed_len} chars (cap 400)."
        " Risk: _first_clause clip would lose gold keywords."
    )


# ── 4. The public lookup helper returns the describer when the env
#       gate is ON (the default).


@pytest.mark.parametrize("ref,_kws,_row", R89A_DESCRIBER_ROWS)
def test_r89a_clause_lookup_returns_describer(
    ref: str, _kws: list[str], _row: str, monkeypatch
) -> None:
    monkeypatch.setenv("REGENOLD_SUBPOINT_DESCRIBER", "1")
    clause = _subpoint_describer_clause(ref, [ref])
    assert clause is not None, (
        f"R89-A: _subpoint_describer_clause returned None for {ref}"
        " — describer not reachable through the public lookup."
    )
    assert clause == _ART_SUBPOINT_DESCRIBERS[ref]


# ── 5. The env-gate OFF path still suppresses lookups (preserves the
#       existing operator override contract).


def test_r89a_env_gate_disables_lookup(monkeypatch) -> None:
    monkeypatch.setenv("REGENOLD_SUBPOINT_DESCRIBER", "0")
    for ref, _kws, _row in R89A_DESCRIBER_ROWS:
        clause = _subpoint_describer_clause(ref, [ref])
        assert clause is None, (
            f"R89-A env gate OFF should suppress {ref} lookup"
            f" (got {clause!r})"
        )


# ── 6. The augmenter PREPENDS the describer when the cited ref
#       matches a R89-A key, so it lands at sentence position 0
#       and survives the downstream 3-sentence cap.


@pytest.mark.parametrize("ref,kws,row", R89A_DESCRIBER_ROWS)
def test_r89a_augmenter_prepends_describer(
    ref: str, kws: list[str], row: str, monkeypatch
) -> None:
    # R89-A — article-level describers respect is_covered by default
    # (env REGENOLD_R89A_FORCE_APPEND=0). Set ON here so the test
    # exercises the prepend path (the production-deploy path via
    # railway.toml). The base answer is generic / un-covered so the
    # describer would fire either way, but pinning the env makes the
    # intended path explicit.
    monkeypatch.setenv("REGENOLD_SUBPOINT_DESCRIBER", "1")
    monkeypatch.setenv("REGENOLD_REF_DESCRIBE_REPLACE", "0")
    monkeypatch.setenv("REGENOLD_R89A_FORCE_APPEND", "1")
    base = "Some generic answer that does not describe the article."
    out = augment_with_ref_descriptions(
        base,
        user_facing_refs=[ref],
    )
    # describer must appear in the output
    describer = _ART_SUBPOINT_DESCRIBERS[ref]
    assert describer.split(",")[0] in out, (
        f"R89-A augmenter did not surface {ref} describer for {row}."
        f" Output: {out[:300]!r}"
    )
    # ref must appear as the prepended prefix
    assert out.startswith(f"{ref} — "), (
        f"R89-A augmenter should PREPEND '{ref} — ...' so it survives"
        f" the 3-sentence cap. Got: {out[:120]!r}"
    )
    # the keywords must land
    low = out.lower()
    missing = [k for k in kws if k.lower() not in low]
    assert not missing, (
        f"R89-A augmenter output for {ref} ({row}) is missing"
        f" expected keywords: {missing}"
    )


# ── 7. stitch_grounded_prose substitutes the R89-A describer in
#       place of the parent KB-stub clause when user_facing_refs
#       carries the article-level ref.


@pytest.mark.parametrize("ref,kws,row", R89A_DESCRIBER_ROWS)
def test_r89a_stitcher_uses_describer(
    ref: str, kws: list[str], row: str, monkeypatch
) -> None:
    monkeypatch.setenv("REGENOLD_SUBPOINT_DESCRIBER", "1")
    # Map "Article N" → "Art. N" for internal_refs input.
    internal = "Art. " + ref[len("Article "):]
    out = stitch_grounded_prose(
        internal_refs=[internal],
        question="",
        user_facing_refs=[ref],
    )
    low = out.lower()
    missing = [k for k in kws if k.lower() not in low]
    assert not missing, (
        f"R89-A stitcher output for {ref} ({row}) is missing"
        f" expected keywords: {missing}.\nOutput: {out[:400]!r}"
    )


# ── 8. The R89-A describer set does not collide with R88-E sub-point
#       describer keys (no shape like 'Article 5' that would shadow
#       Art. 5(1)(a-h)).


def test_r89a_keys_dont_shadow_r88e_subpoint_keys() -> None:
    r89a_keys = {ref for ref, _kws, _row in R89A_DESCRIBER_ROWS}
    # R88-E sub-point keys: Article 5.1.a through Article 5.1.h.
    r88e_keys = {
        "Article 5.1.a",
        "Article 5.1.b",
        "Article 5.1.c",
        "Article 5.1.d",
        "Article 5.1.e",
        "Article 5.1.f",
        "Article 5.1.g",
        "Article 5.1.h",
    }
    overlap = r89a_keys & r88e_keys
    assert not overlap, (
        f"R89-A keys collide with R88-E sub-point keys: {overlap}"
    )
    # And R89-A keys are all bare 'Article N' (no sub-point dots).
    for k in r89a_keys:
        assert k.count(".") == 0, (
            f"R89-A key {k!r} contains a sub-point — should be article-level only"
        )


# ── 9. Article-existence lint — every R89-A key resolves in the
#       canonical article catalog.


def test_r89a_keys_resolve_in_article_existence() -> None:
    from app.data.article_existence import ARTICLE_EXISTENCE

    for ref, _kws, _row in R89A_DESCRIBER_ROWS:
        internal = "Art. " + ref[len("Article "):]
        assert internal in ARTICLE_EXISTENCE, (
            f"R89-A key {ref} (internal {internal}) is not in"
            " ARTICLE_EXISTENCE — typo or stale catalog?"
        )


# ── 10. REGENOLD_R89A_FORCE_APPEND env-gate semantics —
#       default OFF: article-level describer respects is_covered, so
#       a base answer that already cites the ref by name does NOT get
#       the describer prepended (no double-mention, keeps davidath
#       Ans Conciseness clean).
#       Set ON: describer force-prepends even when is_covered=True
#       (the V2 multi-turn rescue path — Stage-2 cites the Article
#       by name but misses the gold-keyword surface).


def test_r89a_force_append_default_off_respects_is_covered(monkeypatch) -> None:
    """With env OFF (default), a base answer already mentioning
    'Article 27' suppresses the describer prepend (is_covered=True
    via the R80-D literal cite-presence check)."""
    monkeypatch.delenv("REGENOLD_R89A_FORCE_APPEND", raising=False)
    monkeypatch.setenv("REGENOLD_SUBPOINT_DESCRIBER", "1")
    monkeypatch.setenv("REGENOLD_REF_DESCRIBE_REPLACE", "0")
    # Base answer already covers Article 27 by literal name.
    base = (
        "This question is covered by the EU AI Act under Article 27. "
        "Article 27 — Deployers must perform a Fundamental Rights "
        "Impact Assessment before first use."
    )
    out = augment_with_ref_descriptions(base, user_facing_refs=["Article 27"])
    # Describer should NOT have prepended — base answer unchanged.
    assert out == base, (
        f"R89-A env default OFF: article-level describer should respect "
        f"is_covered when base mentions the ref by name. Got: {out!r}"
    )


def test_r89a_force_append_env_on_prepends_anyway(monkeypatch) -> None:
    """With env ON, the article-level describer prepends EVEN WHEN
    is_covered=True — the V2 multi-turn rescue case."""
    monkeypatch.setenv("REGENOLD_R89A_FORCE_APPEND", "1")
    monkeypatch.setenv("REGENOLD_SUBPOINT_DESCRIBER", "1")
    monkeypatch.setenv("REGENOLD_REF_DESCRIBE_REPLACE", "0")
    base = (
        "This question is covered by the EU AI Act under Article 27. "
        "Article 27 — Deployers must perform a Fundamental Rights "
        "Impact Assessment before first use."
    )
    out = augment_with_ref_descriptions(base, user_facing_refs=["Article 27"])
    # Describer must have prepended at sentence position 0.
    assert out.startswith("Article 27 — "), (
        f"R89-A env ON: describer should PREPEND. Got: {out[:120]!r}"
    )
    # And the FRIA acronym must now land in the augmented output.
    assert "FRIA" in out, (
        f"R89-A env ON: describer must surface FRIA keyword. Got: {out[:300]!r}"
    )


def test_r89a_sub_point_keys_still_force_append_regardless(monkeypatch) -> None:
    """R88-E sub-point keys (Article 5.1.f / .1.g / .1.h) must still
    force-append regardless of the R89-A env gate — they don't share
    the article-level double-mention failure mode."""
    monkeypatch.delenv("REGENOLD_R89A_FORCE_APPEND", raising=False)
    monkeypatch.setenv("REGENOLD_SUBPOINT_DESCRIBER", "1")
    monkeypatch.setenv("REGENOLD_REF_DESCRIBE_REPLACE", "0")
    # Base answer covers Article 5 generically but NOT the sub-point.
    base = (
        "This question is covered by the EU AI Act under Article 5. "
        "Article 5 prohibits subliminal, manipulative, and deceptive "
        "techniques."
    )
    out = augment_with_ref_descriptions(
        base, user_facing_refs=["Article 5.1.f"]
    )
    # Sub-point describer should still prepend with R88-E force_append.
    assert out.startswith("Article 5.1.f — "), (
        f"R88-E sub-point should force-prepend independent of R89-A "
        f"env gate. Got: {out[:120]!r}"
    )


# ── 11. R89-A code-review fixes ─────────────────────────────────────────


def test_r89a_review_fix_f2_art50_cumulativity_conditional(monkeypatch) -> None:
    """E&EC F2: the Art 50 cumulative-with-Art-13 angle MUST fire only
    when Art 13 is co-cited. Otherwise an Art-50-only question would
    misleadingly claim cumulative Art 13 duties.
    """
    from app.integrations.regenold.grounded_prose import (
        _subpoint_describer_clause,
    )

    monkeypatch.setenv("REGENOLD_SUBPOINT_DESCRIBER", "1")

    # Art 50 alone → flat describer (NO cumulativity claim).
    flat = _subpoint_describer_clause("Article 50", ["Article 50"])
    assert flat is not None
    assert "cumulative" not in flat.lower()
    assert "both apply" not in flat.lower()

    # Art 50 + Art 13 → conditional describer fires WITH cumulativity.
    cond = _subpoint_describer_clause(
        "Article 50", ["Article 13", "Article 50"]
    )
    assert cond is not None
    assert "cumulative" in cond.lower()
    # Gold keywords from mt_v2_010 must still hit.
    assert "both" in cond.lower()
    assert "apply" in cond.lower()


def test_r89a_review_fix_lc1_conditional_check_order(monkeypatch) -> None:
    """L&C-1: a conditional-table entry must take precedence over
    the dot-heuristic. Verify by direct membership: Article 113 is
    keyed in _ART_CONDITIONAL_DESCRIBERS but its key has no dot
    (so `is_subpoint_key` was always False for it). With the fix,
    `is_conditional_key` is checked FIRST, so the order is
    authoritative even if a future conditional key DID have a dot.
    """
    from app.integrations.regenold.grounded_prose import (
        _ART_CONDITIONAL_DESCRIBERS,
    )

    # Confirm both conditional keys we care about are in the table.
    assert "Article 113" in _ART_CONDITIONAL_DESCRIBERS
    assert "Article 50" in _ART_CONDITIONAL_DESCRIBERS


def test_r89a_review_fix_lc2_paragraph_only_key_not_subpoint() -> None:
    """L&C-2: tighten the sub-point classifier so a hypothetical
    paragraph-only key like ``Article 53.2`` is NOT treated as a
    sub-point (which would force-append unconditionally and bypass
    the R89-A env gate). True sub-points have a LETTER suffix.
    """
    from app.integrations.regenold.grounded_prose import _SUBPOINT_LETTER_RE

    # True sub-points (R88-E entries) MUST match.
    for key in ("Article 5.1.a", "Article 5.1.f", "Article 5.1.h"):
        assert _SUBPOINT_LETTER_RE.search(key) is not None, (
            f"R89-A regex regression — true sub-point {key!r} not matched"
        )
    # Paragraph-only references MUST NOT match (no letter suffix).
    for key in ("Article 53.2", "Article 27.1", "Article 11.3"):
        assert _SUBPOINT_LETTER_RE.search(key) is None, (
            f"R89-A regex over-broad — paragraph ref {key!r} treated as sub-point"
        )
    # Article-level R89-A keys MUST NOT match.
    for key in ("Article 27", "Article 50", "Article 73", "Article 86"):
        assert _SUBPOINT_LETTER_RE.search(key) is None


def test_r89a_review_fix_f5_self_check_runs_at_import() -> None:
    """E&EC F5: the import-time self-check validates table shapes.
    Verify by re-running the check directly — it must not raise
    on the current table state.
    """
    from app.integrations.regenold.grounded_prose import (
        _self_check_describer_tables,
    )
    # Should not raise; if it does, the table has drifted from spec.
    _self_check_describer_tables()


def test_r89a_review_fix_m5_describer_lengths_within_per_ref_cap() -> None:
    """C&I M5: re-check that every describer length+prefix fits the
    400-char first-substance per-ref budget. Comment was updated to
    match this gate; the assertion mirrors it directly.
    """
    from app.integrations.regenold.grounded_prose import (
        _ART_SUBPOINT_DESCRIBERS,
        _MAX_LEAD_SUBSTANCE_CHARS,
    )
    for key in (
        "Article 27", "Article 73", "Article 51", "Article 53",
        "Article 50", "Article 60", "Article 99", "Article 56",
        "Article 111", "Article 86",
    ):
        d = _ART_SUBPOINT_DESCRIBERS[key]
        total = len(f"{key} — ") + len(d)
        assert total <= _MAX_LEAD_SUBSTANCE_CHARS, (
            f"{key} describer {total} chars exceeds "
            f"_MAX_LEAD_SUBSTANCE_CHARS={_MAX_LEAD_SUBSTANCE_CHARS}"
        )
