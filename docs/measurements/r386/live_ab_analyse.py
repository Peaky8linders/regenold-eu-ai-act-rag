"""R386 - read the live paired A/B, on the rows where the confound is ABSENT.

CLAUDE.md records the measured live noise floor for this class of lever: 8 of 13
CONTROL rows changed their answer with the lever provably inert, and the
reference axes do not resolve until n >= 120. So the reading is done on the
ZERO-VARIANCE subset -- rows whose ANSWER is byte-identical across arms, where
the reference list is the only thing that can have moved. This is the design
that flipped parent collapse ON at R381.
"""
import json, os, re, statistics, sys
REPO = r"D:\Claude Projects\regenold-eu-ai-act-rag"
HEAD = re.compile(r"^(Article\s+\d{1,3}|Annex\s+[IVXL]+)")

def norm(r):
    r = re.sub(r"\s*\(([0-9]+)\)", r".\1", (r or "").strip())
    r = re.sub(r"\s*\(([a-z])\)", r".\1", r)
    return re.sub(r"\s*\(.*?\)\s*$", "", r).strip()
def head(r):
    m = HEAD.match(norm(r)); return m.group(1) if m else norm(r)
def f1(p, g):
    if not g and not p: return 1.0
    if not g or not p: return 0.0
    tp = len(p & g)
    if not tp: return 0.0
    pr, rc = tp/len(p), tp/len(g)
    return 2*pr*rc/(pr+rc)

gold = {}
for line in open("mingold_rows.jsonl", encoding="utf-8"):
    r = json.loads(line)
    if r.get("expected"): gold[r["id"]] = {norm(x) for x in r["expected"]}

rows = json.load(open("live_ab_grain.json", encoding="utf-8"))
clean = [r for r in rows if r["off"]["transport"] != "bedrock" and r["on"]["transport"] != "bedrock"]
zv = [r for r in clean if r["zero_variance"]]
zvg = [r for r in zv if r["id"] in gold]

print("live paired A/B over the cloudflared wrapper")
print("  paired rows captured        : %d" % len(rows))
print("  wrapper-served both arms    : %d   (Bedrock-contaminated rows excluded: %d)"
      % (len(clean), len(rows) - len(clean)))
print("  ZERO-VARIANCE (answer byte-identical across arms) : %d" % len(zv))
print("  ... of those, carrying a minimal-gold key         : %d" % len(zvg))
print()

fired = [r for r in clean if r["off"]["refs"] != r["on"]["refs"]]
print("PROVE IT FIRES: the wire changed on %d/%d rows (%.0f%%)"
      % (len(fired), len(clean), 100*len(fired)/len(clean)))
zvf = [r for r in zv if r["off"]["refs"] != r["on"]["refs"]]
print("  and on %d/%d ZERO-VARIANCE rows, where nothing else moved" % (len(zvf), len(zv)))
print()

# Head-set invariance -- hard rule #8, asserted on LIVE wire output.
viol = [r for r in zv if {head(x) for x in r["off"]["refs"]} != {head(x) for x in r["on"]["refs"]}]
print("HEAD SET unchanged on %d/%d zero-variance rows  ->  hard rule #8 delta +%d"
      % (len(zv) - len(viol), len(zv), len(viol)))
for r in viol:
    print("   !! %s  %s -> %s" % (r["id"], r["off"]["refs"], r["on"]["refs"]))
print()

nb = statistics.mean([len(r["off"]["refs"]) for r in zv])
na = statistics.mean([len(r["on"]["refs"]) for r in zv])
lb = 100*sum(1 for r in zv for x in r["off"]["refs"] if "." in norm(x)) / max(1, sum(len(r["off"]["refs"]) for r in zv))
la = 100*sum(1 for r in zv for x in r["on"]["refs"] if "." in norm(x)) / max(1, sum(len(r["on"]["refs"]) for r in zv))
print("on the zero-variance subset:")
print("  refs/row            %.2f -> %.2f" % (nb, na))
print("  sub-point grain     %.1f%% -> %.1f%%" % (lb, la))

if zvg:
    L = [(f1({head(x) for x in r["off"]["refs"]}, {head(x) for x in gold[r["id"]]}),
          f1({head(x) for x in r["on"]["refs"]},  {head(x) for x in gold[r["id"]]})) for r in zvg]
    S = [(f1({norm(x) for x in r["off"]["refs"]}, gold[r["id"]]),
          f1({norm(x) for x in r["on"]["refs"]},  gold[r["id"]])) for r in zvg]
    print()
    print("scored against the MINIMAL-GOLD key, zero-variance rows only (n=%d):" % len(zvg))
    print("  Ref Loose   %5.1f -> %5.1f  (%+.1f pp)"
          % (100*statistics.mean([a for a,_ in L]), 100*statistics.mean([b for _,b in L]),
             100*(statistics.mean([b for _,b in L]) - statistics.mean([a for a,_ in L]))))
    print("  Ref Strict  %5.1f -> %5.1f  (%+.1f pp)"
          % (100*statistics.mean([a for a,_ in S]), 100*statistics.mean([b for _,b in S]),
             100*(statistics.mean([b for _,b in S]) - statistics.mean([a for a,_ in S]))))
    better = sum(1 for a,b in S if b > a); worse = sum(1 for a,b in S if b < a)
    print("  rows improved on strict: %d    rows made worse: %d" % (better, worse))
