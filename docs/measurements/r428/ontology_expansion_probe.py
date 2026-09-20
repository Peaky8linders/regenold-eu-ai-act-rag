"""R428 — what does the ontology citable expansion actually change?

``REGENOLD_ONTOLOGY_CITABLE_EXPANSION`` (shipped default ON by R426, PR #443)
widens the citable universe with 1-hop ontology neighbours. Its stated purpose is
to stop ``REGENOLD_CITABLE_BASE_GUARD`` from dropping "legitimate gold heads the
LLM correctly identified" — the exact failure that got that guard rejected
(ref conciseness +9.61 pp but head-level recall −18.02 pp and
``gold_dropped_head`` 9 → 19 on a live hard-set A/B).

Two facts make the claim worth measuring rather than accepting:

1. The expansion is consumed ONLY by ``_add_prose_named_refs(citable_bases=...)``
   and that argument is passed only ``if _citable_base_guard_enabled()`` — a flag
   that defaults **OFF**. So at default settings the whole lever is inert.
2. Nothing in PR #443 measures the pair. Its test asserts that Article 53 and
   Annex XIII are in the expanded set for the question ``"GPAI requirements"`` —
   but that question ALSO triggers the function's hardcoded GPAI list, which
   contains both, so the test cannot distinguish the cross-reference path from
   the constant.

This probe is offline and judge-free: the three axes it reports are the emitted
``references`` against gold, with no LLM involved. It replays recorded draws from
the R424/R423 hard-split boards through the REAL
``app.routes.regenold._add_prose_named_refs`` and asks the decision question
directly — of the references the guard blocks, how many are GOLD (rescued by the
expansion, which is its purpose) and how many are excess (conciseness cost)?

Usage::

    .venv\\Scripts\\python.exe -m docs.measurements.r428.ontology_expansion_probe
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.routes.regenold import (  # noqa: E402
    _add_prose_named_refs,
    _canonical_reference_base,
    _expand_citable_bases_with_ontology,
)
from evals.official.rubric import (  # noqa: E402
    reference_conciseness,
    reference_correctness_loose,
    reference_correctness_strict,
)

RESULTS = REPO / "evals" / "bench" / "results"
GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"
LABELS = ("r424-preamble", "r423-need4", "r423-need")
ARMS = ("A", "B")
SAMPLES = 3
ART_RE = re.compile(r"^(Article|Annex)\s+([0-9IVXLC]+)")


def _load_gold() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rid = str(row.get("id") or row.get("question_id") or "")
        if rid:
            out[rid] = row
    return out


def _draws() -> list[tuple[str, str, list[str], list[str]]]:
    """(row id, answer, wire refs, gold expected refs) from the recorded boards."""
    gold = _load_gold()
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str, list[str], list[str]]] = []
    for label in LABELS:
        for arm in ARMS:
            for s in range(SAMPLES):
                path = RESULTS / f"official-{label}-{arm}-hard.ckpt.jsonl"
                if s:
                    path = RESULTS / f"official-{label}-{arm}-hard.r{s}.ckpt.jsonl"
                if not path.exists():
                    continue
                for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    rid = str(row.get("id") or "")
                    if row.get("pushback_answer") or row.get("pushback_refs"):
                        answer = row.get("pushback_answer") or ""
                        refs = [str(x) for x in (row.get("pushback_refs") or [])]
                    else:
                        answer = row.get("pred_answer") or ""
                        refs = [str(x) for x in (row.get("pred_refs") or [])]
                    if not answer or not refs:
                        continue
                    key = (rid, answer)
                    if key in seen:
                        continue
                    seen.add(key)
                    exp = [str(x) for x in ((gold.get(rid) or {}).get("expected_refs") or [])]
                    out.append((rid, answer, refs, exp))
    return out


def _head(ref: str) -> str:
    m = ART_RE.match(str(ref).strip())
    return f"{m.group(1)} {m.group(2)}" if m else str(ref).strip()


def _is_gold(ref: str, exp: list[str]) -> bool:
    r = ref.strip().lower()
    for e in exp:
        e = e.strip().lower()
        if r == e or r.startswith(e + ".") or e.startswith(r + "."):
            return True
    return False


def _prose_bases_conservative(refs: list[str]) -> frozenset[str]:
    """The narrowest reading of the guard's allow-list: what was already emitted.

    The route widens its set with bases of the emitted references so the guard
    "cannot silently become stricter than retrieval OR already emitted"; this
    probe takes that floor, which is the WORST case for the guard and the best
    case for the expansion (any retrieval-only base the route also adds can only
    unblock more, never fewer).
    """
    return frozenset(
        b for r in refs if (b := _canonical_reference_base(r)) is not None
    )


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    draws = _draws()
    print(f"recorded draws replayed: {len(draws)}")

    axes = ("loose", "strict", "conc")
    fns = {
        "loose": reference_correctness_loose,
        "strict": reference_correctness_strict,
        "conc": reference_conciseness,
    }
    sums: dict[str, dict[str, float]] = {a: {k: 0.0 for k in axes} for a in ("off", "guard", "guard_exp")}
    n_axes = {k: 0 for k in axes}

    #: prose refs the plain guard fromholds (its cost) and the ones the
    #: expansion re-admits (its benefit), split by whether the reference is gold.
    withheld = 0
    readmitted = 0
    rescued_gold = 0
    rescued_excess = 0
    rows_moved = 0
    examples: list[str] = []

    for rid, answer, refs, exp in draws:
        bases = _prose_bases_conservative(refs)
        expanded = _expand_citable_bases_with_ontology(bases, question="")
        after_guard = _add_prose_named_refs(list(refs), answer, citable_bases=bases)
        after_exp = _add_prose_named_refs(list(refs), answer, citable_bases=expanded)
        for arm, ref_list in (("off", refs), ("guard", after_guard), ("guard_exp", after_exp)):
            for name in axes:
                val = fns[name](ref_list, exp)
                if val is None:
                    continue
                sums[arm][name] += val
                if arm == "off":
                    n_axes[name] += 1

        withheld += sum(1 for r in refs if r not in after_guard)
        extra = [r for r in after_exp if r not in after_guard and r not in refs]
        readmitted += len(extra)
        for r in extra:
            if _is_gold(r, exp):
                rescued_gold += 1
            else:
                rescued_excess += 1
        if after_exp != after_guard:
            rows_moved += 1
            if len(examples) < 6:
                examples.append(
                    f"  {rid}: guard={after_guard} -> +exp={after_exp}"
                )

    print()
    print(f"{'axis':8s} {'guard OFF':>10s} {'guard ON':>10s} {'guard+exp':>10s} "
          f"{'ON-OFF':>8s} {'+exp':>8s}")
    for name in axes:
        n = n_axes[name] or 1
        off, g, ge = (sums[a][name] / n for a in ("off", "guard", "guard_exp"))
        print(f"{name:8s} {off:10.2f} {g:10.2f} {ge:10.2f} {g - off:8.2f} {ge - g:8.2f}")
    print(f"\nrows where the expansion changed the emitted list: {rows_moved}/{len(draws)}")
    print(f"references the plain guard withholds:        {withheld}")
    print(f"references the EXPANSION re-admits:          {readmitted}")
    print(f"  of those, GOLD (the stated purpose):       {rescued_gold}")
    print(f"  of those, excess (a conciseness cost):     {rescued_excess}")
    for line in examples:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
