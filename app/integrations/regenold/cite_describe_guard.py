"""Round 66-B — Stage-2.5 cite-describe guard.

The **inverse** of :mod:`app.integrations.regenold.citation_guard`.

* The R31 ``citation_guard`` drops *sentences* whose token set has no
  overlap with the surfaced refs' KB pool (sentence-level pruning).
* The R66-B ``cite_describe_guard`` drops *refs* whose KB-summary
  token set has no meaningful overlap with the answer prose
  (reference-level pruning).

## Why this exists

The Regenold competition has two scoring axes that pull in opposite
directions:

* **Davidath rubric** rewards citing every gold reference (more refs
  that match gold = higher RefLoose / RefStrict).
* **LLM-as-Judge ``refs`` axis** rewards prose-faithfulness — if the
  answer cites Article 13 but the prose never substantively describes
  what Article 13 says, the judge marks the row as a refs failure.

R66-B is an opt-in guard targeting the judge axis. The expectation is
that turning it ON will drop davidath RefLoose slightly (fewer refs
cited) while improving the judge refs pass-rate AND RefConciseness
(less padding).

## Design constraints (mirrored from R31 citation_guard)

1. **Never empty the references list.** Round-16 / Round-49 finding:
   over-broad answers beat empty ones on the competition rubric. The
   guard always preserves a minimum-floor of refs even if every
   surfaced ref fails the overlap check (the highest-overlap one
   survives).
2. **Pure stdlib, sub-millisecond.** No LLM call, no new dependencies.
   Uses the same BM25 tokeniser the rest of the pipeline already pays
   the import cost for.
3. **Reversible via env-gate.** ``REGENOLD_CITE_DESCRIBE_GUARD=1``
   opt-in; default OFF until benchmark + judge evidence proves it's a
   net positive.
4. **Fail-soft.** If the KB lookup fails for a ref (phantom citation
   the upstream pipeline somehow surfaced), the ref is KEPT — we
   can't measure it, so we don't penalise it.

## Algorithm

For each user-facing ref the route is about to ship:

1. Convert the ref to internal form (``Article 13`` → ``Art. 13``;
   ``Annex IV.2`` → ``Annex IV``) — matches the BM25 corpus key shape.
2. Look up the article's BM25 token pool via the existing
   :func:`app.integrations.regenold.citation_guard._reference_token_pool`
   so the two passes are guaranteed consistent.
3. Tokenise the answer prose via the existing
   :func:`app.data.kb_search._tokenize` (lowercased + alphanumeric +
   stop-word filtered + length-≥2; same tokens the BM25 index uses).
4. Compute ``overlap_count = |answer_tokens ∩ ref_summary_tokens|``.
5. Keep the ref iff ``overlap_count >= min_overlap_tokens`` (default
   2 per the brief — 1-token overlap is too lenient on a regulator-
   voice answer; 3+ is too aggressive).
6. If every ref fails the threshold, keep the top ``min_floor`` refs
   by overlap score (ties broken by original order) so the answer's
   reference list is never emptied.

The output is a subsequence of the input that preserves original
order.
"""
from __future__ import annotations

import os

_ENV_FLAG: str = "REGENOLD_CITE_DESCRIBE_GUARD"


def is_enabled() -> bool:
    """True iff the env-gate is set. Cheap to call."""
    val = os.getenv(_ENV_FLAG, "").strip().lower()
    return val in ("1", "true", "yes", "on")


