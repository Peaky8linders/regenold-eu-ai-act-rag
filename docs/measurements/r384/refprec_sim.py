"""Zero-variance simulation of reference-precision levers on the live round.

Inputs are FIXED: the 110 live answers and the sonnet-5 judge's per-row
wrong_refs / missing_refs. Every arm below only removes references from the
already-emitted list, so the judge's own labels stay valid — no re-judging and
no generation variance. This is the R317 zero-variance simulator pattern.

⚠ The one thing it cannot model: removing a reference cannot make a MISSING
reference appear, so recall can only fall. Missing refs are carried through
unchanged and counted against every arm.
"""
import json
import os
import re
import statistics
import sys

os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
sys.path.insert(0, r"D:\Claude Projects\regenold-eu-ai-act-rag")

REPO = r"D:\Claude Projects\regenold-eu-ai-act-rag"
j = json.load(open(os.path.join(REPO, "docs/measurements/r384/grounded-r384-now-sonnet5.json"), encoding="utf-8"))
live = {r["id"]: r for r in json.load(
    open(os.path.join(REPO, "docs/measurements/r384/r384-reeval-round-2026-07-2324-live.json"), encoding="utf-8"))}


def first_mention(ans: str, ref: str):
    """Fraction through the answer where this provision is FIRST named, or None."""
    m = re.match(r"(Article|Annex)\s+([\w.]+)", ref)
    if not m:
        return None
    kind, num = m.group(1), m.group(2).split(".")[0]
    pat = (r"Article\s+0*%s\b" % re.escape(num)) if kind == "Article" \
        else (r"Annex\s+%s\b" % re.escape(num))
    s = re.search(pat, ans)
    return (s.start() / max(1, len(ans))) if s else None


ROWS = []
for r in j["rows"]:
    v = (r.get("verdicts") or {}).get("reference_correctness") or {}
    if v.get("judge_error"):
        continue
    src = live.get(r["id"])
    if not src:
        continue
    ans = src["now"]["ans"]
    refs = list(src["now"]["refs"])
    wrong = set(v.get("wrong_refs") or [])
    missing = list(v.get("missing_refs") or [])
    ROWS.append({
        "id": r["id"], "ans": ans, "refs": refs, "wrong": wrong, "missing": missing,
        "pos": {ref: first_mention(ans, ref) for ref in refs},
        "anchor": set(),
    })

# question-named anchors are never dropped by any arm
COORD = re.compile(r"(?:Article|Art\.?)\s*(\d+)|Annex\s+([IVXLC]+)", re.I)
for row in ROWS:
    q = live[row["id"]]["question"]
    nums = {m.group(1) for m in COORD.finditer(q) if m.group(1)}
    anx = {(m.group(2) or "").upper() for m in COORD.finditer(q) if m.group(2)}
    for ref in row["refs"]:
        m = re.match(r"(Article|Annex)\s+([\w.]+)", ref)
        if not m:
            continue
        head = m.group(2).split(".")[0]
        if (m.group(1) == "Article" and head in nums) or (m.group(1) == "Annex" and head.upper() in anx):
            row["anchor"].add(ref)


def score(keep_fn, label):
    tot_kept = tot_wrong_kept = 0
    rows_pass = 0
    right_dropped = wrong_dropped = 0
    counts = []
    for row in ROWS:
        kept = [r for r in row["refs"] if keep_fn(row, r)]
        if not kept:                      # never ship an empty citation list
            kept = list(row["refs"])[:1]
        dropped = [r for r in row["refs"] if r not in kept]
        wrong_dropped += sum(1 for r in dropped if r in row["wrong"])
        right_dropped += sum(1 for r in dropped if r not in row["wrong"])
        wk = sum(1 for r in kept if r in row["wrong"])
        tot_kept += len(kept)
        tot_wrong_kept += wk
        counts.append(len(kept))
        # The judge passes a row with no wrong refs AND no missing refs.
        # CONSERVATIVE CORRECTION: dropping a ref the judge called RIGHT must
        # count as newly MISSING, or the simulation rewards deleting good
        # citations. Without this the arms below read ~4 pp too high.
        rd = sum(1 for r in dropped if r not in row["wrong"])
        if wk == 0 and not row["missing"] and rd == 0:
            rows_pass += 1
    prec = 1 - tot_wrong_kept / max(1, tot_kept)
    refconc = 100 * statistics.mean([min(1.0, 1.4 / max(1, c)) for c in counts])
    print("%-34s pass %5.3f (%2d/%d)  prec %5.3f  refs/row %4.2f  RefConc %4.1f  "
          "dropped: %2d wrong / %2d right"
          % (label, rows_pass / len(ROWS), rows_pass, len(ROWS), prec,
             statistics.mean(counts), refconc, wrong_dropped, right_dropped))
    return rows_pass / len(ROWS), prec, statistics.mean(counts), refconc


print("live round, n=%d judged rows" % len(ROWS))
print("=" * 108)
score(lambda row, r: True, "BASELINE (ship everything)")
print()

# ARM 1 — citable-base guard: drop refs the prose never names at all
score(lambda row, r: row["pos"].get(r) is not None or r in row["anchor"],
      "A. drop refs never named in prose")
print()

# ARM 2 — late-mention threshold, anchors and prose-unnamed handled explicitly
for thr in (0.80, 0.70, 0.60, 0.50, 0.40):
    def mk(t):
        def keep(row, r):
            if r in row["anchor"]:
                return True
            p = row["pos"].get(r)
            if p is None:
                return False          # ungrounded promotion: drop (arm 1 rule)
            return p <= t
        return keep
    score(mk(thr), "B. keep if first named <= %.2f" % thr)
print()

# ARM 3 — combined with a floor of 2 refs (never cut below 2)
def keep_floor(row, r):
    return True
for thr in (0.60, 0.50):
    def mk2(t):
        def keep(row, r):
            if r in row["anchor"]:
                return True
            p = row["pos"].get(r)
            if p is None:
                return False
            if p <= t:
                return True
            # keep late refs only while we are still under 2 kept
            early = [x for x in row["refs"]
                     if x in row["anchor"] or (row["pos"].get(x) is not None and row["pos"][x] <= t)]
            return len(early) < 2
        return keep
    score(mk2(thr), "C. B(%.2f) with a 2-ref floor" % thr)
