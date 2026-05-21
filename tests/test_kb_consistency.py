"""KB / ontology consistency lint.

Enforces the invariants documented in ``docs/ontology/ONTOLOGY.md``:
every article/annex reference appearing anywhere in the typed ontology
OR in any of the legacy lookup maps must resolve to a real entry in
:data:`app.data.article_existence.ARTICLE_EXISTENCE`.

Without this lint, a typo in a new keyword entry (e.g. ``("typo_keyword",
"Art. 500")``) would silently ship a hallucinated citation on the wire,
because the route's ``reference_from_article_ref`` filter validates
against ``ARTICLE_EXISTENCE`` but only at request time. We want fail-fast
at import / CI time — that's what the consistency lint provides.

The lint runs in CI as part of the standard pytest suite. New
ontology entries must pass these checks before they can land.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from app.data.article_existence import ARTICLE_EXISTENCE
from app.data.kb import EC_CHECKER_OBLIGATION_MAP, KB_VERSION
from app.data.ontology import (
    ANNEX_III_REGISTRY,
    PHASE_REGISTRY,
    PRACTICE_REGISTRY,
    ROLE_OBLIGATIONS,
    all_articles_referenced,
)


# ── Helpers ────────────────────────────────────────────────────────────


def _is_known_or_prefix_known(ref: str) -> bool:
    """A reference is valid if it's in :data:`ARTICLE_EXISTENCE` OR a
    sub-paragraph variant of an entry in it.

    Mirrors the route's existence semantics (``Art. 13.1.a`` is valid
    because ``Art. 13`` is in the catalog). Without this fallback, the
    ontology's intentional sub-paragraph references like ``Art. 5.1.a``
    would fail the lint.
    """
    if ref in ARTICLE_EXISTENCE:
        return True
    # Strip trailing ``.X`` segments and re-check.
    candidate = ref
    while "." in candidate:
        candidate = candidate.rsplit(".", 1)[0].strip()
        if candidate in ARTICLE_EXISTENCE:
            return True
    return False


# ── Ontology lint ─────────────────────────────────────────────────────


class TestOntologyConsistency:
    """Every typed-ontology reference must resolve in ARTICLE_EXISTENCE."""

    def test_practice_citations_resolve(self) -> None:
        """Every ``Practice.citation`` tuple member is a known article/annex."""
        for practice in PRACTICE_REGISTRY.values():
            for ref in practice.citation:
                assert _is_known_or_prefix_known(ref), (
                    f"Practice {practice.id!r}: citation {ref!r} not in "
                    f"ARTICLE_EXISTENCE"
                )

    def test_practice_high_risk_anchors_resolve(self) -> None:
        """Every ``Practice.related_high_risk_anchor`` (if set) is known."""
        for practice in PRACTICE_REGISTRY.values():
            if practice.related_high_risk_anchor is None:
                continue
            assert _is_known_or_prefix_known(practice.related_high_risk_anchor), (
                f"Practice {practice.id!r}: "
                f"related_high_risk_anchor={practice.related_high_risk_anchor!r} "
                f"not in ARTICLE_EXISTENCE"
            )

    def test_practice_effective_phases_resolve(self) -> None:
        """Every ``Practice.effective_phase`` is a valid Phase id."""
        for practice in PRACTICE_REGISTRY.values():
            assert practice.effective_phase in PHASE_REGISTRY, (
                f"Practice {practice.id!r}: effective_phase="
                f"{practice.effective_phase!r} is not a Phase id"
            )

    def test_annex_iii_categories_have_keywords(self) -> None:
        """Every Annex III category carries at least one keyword anchor.

        Without keywords the category is unreachable from a user
        question — defeats the purpose of having a typed registry.
        """
        for category in ANNEX_III_REGISTRY.values():
            assert category.keywords, (
                f"AnnexIIICategory {category.id!r} has no keywords"
            )

    def test_annex_iii_related_prohibitions_resolve(self) -> None:
        """Every related-prohibition reference is a valid Practice id."""
        for category in ANNEX_III_REGISTRY.values():
            for practice_id in category.related_prohibitions:
                assert practice_id in PRACTICE_REGISTRY, (
                    f"AnnexIIICategory {category.id!r}: "
                    f"related_prohibitions entry {practice_id!r} is not a "
                    f"Practice id"
                )

    def test_phase_articles_resolve(self) -> None:
        """Every article a Phase activates is in the catalog."""
        for phase in PHASE_REGISTRY.values():
            for ref in phase.articles:
                assert _is_known_or_prefix_known(ref), (
                    f"Phase {phase.id!r}: articles entry {ref!r} not in "
                    f"ARTICLE_EXISTENCE"
                )

    def test_phase_supersession_targets_resolve(self) -> None:
        """``Phase.superseded_by`` (if set) is a valid Phase id."""
        for phase in PHASE_REGISTRY.values():
            if phase.superseded_by is None:
                continue
            assert phase.superseded_by in PHASE_REGISTRY, (
                f"Phase {phase.id!r}: superseded_by={phase.superseded_by!r} "
                f"is not a Phase id"
            )

    def test_role_obligation_matrix_refs_resolve(self) -> None:
        """Every article ref in ROLE_OBLIGATIONS is in the catalog."""
        for role, by_class in ROLE_OBLIGATIONS.items():
            for risk_class, refs in by_class.items():
                for ref in refs:
                    assert _is_known_or_prefix_known(ref), (
                        f"ROLE_OBLIGATIONS[{role.value}][{risk_class.value}]: "
                        f"ref {ref!r} not in ARTICLE_EXISTENCE"
                    )

    def test_all_articles_referenced_helper_returns_only_known(self) -> None:
        """``all_articles_referenced()`` aggregates the full ontology ref set."""
        for ref in all_articles_referenced():
            assert _is_known_or_prefix_known(ref), (
                f"all_articles_referenced() includes {ref!r} not in "
                f"ARTICLE_EXISTENCE"
            )


# ── Legacy lookup-map lint ─────────────────────────────────────────────
#
# The legacy maps in graph_rag.py + scope.py predate the typed
# ontology. They stay live (they encode round-1-through-13 wins) but
# every reference value must still resolve in ARTICLE_EXISTENCE.


class TestLegacyMapConsistency:
    """The legacy keyword + classification maps must point at real refs."""

    def test_ec_checker_obligation_map_keys_resolve(self) -> None:
        """Every key in :data:`EC_CHECKER_OBLIGATION_MAP` is a real article."""
        for key in EC_CHECKER_OBLIGATION_MAP:
            assert _is_known_or_prefix_known(key), (
                f"EC_CHECKER_OBLIGATION_MAP key {key!r} not in ARTICLE_EXISTENCE"
            )

    def test_keyword_entity_map_targets_resolve(self) -> None:
        """Every ``_KEYWORD_ENTITY_MAP`` target article is real."""
        from app.engines.graph_rag import _KEYWORD_ENTITY_MAP

        assert _KEYWORD_ENTITY_MAP, "_KEYWORD_ENTITY_MAP is empty"
        for keyword, ref in _KEYWORD_ENTITY_MAP:
            assert _is_known_or_prefix_known(ref), (
                f"_KEYWORD_ENTITY_MAP[{keyword!r}] = {ref!r}, not in "
                f"ARTICLE_EXISTENCE"
            )

    def test_keyword_to_article_targets_resolve(self) -> None:
        """Every ``KEYWORD_TO_ARTICLE`` (scope) target is a real article."""
        from app.integrations.regenold.scope import KEYWORD_TO_ARTICLE
        for keyword, ref in KEYWORD_TO_ARTICLE.items():
            assert _is_known_or_prefix_known(ref), (
                f"KEYWORD_TO_ARTICLE[{keyword!r}] = {ref!r}, not in "
                f"ARTICLE_EXISTENCE"
            )

    def test_classification_topic_refs_resolve(self) -> None:
        """Every ``_CLASSIFICATION_TOPICS[i]['refs']`` entry is a real article."""
        from app.engines.graph_rag import _CLASSIFICATION_TOPICS
        for topic in _CLASSIFICATION_TOPICS:
            for ref in topic["refs"]:
                assert _is_known_or_prefix_known(ref), (
                    f"_CLASSIFICATION_TOPICS[{topic['name']!r}] cites "
                    f"{ref!r}, not in ARTICLE_EXISTENCE"
                )


# ── Cross-reference graph lint ────────────────────────────────────────


class TestCrossRefGraphConsistency:
    """The auto-derived cross-reference graph must only target real refs."""

    def test_all_edges_target_known_articles(self) -> None:
        from app.data.kb_xrefs import all_edges
        for source, target in all_edges():
            assert _is_known_or_prefix_known(source), (
                f"Cross-ref edge source {source!r} not in ARTICLE_EXISTENCE"
            )
            assert _is_known_or_prefix_known(target), (
                f"Cross-ref edge source={source!r} → target={target!r}: "
                f"target not in ARTICLE_EXISTENCE"
            )

    def test_no_self_edges(self) -> None:
        """A cross-ref graph with self-edges is a regression."""
        from app.data.kb_xrefs import all_edges
        for source, target in all_edges():
            assert source != target, (
                f"Self-edge {source!r} → {target!r} in cross-ref graph"
            )


# ── Manual cross-reference linter ─────────────────────────────────────


class TestManualXRefLinter:
    """The manually-curated edge list in ``kb_xrefs.MANUAL_XREFS``.

    Edges authored by hand are the highest-value but also the easiest to
    break: a typo in ``Art. 5OO`` or ``Annex XIV`` would silently ship a
    hallucinated citation. The lint enforces:

    1. Every endpoint resolves in :data:`ARTICLE_EXISTENCE`.
    2. No duplicate ``(source, target)`` pairs (manual edges should not
       overlap themselves; overlap with the regex-extracted set is
       fine — the merge in ``_build_xref_graph`` deduplicates).
    3. Bidirectional edges (those whose reverse is also in the manual
       set) are present in both directions.
    """

    def test_manual_xrefs_lint_runs_at_import(self) -> None:
        """``MANUAL_XREFS_LINTED`` is populated only if the import-time
        lint passed."""
        from app.data.kb_xrefs import MANUAL_XREFS, MANUAL_XREFS_LINTED
        assert MANUAL_XREFS_LINTED is MANUAL_XREFS or (
            tuple(MANUAL_XREFS_LINTED) == tuple(MANUAL_XREFS)
        )

    def test_manual_xref_endpoints_resolve(self) -> None:
        from app.data.kb_xrefs import MANUAL_XREFS
        for source, target, _reason in MANUAL_XREFS:
            assert _is_known_or_prefix_known(source), (
                f"MANUAL_XREFS source {source!r} not in ARTICLE_EXISTENCE"
            )
            assert _is_known_or_prefix_known(target), (
                f"MANUAL_XREFS source={source!r} → target={target!r}: "
                f"target not in ARTICLE_EXISTENCE"
            )

    def test_manual_xrefs_have_no_duplicates(self) -> None:
        """Each ``(source, target)`` pair appears at most once."""
        from app.data.kb_xrefs import MANUAL_XREFS
        seen: set[tuple[str, str]] = set()
        for source, target, _reason in MANUAL_XREFS:
            pair = (source, target)
            assert pair not in seen, (
                f"Duplicate MANUAL_XREFS edge {pair!r}"
            )
            seen.add(pair)

    def test_manual_xrefs_no_self_edges(self) -> None:
        from app.data.kb_xrefs import MANUAL_XREFS
        for source, target, _reason in MANUAL_XREFS:
            assert source != target, (
                f"MANUAL_XREFS self-edge {source!r} → {target!r}"
            )

    def test_manual_xrefs_reasons_non_empty(self) -> None:
        from app.data.kb_xrefs import MANUAL_XREFS
        for source, target, reason in MANUAL_XREFS:
            assert reason and reason.strip(), (
                f"MANUAL_XREFS {source!r} → {target!r} has empty reason"
            )

    def test_manual_xrefs_bidirectional_pairs_have_both_directions(self) -> None:
        """Every Annex↔Article edge that the curated list claims is
        bidirectional must actually appear in both directions.

        The intent of the manual set is to fix the directed-graph
        asymmetry of the regex extractor. If an edge is added in one
        direction only, the reverse-lookup ("what references Annex IV?")
        will silently miss the connection — defeating the purpose.
        """
        from app.data.kb_xrefs import MANUAL_XREFS
        pairs = {(s, t) for s, t, _ in MANUAL_XREFS}
        # The pairs we explicitly intend to be bidirectional are those
        # where BOTH the (a, b) and (b, a) entries exist in the curated
        # list. The lint just verifies each such pair has its mate.
        for source, target in list(pairs):
            reverse = (target, source)
            if reverse in pairs:
                # Trivially holds, but the assert makes the intent
                # explicit in the test surface.
                assert reverse in pairs

        # The substantive check: every Annex referenced as a source in
        # any manual edge must have at least one reverse mate from an
        # Art. anchor — otherwise the manual edge is unidirectional.
        annex_sources = {s for s, _, _ in MANUAL_XREFS if s.startswith("Annex")}
        for annex in annex_sources:
            forward = [t for s, t, _ in MANUAL_XREFS if s == annex]
            assert forward, f"Annex {annex} has no outbound edges"
            # At least one reverse mate must exist somewhere in the set.
            reverse_count = sum(
                1 for s, t, _ in MANUAL_XREFS if t == annex and s in forward
            )
            assert reverse_count >= 1, (
                f"Annex {annex} has outbound edges {forward} but no "
                f"corresponding inbound edge — manual graph is "
                f"unidirectional, which is the bug this layer fixes"
            )

    def test_merged_graph_contains_manual_edges(self) -> None:
        """After merge, every manual edge appears in ``cross_refs``."""
        from app.data.kb_xrefs import MANUAL_XREFS, cross_refs
        for source, target, _reason in MANUAL_XREFS:
            # `cross_refs` enforces a default limit; raise it so the
            # merge result is not truncated for hub articles.
            refs = cross_refs(source, limit=100)
            assert target in refs, (
                f"Manual edge {source!r} → {target!r} missing from "
                f"merged cross_refs({source!r}); got {refs}"
            )

    def test_cross_refs_with_reason_returns_pairs(self) -> None:
        """``cross_refs_with_reason`` returns ``(target, reason)`` tuples."""
        from app.data.kb_xrefs import cross_refs_with_reason
        pairs = cross_refs_with_reason("Annex IV", limit=10)
        # Annex IV → Art. 11 is the canonical example.
        target_to_reason = dict(pairs)
        assert "Art. 11" in target_to_reason, (
            f"Expected Art. 11 in cross_refs_with_reason('Annex IV'); got {pairs}"
        )
        # The reason must be the curated one, not the fallback.
        assert "technical documentation" in target_to_reason["Art. 11"].lower()


# ── KB_VERSION bump lint (R56-A) ──────────────────────────────────────
#
# R54.1 deep-code-review fix C3 found that R53.2's edits to Art. 25 +
# Art. 101 stubs silently bypassed the ``KB_VERSION`` bump rule because
# the convention was doc-only. Two downstream consumers key on
# ``KB_VERSION``:
#
#   1. The engine LRU cache (``app/routes/regenold.py::_engine_cache_key``)
#      folds it into the sha256, so a stale version → stale answers.
#   2. The Neo4j auto-seed (``app/main.py::_maybe_auto_seed_neo4j``)
#      skips re-seeding when ``KBMetadata.seed_version`` matches the
#      stored value, so a stale version → stale graph.
#
# R56-A converts the doc-only rule into an enforced CI lint by pinning
# a hash signature of ``EC_CHECKER_OBLIGATION_MAP`` together with the
# current ``KB_VERSION`` in a snapshot file. The hash canonicalises
# whitespace so cosmetic re-flows don't trip the lint, but any content
# edit (insert / delete / re-word) will.


_KB_SNAPSHOT_PATH = (
    Path(__file__).parent / "_snapshots" / "kb_version_signature.txt"
)


def _compute_kb_signature() -> str:
    """Stable hash over ``EC_CHECKER_OBLIGATION_MAP`` content.

    Sorted keys + whitespace-canonicalised values, so cosmetic edits
    (re-flowing a multi-line stub at a different column, normalising
    NBSP, adding a trailing newline) do NOT trip the lint, but real
    content changes (insert / delete / re-word) do.
    """
    items = sorted(EC_CHECKER_OBLIGATION_MAP.items(), key=lambda kv: kv[0])
    canonical = "\n".join(
        f"{key}::{' '.join(str(value).split())}"
        for key, value in items
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class TestKBVersionSnapshot:
    """R56-A — enforce the C3 ``KB_VERSION`` bump rule via CI lint.

    The snapshot at ``tests/_snapshots/kb_version_signature.txt`` is
    a single line ``<KB_VERSION>::<sha256_hex>`` pinning the current
    KB content against its declared version.

    To deliberately update the KB content:

    1. Edit ``EC_CHECKER_OBLIGATION_MAP`` in ``app/data/kb.py``.
    2. Bump ``KB_VERSION`` in ``app/data/kb.py`` (e.g. ``v3`` → ``v4``).
    3. Update ``tests/_snapshots/kb_version_signature.txt`` to the new
       ``<version>::<hash>`` pair (re-run this test; the failure message
       prints the new hash).
    4. Commit the test snapshot alongside the KB edit.

    The lint catches two failure modes:

    * Content changed but ``KB_VERSION`` not bumped (the R53.2 → R54.1
      C3 regression) → engine cache + Neo4j seed both serve stale data.
    * ``KB_VERSION`` bumped without a content change (drift / typo) →
      forces an unnecessary cache invalidation.
    """

    def test_kb_version_bumped_when_content_changes(self) -> None:
        """If ``EC_CHECKER_OBLIGATION_MAP`` content changes,
        ``KB_VERSION`` MUST bump (and the snapshot MUST be updated)."""
        actual_hash = _compute_kb_signature()

        if not _KB_SNAPSHOT_PATH.exists():
            # First run: contributor must create the snapshot. Print
            # the exact line to write so it's a one-shot fix.
            raise AssertionError(
                f"KB version snapshot missing at {_KB_SNAPSHOT_PATH}. "
                f"Create the file with this single line:\n"
                f"  {KB_VERSION}::{actual_hash}\n"
                f"and commit it alongside the KB edit."
            )

        expected = _KB_SNAPSHOT_PATH.read_text(encoding="utf-8").strip()
        expected_version, sep, expected_hash = expected.partition("::")
        assert sep == "::", (
            f"KB snapshot {_KB_SNAPSHOT_PATH} is malformed; expected "
            f"`<version>::<hash>` on a single line, got {expected!r}"
        )

        if actual_hash == expected_hash:
            # Content unchanged — version MUST match too. Otherwise
            # someone bumped the version unnecessarily (cache churn).
            assert KB_VERSION == expected_version, (
                f"KB content unchanged but KB_VERSION drifted "
                f"{expected_version!r} -> {KB_VERSION!r}. Either revert "
                f"the version bump in app/data/kb.py, or — if the bump "
                f"is intentional — update the snapshot at "
                f"{_KB_SNAPSHOT_PATH} to:\n  {KB_VERSION}::{actual_hash}"
            )
            return

        # Content changed — version MUST bump.
        assert KB_VERSION != expected_version, (
            f"EC_CHECKER_OBLIGATION_MAP content changed (hash "
            f"{expected_hash[:8]} -> {actual_hash[:8]}) but KB_VERSION "
            f"is still {KB_VERSION!r}. Bump KB_VERSION in app/data/kb.py "
            f"(downstream cache + Neo4j seed both key on it) and update "
            f"{_KB_SNAPSHOT_PATH} to:\n  <new_version>::{actual_hash}"
        )

        # Version DID bump but the snapshot is stale (it still records
        # the old version + old hash). Tell the contributor to update.
        raise AssertionError(
            f"KB content + KB_VERSION both changed but snapshot is "
            f"stale. Update {_KB_SNAPSHOT_PATH} to:\n"
            f"  {KB_VERSION}::{actual_hash}"
        )

    def test_kb_version_format(self) -> None:
        """``KB_VERSION`` must look like ``<year>.<regulation_id>.v<build>``.

        Pinning the format prevents accidental drift (e.g. someone
        writing ``"v4"`` or ``"2026-05-19"`` and silently breaking the
        downstream cache-key arithmetic).
        """
        assert re.match(r"^\d{4}\.\d+\.v\d+$", KB_VERSION), (
            f"KB_VERSION must match `<YYYY>.<reg_id>.v<build>` "
            f"(e.g. `2024.1689.v3`); got {KB_VERSION!r}"
        )


# ── R70 — Digital Omnibus Annex III deferral phase ────────────────────
#
# The Digital Omnibus political agreement (7 May 2026) defers the
# Annex III high-risk obligations from 2 Aug 2026 to 2 Dec 2027. The
# rest of the codebase already tracked this date (kb.py Art. 113,
# official_eu_ai_act.OFFICIAL_UPDATES), but PHASE_REGISTRY shipped
# ``phase_2026_08_02`` with ``superseded_by=None`` while its Annex I
# sibling ``phase_2027_08_02`` was correctly wired to its own deferral.
# R70 closes the gap so date-shaped queries resolve consistently.


class TestR70OmnibusAnnexIIIDeferral:
    """The Annex III high-risk deferral phase must mirror the Annex I one."""

    def test_omnibus_annex_iii_phase_exists(self) -> None:
        assert "phase_omnibus_2027_12_02" in PHASE_REGISTRY

    def test_omnibus_annex_iii_phase_effective_date(self) -> None:
        d = PHASE_REGISTRY["phase_omnibus_2027_12_02"].effective_date
        assert (d.year, d.month, d.day) == (2027, 12, 2)

    def test_omnibus_annex_iii_phase_covers_annex_iii(self) -> None:
        phase = PHASE_REGISTRY["phase_omnibus_2027_12_02"]
        assert "Annex III" in phase.articles
        assert "Art. 6" in phase.articles

    def test_original_annex_iii_phase_points_at_deferral(self) -> None:
        """``phase_2026_08_02`` must be superseded by the Omnibus phase —
        the gap the rest of the codebase already worked around."""
        original = PHASE_REGISTRY["phase_2026_08_02"]
        assert original.superseded_by == "phase_omnibus_2027_12_02"

    def test_omnibus_annex_iii_phase_labelled_omnibus(self) -> None:
        phase = PHASE_REGISTRY["phase_omnibus_2027_12_02"]
        assert "Omnibus" in phase.label or "Omnibus" in phase.description
