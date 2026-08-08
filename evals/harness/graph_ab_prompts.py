"""Build paired Stage-2 prompts (graph OFF vs graph ON) for a live A/B.

The R323/R324 knowledge-graph work reaches the model ONLY through the Stage-2
references block. So the only way to measure it is to assemble that block both
ways for the same question and put both in front of a real model.

Emits JSONL: {qid, question, gold_refs, prompt_off, prompt_on, delta_chars}.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def build(questions: list[dict], out_path: str) -> dict:
    os.environ.setdefault("P2P_GRAPH_RAG_PROVIDER", "cli")
    os.environ["REGENOLD_KG_CONTEXT"] = "1"

    from evals.harness.faithful_graph import install

    install()

    import app.engines._graph_rag_impl as impl
    import app.engines.kg_context as kg

    rows, n_moved = [], 0
    for q in questions:
        question = q["question"]
        query = impl._deterministic_parse(question)
        context = impl._retrieve_from_graph(query)

        kg.reset_render_memo()
        os.environ["REGENOLD_KG_CONTEXT"] = "0"
        prompt_off = impl._build_context_references_block(context, question=question)

        kg.reset_render_memo()
        os.environ["REGENOLD_KG_CONTEXT"] = "1"
        prompt_on = impl._build_context_references_block(context, question=question)

        if prompt_on != prompt_off:
            n_moved += 1
        rows.append({
            "qid": q["qid"],
            "question": question,
            "gold_refs": q.get("gold_refs", []),
            "prompt_off": prompt_off,
            "prompt_on": prompt_on,
            "delta_chars": len(prompt_on) - len(prompt_off),
        })

    with open(out_path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    return {
        "rows": len(rows),
        "treatment_rows": n_moved,
        "mean_delta_chars": sum(r["delta_chars"] for r in rows) / max(1, len(rows)),
        "out": out_path,
    }


def _load_probe(limit: int) -> list[dict]:
    """Gold-bearing questions from the project's own probe surfaces."""
    out: list[dict] = []

    # The project's canonical gold-bearing probe set (paper_st_v4 / tricky /
    # multiturn) — 132 rows, each with expected_refs.
    from evals.harness.probe_set import load_probe_set

    for r in load_probe_set():
        q = r.live_question or (r.messages[-1]["content"] if r.messages else "")
        out.append({
            "qid": r.id,
            "question": q,
            "gold_refs": list(r.expected_refs or []),
            "gold_keywords": list(r.expected_keywords or []),
            "category": r.category,
            "source": r.source,
        })

    # Plus the medtech/life-sciences gold set, which is where the graph's
    # Annex-I / medical-device structure is most likely to matter.
    from evals.regenold.scenarios_medtech_graphrag_v124 import GROUND_TRUTH

    for r in GROUND_TRUTH:
        out.append({
            "qid": r["id"],
            "question": r["question"],
            "gold_refs": list(r.get("expected_refs") or []),
            "gold_keywords": list(r.get("expected_keywords") or []),
            "category": r.get("category", "medtech"),
            "source": "medtech_v124",
        })

    out = [r for r in out if r["question"]]
    return out[:limit]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--out", default=".evalout/graph_ab_prompts.jsonl")
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    print(json.dumps(build(_load_probe(a.limit), a.out), indent=2), file=sys.stderr)
