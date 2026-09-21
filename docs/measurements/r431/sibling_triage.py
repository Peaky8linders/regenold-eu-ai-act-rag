"""R431 — who owns the sibling-limb deficit: attribution, or generation?

R429 closed the DEPTH half of the gold sub-point deficit (a wire coordinate
shallower than the key). Its checkpoint named what it could not reach: unmet gold
sub-points where the wire carries a SIBLING of the key. Before designing a fix,
this file answers the two questions that decide the mechanism.

**Q1 — is the deficit structural or draw-dependent?** The board is 110 ROWS; the
recorded corpus holds several draws per row. Counting per draw over-weights rows
with more draws. So every expectation is scored per row and split three ways:
met in every recorded draw, met in some (draw-dependent), met in none (STRUCTURAL).
Only the structural set is a defect to engineer against.

**Q2 — did the answer say the gold limb's substance and cite a neighbour, or omit
it?** Measured as content-token recall of the limb's own statutory text
(`provision_text.get_provision_text`) inside the answer, using the engine's own
tokenizer. High recall with a neighbour on the wire is an ATTRIBUTION problem,
fixable after Stage-2. Low recall is a GENERATION problem, and rewriting the
citation would be an ungrounded claim about a limb the answer never discussed.

**Q3 — is the "sibling" even a different limb?** Some coordinate pairs
(`Annex I.A.11` against `Annex I.11`) may be two renderings of one provision. A
pair whose statutory TEXT is the same is a coordinate-form artefact, not a model
miss, and must not be counted as headroom.

Usage::

    .venv\\Scripts\\python.exe -m docs.measurements.r431.sibling_triage
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.data.provision_text import _tokens, get_provision_text  # noqa: E402
from app.routes import regenold as R  # noqa: E402

RESULTS = REPO / "evals" / "bench" / "results"
GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"

CORPUS = (
    "official-r424-*-hard*.ckpt.jsonl",
    "official-r423-need4-*-hard*.ckpt.jsonl",
    "official-r423-need3-*-hard*.ckpt.jsonl",
)

#: Below this content-token recall the answer is not discussing the limb.
ABSENT = 0.30
#: At or above this it is discussing it.
PRESENT = 0.60
#: Jaccard above which two coordinates are the same provision in two forms.
SAME_LIMB = 0.75


def _draws() -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for pat in CORPUS:
        for path in sorted(RESULTS.glob(pat)):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    out.append((path.stem, json.loads(line)))
    return out


def _graded_pair(row: dict[str, Any]) -> tuple[str, list[str]]:
    if row.get("pushback_answer") or row.get("pushback_refs"):
        return (
            row.get("pushback_answer") or "",
            [str(x) for x in (row.get("pushback_refs") or [])],
        )
    return row.get("pred_answer") or "", [str(x) for x in (row.get("pred_refs") or [])]


def _stage2_landed(row: dict[str, Any]) -> bool:
    return bool((row.get("provenance") or {}).get("stage2_polish"))


def _is_descendant(pred: str, expected: str) -> bool:
    return pred == expected or pred.startswith(expected + ".")


def _parent(ref: str) -> str:
    return ref.split(".")[0]


def _relation(a: str, b: str) -> str:
    x, y = a.lower(), b.lower()
    if x == y:
        return "same"
    if x.startswith(y + "."):
        return "finer"
    if y.startswith(x + "."):
        return "coarser"
    return "sibling"


def _recall(text: str, answer_tokens: set[str]) -> float:
    want = {t for t in _tokens(text) if len(t) >= 4}
    if not want:
        return 0.0
    return len(want & answer_tokens) / len(want)


def _jaccard(a: str, b: str) -> float:
    ta = {t for t in _tokens(a) if len(t) >= 4}
    tb = {t for t in _tokens(b) if len(t) >= 4}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def main() -> int:
    gold: dict[str, Any] = {}
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        if line.strip():
            g = json.loads(line)
            gold[str(g["id"])] = g

    by_row: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for _stem, row in _draws():
        if not _stage2_landed(row):
            continue
        rid = str(row.get("id"))
        if rid in gold:
            by_row[rid].append(row)

    status: Counter[str] = Counter()
    buckets: Counter[str] = Counter()
    substance: Counter[str] = Counter()
    form: Counter[str] = Counter()
    gold_recall: list[float] = []
    sib_recall: list[float] = []
    rows = 0
    examples: list[str] = []
    form_examples: list[str] = []
    # Per DRAW, the denominator the R428/R429 checkpoints used, so the prior
    # round's numbers can be reconciled instead of quietly replaced.
    draw_unmet = 0
    draw_buckets: Counter[str] = Counter()
    for _stem, row in _draws():
        if not _stage2_landed(row):
            continue
        rid = str(row.get("id"))
        if rid not in gold:
            continue
        answer, refs = _graded_pair(row)
        if not refs:
            continue
        wire = R._ground_wire_subpoints(answer, list(refs))
        for exp in (str(x) for x in gold[rid]["expected_refs"]):
            if any(_is_descendant(w.lower(), exp.lower()) for w in wire):
                continue
            draw_unmet += 1
            named = any(
                _is_descendant(c.lower(), exp.lower())
                for c in R._prose_named_subpoints(answer).get(_parent(exp).lower(), [])
            )
            present = [w for w in wire if _parent(w).lower() == _parent(exp).lower()]
            if not present:
                draw_buckets[
                    "named_but_no_coord_of_parent_on_wire" if named else "unnamed_no_coord"
                ] += 1
            elif any(_relation(w, exp) == "coarser" for w in present):
                draw_buckets["coarser_on_wire_R429_remit"] += 1
            elif not [w for w in present if _relation(w, exp) == "sibling"]:
                draw_buckets[
                    "named_other_coordinate_of_parent" if named else "unnamed_other_coord"
                ] += 1
            elif named:
                draw_buckets["named_sibling_on_wire_R425_remit"] += 1
            else:
                draw_buckets["sibling_not_named"] += 1

    for rid, draws in sorted(by_row.items()):
        rows += 1
        expected = [str(x) for x in gold[rid]["expected_refs"]]
        for exp in expected:
            met_flags = []
            for row in draws:
                answer, refs = _graded_pair(row)
                wire = R._ground_wire_subpoints(answer, list(refs))
                met_flags.append(any(_is_descendant(w.lower(), exp.lower()) for w in wire))
            if all(met_flags):
                status["met_in_every_draw"] += 1
                continue
            if any(met_flags):
                status["draw_dependent"] += 1
                continue
            status["STRUCTURAL (met in no draw)"] += 1

            # Classify on the last draw (all of them are unmet; the wire's shape is
            # what matters and it is stable on this population).
            row = draws[-1]
            answer, refs = _graded_pair(row)
            wire = R._ground_wire_subpoints(answer, list(refs))
            named = any(
                _is_descendant(c.lower(), exp.lower())
                for c in R._prose_named_subpoints(answer).get(_parent(exp).lower(), [])
            )
            # ORDER MATTERS, and the inherited classifier had it wrong: testing
            # "named" first folds "named but never wired" into a bucket that looks
            # like a pass failure, hiding the one case where the claim is asserted
            # and the citation never appears. The wire state is read FIRST.
            present = [w for w in wire if _parent(w).lower() == _parent(exp).lower()]
            if not present:
                key = "named_but_no_coord_of_parent_on_wire" if named else "unnamed_no_coord"
                buckets[key] += 1
                continue
            sibs = [w for w in present if _relation(w, exp) == "sibling"]
            if any(_relation(w, exp) == "coarser" for w in present):
                buckets["coarser_on_wire_R429_remit"] += 1
                continue
            if not sibs:
                buckets["named_other_coordinate_of_parent" if named else "unnamed_other_coord"] += 1
                continue
            buckets["named_sibling_on_wire_R425_remit" if named else "sibling_not_named"] += 1

            atoks = _tokens(answer)
            g_text = get_provision_text(exp) or ""
            g_r = _recall(g_text, atoks)
            best = max(sibs, key=lambda s: _recall(get_provision_text(s) or "", atoks))
            s_text = get_provision_text(best) or ""
            s_r = _recall(s_text, atoks)
            gold_recall.append(g_r)
            sib_recall.append(s_r)

            jac = _jaccard(g_text, s_text)
            if jac >= SAME_LIMB:
                form["same_limb_two_coordinate_forms"] += 1
                if len(form_examples) < 10:
                    form_examples.append(
                        f"  {rid}: gold={exp} vs wire={best}  jaccard={jac:.2f}"
                    )
            else:
                form["genuinely_different_limb"] += 1

            if g_r >= PRESENT:
                substance["substance_said_citation_neighbour"] += 1
            elif g_r <= ABSENT:
                substance["substance_omitted"] += 1
            else:
                substance["partial"] += 1
            if len(examples) < 12:
                examples.append(
                    f"  {rid}: gold={exp} (recall {g_r:.2f}) wire sibling={best} "
                    f"(recall {s_r:.2f}) jaccard={jac:.2f} len={len(answer)}"
                )

    n = len(gold_recall)
    print("PER DRAW (the R428/R429 denominator), on today's board:")
    print(f"  unmet gold expectations             : {draw_unmet}")
    for name, count in draw_buckets.most_common():
        print(f"    {name:46} {count:5}")
    print()
    print(f"PER ROW (the board denominator): {rows} rows with a landed Stage-2 draw")
    for name, count in status.most_common():
        print(f"  {name:32} {count:5}")
    print()
    print("of the STRUCTURAL ones, why:")
    for name, count in buckets.most_common():
        print(f"  {name:46} {count:5}")
    print()
    print(f"sibling population: {n} expectations on {n} rows")
    print("  Q3 — is the wire sibling even a different limb?")
    for name, count in form.most_common():
        print(f"    {name:38} {count:5}  ({count / n * 100:.1f}%)")
    print("  Q2 — was the gold limb's substance said?")
    for name, count in substance.most_common():
        print(f"    {name:38} {count:5}  ({count / n * 100:.1f}%)")
    if n:
        print(f"    mean content-token recall: gold {sum(gold_recall) / n:.3f} "
              f"vs cited sibling {sum(sib_recall) / n:.3f}")
    print()
    if form_examples:
        print("Q3 examples (same limb, two forms):")
        for line in form_examples:
            print(line)
        print()
    print("Q2 examples:")
    for line in examples:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