def _ref_summary_pool(user_facing_ref: str) -> frozenset[str] | None:
    """Return the KB-summary token pool for ``user_facing_ref``.

    Returns ``None`` when the ref doesn't resolve in the BM25 corpus
    (no KB-doc, ontology-doc, or definition-doc rows are keyed to this
    article) — the caller treats that as "can't measure, keep the
    ref" so a phantom citation surviving upstream doesn't get
    penalised here.

    Mirrors the R31 citation_guard's :func:`_reference_token_pool`
    normalisation (user-facing → internal, sub-points collapse to
    parent) for shape parity, but probes the BM25 index DIRECTLY so
    we can distinguish "has KB content" from "the citation_guard
    helper folded the bare ref-tokens (e.g. 'article', '999') into
    the pool". Without that probe, every phantom citation would have
    a single-token "pool" containing just its article number and we
    couldn't drop a ref vs flag it as unmeasurable.
    """
    # Lazy imports — keeps module-load cheap and avoids touching the
    # BM25 corpus at process boot. The route always calls this AFTER
    # retrieval, so the BM25 index is guaranteed already built.
    from app.data.kb_search import _build_index, _tokenize  # noqa: PLC0415
    from app.integrations.regenold.citation_guard import (  # noqa: PLC0415
        _to_internal_ref,
    )

    internal = _to_internal_ref(user_facing_ref)
    index = _build_index()

    # Walk the BM25 corpus once, collect every doc whose article_refs
    # entry matches the internal ref. If NO doc rows match, the
    # citation is a phantom — return None.
    tokens: set[str] = set()
    matched_any = False
    for doc_idx, ref in enumerate(index.article_refs):
        if ref != internal:
            continue
        matched_any = True
        tokens.update(index.docs[doc_idx])
    if not matched_any:
        return None
    # Fold the ref-itself tokens in so a sentence saying "Article 13"
    # registers overlap. This mirrors the R31 helper's final step,
    # but ONLY when we've confirmed real KB content exists.
    tokens.update(_tokenize(user_facing_ref))
    tokens.update(_tokenize(internal))
    return frozenset(tokens)


