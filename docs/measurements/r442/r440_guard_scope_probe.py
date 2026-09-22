"""R442 — does ``_grounded_branch_guard`` fire on the hard-mode preamble rather than the live question?

Measured on the main-branch guard (1aa09b8): all 11 blocks (5,611 chars) on every R440
gate row. Run from the repo root with REGENOLD_SKIP_DOTENV=1.
"""
import os
import sys

sys.path.insert(0, os.getcwd())
from app.data.graph_rag_prompts import _grounded_branch_guard
from app.integrations.regenold.models import RegenoldChatMessage
from app.routes.regenold import _build_question_from_history
from evals.regenold import hard_preamble as hp
from evals.regenold.official_batch import load_official_batch  # noqa

ids = "rg_002 rg_004 rg_007 rg_008 rg_026 rg_055 rg_058 rg_070 rg_073 rg_074 rg_075 rg_080 rg_081 rg_083 rg_088 rg_092 rg_101 rg_103 rg_106 rg_108 rg_109".split()
rows = {r.id: r for r in load_official_batch()}
def blocks(text):
    g = _grounded_branch_guard(text)
    return [ln.split(":")[0] for ln in g.splitlines()[1:] if ln.strip()], len(g)
tot_live = tot_flat = 0
for rid in ids:
    q = rows[rid].question
    msgs = [RegenoldChatMessage(**m) for m in hp.build_prefixed_messages(q)]
    res = _build_question_from_history(msgs)
    flat = res.question if hasattr(res, "question") else res[0]
    bl, cl = blocks(q)
    bf, cf = blocks(flat)
    tot_live += cl
    tot_flat += cf
    print(f"{rid}: live={len(bl)} blocks {cl:5d} chars | flattened={len(bf)} blocks {cf:5d} chars  live_marker={'Latest question:' in flat}")
print(f"TOTAL chars appended: live-only={tot_live}  flattened={tot_flat}")
