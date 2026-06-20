"""R136 — reference-conciseness + degenerate-fallback regression tests.

Two byte-identical (davidath-neutral) wire fixes driven by the R136 live
Antifragile-20 re-measurement:

1. ``_surface_prose_subpoints`` over-citation guard — when the polished prose
   names >=3 distinct sub-points of the SAME parent (a "describe the whole
   article" pattern, e.g. a "what is high-risk" answer enumerating
   Article 6(1)/(2)/(3)), the parent article is the minimal cover; surfacing
   every sub-point alongside it over-cites against the competition's
   minimal-reference rule. Live antifragile q03 shipped
   ``Article 6 + 6.1 + 6.2 + 6.3`` where the gold (even at sub-point
   granularity) is ``Article 6`` alone. Targeted 1-2 sub-point clauses
   (the R133 precision win) are preserved.

2. ``normalise_answer_for_regenold`` degenerate fallback — when every
   sentence is scrubbed away, the old fallback shipped a refusal-shaped
   "Please refer to the referenced articles for the detailed compliance
   requirements" deflection ALONGSIDE a non-empty references list (the
   cite-but-don't-describe failure mode the project eliminated in
   R49-A / R81-H / R109). It now prefers the cleaned pre-pass text and
   never ships that deflection.
"""
from __future__ import annotations

from app.integrations.regenold.models import normalise_answer_for_regenold
from app.routes.regenold import _surface_prose_subpoints


class TestR136SubpointOverCitationGuard:
    def test_three_subpoints_of_one_parent_collapse_to_parent(self):
        # q03-shape: prose describes Article 6's two routes + carve-out.
        answer = (
            "High-risk classification under Article 6 has two routes: "
            "Article 6(1) for Annex I product-safety components and "
            "Article 6(2) for the Annex III use cases, with carve-outs "
            "under Article 6(3)."
        )
        refs = ["Article 6", "Annex I", "Annex III"]
        out = _surface_prose_subpoints(answer, refs)
        assert out == ["Article 6", "Annex I", "Annex III"]
        # No sub-point of Article 6 was surfaced (parent is the minimal cover).
        assert not any(r.startswith("Article 6.") for r in out)

    def test_two_subpoints_are_preserved(self):
        # Distinct-duty split — the R133 precision win must NOT regress.
        answer = (
            "Article 50(1) is a provider duty to disclose AI interaction; "
            "Article 50(3) is a deployer duty toward exposed persons."
        )
        out = _surface_prose_subpoints(answer, ["Article 50"])
        assert "Article 50.1" in out
        assert "Article 50.3" in out
        assert "Article 50" in out

    def test_single_subpoint_is_preserved(self):
        answer = "Under Article 3(1) an AI system is a machine-based system."
        out = _surface_prose_subpoints(answer, ["Article 3"])
        assert out == ["Article 3", "Article 3.1"]

    def test_two_parents_each_below_threshold_not_collapsed(self):
        # Two parents, two sub-points each (< 3 each) -> the guard does not
        # collapse either; the R133 total-add cap (3) still applies, so at
        # least the first parent's sub-points survive.
        answer = (
            "Article 50(1) and Article 50(2) are provider duties; "
            "Annex IV(2) lists the technical documentation."
        )
        out = _surface_prose_subpoints(answer, ["Article 50", "Annex IV"])
        assert "Article 50.1" in out and "Article 50.2" in out
        # Guard did NOT collapse Article 50 (it had only 2 sub-points).
        assert "Article 50" in out

    def test_no_subpoints_named_is_passthrough(self):
        refs = ["Article 5", "Annex III"]
        assert _surface_prose_subpoints("Article 5 prohibits eight practices.", refs) == refs


class TestR136DegenerateFallback:
    def test_degenerate_input_never_ships_refer_deflection(self):
        # Across a spread of degenerate inputs, the old refusal-shaped
        # deflection must NEVER appear (it is removed from the code). An
        # empty return is acceptable — the route treats empty normalise
        # output via its no-match / consistency-guard paths.
        for bad in ("...", "…", "....", "(...)", "…)"):
            out = normalise_answer_for_regenold(bad, question="anything")
            assert "Please refer to the referenced articles" not in out
            assert "detailed compliance requirements applicable to this system" not in out

    def test_clipped_fragment_fallback_prefers_content_over_deflection(self):
        # A sub-40-char clipped fragment with real content reaches the
        # R136 degenerate fallback; it must keep the content, never the
        # deflection, and never be empty.
        out = normalise_answer_for_regenold("Article 5 prohibits", question="x")
        assert "Please refer to the referenced articles" not in out
        assert "Article 5" in out or out == ""

    def test_normal_answer_unaffected(self):
        ans = "Article 5 prohibits eight practices, including social scoring."
        out = normalise_answer_for_regenold(ans, question="What is prohibited?")
        assert "Article 5" in out
        assert "Please refer to the referenced articles" not in out
