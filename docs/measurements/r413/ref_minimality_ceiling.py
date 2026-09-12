"""R413 — Ref-minimality (roadmap row 2): SHIP or FALSIFY, with the exact ceiling.

WHY THIS INSTRUMENT. ``Ref Conciseness`` is

    ratio = min(|pred heads|, |gold heads|) / max(|pred heads|, |gold heads|)
    ref_conc = ratio ** 2                      # evals/bench/metrics.py

a pure COUNT ratio: it never asks whether a cited provision is discussed, only
how many heads were emitted. So the entire lever is computable offline from the
two reference LISTS — no generation, no judge, no provider. That makes a
decisive gate cheap, which is the point: four rounds have now been spent on this
row and it is still unproven.

THE TENSION. Any prune that removes a head in ``P \\ G`` raises ``ref_conc`` and
leaves ``ref_loose``/``ref_strict`` untouched — a pure win. Any prune that
removes a head in ``P & G`` is a loss of recall (loose) and precision (strict,
which is an F1). The gold key is invisible at inference, so a usable rule must
separate ``P \\ G`` from ``P & G`` using OBSERVABLE features only.

WHAT THIS MEASURES.

1. The exact per-candidate trade on the frozen live ledger: excess heads
   removed, expected heads lost, and the resulting Δ on all three reference axes
   plus an overall geomean delta anchored on the recorded easy-split scorecard.
2. The SEPARABILITY of each observable feature (how well it ranks ``P \\ G``
   above ``P & G``), i.e. whether a better threshold could exist at all. If every
   feature's AUC hovers at 0.5 the row is closed: no rule of this class can pay.
3. The ORACLE ceiling: the largest lossless removal ANY rule can achieve, which
   bounds the row's upside regardless of how clever the next form is.

Row 2 is SHIPPED only if a candidate is lossless (0 expected heads lost) AND its
Δoverall reaches the roadmap's threshold. Otherwise it is FALSIFIED with the
number that closes it.

SCOPE NOTE (what this does and does not model). Both the prediction and the gold
key are folded onto ARTICLE/ANNEX HEADS, which is exactly what a head-level
prune acts on. So the absolute axis values printed here are NOT the official
scorecard values (the official strict/conc axes carry sub-point grain), and the
COST of dropping an expected head is if anything under-stated: every sub-point
of that head disappears with it. Both biases point the same way, so a candidate
that fails here is not rescued by the grain question.

Usage::

    .venv/Scripts/python.exe docs/measurements/r413/ref_minimality_ceiling.py
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.bench.metrics import article_heads  # noqa: E402

OUT = ROOT / "docs" / "measurements" / "r413"
LIVE = ROOT / "evals" / "bench" / "results" / "official-r286-easy-live-easy.ckpt.jsonl"
HARD = ROOT / "evals" / "bench" / "results" / "official-r407-direct-bedrock-cohere-v4-pro-hard.ckpt.jsonl"
REFKEY = ROOT / "docs" / "measurements" / "r388" / "official_refkey_n110.jsonl"
GOLD = ROOT / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"

#: The recorded easy-split scorecard (R413 splice arm — the shipped engine's live
#: answers). The six non-reference axes are UNAFFECTED by a reference prune, so
#: they are held fixed and the geomean delta is computed from the three that move.
#: Anchoring on a recorded scorecard rather than re-judging keeps this gate free
#: of provider calls; the anchor is printed with every delta.
ANCHOR = {
    "ans_correctness_loose": 75.9,
    "ans_correctness_strict": 52.5,
    "ans_conciseness": 75.4,
    "ref_correctness_loose": 90.5,
    "ref_correctness_strict": 72.5,
    "ref_conciseness": 55.0,
    "regulatory_tone": 92.5,
    "resp_speed": 94.3,
}

#: The roadmap's threshold for closing row 2 as shipped: +2.2 pp overall.
THRESHOLD_PP = 2.2


def _load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _expected_by_id() -> dict[str, list[str]]:
    """``id -> expected refs``, with the benchmark's unstable rows excluded."""
    gold_ids = {r["id"] for r in _load(GOLD)}
    out: dict[str, list[str]] = {}
    for row in _load(REFKEY):
        if row["id"] not in gold_ids:
            continue
        out[row["id"]] = [] if row.get("unstable") else list(row.get("expected") or [])
    return out


