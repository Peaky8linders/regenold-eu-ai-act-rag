"""R460 - screen REF-LIST PRUNING rules offline against the two live boards.

Why this is a different lever from every ref transform R442 falsified: the
official instrument computes ``ref_conciseness = min(1, |expected|/|provided|)``
(a pure count ratio) and judges the answer axes from the ANSWER TEXT ONLY - the
judge prompt carries the key's provisions, never the arm's own ref list. So
removing a ref from the emitted list cannot move the answer, conciseness, tone or
speed axes; it can only gain conciseness and (if the ref was key-relevant) lose
recall on the two reference-correctness axes.

That makes pruning screenable offline, exactly, from a checkpoint: the ref axes
are pure functions of (emitted list, key). The screen prices realisable rules
against two ceilings:

  min_preserve  shortest SUBSEQUENCE of the emitted list that still matches every
                expected ref the shipped list matched (order-preserving => what a
                perfect "drop the dead weight" policy could do)
  oracle_match  keep only refs that individually satisfy the loose predicate

Screened rules (key-blind, runnable in the engine AFTER Stage-2):
  mention       keep refs whose head is named in the graded answer prose
  dedupe_head   keep the first ref per article/annex head
  mention+dedupe / mention+cap2

    ../../.venv/Scripts/python.exe docs/measurements/r460/ref_prune_screen.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from evals.official.rubric import (  # noqa: E402
    _clean,
    reference_conciseness,
    reference_correctness_loose,
    reference_correctness_strict,
)
from evals.official.score_arm import build_rows, load_ckpt, load_gold  # noqa: E402

SCORES = REPO / "docs" / "measurements" / "r388"
ARMS = [
    ("hard", "r460-cohere-hard-s3", "official-r460-cohere-hard-s3-hard.ckpt.jsonl"),
    ("easy", "r460-cohere-easy-s3", "official-r460-cohere-easy-s3-easy.ckpt.jsonl"),
]

_HEAD_ART = re.compile(r"^(Article|Art\.)\s+(\d{1,3})")
_HEAD_ANNEX = re.compile(r"^Annex\s+([IVXLCDM]+)", re.IGNORECASE)


def _head(ref: str) -> str:
    """Article/annex HEAD of a ref: 'Article 13.2' -> 'Article 13'."""
    ref = (ref or "").strip()
    m = _HEAD_ART.match(ref)
    if m:
        return f"Article {int(m.group(2))}"
    m = _HEAD_ANNEX.match(ref)
    if m:
        return f"Annex {m.group(1).upper()}"
    return ref


def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _matched_set(expected: list[str], provided: list[str]) -> set[str]:
    """Expected refs the provided list satisfies (per-ref loose predicate)."""
    from evals.official.rubric import _is_descendant  # noqa: PLC0415

    exp = list(dict.fromkeys(_clean(expected)))
    got = _clean(provided)
    return {e for e in exp if any(_is_descendant(p, e) for p in got)}


def _min_preserve(provided: list[str], expected: list[str]) -> list[str]:
    """Shortest order-preserving sublist that keeps every matched expected ref."""
    keep = list(provided)
    matched = _matched_set(expected, provided)
    for i in range(len(provided) - 1, -1, -1):
        if len(keep) <= 1:
            break
        trial = keep[:i] + keep[i + 1 :]
        if _matched_set(expected, trial) >= matched:
            keep = trial
    return keep


def _dedupe_head(refs: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for r in refs:
        h = _head(r)
        if h in seen:
            continue
        seen.add(h)
        out.append(r)
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    from app.engines._graph_rag_impl import _mine_refs_from_text  # noqa: PLC0415
    from app.routes.regenold import _deepen_ref_grain  # noqa: PLC0415

    gold = load_gold()
    for mode, label, ckpt in ARMS:
        rows = build_rows(load_ckpt(REPO / "evals" / "bench" / "results" / ckpt), gold)
        for r in rows:
            r["references"] = _deepen_ref_grain(
                list(r["references"]), r.get("question") or "", r.get("answer") or ""
            )
        axes = json.loads((SCORES / f"score-{label}-{mode}.json").read_text(encoding="utf-8"))["axes"]
        frozen = [axes["ans_correctness_loose"], axes["ans_correctness_strict"],
                  axes["ans_conciseness"], axes["regulatory_tone"], axes["resp_speed"]]

        def mentioned(r: dict, ref: str) -> bool:
            mined = _mine_refs_from_text(r.get("answer") or "")
            h = _head(ref)
            if h.startswith("Article "):
                return f"Art. {h.split()[1]}" in mined
            return h in mined

        def noop(r: dict, refs: list[str]) -> list[str]:
            return refs

        def mention(r: dict, refs: list[str]) -> list[str]:
            keep = [x for x in refs if mentioned(r, x)]
            return keep or refs[:1]

        def mention_dedupe(r: dict, refs: list[str]) -> list[str]:
            return _dedupe_head(mention(r, refs))

        def mention_cap2(r: dict, refs: list[str]) -> list[str]:
            return mention(r, refs)[:2]

        def dedupe(r: dict, refs: list[str]) -> list[str]:
            return _dedupe_head(refs)

        def drop_parent(r: dict, refs: list[str]) -> list[str]:
            """Drop a ref that another ref in the list REFINES.

            A child satisfies BOTH axes for a parent key ref (loose matches on
            heads, strict credits descendants), so the coarser coordinate is
            redundant whenever its child is present.
            """
            from evals.official.rubric import _is_descendant  # noqa: PLC0415

            cleaned = _clean(refs)
            out = [x for x in refs
                   if any(y != x and _is_descendant(y, x) for y in cleaned)]
            return out or refs[:1]

        def finest_per_head(r: dict, refs: list[str]) -> list[str]:
            from evals.official.rubric import _is_descendant  # noqa: PLC0415

            cleaned = _clean(refs)
            out = [x for x in refs
                   if not any(y != x and _is_descendant(x, y) for y in cleaned)]
            return out or refs[:1]

        def mention_drop_parent(r: dict, refs: list[str]) -> list[str]:
            return drop_parent(r, mention(r, refs))

        def min_preserve(r: dict, refs: list[str]) -> list[str]:
            return _min_preserve(refs, r.get("expected_refs") or [])

        def oracle_match(r: dict, refs: list[str]) -> list[str]:
            matched = _matched_set(r.get("expected_refs") or [], refs)
            out = [x for x in refs if x in matched]
            return out or refs[:1]

        pols = [("shipped", noop), ("mention", mention), ("dedupe", dedupe),
                ("drop_parent", drop_parent), ("finest_per_head", finest_per_head),
                ("mention+dedupe", mention_dedupe), ("mention+cap2", mention_cap2),
                ("mention+drop_par", mention_drop_parent),
                ("CEIL min_preserve", min_preserve), ("CEIL oracle_match", oracle_match)]

        print(f"\n=== {mode.upper()}  ({label}, n={len(rows)}) "
              f"shipped overall {axes['overall']:.2f} ===")
        print("  policy              ref_loose  ref_strict  ref_conc  refs/row  overall  d_overall")
        for name, fn in pols:
            rl, rs, rc, lens = [], [], [], []
            for r in rows:
                refs = fn(r, list(r["references"]))
                rc_v = reference_conciseness(refs, r.get("expected_refs") or [])
                if rc_v is None:
                    continue
                lens.append(len(_clean(refs)))
                rl.append(reference_correctness_loose(refs, r.get("expected_refs") or []))
                rs.append(reference_correctness_strict(refs, r.get("expected_refs") or []))
                rc.append(rc_v)
            rl_m, rs_m, rc_m = _mean(rl) * 100, _mean(rs) * 100, _mean(rc) * 100
            prod = 1.0
            for v in (rl_m, rs_m, rc_m, *frozen):
                prod *= v
            overall = prod ** (1 / 8)
            print(f"  {name:<19} {rl_m:8.2f}  {rs_m:10.2f}  {rc_m:8.2f}  "
                  f"{_mean(lens):8.2f}  {overall:7.2f}  {overall - axes['overall']:+8.2f}")

        # Is "unmentioned" a signal for "not in the key"? 2x2 over supplied refs.
        cells = Counter()
        for r in rows:
            exp = r.get("expected_refs") or []
            if not _clean(exp):
                continue
            matched = _matched_set(exp, r["references"])
            for ref in r["references"]:
                key_rel = ref in matched
                ment = mentioned(r, ref)
                cells[(key_rel, ment)] += 1
        tot = sum(cells.values())
        print("  supplied refs 2x2 (key-relevant?, mentioned in answer?):")
        for kr in (True, False):
            for ment in (True, False):
                print(f"    key={str(kr):<5} mentioned={str(ment):<5} {cells[(kr, ment)]:4d} "
                      f"({cells[(kr, ment)] / tot * 100:4.1f}%)")

    print("\nCaveat: the instrument judges the answer axes from the answer text and the "
          "KEY's provisions only, so pruning cannot move them HERE; the official "
          "evaluator's prompt is not visible to us. Ref axes are exact.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
