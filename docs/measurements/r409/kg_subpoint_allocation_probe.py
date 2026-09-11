"""R409 — live-Aura measurement of the Stage-2 sub-point block, three query shapes.

OLD  = pre-R408 (13547ff~1): points reachable only when they carry a SubPoint.
R408 = 5f43818: every point, but ONE global ``LIMIT $max_units`` under
       ``ORDER BY cite`` ("Annex" < "Article").
FIXED = working tree: every point, rows in ref order, budget shared by
        ``kg_context._allocate_units``.

Input: the refs of every row of the R407 hard-mode checkpoint (turn 1 + graded
turn), mapped through ``kg_context._node_ids`` exactly as the renderer does.
Run: PYTHONPATH=. py -3.12 docs/measurements/r409/kg_subpoint_allocation_probe.py
"""
import collections
import json
import os
import subprocess

from dotenv import load_dotenv

load_dotenv(".env")
from neo4j import GraphDatabase  # noqa: E402

from app.engines import kg_context as kc  # noqa: E402

CKPT = "evals/bench/results/official-r407-direct-bedrock-cohere-v4-pro-hard.ckpt.jsonl"


def _cypher_at(rev: str) -> str:
    src = subprocess.run(
        ["git", "show", f"{rev}:app/engines/kg_context.py"],
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout
    ns: dict = {}
    start = src.index('_SUBPOINT_CYPHER = """')
    exec(src[start: src.index('"""', start + 25) + 3], ns)  # noqa: S102
    return ns["_SUBPOINT_CYPHER"]


OLD, R408 = _cypher_at("13547ff~1"), _cypher_at("5f43818")
units, chars_cap = kc._DEFAULT_MAX_UNITS, kc._DEFAULT_UNIT_CHARS
auth = (os.environ.get("NEO4J_USERNAME") or os.environ.get("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"])
driver = GraphDatabase.driver(os.environ["NEO4J_URI"], auth=auth)
rows = [json.loads(line) for line in open(CKPT, encoding="utf-8")]
stats: collections.Counter = collections.Counter()
chars: dict = collections.defaultdict(int)
with driver.session() as s:
    for r in rows:
        turn1 = list(r.get("turn1_refs") or [])
        refs = turn1 + [x for x in (r.get("pred_refs") or []) if x not in turn1]
        ids = kc._node_ids(refs, limit=kc._DEFAULT_MAX_REFS)
        if not ids:
            continue
        full = s.run(kc._SUBPOINT_CYPHER, ids=ids, max_rows=kc._SUBPOINT_ROW_CEILING).data()
        reach = {x["cite"] for x in full}
        if not reach:
            continue
        stats["rows_with_point_text"] += 1
        arms = {
            "old": s.run(OLD, ids=ids, max_units=units).data(),
            "r408": s.run(R408, ids=ids, max_units=units).data(),
            "fixed": kc._allocate_units(full, units),
        }
        for name, got in arms.items():
            stats[f"{name}_evicts_a_cited_provision"] += bool(reach - {x["cite"] for x in got})
            chars[name] += sum(len((x["text"] or "")[:chars_cap]) for x in got)
        stats["fixed_loses_text_old_had"] += bool({x["cite"] for x in arms["old"]} - {x["cite"] for x in arms["fixed"]})
        stats["r408_loses_text_old_had"] += bool({x["cite"] for x in arms["old"]} - {x["cite"] for x in arms["r408"]})
driver.close()
n = stats["rows_with_point_text"]
print(json.dumps(dict(stats), indent=1))
print("mean sub-point block chars per row:", {k: round(v / n) for k, v in chars.items()})
