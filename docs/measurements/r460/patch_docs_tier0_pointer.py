"""Two doc touch-ups: the plan's "long system dies" item is superseded by the
wrapper log evidence, and CHECKPOINT should point at TIER0-FIXES.md. Idempotent.
"""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent

A = OUT / "ANALYSIS-AND-PLAN.md"
a = A.read_text(encoding="utf-8")
OLD = """5. **Find where the long system dies for Sonnet.** The canary localizes it to the
   wrapper/CLI (repo `claude-code-openai-wrapper`, `claude_cli.py:152`); find the
   cap and whether it is per-model. Until then, treat the shipped R412 gate as
   Opus-only.
"""
NEW = """5. **Treat the long-system contract as model-specific.** The wrapper's own log
   rules out a delivery drop (>= 30,000 chars spills to `--system-prompt-file`
   for every model); at 60 k Opus obeyed 3/3 and Sonnet 1/3, so what remains is
   model adherence to a tail instruction inside a 60k stack. Keep the R412
   full-system gate Opus-only until Sonnet has its own measurement, and note
   that fast mode (`CLAUDE_CODE_FAST_MODE`) is Opus-only by design, so it cannot
   make Sonnet faster.
"""
if NEW in a:
    print("plan item already updated")
else:
    assert a.count(OLD) == 1, a.count(OLD)
    A.write_text(a.replace(OLD, NEW), encoding="utf-8")
    print("plan item updated")

CP = OUT / "CHECKPOINT.md"
cp = CP.read_text(encoding="utf-8")
MARK = "## 2026-09-30 (Tier-0) -- transport + instrumentation fixes landed"
SECTION = f"""
---

{MARK}

`TIER0-FIXES.md` records them: the wrapper Stage-2 deadline
(`REGENOLD_STAGE2_WRAPPER_TIMEOUT_S`, default 150 s, cache-keyed), the harness
slow-not-down probe (`REGENOLD_BATCH_PROBE_BEFORE_ABORT`, default ON), and
per-dispatch `stage2_usage` capture into the row schema. 397 tests pass, lint
neutral. The wrapper was root-caused read-only: `WRAPPER_FORWARD_SYSTEM_PROMPT`
is ON, >= 30,000-char systems spill to `--system-prompt-file` for BOTH models,
so the canary's 3/3 (Opus) vs 1/3 (Sonnet) at 60 k is model-side. Still blocked:
Cohere quota (live numbers remain SVD floors), the R450 `density` live gate,
and the R451 HOLD note.
"""
if MARK in cp:
    print("checkpoint already updated")
else:
    CP.write_text(cp.rstrip("\n") + "\n" + SECTION, encoding="utf-8")
    print("checkpoint updated")
