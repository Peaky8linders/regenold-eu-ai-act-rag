"""R313 — bounded faithfulness verification over the Stage-2 answer.

Every test that names a failure uses the VERBATIM shape from the R312 grounded
judge's own ``failure_mode`` strings, not a paraphrase. R305 shipped a detector
that returned ``False`` on its own target question because its test asserted on
a TRUNCATED copy of that question; asserting on the real shapes is how that
class of green-test-broken-production is avoided.
"""

from __future__ import annotations

import pytest

from app.engines import faithfulness_verify as fv


# ── Env gate ─────────────────────────────────────────────────────────────────

class TestEnvGate:
    def test_default_is_off(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_ANSWER_VERIFY", raising=False)
        assert fv.faithfulness_verify_enabled() is False

    @pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on", " On "])
    def test_truthy_values_enable(self, monkeypatch, val):
        monkeypatch.setenv("REGENOLD_ANSWER_VERIFY", val)
        assert fv.faithfulness_verify_enabled() is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", ""])
    def test_falsy_values_disable(self, monkeypatch, val):
        monkeypatch.setenv("REGENOLD_ANSWER_VERIFY", val)
        assert fv.faithfulness_verify_enabled() is False

    def test_disabled_returns_answer_untouched(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_ANSWER_VERIFY", raising=False)
        ans = "Article 6(3) derogates from the Annex III classification."
        out, action = fv.verify_and_repair(ans, "q")
        assert out == ans
        assert action == "disabled"

    def test_budget_knobs_clamp_and_fall_back(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_VERIFY_MAX_REFS", "99")
        assert fv._max_refs() == 12
        monkeypatch.setenv("REGENOLD_VERIFY_MAX_REFS", "not-a-number")
        assert fv._max_refs() == fv._DEFAULT_MAX_REFS
        monkeypatch.setenv("REGENOLD_VERIFY_REF_CHARS", "10")
        assert fv._ref_chars() == 200
        monkeypatch.setenv("REGENOLD_VERIFY_REF_CHARS", "")
        assert fv._ref_chars() == fv._DEFAULT_REF_CHARS


# ── Citation extraction ──────────────────────────────────────────────────────

class TestExtractCitedRefs:
    def test_plain_article(self):
        assert fv.extract_cited_refs("Under Article 16 the provider must act.") == ["Art. 16"]

    def test_paragraph_and_point(self):
        assert fv.extract_cited_refs("Article 6(3)") == ["Art. 6(3)"]
        assert fv.extract_cited_refs("Article 5(1)(b)") == ["Art. 5(1)(b)"]

    def test_dotted_wire_form(self):
        assert fv.extract_cited_refs("Article 50.3 applies.") == ["Art. 50(3)"]

    def test_abbreviated_forms(self):
        assert fv.extract_cited_refs("art. 6 and Arts. 9") == ["Art. 6", "Art. 9"]

    def test_annex_with_subpoints(self):
        assert fv.extract_cited_refs("Annex III(1)(c)") == ["Annex III(1)(c)"]

    def test_plural_enumeration_captures_every_member(self):
        """The singular pass captures only the head of "Articles 9, 10 and 15"."""
        refs = fv.extract_cited_refs("Under Articles 9, 10 and 15 the provider must act.")
        assert set(refs) == {"Art. 9", "Art. 10", "Art. 15"}

    def test_annex_enumeration_does_not_invent_annex_d_from_and(self):
        """A case-insensitive roman scan matches the 'd' in 'and'."""
        refs = fv.extract_cited_refs("See Annexes IV and V.")
        assert set(refs) == {"Annex IV", "Annex V"}
        assert "Annex D" not in refs

    def test_word_boundary_does_not_match_part(self):
        assert fv.extract_cited_refs("A part 6 of the system") == []

    def test_parent_and_leaf_both_retained(self):
        """Two distinct claims are made, so both need checking."""
        refs = fv.extract_cited_refs(
            "Article 6 classifies Annex III systems, and Article 6(3) derogates."
        )
        assert set(refs) == {"Art. 6", "Art. 6(3)", "Annex III"}

    def test_empty_and_none_safe(self):
        assert fv.extract_cited_refs("") == []
        assert fv.extract_cited_refs(None) == []  # type: ignore[arg-type]

    def test_order_preserved_and_deduped(self):
        refs = fv.extract_cited_refs("Article 13, then Article 6, then Article 13 again.")
        assert refs == ["Art. 13", "Art. 6"]


# ── Ground truth ─────────────────────────────────────────────────────────────

class TestBuildGroundTruth:
    def test_resolves_verbatim_article_text(self):
        gt = dict(fv.build_ground_truth(["Art. 16"]))
        assert "Art. 16" in gt
        assert len(gt["Art. 16"]) > 50

    def test_sub_provisions_resolve_distinctly(self):
        """tp_v4_012: Article 6(3) credited with Article 6(4)'s duty."""
        gt = dict(fv.build_ground_truth(["Art. 6(3)", "Art. 6(4)"]))
        assert gt["Art. 6(3)"] != gt["Art. 6(4)"]
        assert "derogation" in gt["Art. 6(3)"].lower()
        assert "document" in gt["Art. 6(4)"].lower()

    def test_siblings_are_supplied_so_a_claim_can_be_reattributed(self):
        """Shown only 6(3), a verifier can delete but cannot re-point."""
        refs = [r for r, _ in fv.build_ground_truth(["Art. 6(3)"])]
        assert "Art. 6(3)" in refs
        assert "Art. 6(4)" in refs

    def test_unresolvable_ref_is_skipped_not_raised(self):
        assert fv.build_ground_truth(["Art. 999"]) == []

    def test_respects_max_refs_budget(self):
        gt = fv.build_ground_truth(
            ["Art. 9", "Art. 10", "Art. 11", "Art. 12"], max_refs=2
        )
        assert len(gt) == 2

    def test_respects_char_budget(self):
        gt = fv.build_ground_truth(["Art. 6"], ref_chars=200)
        assert all(len(body) <= 200 for _, body in gt)


# ── Safety gates — the pass may only subtract or re-attribute ────────────────

class TestAcceptanceGates:
    ORIG = (
        "Article 6(3) requires the provider to document its assessment before "
        "placing the system on the market, and Annex III lists the high-risk areas."
    )

    def test_accepts_a_faithful_repair(self):
        cand = (
            "Article 6(4) requires the provider to document its assessment before "
            "placing the system on the market, and Annex III lists the high-risk areas."
        )
        ok, reason = fv._accept(self.ORIG, cand)
        assert ok, reason

    def test_rejects_empty(self):
        assert fv._accept(self.ORIG, "") == (False, "empty")
        assert fv._accept(self.ORIG, "   ") == (False, "empty")

    def test_rejects_collapse_to_a_stub(self):
        ok, reason = fv._accept(self.ORIG, "Article 6 applies.")
        assert not ok
        assert reason in ("too_short_abs", "too_short_ratio")

    def test_rejects_an_added_citation(self):
        """legal_v2 scores governing/(governing+supporting+wrong): an added
        supporting ref is an arithmetic loss even when the prose is true."""
        cand = self.ORIG + " Article 99 sets the penalties."
        assert fv._accept(self.ORIG, cand) == (False, "citation_added")

    def test_allows_reattribution_to_a_sibling_of_a_cited_article(self):
        """Art. 6(3) -> Art. 6(4) is the repair we explicitly ask for."""
        cand = self.ORIG.replace("Article 6(3)", "Article 6(4)")
        ok, _ = fv._accept(self.ORIG, cand)
        assert ok

    def test_rejects_a_new_article_even_when_it_looks_like_a_correction(self):
        cand = self.ORIG.replace("Article 6(3)", "Article 43(1)")
        assert fv._accept(self.ORIG, cand) == (False, "citation_added")

    def test_rejects_stripping_every_citation(self):
        cand = (
            "The provider must document its assessment before placing the system "
            "on the market, and the high-risk areas are listed in the annex."
        )
        assert fv._accept(self.ORIG, cand) == (False, "citations_stripped")

    @pytest.mark.parametrize(
        "lead",
        [
            "Corrected answer: Article 6(4) requires documentation before market placement and Annex III lists high-risk areas.",
            "I have corrected the misattribution. Article 6(4) requires documentation and Annex III lists the areas covered.",
            "Here is the corrected text: Article 6(4) requires documentation before market placement, Annex III lists areas.",
            "No corrections were needed. Article 6(3) requires documentation before market placement and Annex III applies.",
        ],
    )
    def test_rejects_meta_commentary_leaks(self, lead):
        ok, reason = fv._accept(self.ORIG, lead)
        assert not ok
        assert reason == "meta_leak"

    def test_does_not_false_positive_on_legitimate_deep_prose(self):
        """'unchanged' / 'verification' are legitimate compliance vocabulary."""
        cand = (
            "Article 6(3) requires the provider to document its assessment before "
            "placing the system on the market. Annex III lists the high-risk areas, "
            "and that classification remains unchanged pending verification."
        )
        ok, _ = fv._accept(self.ORIG, cand)
        assert ok


# ── End-to-end behaviour with an injected provider ───────────────────────────

class TestVerifyAndRepair:
    ANS = (
        "Article 6(3) requires the provider to document its assessment before "
        "placing the system on the market, and Annex III lists the high-risk areas."
    )

    @pytest.fixture(autouse=True)
    def _on(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_ANSWER_VERIFY", "1")

    def test_no_citations_short_circuits_without_a_call(self):
        called = []

        def _fn(**kwargs):
            called.append(kwargs)
            return "x"

        out, action = fv.verify_and_repair("No provisions here at all.", "q", complete_fn=_fn)
        assert action == "no_citations"
        assert called == []

    def test_unresolvable_citations_short_circuit(self):
        called = []

        def _fn(**kwargs):
            called.append(kwargs)
            return "x"

        out, action = fv.verify_and_repair("Article 999 applies.", "q", complete_fn=_fn)
        assert action == "no_ground_truth"
        assert called == []

    def test_provider_failure_keeps_the_original(self):
        out, action = fv.verify_and_repair(self.ANS, "q", complete_fn=lambda **k: None)
        assert out == self.ANS
        assert action == "call_failed"

    def test_provider_exception_keeps_the_original(self):
        def _boom(**kwargs):
            raise RuntimeError("wrapper down")

        out, action = fv.verify_and_repair(self.ANS, "q", complete_fn=_boom)
        assert out == self.ANS
        assert action == "error"

    def test_identical_output_reports_unchanged(self):
        out, action = fv.verify_and_repair(self.ANS, "q", complete_fn=lambda **k: self.ANS)
        assert out == self.ANS
        assert action == "unchanged"

    def test_whitespace_only_difference_is_unchanged(self):
        noisy = "  " + self.ANS.replace(" and ", "  and  ") + "  "
        out, action = fv.verify_and_repair(self.ANS, "q", complete_fn=lambda **k: noisy)
        assert action == "unchanged"
        assert out == self.ANS

    def test_repairs_the_r312_tp_v4_012_misattribution(self):
        """Article 6(3) credited with the duty that belongs to Article 6(4)."""
        fixed = self.ANS.replace("Article 6(3)", "Article 6(4)")
        out, action = fv.verify_and_repair(self.ANS, "q", complete_fn=lambda **k: fixed)
        assert action == "repaired"
        assert out == fixed

    def test_rejected_repair_keeps_the_original(self):
        bad = self.ANS + " Article 99 sets the penalties."
        out, action = fv.verify_and_repair(self.ANS, "q", complete_fn=lambda **k: bad)
        assert out == self.ANS
        assert action == "rejected:citation_added"

    def test_the_verifier_sees_the_sibling_ground_truth(self):
        seen = {}

        def _fn(**kwargs):
            seen.update(kwargs)
            return self.ANS

        fv.verify_and_repair(self.ANS, "Is it high-risk?", complete_fn=_fn)
        user = seen["user"]
        assert "Art. 6(3)" in user
        assert "Art. 6(4)" in user, "sibling text is what makes re-attribution possible"
        assert "Is it high-risk?" in user
        assert self.ANS in user

    def test_runs_off_the_stage2_answer_model_not_the_opus_answer_tier(self):
        """stage_name must not contain "stage 2" or the wrapper routes it to
        the Opus answer tier with a thinking budget — a text-vs-text check does
        not need either, and latency is a scored axis."""
        seen = {}

        def _fn(**kwargs):
            seen.update(kwargs)
            return self.ANS

        fv.verify_and_repair(self.ANS, "q", complete_fn=_fn)
        assert "stage 2" not in seen["stage_name"].lower()
        assert seen["temperature"] == 0.0


# ── Engine wiring ────────────────────────────────────────────────────────────

class TestEngineWiring:
    def test_stage2_complete_helper_exists_and_is_fail_soft(self, monkeypatch):
        from app.engines import _graph_rag_impl as impl

        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "gemini")
        monkeypatch.setattr(
            "app.llm.openai_wrapper_provider.is_gemini_provider_enabled",
            lambda: False,
        )
        assert impl._stage2_complete(system="s", user="u", max_tokens=64) is None

    def test_default_off_leaves_the_engine_path_inert(self, monkeypatch):
        """davidath byte-identical BY CONSTRUCTION: gate off ⇒ no call, no edit."""
        monkeypatch.delenv("REGENOLD_ANSWER_VERIFY", raising=False)
        called = []
        monkeypatch.setattr(
            fv, "verify_and_repair",
            lambda *a, **k: (called.append(1), ("x", "repaired"))[1],
        )
        ans = "Article 6 applies."
        out, action = fv.verify_and_repair(ans, "q") if fv.faithfulness_verify_enabled() else (ans, "disabled")
        assert out == ans
        assert called == []

    def test_cache_key_registers_the_r313_flags(self):
        """R263.2 — an omitted flag makes the two-arm A/B measure nothing."""
        import inspect

        from app.routes import regenold

        src = inspect.getsource(regenold._engine_cache_key)
        for var in (
            "REGENOLD_ANSWER_VERIFY",
            "REGENOLD_VERIFY_MAX_REFS",
            "REGENOLD_VERIFY_REF_CHARS",
        ):
            assert var in src, f"{var} missing from _engine_cache_key"

    def test_cache_key_actually_differs_across_arms(self, monkeypatch):
        from app.routes import regenold

        monkeypatch.delenv("REGENOLD_ANSWER_VERIFY", raising=False)
        off = regenold._engine_cache_key("q", None)
        monkeypatch.setenv("REGENOLD_ANSWER_VERIFY", "1")
        on = regenold._engine_cache_key("q", None)
        assert off != on
