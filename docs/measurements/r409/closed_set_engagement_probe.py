"""R409/R410 — probe: which engagement rule makes the closed-set member detector precise?

Deterministic, no network. Replays every `missing_closed_set_members` fire over the
frozen R407 hard ledger and compares engagement rules:

* ``OLD``  — the shipped rule: the ANSWER's own citations engage the group.
* ``exact`` — the QUESTION must name the group's parent coordinate exactly, or contain
  a distinctive bigram from the group parent's chapeau (a bigram whose words do not
  recur in the df corpus).
* ``head`` — same, but the df corpus is every member of the head (paragraphs included),
  not just the group's own children.

Run:  REGENOLD_SKIP_DOTENV=1 py -3.12 docs/measurements/r409/closed_set_engagement_probe.py
"""

from __future__ import annotations

import json
import os
import re
import sys

os.environ["REGENOLD_SKIP_DOTENV"] = "1"
sys.path.insert(0, ".")

from app.data.provision_hierarchy import closed_set_members  # noqa: E402
from app.data.provision_text import _tokens, get_provision_text  # noqa: E402
from app.engines import answer_completeness as ac  # noqa: E402

CKPT = "evals/bench/results/official-r407-direct-bedrock-cohere-v4-pro-hard.ckpt.jsonl"
LEDGER = "docs/measurements/r409/r407_sonnet5_failing_criteria_triage.json"
SCORE = "docs/measurements/r388/score-r407-sonnet5-tunnel-hard.json"


def chapeau_of(parent: str, children: list[tuple[str, str]]) -> str:
    """The parent's introductory text, up to its first member."""
    txt = get_provision_text(parent) or ""
    if not txt:
        return ""
    first = " ".join(ac._member_own_text(children[0][1]).split())[:40]
    idx = txt.find(first)
    return txt[:idx] if idx > 0 else txt


def bigrams(text: str) -> set[tuple[str, str]]:
    toks = [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 2]
    return {(toks[i], toks[i + 1]) for i in range(len(toks) - 1)}


def distinctive(chap: str, corpus: list[tuple[str, str]]) -> set[tuple[str, str]]:
    """Chapeau bigrams whose every word occurs in at most one corpus unit."""
    df: dict[str, int] = {}
    for _c, t in corpus:
        for tok in _tokens(t):
            df[tok] = df.get(tok, 0) + 1
    return {(a, b) for a, b in bigrams(chap) if df.get(a, 0) <= 1 and df.get(b, 0) <= 1}


def engages(ask: str, parent: str, children: list[tuple[str, str]], corpus) -> bool:
    if parent in {ac._coord_str(p) for p in ac._paths_in(ask)}:
        return True
    dist = distinctive(chapeau_of(parent, children), corpus)
    return bool(dist and (dist & bigrams(ask)))


def main() -> int:
    rows = [json.loads(line) for line in open(CKPT, encoding="utf-8") if line.strip()]
    ledger = json.load(open(LEDGER, encoding="utf-8"))
    targets = {c["id"] for c in ledger if c["rc"] == "OMITTED_ENUMERATED_ITEM"}
    scored = json.load(open(SCORE, encoding="utf-8"))["rows"]
    passing = {r["id"] for r in scored if all(r["criteria"])}

    names = ("OLD (answer-citation engagement)",
             "Q exact-parent + distinctive bigram (df = group children)",
             "Q exact-parent + distinctive bigram (df = all head members)")
    fires: dict[str, set[str]] = {n: set() for n in names}
    hits: dict[str, dict[str, list[str]]] = {n: {} for n in names}

    for r in rows:
        rid = r["id"]
        gaps = ac.missing_closed_set_members(r["question"], r["pred_answer"])
        if not gaps:
            continue
        fires[names[0]].add(rid)
        ask = ac._ask_text(r["question"])
        for name, df_scope in ((names[1], "kids"), (names[2], "head")):
            keep = []
            for g in gaps:
                parent = g.coordinate.rsplit(".", 1)[0]
                head = " ".join(parent.split(".")[0].split()[:2])
                members = closed_set_members(head)
                kids = [c for p, c in ac._groups(members) if p == parent]
                if not kids:
                    keep.append(g)
                    continue
                corpus = kids[0] if df_scope == "kids" else members
                if engages(ask, parent, kids[0], corpus):
                    keep.append(g)
                    exact = {ac._coord_str(p) for p in ac._paths_in(ask)}
                    why = [f"coord:{parent}"] if parent in exact else []
                    if not why:
                        dist = distinctive(chapeau_of(parent, kids[0]), corpus)
                        why = [f"bigram:{a} {b}" for a, b in sorted(dist & bigrams(ask))]
                    hits[name][rid] = why
            if keep:
                fires[name].add(rid)

    for name in names:
        fired = fires[name]
        print(f"{name}\n    fires={len(fired)}  TP={len(fired & targets)}/{len(targets)}  "
              f"FP_on_passing={len(fired & passing)}/{len(passing)}")
        print(f"    TP: {sorted(fired & targets)}")
        print(f"    FP: {sorted(fired & passing)}")
    print()
    for name in names[1:]:
        for rid in sorted(fires[name]):
            print(f"  [{name[2:14]}] {rid} <- {hits[name].get(rid)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
