"""R332 — the dynamic A/B harness, and the one property it exists for.

The load-bearing test here is `TestFireCheck`: this harness replaces davidath
precisely because a flat result and a dead feature look identical, and every
inert A/B in this repo's history (R326 vector recall, R327 semantic layers,
three R329 reranker placements) reported a clean +0.0000 while the feature never
executed. If the fire check can be fooled, the harness is worth nothing.
"""
from __future__ import annotations

from evals.harness import dynamic_ab as D


def _row(rid: str, answer: str, refs: list[str], **scores):
    base = {
        "ref_loose": 0.5, "ref_strict": 0.5, "ref_conc": 0.5, "kw_recall": 0.5,
        "gold_dropped_head": 0.0, "gold_dropped_exact": 0.0,
        "answer_chars": float(len(answer)), "n_refs": float(len(refs)),
    }
    base.update(scores)
    return {"id": rid, "source": "s", "pred_answer": answer,
            "pred_refs": refs, "error": None, "scores": base}


class TestFireCheck:
    def test_identical_arms_do_not_fire(self):
        """The inert signature: byte-identical arms."""
        a = [_row("1", "x", ["Article 5"]), _row("2", "y", ["Article 6"])]
        b = [_row("1", "x", ["Article 5"]), _row("2", "y", ["Article 6"])]
        f = D.fire_check(a, b)
        assert f["fired"] is False
        assert f["any_changed"] == 0

    def test_a_changed_reference_list_fires(self):
        a = [_row("1", "x", ["Article 5"])]
        b = [_row("1", "x", ["Article 6"])]
        assert D.fire_check(a, b)["fired"] is True

    def test_a_changed_answer_fires_even_with_identical_refs(self):
        """Prompt-only changes move prose, not citations — must still count."""
        a = [_row("1", "old prose", ["Article 5"])]
        b = [_row("1", "new prose", ["Article 5"])]
        f = D.fire_check(a, b)
        assert f["fired"] is True
        assert f["answers_changed"] == 1 and f["refs_changed"] == 0

    def test_reordering_refs_counts_as_a_change(self):
        """A reranker's whole job is order — order must not read as identical."""
        a = [_row("1", "x", ["Article 5", "Article 6"])]
        b = [_row("1", "x", ["Article 6", "Article 5"])]
        assert D.fire_check(a, b)["fired"] is True


class TestVerdicts:
    def test_ci_excluding_zero_above_is_a_win(self):
        assert D._verdict(0.05, 0.01, 0.09, null_band=0.01) == "WIN"

    def test_ci_excluding_zero_below_is_a_loss(self):
        assert D._verdict(-0.05, -0.09, -0.01, null_band=0.01) == "LOSS"

    def test_tight_ci_around_zero_is_a_real_null(self):
        assert D._verdict(0.0005, -0.004, 0.005, null_band=0.01) == "NULL"

    def test_wide_ci_around_zero_is_underpowered_not_null(self):
        """The R331 retrieval result: 0.003 on 9 rows is NOT evidence of null."""
        assert D._verdict(0.003, -0.25, 0.26, null_band=0.01) == "UNDERPOWERED"


class TestGoldVeto:
    def test_gold_drop_is_surfaced_as_a_delta(self):
        a = [_row("1", "x", ["Article 5"], gold_dropped_head=0.0)]
        b = [_row("1", "z", ["Article 9"], gold_dropped_head=1.0)]
        res = D._analyse(a, b, null_band=0.01)
        assert res["gold"]["gold_dropped_head"]["delta"] == 1.0

    def test_no_gold_drop_reads_zero(self):
        a = [_row("1", "x", ["Article 5"])]
        b = [_row("1", "z", ["Article 5"])]
        res = D._analyse(a, b, null_band=0.01)
        assert res["gold"]["gold_dropped_head"]["delta"] == 0.0


class TestStratification:
    def test_sample_spans_sources_rather_than_taking_a_head_slice(self):
        """`probe_set` is ordered by source, so [:n] drops whole sources.

        Earlier runs called that "stratified"; it was a head slice covering one
        category apiece. This asserts the real thing.
        """
        probe = D.load_probe_set()
        sources = {r.source for r in probe}
        if len(sources) < 2:
            return
        sample = D._stratified(probe, 12, seed=1)
        assert len({r.source for r in sample}) >= min(len(sources), 3)
        head = probe[:12]
        assert len({r.source for r in sample}) >= len({r.source for r in head})


class TestReportRefusesInertNumbers:
    def test_inert_result_prints_no_axis_table(self):
        lines: list[str] = []
        D._report({"label": "x", "verdict": "INERT", "fire": {}}, emit=lines.append)
        assert lines == [], "an INERT run must not print an axis table"
