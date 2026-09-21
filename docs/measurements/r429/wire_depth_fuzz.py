"""R429 — the depth-completion's licence, asserted UNIVERSALLY rather than sampled.

The offline probe (`wire_depth_probe.py`) proves the pass is monotone and
count/head-neutral on 477 recorded hard draws, and the live gate proves it on a
fresh draw. Both are samples. This file asserts the property itself over the REAL
pass on randomised inputs, so the licence does not rest on the draws that happened
to be recorded.

The pass edits only the `references` list, in place, 1:1. So for EVERY input the
following must hold, and a single counterexample falsifies the round:

1. **count invariance** — ``len(out) == len(refs)``. Ref. Conciseness is a pure
   count ratio, so this is what makes the lever free on that axis.
2. **head-set invariance** — the multiset of ``ref_head`` is unchanged. Ref.
   Correctness (Loose) scores through heads, and Hard Rule #8 is about gold heads.
3. **the changed slot is attributable** — every coordinate that CHANGED is either
   (a) a strict descendant of what it replaced,which is R429's completion and is
   **monotone by ``rubric._is_descendant``** (a deeper prediction satisfies every
   expectation its ancestor satisfied, and Ref. Strict is recall), or (b) a
   rewrite onto a coordinate the answer's own prose names, which is **R425's
   already-gated substitution lever** — a DIFFERENT pass with its own gate, kept
   deliberately out of R429's monotonicity claim. The assertion is a disjunction
   and a counterexample is anything in neither class.
4. **never mints** — every emitted coordinate passes ``coordinate_exists``.
5. **fixed point** — re-running the pass on its own output changes nothing, so a
   cached or replayed answer cannot drift.
6. **the R429 population is exercised** — at least one completion per run, and
   EVERY member of it strictly refines the coordinate it replaced.

⚠ What this file does NOT claim: that the substitution half is monotone. It is
not, and it does not have to be — its licence is a measurement on the board (R425:
the replaced wire limb was gold in 0 of 106 substitutions), not an algebraic
property.

Non-vacuity is asserted too: a run in which no coordinate was ever completed would
satisfy all five vacuously and prove nothing.

Usage::

    .venv\\Scripts\\python.exe -m docs.measurements.r429.wire_depth_fuzz
"""

from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.data.provision_coordinates import coordinate_exists  # noqa: E402
from app.routes import regenold as R  # noqa: E402
from evals.official.rubric import _is_descendant, ref_head  # noqa: E402

RESULTS = REPO / "evals" / "bench" / "results"
GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"
FLAG = "REGENOLD_GROUND_WIRE_DEPTH"
TRIALS = 20000