def _heads(refs: list[str]) -> set[str]:
    return article_heads(refs)


# ── observable features ──────────────────────────────────────────────────────


def _head_mentioned(prose: str, head: str) -> bool:
    """Is this HEAD cited in the prose (either spelling)? Lenient by design."""
    num = head.split(" ", 1)[1]
    if head.startswith("Article"):
        return bool(re.search(rf"\b(?:Article|Art\.?)\s*{re.escape(num)}\b", prose or "", re.I))
    return bool(re.search(rf"\bAnnex\s+{re.escape(num)}\b", prose or "", re.I))


def _head_mention_pos(prose: str, head: str) -> float:
    """Relative position of the LAST mention in the prose, or None-ish 2.0."""
    num = head.split(" ", 1)[1]
    pat = (
        rf"\b(?:Article|Art\.?)\s*{re.escape(num)}\b"
        if head.startswith("Article")
        else rf"\bAnnex\s+{re.escape(num)}\b"
    )
    hits = list(re.finditer(pat, prose or "", re.I))
    if not hits:
        return 2.0
    return hits[-1].end() / max(1, len(prose))


def _sentences(prose: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", prose or "") if s.strip()]


def _dump_sentence_only(prose: str, head: str, heads: set[str]) -> bool:
    """True when the head appears ONLY in a sentence that cites 3+ other heads.

    The "enumeration dump" shape: a sentence listing a whole chapter's worth of
    provisions. A head that never appears outside such a sentence is a candidate
    for removal.
    """
    sents = _sentences(prose)
    if not sents:
        return False
    in_dump = False
    appears = False
    for s in sents:
        if not _head_mentioned(s, head):
            continue
        appears = True
        others = sum(1 for h in heads if h != head and _head_mentioned(s, h))
        if others < 3:
            return False  # it also appears in a focused sentence
        in_dump = True
    return appears and in_dump


def _auc(pos: list[float], neg: list[float]) -> float | None:
    """Rank-AUC: P(feature ranks an EXCESS head above an EXPECTED-PRESENT head).

    Implemented as the Mann-Whitney U statistic, ties counted as 0.5. 0.5 means
    the feature cannot separate the two classes at all.
    """
    if not pos or not neg:
        return None
    wins = 0.0
    for p in pos:
        for n in neg:
            wins += 1.0 if p > n else (0.5 if p == n else 0.0)
    return wins / (len(pos) * len(neg))


# ── the instrument ───────────────────────────────────────────────────────────


def _rows(ledger: Path, expected: dict[str, list[str]]) -> list[dict]:
    out: list[dict] = []
    for row in _load(ledger):
        exp = expected.get(row["id"])
        if not exp:
            continue  # no annotated expected refs ⇒ excluded from the ref metrics
        gold = _heads(exp)
        pred = _heads(row.get("pushback_refs") or row.get("pred_refs") or [])
        prose = row.get("pushback_answer") or row.get("pred_answer") or ""
        if not gold or not pred:
            continue
        out.append({"id": row["id"], "gold": gold, "pred": pred, "prose": prose})
    return out


def _axes(rows: list[dict], keep: list[set[str]]) -> dict[str, float]:
    """Reference axes from the (possibly pruned) kept-head sets."""
    loose: list[float] = []
    strict: list[float] = []
    conc: list[float] = []
    for row, kept in zip(rows, keep, strict=True):
        gold = row["gold"]
        lp, lg = len(kept), len(gold)
        hit = len(kept & gold) / len(gold)
        prec = len(kept & gold) / max(1, lp)
        f1 = 0.0 if prec + hit == 0 else 2 * prec * hit / (prec + hit)
        loose.append(hit)
        strict.append(f1)
        conc.append((min(lp, lg) / max(lp, lg)) ** 2 if lg else (1.0 if lp == 0 else 0.0))
    n = len(rows)
    return {
        "ref_correctness_loose": 100 * sum(loose) / n,
        "ref_correctness_strict": 100 * sum(strict) / n,
        "ref_conciseness": 100 * sum(conc) / n,
    }


def _overall(axes: dict[str, float]) -> float:
    vals = []
    for key, base in ANCHOR.items():
        vals.append(axes.get(key, base) / 100.0)
    if any(v <= 0 for v in vals):
        return 0.0
    return 100.0 * math.exp(sum(math.log(v) for v in vals) / len(vals))


def _candidate(name: str, rows: list[dict], drop: list[set[str]]) -> dict:
    keep = [row["pred"] - d for row, d in zip(rows, drop, strict=True)]
    axes = _axes(rows, keep)
    lost = sum(len(row["pred"] & row["gold"] & d) for row, d in zip(rows, drop, strict=True))
    removed = sum(len(d) for d in drop)
    return {
        "candidate": name,
        "heads_removed": removed,
        "expected_lost": lost,
        "lossless": lost == 0,
        "axes": axes,
        "overall": _overall(axes),
    }


def main() -> int:
    expected = _expected_by_id()
    verdicts: dict[str, list[dict]] = {}
    for label, ledger in (("easy-live (n=110 gold)", LIVE), ("hard-ledger (R407)", HARD)):
        if not ledger.exists():
            print(f"!! missing ledger {ledger}")
            continue
        rows = _rows(ledger, expected)
        if not rows:
            continue
        base_axes = _axes(rows, [row["pred"] for row in rows])
        base_overall = _overall(base_axes)
        print("=" * 92)
        print(f"REF MINIMALITY — {label}: {len(rows)} ref-scored rows")
        print("=" * 92)
        print("anchored scorecard axes for the OVERALL geomean (6 held fixed):")
        print(f"  {', '.join(f'{k}={v}' for k, v in ANCHOR.items())}")
        print(f"  baseline (this ledger): ref_loose={base_axes['ref_correctness_loose']:.2f} "
              f"ref_strict={base_axes['ref_correctness_strict']:.2f} "
              f"ref_conc={base_axes['ref_conciseness']:.2f}  OVERALL={base_overall:.2f}")
        emitted = sum(len(row["pred"]) for row in rows)
        excess = sum(len(row["pred"] - row["gold"]) for row in rows)
        gold_present = sum(len(row["pred"] & row["gold"]) for row in rows)
        print(f"  emitted heads={emitted}  expected-present={gold_present}  excess={excess} "
              f"({excess / emitted:.1%})")

        # candidate prunes
        c_ungrounded, c_dump, c_pos, c_budget = [], [], [], []
        for row in rows:
            heads, prose = row["pred"], row["prose"]
            c_ungrounded.append({h for h in heads if not _head_mentioned(prose, h)})
            c_dump.append({h for h in heads if _dump_sentence_only(prose, h, heads)})
            # "late" means mentioned, but only in the trailing 30% of the prose
            # (2.0 is the never-mentioned sentinel, which candidate A owns).
            c_pos.append({h for h in heads if 0.7 < _head_mention_pos(prose, h) < 2.0})
            # A budget with NO gold knowledge: keep the first K heads, K = the
            # corpus-median gold cardinality (the only "size" signal available).
            pass
        med = sorted(len(row["gold"]) for row in rows)[len(rows) // 2]
        for row in rows:
            ordered = list(row["pred"])
            c_budget.append(set(ordered[med:]) if len(ordered) > med else set())

        cands = [
            _candidate("A drop heads the prose never cites (R411 form)", rows, c_ungrounded),
            _candidate("B drop heads confined to an enumeration dump", rows, c_dump),
            _candidate("C drop heads whose last mention is past 70% of the prose", rows, c_pos),
            _candidate(f"D cap the list at the median gold size K={med}", rows, c_budget),
        ]

        # oracle ceilings over the observable features
        print("\nORACLE ceilings (removals with ZERO expected loss):")
        ceilings: dict[str, int] = {}
        for fname, fn in (
            ("never-cited", lambda r, h: not _head_mentioned(r["prose"], h)),
            ("dump-only", lambda r, h: _dump_sentence_only(r["prose"], h, r["pred"])),
            ("late-mention", lambda r, h: 0.7 < _head_mention_pos(r["prose"], h) < 2.0),
        ):
            # a per-HEAD feature applied only where it is SAFE for that row:
            # the ceiling is what a perfect classifier of the SAME feature buys.
            best = 0
            drop = []
            for row in rows:
                removable = {h for h in (row["pred"] - row["gold"]) if fn(row, h)}
                best += len(removable)
                drop.append({h for h in removable})
            ceilings[fname] = best
            c = _candidate(f"oracle[{fname}] (excess only)", rows, drop)
            print(f"  {fname:<14} removes {c['heads_removed']:>3} excess heads → "
                  f"ref_conc {c['axes']['ref_conciseness']:.2f} "
                  f"(Δ{c['axes']['ref_conciseness'] - base_axes['ref_conciseness']:+.2f}), "
                  f"OVERALL {c['overall']:.2f} (Δ{c['overall'] - base_overall:+.2f} pp)")

        print("\nCANDIDATES (shippable only when expected_lost == 0):")
        print(f"  {'candidate':<56}{'rm':>4}{'lost':>6}{'ref_conc':>10}{'Δconc':>8}{'Δovr':>8}")
        for c in cands:
            print(f"  {c['candidate']:<56}{c['heads_removed']:>4}{c['expected_lost']:>6}"
                  f"{c['axes']['ref_conciseness']:>10.2f}"
                  f"{c['axes']['ref_conciseness'] - base_axes['ref_conciseness']:>+8.2f}"
                  f"{c['overall'] - base_overall:>+8.2f}")
        best_lossless = max(
            (c for c in cands if c["lossless"]), key=lambda c: c["overall"], default=None
        )
        print(f"\n  best LOSSLESS candidate: "
              f"{best_lossless['candidate'] if best_lossless else 'NONE'}"
              + (f" → Δoverall {best_lossless['overall'] - base_overall:+.2f} pp "
                 f"(threshold {THRESHOLD_PP} pp)"
                 if best_lossless else ""))
        verdicts[label] = [*cands, {"baseline_overall": base_overall, "baseline": base_axes,
                                    "emitted": emitted, "excess": excess,
                                    "rows": len(rows), "ceilings": ceilings}]

        # feature separability
        print("\nSEPARABILITY (rank-AUC: excess heads vs expected-and-present heads):")
        for fname, fn in (
            ("never-cited", lambda r, h: 0.0 if _head_mentioned(r["prose"], h) else 1.0),
            ("dump-only", lambda r, h: 1.0 if _dump_sentence_only(r["prose"], h, r["pred"]) else 0.0),
            ("late-mention", lambda r, h: _head_mention_pos(r["prose"], h)),
        ):
            pos = [fn(r, h) for r in rows for h in (r["pred"] - r["gold"])]
            neg = [fn(r, h) for r in rows for h in (r["pred"] & r["gold"])]
            a = _auc(pos, neg)
            print(f"  {fname:<14} AUC={a if a is None else round(a, 3)}  "
                  f"(excess n={len(pos)}, expected-present n={len(neg)})")
        print()

    (OUT / "ref-minimality-ceiling.json").write_text(
        json.dumps(verdicts, indent=2), encoding="utf-8"
    )
    print(f"wrote {OUT / 'ref-minimality-ceiling.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
