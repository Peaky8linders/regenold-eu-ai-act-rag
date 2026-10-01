"""R451 — BM25F contextual-field weights, and the sweep that tunes them.

R449 shipped the fielded BM25 path with four constants picked by argument
(``title=2.0, body=1.0, b_title=0.6, b_body=0.75``) and judged the technique at
that one point. R451 makes the choice measurable and this file pins the parts
that must not drift:

1. **Defaults byte-identical.** Unset env must resolve to exactly the shipped
   constants, or every recorded contextual-fields number is a number about a
   different ranker.
2. **A typo cannot change the evidence.** Non-numeric, empty, NaN and infinite
   values fall back to the shipped default; out-of-range values are CLAMPED to
   the documented bounds (a sweep needs to probe the edges), and the harness grid
   is asserted to sit inside those bounds so no cell silently measures a clamped
   weight it does not name.
3. **The weights are read per score call.** That is what lets one built index
   serve a whole in-process grid; a cached weight would make the sweep report
   "weights do not matter" for every cell.
4. **The sparse control is genuinely un-fielded.** ``_build_index`` is
   ``lru_cache(maxsize=1)`` and the fielded/plain choice is baked in at build
   time, so a control run in a warm process silently scores through the fielded
   index. That confound would make the whole sweep uninterpretable, so it is
   pinned directly.
5. **The paired delta's sign convention.** An earlier revision computed
   ``baseline - cell`` while the callers passed cells first, which inverted every
   verdict while leaving the aggregate columns correct. The two must agree.
6. **The verdict is the pre-registered rule, and the multiplicity diagnostic does
   not rewrite it.** A 17-cell sweep at alpha=0.05 buys a marginal pass by chance;
   that is reported next to the verdict, never instead of it.
"""
from __future__ import annotations

import pytest

from app.data import kb_search as kb
from evals.retrieval import field_weight_sweep as fws

_FIELD_ENVS = (
    "REGENOLD_FIELD_WEIGHT_TITLE",
    "REGENOLD_FIELD_WEIGHT_BODY",
    "REGENOLD_FIELD_B_TITLE",
    "REGENOLD_FIELD_B_BODY",
    "REGENOLD_CONTEXTUAL_FIELDS",
)


@pytest.fixture(autouse=True)
def _clean_field_state(monkeypatch: pytest.MonkeyPatch):
    """Unset the gates and drop the memoised index before AND after each test.

    The index cache is process-global: a test that left a FIELDED index cached
    would make every later test in the session score through the fielded path
    regardless of its own env, which is exactly the confound
    ``test_sparse_control_is_genuinely_un_fielded`` exists to expose.
    """
    for name in _FIELD_ENVS:
        monkeypatch.delenv(name, raising=False)
    kb._build_index.cache_clear()
    yield
    kb._build_index.cache_clear()


# ── Defaults, overrides and the clamp ────────────────────────────────────────


def test_defaults_are_exactly_the_shipped_constants() -> None:
    for field, default in kb._FIELD_WEIGHTS.items():  # noqa: SLF001
        assert kb.field_weight(field) == pytest.approx(default)
    for field, default in kb._FIELD_B.items():  # noqa: SLF001
        assert kb.field_b(field) == pytest.approx(default)


def test_env_override_is_read_per_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """A cached weight would make a whole in-process grid read flat."""
    monkeypatch.setenv("REGENOLD_FIELD_WEIGHT_TITLE", "3.5")
    assert kb.field_weight("title") == pytest.approx(3.5)
    monkeypatch.setenv("REGENOLD_FIELD_WEIGHT_TITLE", "0.25")
    assert kb.field_weight("title") == pytest.approx(0.25)
    monkeypatch.setenv("REGENOLD_FIELD_B_BODY", "0.1")
    assert kb.field_b("body") == pytest.approx(0.1)


