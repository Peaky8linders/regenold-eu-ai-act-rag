"""R474 - compare two offline replays (pre-R473 vs deployed) question by question.

The R473 route changes are post-generation and deterministic, so a paired replay
is exact: there is no sampling variance to average away. What matters is WHICH
questions change and whether every change is monotone on the quantity the merge
gate protects (AGENTS.md hard rule #8: ``gold_dropped_head``). The head set is the
quantity: if the new head set contains the old one on EVERY changed row, no row
can newly drop a gold head, with no gold needed.

Usage:  python compare_replays.py PRE.json DEPLOYED.json LABELS.json [OUT.json]
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_HEAD = re.compile(r"^(Article\s+\d+|Annex\s+[IVXL]+)")
_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\"'])")


def heads(refs: list[str]) -> set[str]:
    out = set()
    for r in refs:
        m = _HEAD.match(" ".join(str(r).split()))
        if m:
            out.add(m.group(1))
    return out


def sentences(text: str) -> list[str]:
    return [s for s in _SPLIT.split((text or "").strip()) if s]


def main() -> int:
    pre = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["rows"]
    dep = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))["rows"]
    labels = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))["labels"]
    assert [r["question"] for r in pre] == [r["question"] for r in dep], "pools differ"
    bad = [(a["status"], b["status"]) for a, b in zip(pre, dep, strict=True) if a["status"] != 200 or b["status"] != 200]
    changed = []
    for a, b in zip(pre, dep, strict=True):
        if a["answer"] == b["answer"] and a["references"] == b["references"]:
            continue
        ha, hb = heads(a["references"]), heads(b["references"])
        sa, sb = sentences(a["answer"]), sentences(b["answer"])
        changed.append({
            "question": a["question"],
            "label": labels.get(a["question"]),
            "answer_changed": a["answer"] != b["answer"],
            "refs_changed": a["references"] != b["references"],
            "sent": [len(sa), len(sb)],
            "chars": [len(a["answer"]), len(b["answer"])],
            "n_refs": [len(a["references"]), len(b["references"])],
            "head_relation": ("equal" if ha == hb else "superset" if hb > ha else "subset" if hb < ha else "different"),
            "heads_lost": sorted(ha - hb),
            "heads_gained": sorted(hb - ha),
            "old_sentences_kept": all(s in sb for s in sa),
            "refs_pre": a["references"],
            "refs_deployed": b["references"],
        })
    n = len(pre)
    print(f"pool={n}  non-200 rows={len(bad)}  CHANGED={len(changed)}  ({100*len(changed)/n:.2f}%)")
    print("by label:", dict(collections.Counter(c["label"] for c in changed)))
    print("head relation:", dict(collections.Counter(c["head_relation"] for c in changed)))
    print("rows that LOST a head:", sum(1 for c in changed if c["heads_lost"]))
    print("answer changed:", sum(c["answer_changed"] for c in changed), " refs changed:", sum(c["refs_changed"] for c in changed))
    print()
    for c in changed:
        print(f"- [{c['label']}] {c['question'][:100]!r}")
        print(f"    sentences {c['sent']}  chars {c['chars']}  refs {c['n_refs']}  heads={c['head_relation']}"
              f"  lost={c['heads_lost']} gained={c['heads_gained']}  old_sentences_kept={c['old_sentences_kept']}")
        print(f"    pre      : {c['refs_pre']}")
        print(f"    deployed : {c['refs_deployed']}")
    if len(sys.argv) > 4:
        Path(sys.argv[4]).write_text(json.dumps({"pool": n, "changed": changed}, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
