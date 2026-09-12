"""Is a "grounded-only" reference prune SAFE?  (frozen R407 hard ledger, no network)

MOTIVATION. ``Ref Conciseness`` is our lowest axis (55.93). Over the 107
ref-scored rows of the frozen R407 ledger, 221 of 301 emitted references (73.4 %)
are NOT in the expected key, and 72 % of rows add at least one provision whose
ARTICLE is not in the key at all. The cheapest imaginable prune is: drop any
emitted ref the answer's prose never mentions. That is meant to be
reference-neutral by construction — ``Ref Correctness`` only asks whether the
EXPECTED refs are present, and a ref the prose never mentions is not carrying any
answer content.

SAFETY TEST. If an EXPECTED ref is itself unmentioned by this rule, the prune
would delete it and lose ``ref_loose``. This probe measures exactly that, and it
is the check that keeps the rule honest.

FIRST-RUN TRAP (recorded because it is the whole point of the instrument). A
first cut parsed only ``Article N`` and treated every ANEX ref as unmentioned —
because the parser returned ``None`` for ``Annex III.8`` rather than "not found".
That reported 78 prunable refs and hid 15 expected refs inside them, including
``rg_092`` whose prose literally reads "not all of Annex I, Annex II, and Annex
III...". A prune built on that number would have deleted expected Annex refs. The
`mentioned()` below therefore handles BOTH heads.

Run:  .venv/Scripts/python.exe docs/measurements/r411/ref_minimality_probe.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CKPT = ROOT / "evals/bench/results/official-r407-direct-bedrock-cohere-v4-pro-hard.ckpt.jsonl"
REFKEY = ROOT / "docs/measurements/r388/official_refkey_n110.jsonl"


def norm(ref: str) -> str:
    r = re.sub(r"\s+", " ", str(ref or "")).strip().rstrip(".")
    r = re.sub(r"^(Article|Art\.?)\s*", "Article ", r, flags=re.I)
    r = re.sub(r"^(Annex)\s*", "Annex ", r, flags=re.I)
    return r


def head(ref: str) -> tuple[str, str] | None:
    """('Article', '6') / ('Annex', 'III') / None."""
    m = re.match(r"Article\s+(\d+)\b", ref)
    if m:
        return ("Article", m.group(1))
    m = re.match(r"Annex\s+([IVXL]+)\b", ref)
    if m:
        return ("Annex", m.group(1).upper())
    return None


def mentioned(prose: str, ref: str) -> bool:
    """Is this ref's HEAD cited anywhere in the prose?

    Deliberately lenient: HEAD-level only, in either the ``Article 6`` / ``Art. 6``
    or ``Annex III`` spelling. Lenient is the right bias here — an under-detected
    mention makes the pruner look unsafe, which fails the gate closed.
    """
    h = head(ref)
    if h is None:
        return False
    kind, num = h
    if kind == "Article":
        return bool(re.search(rf"\b(?:Article|Art\.?)\s*{num}\b", prose or "", re.I))
    return bool(re.search(rf"\bAnnex\s+{re.escape(num)}\b", prose or "", re.I))


def main() -> int:
    ck = [
        json.loads(line)
        for line in CKPT.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    refkey = {
        json.loads(line)["id"]: json.loads(line)
        for line in REFKEY.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }

    scored = pred_total = excess_total = 0
    excess_mentioned = excess_unmentioned = 0
    gold_present = gold_present_unmentioned = 0
    gold_absent = 0
    unsafe: list[tuple[str, str, str]] = []
    rows_shed = 0

    for row in ck:
        rid = row["id"]
        r = refkey.get(rid)
        if not r or not r.get("expected"):
            continue
        scored += 1
        gold = {norm(x) for x in r["expected"]}
        pred = {norm(x) for x in (row.get("pushback_refs") or row.get("pred_refs") or [])}
        prose = row.get("pushback_answer") or row.get("pred_answer") or ""

        for p in pred:
            pred_total += 1
            if p not in gold:
                excess_total += 1
                if mentioned(prose, p):
                    excess_mentioned += 1
                else:
                    excess_unmentioned += 1
        for g in gold & pred:
            gold_present += 1
            if not mentioned(prose, g):
                gold_present_unmentioned += 1
                unsafe.append((rid, g, prose[:110]))
        gold_absent += len(gold - pred)
        if any(
            p not in gold and not mentioned(prose, p) for p in pred
        ):
            rows_shed += 1

    print("=" * 88)
    print("GROUNDED-ONLY REF PRUNE — safety on the frozen R407 hard ledger (n=107 ref-scored)")
    print("=" * 88)
    print(f"emitted refs                       : {pred_total}")
    print(f"  in expected key                  : {pred_total - excess_total}")
    print(f"  EXCESS                           : {excess_total} ({excess_total / pred_total:.1%})")
    print(f"    excess, HEAD cited in prose    : {excess_mentioned}")
    print(f"    excess, HEAD absent from prose : {excess_unmentioned}")
    print(f"rows that would shed >= 1 ref      : {rows_shed}")
    print()
    print(f"expected refs present in the list  : {gold_present}")
    print(f"  ...whose HEAD is ABSENT from prose: {gold_present_unmentioned}  <-- UNSAFE if > 0")
    print(f"expected refs absent from the list : {gold_absent} (the ref_loose recall gap)")
    if unsafe:
        print("\nUNSAFE cases (pruning these would LOSE an expected ref):")
        for rid, g, prose in unsafe[:20]:
            print(f"  {rid}: {g}\n      prose: {prose!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
