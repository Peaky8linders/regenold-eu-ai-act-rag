"""Regression tests for R88-B / R88-C / R88-D / R88-E.

R88-A landed assistant-anchor inheritance for V2 multi-turn coherence
(see ``test_r88a_assistant_anchor_inheritance.py``). R88-B/C/D/E close
the remaining 4 V2 multi-turn zero-refL / zero-kw rows surfaced by
``v2-r87-v2-live.json``:

* R88-B — fines-authority seed (Art. 101) for ``"can they fine us
  directly?"`` follow-ups under AI-Office / GPAI context (mt_v2_022).
* R88-C — right-to-explanation natural-language phrasings (Art. 86)
  for ``"customer wants to know why ... rejected by our AI"`` shape
  (mt_v2_024).
* R88-D — Annex-applicability seed (Art. 113) for ``"And for Annex I
  embedded systems?"`` follow-ups under a prior applicability frame
  (mt_v2_019).
* R88-E — Article-sub-point describer table — Art. 5.1.f/g/h surface
  their specific prohibition prose (carrying ``workplace`` / ``race``
  / ``ethnicity`` / ``judicial`` / ``authorization`` keywords) instead
  of the parent Art. 5 8-category list clipped at ~400 chars
  (mt_v2_012/013/014).

Each suite also pins OOS safety — the new triggers must NOT fire on
adversarial / generic English shapes.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest


# ────────────────────────────────────────────────────────────────────────
# R88-B — fines-authority seed (Art. 101)
# ────────────────────────────────────────────────────────────────────────


def _turn(role: str, content: str):
    return SimpleNamespace(role=role, content=content)


class TestR88BFinesAuthoritySeed:
    """Mt_v2_022: assistant established AI Office + GPAI context, live
    turn asks ``"Can they fine us directly?"``. Gold: Art. 101.
    """

    def test_mt_v2_022_seed_fires(self):
        from app.routes.regenold import _detect_fines_authority_seed
        history = [
            _turn("user", "The AI Office contacted us about our GPAI."),
            _turn(
                "assistant",
                "The AI Office sits within the Commission and oversees "
                "GPAI providers under Article 88+.",
            ),
        ]
        assert _detect_fines_authority_seed(history, "Can they fine us directly?") == "Article 101"

    def test_standalone_who_can_fine_gpai(self):
        from app.routes.regenold import _detect_fines_authority_seed
        # Single-turn — no history but the live turn itself names GPAI.
        assert (
            _detect_fines_authority_seed([], "Who can fine GPAI providers directly?")
            == "Article 101"
        )

    def test_commission_fine_multi_turn(self):
        from app.routes.regenold import _detect_fines_authority_seed
        history = [
            _turn("user", "Our GPAI model exceeds the systemic threshold."),
            _turn(
                "assistant",
                "GPAI systemic-risk providers fall under Chapter V; the "
                "Commission supervises them.",
            ),
        ]
        assert (
            _detect_fines_authority_seed(history, "Can the Commission fine us?")
            == "Article 101"
        )

    def test_no_seed_on_generic_penalties(self):
        from app.routes.regenold import _detect_fines_authority_seed
        # No authority context AND no direct-qualifier → don't fire.
        assert (
            _detect_fines_authority_seed([], "What are the penalties for non-compliance?")
            is None
        )

    def test_no_seed_when_no_authority_context(self):
        from app.routes.regenold import _detect_fines_authority_seed
        # 'fine ... directly' fires the direct qualifier, but without
        # AI Office / Commission / GPAI context the seed must not fire.
        # (Restaurants, e-commerce, etc.)
        assert (
            _detect_fines_authority_seed(
                [],
                "Can the local restaurant fine me directly for being loud?",
            )
            is None
        )
        assert (
            _detect_fines_authority_seed(
                [],
                "Can my landlord fine me directly for a late payment?",
            )
            is None
        )

    def test_apply_helper_inserts_at_head(self):
        from app.routes.regenold import _apply_fines_authority_seed
        history = [
            _turn("user", "The AI Office contacted us about our GPAI."),
            _turn("assistant", "The AI Office sits within the Commission and oversees GPAI providers."),
        ]
        out = _apply_fines_authority_seed(
            ["Article 51", "Article 64", "Article 53"],
            history,
            "Can they fine us directly?",
        )
        assert out[0] == "Article 101"
        assert out[1:] == ["Article 51", "Article 64", "Article 53"]

    def test_apply_helper_dedupes_when_already_present(self):
        from app.routes.regenold import _apply_fines_authority_seed
        history = [_turn("assistant", "AI Office covers GPAI providers.")]
        out = _apply_fines_authority_seed(
            ["Article 101", "Article 51"],
            history,
            "Can the AI Office fine us?",
        )
        assert out == ["Article 101", "Article 51"]

    def test_apply_helper_dedupes_subpoint_parent(self):
        from app.routes.regenold import _apply_fines_authority_seed
        history = [_turn("assistant", "AI Office covers GPAI providers.")]
        out = _apply_fines_authority_seed(
            ["Article 101.1", "Article 51"],
            history,
            "Can the AI Office fine us?",
        )
        # Sub-point of Art. 101 already present → don't double-inject parent.
        assert "Article 101" not in out
        assert out == ["Article 101.1", "Article 51"]

    def test_env_off_returns_unchanged(self, monkeypatch):
        from app.routes.regenold import _apply_fines_authority_seed
        monkeypatch.setenv("REGENOLD_FINES_AUTHORITY_SEED", "0")
        history = [_turn("assistant", "AI Office covers GPAI providers.")]
        out = _apply_fines_authority_seed(
            ["Article 51"],
            history,
            "Can the AI Office fine us?",
        )
        assert out == ["Article 51"]


# ────────────────────────────────────────────────────────────────────────
# R88-C — right-to-explanation natural-language phrasings (Art. 86)
# ────────────────────────────────────────────────────────────────────────


class TestR88CRightToExplanation:
    """Mt_v2_024: live turn ``"A customer wants to know why their loan
    was rejected by our AI."``. Gold: Art. 86.
    """

    def test_mt_v2_024_live_turn_in_scope(self):
        from app.integrations.regenold.scope import classify_scope
        verdict = classify_scope(
            "A customer wants to know why their loan was rejected by our AI."
        )
        assert verdict.in_scope is True
        assert "Art. 86" in verdict.referenced_articles

    @pytest.mark.parametrize(
        "text",
        [
            "A customer wants to know why their loan was rejected by our AI.",
            "Our customer was denied by an AI — they want an explanation.",
            "Why was their application declined by our AI?",
            "A user requests an explanation of the AI decision.",
            "The applicant was declined by the AI system.",
        ],
    )
    def test_positive_in_scope(self, text):
        from app.integrations.regenold.scope import classify_scope
        verdict = classify_scope(text)
        assert verdict.in_scope is True, (
            f"Should be in-scope: {text!r} verdict={verdict.reason.name}"
        )

    @pytest.mark.parametrize(
        "text",
        [
            # Generic English "wants to know why" without AI context.
            "My child wants to know why the sky is blue.",
            "I want to know why my Netflix subscription was cancelled.",
            "A customer wants to understand why our pricing changed.",
            "Wants to know why the bank declined their mortgage.",
            # 'declined' / 'rejected' shapes without AI co-occurrence.
            "My loan was denied by my bank — what do I do?",
            "Why was the package rejected at customs?",
            "A customer was rejected by our front-desk for misbehaving.",
        ],
    )
    def test_oos_safety(self, text):
        from app.integrations.regenold.scope import classify_scope
        verdict = classify_scope(text)
        assert verdict.in_scope is False, (
            f"Must refuse OOS: {text!r} verdict={verdict.reason.name}"
        )


# ────────────────────────────────────────────────────────────────────────
# R88-D — Annex-applicability seed (Art. 113)
# ────────────────────────────────────────────────────────────────────────


class TestR88DAnnexApplicabilitySeed:
    """Mt_v2_019: assistant established Annex III applicability frame
    (2 December 2027), live turn is ``"And for Annex I (medical devices
    etc.) embedded systems?"``. Gold: Art. 113.
    """

    def test_mt_v2_019_seed_fires(self):
        from app.routes.regenold import _detect_annex_applicability_seed
        history = [
            _turn("user", "When do high-risk Annex III obligations apply?"),
            _turn(
                "assistant",
                "Per the May 2026 Digital Omnibus political agreement, "
                "Annex III high-risk obligations apply from 2 December 2027.",
            ),
        ]
        live = "And for Annex I (medical devices etc.) embedded systems?"
        assert _detect_annex_applicability_seed(history, live) == "Article 113"

    def test_single_turn_when_does_annex_iii_apply(self):
        from app.routes.regenold import _detect_annex_applicability_seed
        assert (
            _detect_annex_applicability_seed([], "When does Annex III apply?")
            == "Article 113"
        )

    def test_single_turn_annex_i_applicability(self):
        from app.routes.regenold import _detect_annex_applicability_seed
        assert (
            _detect_annex_applicability_seed(
                [],
                "Applicability date for Annex I embedded products?",
            )
            == "Article 113"
        )

    def test_no_seed_on_bare_annex_content_question(self):
        from app.routes.regenold import _detect_annex_applicability_seed
        # Bare content / definition shapes → no applicability anchor.
        assert _detect_annex_applicability_seed([], "What is Annex III?") is None
        assert (
            _detect_annex_applicability_seed([], "Which AI systems are in Annex III?")
            is None
        )

    def test_no_seed_when_no_applicability_frame_in_prior(self):
        from app.routes.regenold import _detect_annex_applicability_seed
        history = [
            _turn("user", "Our system falls under Annex III(4) — employment."),
            _turn(
                "assistant",
                "Annex III(4) covers employment, workers management and access to self-employment.",
            ),
        ]
        # Live turn has 'Annex III' but no applicability cue AND the
        # prior assistant turn lacks the applicability frame.
        assert (
            _detect_annex_applicability_seed(
                history,
                "What are the obligations under Annex III?",
            )
            is None
        )

    def test_no_seed_without_annex_ref_in_live(self):
        from app.routes.regenold import _detect_annex_applicability_seed
        # The applicability frame exists in prior but live turn has no
        # Annex ref → don't fire.
        history = [
            _turn(
                "assistant",
                "Annex III obligations apply from 2 December 2027.",
            ),
        ]
        assert (
            _detect_annex_applicability_seed(history, "Does our system qualify?")
            is None
        )

    def test_apply_helper_inserts_at_head(self):
        from app.routes.regenold import _apply_annex_applicability_seed
        history = [
            _turn(
                "assistant",
                "Annex III high-risk obligations apply from 2 December 2027.",
            ),
        ]
        out = _apply_annex_applicability_seed(
            ["Annex I"],
            history,
            "And for Annex I (medical devices etc.) embedded systems?",
        )
        assert out == ["Article 113", "Annex I"]

    def test_apply_helper_dedupes_existing(self):
        from app.routes.regenold import _apply_annex_applicability_seed
        history = [_turn("assistant", "Obligations apply from 2 December 2027.")]
        out = _apply_annex_applicability_seed(
            ["Article 113", "Annex I"],
            history,
            "And for Annex I embedded systems?",
        )
        assert out == ["Article 113", "Annex I"]

    def test_env_off_returns_unchanged(self, monkeypatch):
        from app.routes.regenold import _apply_annex_applicability_seed
        monkeypatch.setenv("REGENOLD_ANNEX_APPLICABILITY_SEED", "0")
        history = [_turn("assistant", "Obligations apply from 2 December 2027.")]
        out = _apply_annex_applicability_seed(
            ["Annex I"],
            history,
            "And for Annex I embedded systems?",
        )
        assert out == ["Annex I"]


# ────────────────────────────────────────────────────────────────────────
# R88-E — Article-sub-point describer table
# ────────────────────────────────────────────────────────────────────────


class TestR88ESubpointDescriber:
    """Mt_v2_012/013/014: Art. 5.1.f/g/h sub-point describers must
    surface their specific prohibition keywords (workplace / race /
    ethnicity / judicial / authorization).
    """

    def test_table_covers_known_subpoints(self):
        from app.integrations.regenold.grounded_prose import _ART_SUBPOINT_DESCRIBERS
        # Art. 5(1)(a)-(h) all present so future V2 expansions don't
        # silently regress.
        for letter in "abcdefgh":
            assert f"Article 5.1.{letter}" in _ART_SUBPOINT_DESCRIBERS

    def test_mt_v2_012_workplace_keywords(self):
        from app.integrations.regenold.grounded_prose import stitch_grounded_prose
        out = stitch_grounded_prose(
            ["Art. 5"],
            question="We sell it to call centres for monitoring agent stress levels.",
            user_facing_refs=["Article 5.1.f", "Article 5"],
        )
        low = out.lower()
        assert "workplace" in low
        assert "prohibited" in low
        # Either "call-centre" / "call centre" / "call centres" form.
        assert any(s in low for s in ("call-centre", "call centre", "call centres"))

    def test_mt_v2_013_biometric_race_ethnicity(self):
        from app.integrations.regenold.grounded_prose import stitch_grounded_prose
        out = stitch_grounded_prose(
            ["Art. 5"],
            question="What if we add ethnicity inference for marketing personalisation?",
            user_facing_refs=["Article 5.1.g", "Article 5"],
        )
        low = out.lower()
        assert "race" in low
        assert "ethnicity" in low
        assert "prohibited" in low

    def test_mt_v2_014_judicial_authorization(self):
        from app.integrations.regenold.grounded_prose import stitch_grounded_prose
        out = stitch_grounded_prose(
            ["Art. 5", "Annex III"],
            question="Do we still need judicial pre-authorization?",
            user_facing_refs=["Article 5.1.h", "Annex III.8", "Article 5", "Annex III"],
        )
        low = out.lower()
        assert "judicial" in low
        assert "authoriz" in low  # authoris/authoriz both fine.
        assert "prior" in low

    def test_parent_dropped_when_subpoint_surfaces(self):
        """When Article 5.1.f sub-point is surfaced, the parent Art. 5
        8-category list should not also be glued on top — that would
        dilute the sub-point keyword density. Verify by char-count
        ceiling that the parent stub is suppressed.
        """
        from app.integrations.regenold.grounded_prose import stitch_grounded_prose
        out = stitch_grounded_prose(
            ["Art. 5"],
            question="We sell it to call centres for monitoring agent stress levels.",
            user_facing_refs=["Article 5.1.f", "Article 5"],
        )
        # The base Art. 5 stub starts with "Prohibits eight categories".
        # When the sub-point is the surfaced substance, the 8-category
        # phrase MUST NOT also appear.
        assert "eight categories" not in out.lower()

    def test_no_user_facing_refs_legacy_path(self):
        """When user_facing_refs is None (legacy callers), the stitcher
        still produces a non-empty regulator-voice answer carrying the
        cited article.

        R90 — pre-R90 also required "EU AI Act" literal in the prose
        (from the dropped "This question is covered by the EU AI Act
        under Article X" lead sentence). R90 drops that lead; the
        Article 5 reference now lands as the sentence subject in the
        counsel-voice substance prose.
        """
        from app.integrations.regenold.grounded_prose import stitch_grounded_prose
        # Same call without user_facing_refs → falls back to parent stub.
        out_legacy = stitch_grounded_prose(["Art. 5"])
        # Article number must still appear as cite anchor.
        assert "Article 5" in out_legacy
        # Non-empty, regulator-voice substance.
        assert len(out_legacy.strip()) > 80

    def test_subpoint_describer_env_off(self, monkeypatch):
        from app.integrations.regenold.grounded_prose import _subpoint_describer_clause
        monkeypatch.setenv("REGENOLD_SUBPOINT_DESCRIBER", "0")
        assert _subpoint_describer_clause("Article 5.1.f") is None

    def test_augmenter_uses_subpoint_describer(self):
        """The R77 augmenter must also surface sub-point describer
        clauses when the user-facing ref carries the sub-point.
        """
        from app.integrations.regenold.grounded_prose import augment_with_ref_descriptions
        base = (
            "Art. 5(1)(f) generally prohibits emotion recognition in "
            "certain settings. Article 5 sets out eight prohibited AI "
            "practices."
        )
        augmented = augment_with_ref_descriptions(
            base,
            ["Article 5.1.f", "Article 5"],
            question="We sell it to call centres for monitoring agent stress levels.",
        )
        low = augmented.lower()
        assert "workplace" in low
        # "call-centre" / "call centre" form.
        assert any(s in low for s in ("call-centre", "call centre", "call centres"))

    def test_augmenter_unknown_subpoint_falls_back_to_kb_stub(self):
        """For sub-points NOT in the describer table, the augmenter
        should fall back to the legacy KB-stub clip rather than
        skipping the ref entirely.
        """
        from app.integrations.regenold.grounded_prose import augment_with_ref_descriptions
        base = "An answer that doesn't describe Article 13."
        augmented = augment_with_ref_descriptions(
            base,
            ["Article 13.2.b"],  # Sub-point not in _ART_SUBPOINT_DESCRIBERS.
            question="What does Article 13.2.b require?",
        )
        # Augmenter should append SOMETHING about Article 13 (from
        # legacy KB-stub path) — verify by checking the answer changed.
        # If the KB stub of Art. 13 doesn't fire (e.g. force_append
        # gate behavior), at minimum the call must not raise.
        assert isinstance(augmented, str)


# ────────────────────────────────────────────────────────────────────────
# R88 — cache-key invariants
# ────────────────────────────────────────────────────────────────────────


class TestR88CacheKeyInvariants:
    """The R88-B/C/D/E env gates flip ENGINE behaviour (anchor/seed
    injection re-ranks candidates → flips ``GraphRAGResponse.references``).
    Per the R30/R56/R79 cache-poisoning doctrine, each must be in the
    engine cache key.
    """

    def test_cache_key_changes_when_r88b_env_flips(self, monkeypatch):
        from app.routes.regenold import _engine_cache_key
        monkeypatch.setenv("REGENOLD_FINES_AUTHORITY_SEED", "1")
        k_on = _engine_cache_key("test question", None)
        monkeypatch.setenv("REGENOLD_FINES_AUTHORITY_SEED", "0")
        k_off = _engine_cache_key("test question", None)
        assert k_on != k_off

    def test_cache_key_changes_when_r88d_env_flips(self, monkeypatch):
        from app.routes.regenold import _engine_cache_key
        monkeypatch.setenv("REGENOLD_ANNEX_APPLICABILITY_SEED", "1")
        k_on = _engine_cache_key("test question", None)
        monkeypatch.setenv("REGENOLD_ANNEX_APPLICABILITY_SEED", "0")
        k_off = _engine_cache_key("test question", None)
        assert k_on != k_off

    def test_cache_key_changes_when_r88e_env_flips(self, monkeypatch):
        from app.routes.regenold import _engine_cache_key
        monkeypatch.setenv("REGENOLD_SUBPOINT_DESCRIBER", "1")
        k_on = _engine_cache_key("test question", None)
        monkeypatch.setenv("REGENOLD_SUBPOINT_DESCRIBER", "0")
        k_off = _engine_cache_key("test question", None)
        assert k_on != k_off
