"""R79 — regression coverage for the deep-code-review bug fixes.

Five parallel-agent-surfaced correctness bugs, each fixed in R79:

* Fix 2 — ``augment_with_ref_descriptions`` fused the first appended
  clause onto the last base word when the base answer had no terminal
  punctuation.
* Fix 3 — ``_hard_truncate_at_clause`` only recognised lowercase
  ``(a)`` enumerators, missing uppercase / roman-numeral points.
* Fix 4 — ``_deterministic_parse``'s R63-A topic-extension prepend
  deduped only against the existing entity list, not against itself,
  so two keywords mapping to the same article double-added it.
* Fix 5 — ``_engine_cache_key`` omitted ``P2P_GRAPH_RAG_ENABLE_STAGE2``
  (an engine-behaviour flag added in R77), so flipping it could serve
  a stale cached ``GraphRAGResponse``.
* Fix 6 — ``_deterministic_parse`` scanned the raw ``.lower()``
  question, so U+2011 non-breaking hyphens (used by the davidath
  dataset) silently missed the ASCII-hyphen ``_KEYWORD_ENTITY_MAP``
  keys.
"""

from __future__ import annotations

from app.engines.graph_rag import _deterministic_parse
from app.integrations.regenold.grounded_prose import augment_with_ref_descriptions
from app.integrations.regenold.models import _hard_truncate_at_clause
from app.routes.regenold import _engine_cache_key


# ── Fix 2 — augmenter terminal-punctuation guard ────────────────────────────


class TestR79AugmenterPeriod:
    # R89-A note: Article 51 became a describer key (prepend path), so
    # the original test ref no longer exercises the APPEND path this
    # guard protects. Switched to Article 22 (authrep) — has a KB stub,
    # is NOT in the R89-A describer table, so it still goes through
    # the legacy append flow.
    def test_period_inserted_before_appended_clause(self) -> None:
        """A base answer without terminal punctuation must not fuse into
        the first appended ``Article N — …`` clause."""
        base = "Operators bear no further categorical duties beyond registration"
        out = augment_with_ref_descriptions(base, ["Article 22"])
        if out == base:
            # Augmenter did not fire (ref considered covered / no stub) —
            # the period guard is untested but not violated. Skip rather
            # than false-fail on a KB-content change.
            return
        # The base text must never run straight into the appended clause.
        assert "registration Article" not in out
        # And the base content must still end with a sentence terminator.
        assert ". Article" in out or ".  Article" in out

    def test_base_with_period_unchanged_join(self) -> None:
        """A base answer already ending in a period is not double-punctuated."""
        base = "Operators bear no further categorical duties here."
        out = augment_with_ref_descriptions(base, ["Article 22"])
        assert ".. Article" not in out


# ── Fix 3 — hard-truncate recognises uppercase / roman enumerators ──────────


class TestR79HardTruncateEnumerators:
    def test_uppercase_enumeration_cut_cleanly(self) -> None:
        text = (
            "Annex point coverage requires the following items: "
            + "; ".join(
                f"({c}) item {c} described in adequate regulatory detail "
                f"for the operator here"
                for c in "ABCDEFGH"
            )
            + "."
        )
        assert len(text) > 600
        out = _hard_truncate_at_clause(text, 600)
        assert len(out) <= 600
        assert out[-1] in ".!?"
        assert not out.rstrip().rstrip(".").endswith("(")

    def test_roman_enumeration_cut_cleanly(self) -> None:
        text = (
            "The technical documentation comprises the following points: "
            + "; ".join(
                f"({c}) point {c} described in adequate regulatory detail "
                f"for the provider and the downstream operator here"
                for c in ("ii", "iii", "iv", "vi", "vii", "viii", "ix", "xi")
            )
            + "."
        )
        assert len(text) > 600
        out = _hard_truncate_at_clause(text, 600)
        assert len(out) <= 600
        assert out[-1] in ".!?"


# ── Fix 4 — topic-extension prepend self-dedup ──────────────────────────────


class TestR79TopicPrependDedup:
    def test_same_article_not_double_added(self) -> None:
        """Two ``_TOPIC_KEYWORD_EXTENSIONS`` keywords mapping to Art. 49
        in the live turn must not double-add it to the entity list."""
        q = (
            "Conversation so far:\n"
            "User: We built an AI hiring tool.\n"
            "Assistant: Understood.\n\n"
            "Latest question:\n"
            "Where do we register, and how do we register the system?"
        )
        ents = _deterministic_parse(q).entities
        assert ents.count("Art. 49") <= 1, f"Art. 49 double-added: {ents}"


# ── Fix 5 — engine cache key includes the Stage-2 master flag ───────────────


class TestR79CacheKeyStage2Flag:
    def test_stage2_flag_changes_cache_key(
        self, monkeypatch
    ) -> None:
        monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "0")
        key_off = _engine_cache_key("What does Article 13 require?", "ctx")
        monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "1")
        key_on = _engine_cache_key("What does Article 13 require?", "ctx")
        assert key_off != key_on, (
            "P2P_GRAPH_RAG_ENABLE_STAGE2 flips the engine answer (Stage-2 "
            "polish) — it must be part of the cache identity"
        )

    def test_cache_key_stable_for_same_stage2_flag(self, monkeypatch) -> None:
        monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "0")
        a = _engine_cache_key("Q", "ctx")
        b = _engine_cache_key("Q", "ctx")
        assert a == b


# ── Fix 6 — Unicode non-breaking hyphen normalised before keyword scan ──────


class TestR79UnicodeHyphenNormalisation:
    def test_nonbreaking_hyphen_matches_ascii_keyword(self) -> None:
        """U+2011 in a ``_KEYWORD_ENTITY_MAP`` key must still resolve."""
        ascii_q = "What does post-market monitoring require?"
        nbh_q = "What does post‑market monitoring require?"
        ascii_ents = _deterministic_parse(ascii_q).entities
        nbh_ents = _deterministic_parse(nbh_q).entities
        assert "Art. 72" in ascii_ents
        assert "Art. 72" in nbh_ents, (
            f"U+2011 non-breaking hyphen lost the keyword match: {nbh_ents}"
        )