def prune_undescribed_refs(
    answer: str,
    references: list[str],
    *,
    min_floor: int = 1,
    min_overlap_tokens: int = 2,
) -> tuple[list[str], dict[str, str]]:
    """Drop references whose KB summary isn't substantively described
    in ``answer``.

    :param answer: the final answer prose. When empty / whitespace,
        ``references`` is returned unchanged (defensive — don't
        worsen the answer).
    :param references: user-facing ref shapes (``Article N`` /
        ``Annex X``). Iteration order is preserved on the kept refs.
    :param min_floor: minimum number of refs to keep when every ref
        fails the overlap check. Default 1 — honours the R16 / R49
        "never empty the answer" invariant. Set to ``len(references)``
        to disable the pruning entirely (test fixture use).
    :param min_overlap_tokens: minimum overlap-count required to KEEP
        a ref. Default 2 — 1 was tested to be too lenient (a single
        shared token like "article" or "compliance" passes), 3+ is
        too aggressive on legitimate concise prose.

    :returns: ``(pruned_references, drop_reasons)`` where
        ``pruned_references`` is the surviving subsequence (always
        preserves original order) and ``drop_reasons`` is a dict from
        DROPPED ref → human-readable reason string. The reasons dict
        is for the reasoning-trace audit; production code that only
        wants the pruned list can ignore the second tuple element.

    The function never raises. It treats every failure mode
    defensively:

    * Empty / whitespace ``answer`` → return references unchanged,
      empty reasons dict.
    * Empty ``references`` → return ``([], {})``.
    * KB lookup returns ``None`` for a ref (phantom citation) → KEEP
      the ref (mark it ``measurement_unavailable`` in the reasons
      dict but don't drop).
    * All refs fail the overlap threshold → keep the top
      ``min_floor`` refs by overlap score so the floor invariant
      holds. Dropped refs still appear in the reasons dict.
    """
    if not references:
        return [], {}
    if not answer or not answer.strip():
        # Defensive — don't measure on empty prose.
        return list(references), {}

    # Lazy import — tokeniser is the same one BM25 uses, keeps overlap
    # measurement consistent with retrieval scoring.
    from app.data.kb_search import _tokenize  # noqa: PLC0415

    answer_tokens = frozenset(_tokenize(answer))
    if not answer_tokens:
        # The answer prose collapsed to all-stopwords. Defensive: keep
        # refs unchanged because the floor invariant beats over-pruning.
        return list(references), {}

    # Per-ref score sheet. Negative overlap means "can't measure"
    # (KB lookup miss) — those refs always survive.
    UNMEASURABLE = -1
    scores: list[tuple[int, str, int]] = []  # (index, ref, overlap)
    drop_reasons: dict[str, str] = {}
    for idx, ref in enumerate(references):
        pool = _ref_summary_pool(ref)
        if pool is None:
            # Can't measure — keep the ref. Record for trace audit so
            # the judge can spot phantom-citation cases.
            scores.append((idx, ref, UNMEASURABLE))
            continue
        overlap = len(answer_tokens & pool)
        scores.append((idx, ref, overlap))

    # First pass — keep every ref with overlap >= threshold OR
    # unmeasurable. Drop the rest into ``failed`` for the floor pass.
    kept: list[tuple[int, str, int]] = []
    failed: list[tuple[int, str, int]] = []
    for entry in scores:
        idx, ref, overlap = entry
        if overlap == UNMEASURABLE or overlap >= min_overlap_tokens:
            kept.append(entry)
        else:
            failed.append(entry)

    # Floor invariant — when EVERY ref failed the threshold, promote
    # the top ``min_floor`` by overlap-score (ties broken by original
    # order) into ``kept`` so the references list is never emptied
    # below ``min_floor``.
    if not kept and failed:
        # Sort by overlap desc, then by original index asc for tie-break.
        failed_sorted = sorted(failed, key=lambda t: (-t[2], t[0]))
        floor_keep = failed_sorted[:max(min_floor, 1)]
        kept = floor_keep
        # The remainder of ``failed`` are truly dropped — record reasons.
        floor_keep_keys = {(t[0], t[1]) for t in floor_keep}
        for entry in failed:
            idx, ref, overlap = entry
            if (idx, ref) in floor_keep_keys:
                continue
            drop_reasons[ref] = f"below_threshold(overlap={overlap},floor_kept_higher)"
    else:
        # Standard path — record each failed ref's drop reason.
        for entry in failed:
            idx, ref, overlap = entry
            drop_reasons[ref] = f"below_threshold(overlap={overlap}<{min_overlap_tokens})"

    # Also record any unmeasurable refs in the reasons dict so the
    # trace surfaces them (but they're NOT dropped — they're in
    # ``kept`` already). Use a distinct prefix so the audit can tell
    # them apart from real drops.
    for entry in scores:
        idx, ref, overlap = entry
        if overlap == UNMEASURABLE:
            # ``measurement_unavailable`` is informational, not a drop.
            # Don't overwrite an existing reason if one was set above.
            drop_reasons.setdefault(
                f"__measurement_unavailable__:{ref}",
                "kb_summary_missing",
            )

    # Preserve original order on the output.
    kept.sort(key=lambda t: t[0])
    pruned_references = [t[1] for t in kept]
    return pruned_references, drop_reasons


def maybe_apply_guard(
    answer: str,
    references: list[str],
    *,
    min_floor: int = 1,
    min_overlap_tokens: int = 2,
) -> tuple[list[str], dict[str, str]]:
    """Env-gated wrapper around :func:`prune_undescribed_refs`.

    Returns ``(references_unchanged, {})`` when the env-gate is OFF.
    Otherwise calls the guard with the supplied thresholds.

    The route layer calls THIS function so one env-flag lookup
    short-circuits the work when the guard is off.
    """
    if not is_enabled():
        return list(references), {}
    return prune_undescribed_refs(
        answer,
        references,
        min_floor=min_floor,
        min_overlap_tokens=min_overlap_tokens,
    )


__all__ = [
    "is_enabled",
    "maybe_apply_guard",
    "prune_undescribed_refs",
]
