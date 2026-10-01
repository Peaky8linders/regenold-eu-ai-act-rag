"""Correct the canary paragraphs with the n=3 result and the wrapper-log
mechanism (both long calls went through --system-prompt-file, so the divergence
is model-side). Idempotent.
"""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent

A = OUT / "ANALYSIS-AND-PLAN.md"
a = A.read_text(encoding="utf-8")
A_OLD_TABLE = """| system chars | Sonnet 5 | Opus 5.5 |
| --: | :-- | :-- |
| 129 | obeyed ("BANANA\\\\nOK") | obeyed |
| 3,131 | obeyed | obeyed |
| 60,774 | **not obeyed** - reply paraphrases the *head* of the stack | obeyed |
"""
A_NEW_TABLE = """| system chars | Sonnet 5 | Opus 5.5 |
| --: | :-- | :-- |
| 129 | obeyed 3/3 | obeyed 3/3 |
| 3,131 | obeyed 3/3 | obeyed 3/3 |
| 60,774 | **obeyed 1/3** | **obeyed 3/3** |
"""
A_OLD_2 = """2. At production length it is **model-dependent**: Opus gets the stack, Sonnet
   gets at most a head/truncated version (its reply quotes "EU AI Act Legal
   Specialist" - it saw the beginning - but not the tail canary). This is a
   *config-level* reason not to promote Sonnet beyond the correctness gate: on
   the easy board (every row single-turn, full stack by R412's gate) Sonnet would
   silently run with a degraded system prompt.
"""
A_NEW_2 = """2. At production length it is **model-dependent, and the wrapper is not the
   cause**: both long calls were handed to the CLI as `--system-prompt-file`
   (the wrapper's own log, 12:44:19 / 12:44:38: `System prompt 60877 chars >=
   30000 argv limit` - `claude_cli.py` spills >= 30,000 chars to a temp file),
   i.e. the same path for both models, and yet Opus obeyed 3/3 while Sonnet
   managed 1/3. So this is model-side adherence to a tail instruction buried in
   60k of prompt, not a delivery gap - and it is why the R411/R412 full-system
   result does not transfer to Sonnet without its own gate.
"""
for old, new, label in (
    (A_OLD_TABLE, A_NEW_TABLE, "table"),
    (A_OLD_2, A_NEW_2, "consequence 2"),
):
    if new in a:
        print(f"analysis already fixed: {label}")
        continue
    assert a.count(old) == 1, ("analysis", label, a.count(old))
    a = a.replace(old, new)
    A.write_text(a, encoding="utf-8")
    print(f"analysis fixed: {label}")

G = OUT / "SONNET-VS-OPUS55-GATE.md"
g = G.read_text(encoding="utf-8")
G_OLD = """   What the counter cannot show, the canary settles
   (`system_delivery_canary.py`, run after this section was first drafted): the
   system message **is** delivered - both models obey a canary written only into
   the system at 129 and 3,131 chars - and at **60,774 chars Opus 5.5 still
   obeys it while Sonnet 5 does not** (its reply paraphrases the head of the
   stack: "This system serves as an EU AI Act Legal Specialist...", and misses
   the tail canary). Consequences: the payload cut is a *behavioral* lever
   wherever the stack is delivered (the single-turn shape: easy mode and the
   opening hard dispatches of a run), not an inert byte reduction; and
   Sonnet's long-system handling is a second, config-level reason not to
   promote it.
"""
G_NEW = """   What the counter cannot show, the canary settles
   (`system_delivery_canary.py --reps 3`, 18 calls, run after this section was
   first drafted): the system message **is** delivered - 3/3 at 129 and 3,131
   chars for both models - and at **60,774 chars Opus 5.5 obeys 3/3 while
   Sonnet 5 obeys 1/3**. That is not a transport drop: the wrapper's own log
   records both long calls as `System prompt 60877 chars >= 30000 argv limit -
   passing via --system-prompt-file` (`claude_cli.py` spills >= 30,000 chars to
   a temp file), i.e. the same path for both models, so the divergence is
   model-side adherence to a tail instruction inside a 60k stack. Consequences:
   the payload cut is a *behavioral* lever wherever the stack is delivered (the
   single-turn shape: easy mode and the opening hard dispatches of a run), not
   an inert byte reduction; and a long system prompt is a weaker contract on
   Sonnet than on Opus, which is a second reason not to promote it on this
   configuration.
"""
if G_NEW in g:
    print("gate doc already fixed")
else:
    assert g.count(G_OLD) == 1, ("gate", g.count(G_OLD))
    G.write_text(g.replace(G_OLD, G_NEW), encoding="utf-8")
    print("gate doc fixed")