@pytest.mark.parametrize("bad", ["", "  ", "abc", "2.0x", "NaN", "inf", "-inf", "nan"])
def test_garbage_and_non_finite_fall_back_to_the_shipped_default(
    monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    monkeypatch.setenv("REGENOLD_FIELD_WEIGHT_TITLE", bad)
    assert kb.field_weight("title") == pytest.approx(2.0)
    monkeypatch.setenv("REGENOLD_FIELD_B_TITLE", bad)
    assert kb.field_b("title") == pytest.approx(0.6)


def test_out_of_range_values_are_clamped_to_the_documented_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sweep needs the edges; the edges are the bounds, not a rejection."""
    w_lo, w_hi = kb._FIELD_WEIGHT_BOUNDS  # noqa: SLF001
    b_lo, b_hi = kb._FIELD_B_BOUNDS  # noqa: SLF001

    monkeypatch.setenv("REGENOLD_FIELD_WEIGHT_TITLE", "-4")
    assert kb.field_weight("title") == pytest.approx(w_lo)
    monkeypatch.setenv("REGENOLD_FIELD_WEIGHT_TITLE", "99")
    assert kb.field_weight("title") == pytest.approx(w_hi)
    monkeypatch.setenv("REGENOLD_FIELD_B_BODY", "-1")
    assert kb.field_b("body") == pytest.approx(b_lo)
    monkeypatch.setenv("REGENOLD_FIELD_B_BODY", "5")
    assert kb.field_b("body") == pytest.approx(b_hi)


def test_weight_zero_is_unrepresentable_which_is_why_the_grid_stops_at_0_1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mechanism behind the grid's low extreme.

    A cell labelled ``w0`` would print a weight production never used, because
    the clamp floors it. This pins the clamp so the grid cannot regress to 0.0.
    """
    lo, hi = kb._FIELD_WEIGHT_BOUNDS  # noqa: SLF001
    assert lo > 0.0
    monkeypatch.setenv("REGENOLD_FIELD_WEIGHT_TITLE", "0")
    assert kb.field_weight("title") == pytest.approx(lo)
    assert fws.TITLE_WEIGHTS[0] == pytest.approx(lo)
    assert min(fws.TITLE_WEIGHTS) >= lo and max(fws.TITLE_WEIGHTS) <= hi


# ── Production <-> harness parity ────────────────────────────────────────────


def test_harness_env_names_and_bounds_match_production() -> None:
    shipped = next(c for c in fws.build_grid() if c.label == "shipped")
    assert set(shipped.env()) == {
        kb._FIELD_WEIGHT_ENVS["title"],  # noqa: SLF001
        kb._FIELD_WEIGHT_ENVS["body"],  # noqa: SLF001
        kb._FIELD_B_ENVS["title"],  # noqa: SLF001
        kb._FIELD_B_ENVS["body"],  # noqa: SLF001
    }
    assert tuple(fws._FIELD_WEIGHT_BOUNDS) == tuple(kb._FIELD_WEIGHT_BOUNDS)  # noqa: SLF001
    assert tuple(fws._FIELD_B_BOUNDS) == tuple(kb._FIELD_B_BOUNDS)  # noqa: SLF001


def test_grid_sits_inside_the_production_clamps() -> None:
    """No cell may be silently clamped: the table would name a weight that never ran."""
    fws.assert_grid_representable(fws.build_grid())


def test_grid_assertion_rejects_an_unrepresentable_cell() -> None:
    bad = [fws.Cell(label="oops", w_title=0.0, w_body=1.0, b_title=0.6, b_body=0.75)]
    with pytest.raises(ValueError, match="clamped by production"):
        fws.assert_grid_representable(bad)


def test_grid_keeps_exactly_one_shipped_cell_with_the_shipped_values() -> None:
    """The shipped label is the paired baseline; a family overwriting it breaks every delta."""
    grid = fws.build_grid()
    shipped = [c for c in grid if c.label == "shipped"]
    assert len(shipped) == 1
    assert grid[0] is shipped[0], "shipped must sort first for a readable table"
    for field, value in fws.SHIPPED.items():
        assert getattr(shipped[0], field) == pytest.approx(value)
    # No family label may impersonate the shipped parameter tuple.
    for cell in grid:
        if cell.label != "shipped":
            assert (
                cell.w_title, cell.w_body, cell.b_title, cell.b_body
            ) != (
                shipped[0].w_title, shipped[0].w_body,
                shipped[0].b_title, shipped[0].b_body,
            ), f"{cell.label} duplicates the shipped cell"


def test_every_family_varies_exactly_one_parameter() -> None:
    """One-factor-at-a-time, or a cell's effect is not attributable."""
    grid = fws.build_grid()
    shipped = next(c for c in grid if c.label == "shipped")
    prefix_to_attr = {"w": "w_title", "bt": "b_title", "bb": "b_body", "bw": "w_body"}
    named = {name for name in prefix_to_attr}
    seen: set[str] = set()
    for cell in grid:
        if cell.label == "shipped":
            continue
        prefix = next(
            (p for p in sorted(named, key=len, reverse=True) if cell.label.startswith(p)),
            None,
        )
        assert prefix is not None, f"unrecognised family: {cell.label}"
        seen.add(prefix)
        changed = [
            name
            for name in ("w_title", "w_body", "b_title", "b_body")
            if getattr(cell, name) != getattr(shipped, name)
        ]
        assert changed == [prefix_to_attr[prefix]], (cell.label, changed)
    assert seen == named, f"a family produced no cells: {named - seen}"


# ── The ranker actually reads them ───────────────────────────────────────────

_QUESTIONS = (
    "Does the technical documentation of a high-risk AI system require to "
    "provide specifications regarding the required hardware?",
    "What obligations apply to distributors of high-risk AI systems?",
    "When does the regulation enter into force?",
    "Is emotion recognition in the workplace prohibited?",
    "What must a provider include in the instructions for use?",
)


def _top8(question: str) -> list[str]:
    return kb.top_articles_by_relevance(question, k=8, min_score=1.0)


def test_the_title_weight_changes_the_ranking(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-vacuity: an inert weight would make the whole R451 grid flat by construction."""
    monkeypatch.setenv("REGENOLD_CONTEXTUAL_FIELDS", "1")
    fws._fresh_index(contextual=True)  # noqa: SLF001
    monkeypatch.setenv("REGENOLD_FIELD_WEIGHT_TITLE", "0.1")
    low = {q: _top8(q) for q in _QUESTIONS}
    monkeypatch.setenv("REGENOLD_FIELD_WEIGHT_TITLE", "5")
    high = {q: _top8(q) for q in _QUESTIONS}
    assert any(low[q] != high[q] for q in _QUESTIONS), "title weight is inert"


def test_the_body_slope_changes_the_ranking(monkeypatch: pytest.MonkeyPatch) -> None:
    """``b_body`` is the family R451 actually found an effect in; it must bite."""
    monkeypatch.setenv("REGENOLD_CONTEXTUAL_FIELDS", "1")
    fws._fresh_index(contextual=True)  # noqa: SLF001
    monkeypatch.setenv("REGENOLD_FIELD_B_BODY", "0.3")
    low = {q: _top8(q) for q in _QUESTIONS}
    monkeypatch.setenv("REGENOLD_FIELD_B_BODY", "0.9")
    high = {q: _top8(q) for q in _QUESTIONS}
    assert any(low[q] != high[q] for q in _QUESTIONS), "body slope is inert"


def test_explicit_shipped_env_is_a_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting the four vars to the shipped values must not move one reference."""
    monkeypatch.setenv("REGENOLD_CONTEXTUAL_FIELDS", "1")
    fws._fresh_index(contextual=True)  # noqa: SLF001
    bare = {q: _top8(q) for q in _QUESTIONS}
    shipped = next(c for c in fws.build_grid() if c.label == "shipped")
    for name, value in shipped.env().items():
        monkeypatch.setenv(name, value)
    assert {q: _top8(q) for q in _QUESTIONS} == bare


def test_sparse_control_is_genuinely_un_fielded(monkeypatch: pytest.MonkeyPatch) -> None:
    """The confound that would make the whole sweep uninterpretable.

    ``_build_index`` memoises and decides fielded-vs-plain AT BUILD TIME, so a
    control that only flips the env var in a warm process would score through the
    fielded index and read exactly like the shipped cell.
    """
    fws._fresh_index(contextual=True)  # noqa: SLF001
    assert kb._build_index().field_freqs, "fielded build must carry per-field counts"  # noqa: SLF001
    fielded = {q: _top8(q) for q in _QUESTIONS}

    fws._fresh_index(contextual=False)  # noqa: SLF001
    assert not kb._build_index().field_freqs, "sparse build must carry no field counts"  # noqa: SLF001
    assert kb._build_index().docs, "sparse build must still be a real index"  # noqa: SLF001
    sparse = {q: _top8(q) for q in _QUESTIONS}
    assert any(sparse[q] != fielded[q] for q in _QUESTIONS), "control equals the fielded arm"


# ── The sweep's arithmetic ───────────────────────────────────────────────────


def _result(
    label: str,
    recall: list[float],
    ndcg: list[float],
    *,
    added_refs: int = 0,
    added_gold: int = 0,
    fielded: bool = True,
) -> fws.CellResult:
    return fws.CellResult(
        label=label,
        w_title=2.0, w_body=1.0, b_title=0.6, b_body=0.75,
        head_recall=sum(recall) / len(recall),
        row_all_heads=0.0,
        ndcg=sum(ndcg) / len(ndcg),
        excess_refs=0.0,
        context_chars=0.0,
        added_refs=added_refs,
        added_gold=added_gold,
        churn_rows=0,
        per_row_recall=list(recall),
        per_row_ndcg=list(ndcg),
        fielded=fielded,
    )


def test_paired_delta_is_positive_when_the_cell_is_better() -> None:
    """Sign convention: positive means the CELL is better than the baseline.

    Regression for the inverted call: the first revision computed
    ``baseline - cell`` and reported a significant LOSS for a cell that was
    measurably better, while the aggregate means (correctly) showed the gain.
    """
    baseline = [0.5] * 40
    cell = [0.75] * 40
    observed, lo, hi = fws.paired_delta_ci(baseline, cell, seed=1)
    assert observed == pytest.approx(0.25)
    assert lo > 0.0 and hi > 0.0

    back, _back_lo, back_hi = fws.paired_delta_ci(cell, baseline, seed=1)
    assert back == pytest.approx(-0.25)
    assert back_hi < 0.0


def test_paired_delta_agrees_with_the_aggregate_columns() -> None:
    """The contradiction that revealed the sign bug must stay impossible."""
    base = _result("base", [0.0, 0.5, 1.0, 0.5], [0.0, 0.4, 0.8, 0.2])
    cell = _result("cell", [0.0, 1.0, 1.0, 0.5], [0.1, 0.9, 0.9, 0.2])
    observed, _lo, _hi = fws.paired_delta_ci(
        base.per_row_recall, cell.per_row_recall, seed=1
    )
    assert observed == pytest.approx(cell.head_recall - base.head_recall)
    observed_n, _lo_n, _hi_n = fws.paired_delta_ci(
        base.per_row_ndcg, cell.per_row_ndcg, seed=1
    )
    assert observed_n == pytest.approx(cell.ndcg - base.ndcg)


def test_verdict_promotes_a_uniform_gain_without_new_churn() -> None:
    base = _result("shipped", [0.5] * 40, [0.4] * 40, added_refs=10, added_gold=2)
    better = _result("better", [0.75] * 40, [0.6] * 40, added_refs=0)
    verdict = fws.verdict_for(better, base, seed=1)
    assert verdict["verdict"] == "PROMOTE"
    assert verdict["churn_ok"] is True


def test_verdict_holds_on_a_significant_loss() -> None:
    base = _result("shipped", [0.5] * 40, [0.4] * 40)
    worse = _result("worse", [0.25] * 40, [0.2] * 40)
    assert fws.verdict_for(worse, base, seed=1)["verdict"] == "HOLD (significant loss)"


def test_verdict_holds_inside_noise() -> None:
    base = _result("shipped", [0.5, 0.0, 1.0, 0.25], [0.4, 0.0, 0.9, 0.2])
    same = _result("same", [0.5, 0.0, 1.0, 0.25], [0.4, 0.0, 0.9, 0.2])
    assert fws.verdict_for(same, base, seed=1)["verdict"] == "HOLD (inside noise)"


def test_verdict_holds_a_gain_that_is_pure_churn() -> None:
    """A recall gain bought by adding non-gold references is not a tuning win."""
    base = _result("shipped", [0.5] * 40, [0.4] * 40, added_refs=10, added_gold=3)
    churn = _result("churn", [0.75] * 40, [0.6] * 40, added_refs=100, added_gold=3)
    verdict = fws.verdict_for(churn, base, seed=1)
    assert verdict["verdict"] == "HOLD (churn)"
    assert verdict["churn_ok"] is False


def test_multiplicity_diagnostic_does_not_rewrite_the_pre_registered_verdict() -> None:
    """A marginal pass is reported as a weak lead, never silently re-labelled.

    The synthetic cell is better on 5 of 110 rows and identical on the rest: its
    95% CI excludes zero but the Bonferroni level for a 17-cell sweep does not.
    """
    base = _result("shipped", [0.0] * 110, [0.0] * 110)
    marginal = _result("marginal", [0.4] * 5 + [0.0] * 105, [0.4] * 5 + [0.0] * 105)
    verdict = fws.verdict_for(marginal, base, seed=20260928, n_comparisons=17)
    assert verdict["verdict"] == "PROMOTE", "the pre-registered rule must be what decides"
    assert verdict["survives_multiplicity"] is False, "a 5/110 effect cannot survive 17 cells"
    assert verdict["alpha_adjusted"] == pytest.approx(0.05 / 17)


def test_verdict_survives_the_multiplicity_bar_for_a_consistent_effect() -> None:
    base = _result("shipped", [0.0] * 110, [0.0] * 110)
    strong = _result("strong", [0.5] * 110, [0.5] * 110)
    verdict = fws.verdict_for(strong, base, seed=20260928, n_comparisons=17)
    assert verdict["verdict"] == "PROMOTE"
    assert verdict["survives_multiplicity"] is True


def test_markdown_reports_the_control_row_and_the_verdict_column() -> None:
    base = _result("shipped", [0.5] * 40, [0.4] * 40, added_refs=10, added_gold=2)
    better = _result("bb0.6", [0.75] * 40, [0.6] * 40, added_refs=0)
    control = _result("sparse", [0.5] * 40, [0.4] * 40, fielded=False)
    verdicts = {
        "sparse": fws.verdict_for(control, base, seed=1),
        "shipped": fws.verdict_for(base, base, seed=1),
        "bb0.6": fws.verdict_for(better, base, seed=1),
    }
    table = fws.markdown([control, base, better], base, verdicts)
    assert "| `sparse` | - | - | - | - |" in table
    assert "| `bb0.6` |" in table
    assert "PROMOTE" in table
    assert "gain survives" in table


# ── Wiring ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "REGENOLD_FIELD_WEIGHT_TITLE",
        "REGENOLD_FIELD_WEIGHT_BODY",
        "REGENOLD_FIELD_B_TITLE",
        "REGENOLD_FIELD_B_BODY",
    ],
)
def test_weights_are_in_the_engine_cache_key(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """Unkeyed, an in-process weight sweep serves arm A's answer to every arm.

    That is the R263.2/R288.1 cache-poisoning defect, and it is indistinguishable
    from a genuinely inert lever in the sweep output.
    """
    from app.routes.regenold import _engine_cache_key

    monkeypatch.setenv(name, "1")
    key_a = _engine_cache_key("What is AI?", None)
    monkeypatch.setenv(name, "3")
    key_b = _engine_cache_key("What is AI?", None)
    assert key_a != key_b, f"{name} collision"


def test_run_sweep_treats_the_control_as_its_own_baseline() -> None:
    """The sparse row must add nothing over itself, and it must be first."""
    from evals.retrieval import unit_grain as ug

    rows = ug.load_gold(fws._DEFAULT_GOLD, limit=3)  # noqa: SLF001
    grid = [c for c in fws.build_grid() if c.label in ("shipped", "bb0.6")]
    results, baseline, _refs = fws.run_sweep(rows, grid)

    assert [r.label for r in results] == ["sparse", "shipped", "bb0.6"]
    assert baseline.label == "shipped"
    sparse, shipped, cell = results
    assert sparse.fielded is False
    # Additions are measured against the control, so the control adds nothing.
    assert (sparse.added_refs, sparse.added_gold) == (0, 0)
    # Churn is measured against shipped, so shipped cannot churn against itself.
    # (The CONTROL can: churn is the cell-vs-shipped difference, and turning the
    # fields off is a difference by definition.)
    assert shipped.churn_rows == 0
    assert shipped.fielded is True and cell.fielded is True
    assert len(sparse.per_row_recall) == len(shipped.per_row_recall) == 3