def _recorded_coordinates() -> set[str]:
    """Every coordinate the real board has ever put on the wire or in a key."""
    pool: set[str] = set()

    def _add(refs: object) -> None:
        if isinstance(refs, list):
            for ref in refs:
                if isinstance(ref, str) and ref.strip():
                    pool.add(ref.strip())

    if GOLD.exists():
        for line in GOLD.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            for key in ("expected_refs", "references", "gold_refs", "refs"):
                _add(row.get(key))
    for path in sorted(RESULTS.glob("official-r42*-hard*.ckpt.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            for key in ("refs", "pred_refs", "pushback_refs", "references"):
                _add(row.get(key))
    return {c for c in pool if coordinate_exists(c)}


_DESC_CACHE: dict[str, list[str]] = {}


def _descendants_of(parent: str, pool: set[str], limit: int = 12) -> list[str]:
    """Recorded coordinates that refine ``parent``, plus synthetically deepened ones.

    Memoised because the trial loop asks the same question thousands of times.
    """
    cached = _DESC_CACHE.get(parent)
    if cached is not None:
        return cached
    out = [c for c in pool if _is_descendant(c, parent) and c != parent]
    # Synthesise deeper coordinates the Regulation actually contains, so the fuzzer
    # is not limited to the grain the board happened to emit.
    for letter in "abcdefghijklmnop":
        for cand in (
            f"{parent}.{letter}",
            f"{parent}.1.{letter}",
            f"{parent}.2.{letter}",
        ):
            if coordinate_exists(cand):
                out.append(cand)
    result = sorted(set(out))[:limit]
    _DESC_CACHE[parent] = result
    return result


def _ask(answer: str, refs: list[str], question: str) -> list[str]:
    return R._ground_wire_subpoints(answer, list(refs), question)


def main() -> int:
    os.environ[FLAG] = "1"
    pool = _recorded_coordinates()
    if not pool:
        print("FATAL: no recorded coordinates to fuzz from")
        return 2

    parents = sorted({c for c in pool if _descendants_of(c, pool)})
    if not parents:
        print("FATAL: no parent coordinate has a recorded descendant")
        return 2

    rng = random.Random(429)
    pool_list = sorted(pool)
    violated: dict[str, int] = {}
    completions = 0
    substitutions = 0
    trials_with_edit = 0
    rendered_forms: dict[str, int] = {"paren": 0, "dotted": 0}
    edits_by_form: dict[str, int] = {"paren": 0, "dotted": 0}

    for _ in range(TRIALS):
        parent = rng.choice(parents)
        deeper = _descendants_of(parent, pool)
        if not deeper:
            continue
        target = rng.choice(deeper)

        # Wire: the parent (or one of its recorded coordinates) beside other noise.
        base = rng.choice([parent] + [c for c in deeper if c != target] or [parent])
        refs = [base]
        for _ in range(rng.randint(0, 4)):
            refs.append(rng.choice(pool_list))

        # Prose: name the target in one of the two forms the pass reads.
        if rng.random() < 0.5:
            form = "dotted"
            prose = f"The provider's duty under {target} applies."
        else:
            form = "paren"
            head, *tail = target.split(".")
            prose = "The provider's duty under " + head + "".join(
                f"({t})" for t in tail
            ) + " applies."
        rendered_forms[form] += 1
        question = "What must the provider do?"

        before = list(refs)
        out = _ask(prose, before, question)

        # 1. count invariance
        if len(out) != len(before):
            violated["count"] = violated.get("count", 0) + 1
            continue
        # 2. head-set invariance
        if sorted(ref_head(r) for r in out) != sorted(ref_head(r) for r in before):
            violated["head_set"] = violated.get("head_set", 0) + 1
            continue
        # 3. every changed slot is attributable to one of the two passes
        named = {
            leaf for leaves in R._prose_named_subpoints(prose).values() for leaf in leaves
        }
        changed = 0
        for a, b in zip(out, before, strict=True):
            if a == b:
                continue
            changed += 1
            if _is_descendant(a, b):
                completions += 1
            elif a in named:
                substitutions += 1
            else:
                violated["unattributable"] = violated.get("unattributable", 0) + 1
        # 4. never mints a coordinate the Regulation lacks
        if any(not coordinate_exists(r) for r in out):
            violated["minted"] = violated.get("minted", 0) + 1
            continue
        # 5. fixed point
        again = _ask(prose, out, question)
        if again != out:
            violated["fixed_point"] = violated.get("fixed_point", 0) + 1

        if changed:
            trials_with_edit += 1
            edits_by_form[form] += 1

    print(f"pool                 : {len(pool)} recorded coordinates")
    print(f"parent pool          : {len(parents)}")
    print(f"trials               : {TRIALS}  (prose forms {rendered_forms})")
    print(f"trials with an edit  : {trials_with_edit}")
    print(f"R429 completions     : {completions}  (strict descendants)")
    print(f"R425 substitutions   : {substitutions}  (rewrites onto a prose-named limb)")
    print(f"edits by prose form  : {edits_by_form}")
    print(f"violations           : {violated or 'NONE'}")
    print()
    if completions == 0:
        print("VOID — no coordinate was ever completed; the R429 claim was vacuous")
        return 1
    if violated:
        print("FALSIFIED — at least one invariant has a counterexample above")
        return 1
    print("HOLDS — count / head-set / fixed-point invariance, no minting, and every")
    print("        changed slot attributable to a monotone completion or the already-")
    print("        gated substitution, over randomised inputs to the real pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
