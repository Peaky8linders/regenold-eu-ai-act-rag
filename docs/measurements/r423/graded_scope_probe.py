"""R423.3 — WHICH system prompt does a hard-mode dispatch actually carry?

The R423 need-proportional gate published a scope note claiming that both of its
arms ran "the stripped 61-char persona" path. That is a claim about *what gets
dispatched*, so it has to be measured at the provider seam rather than read off
``history_turn_count``. This probe drives REAL hard-mode rows through the real
route (in-process, ``evals.regenold.runner_v2._post_local``) and records, for
every primary-leg dispatch, the row, the turn, the user-payload size and the
system-prompt size.

The finding it exists to keep honest, from ``_graph_rag_impl``'s own predicate::

    if history_turn_count is not None and history_turn_count <= 1 and _single_turn_full_system:
        _full_system = True

``run_official_batch._run_hard`` keeps a ROLLING conversation that starts empty,
so the first rows of a hard run read ``history_turn_count`` 0 and 1 and therefore
receive the FULL system prompt; every later row receives the persona. The scope
note's blanket "persona only" is wrong for those leading rows.

Run::

    .venv/Scripts/python.exe -m docs.measurements.r423.graded_scope_probe
    .venv/Scripts/python.exe -m docs.measurements.r423.graded_scope_probe --ids rg_004
    .venv/Scripts/python.exe -m docs.measurements.r423.graded_scope_probe --ids rg_001,rg_004

Reports the per-dispatch table and a verdict line naming the rows that took the
full prompt.

The `--ids` runs are the decisive pair: **the same row, the same harness, only its
POSITION differs.** `rg_004` as the only row reads `history_turn_count` 0 and takes
the full system prompt; `rg_004` behind `rg_001` reads 2 and takes the persona. That
is what makes this a harness artifact rather than a property of a row, and it is why
`--resume` (which restarted the rolling history) put a real difference in the system
slot between a resumed arm and a continuous one.
"""

from __future__ import annotations

import os

# The shipped default is ON; assert that default rather than a local override.
for _flag in (
    "REGENOLD_STAGE2_FULL_SYSTEM",
    "REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN",
):
    os.environ.pop(_flag, None)

CALLS: list[tuple[str, str, int, int]] = []
COUNTER: dict[str, str | None] = {"row": None, "turn": None}

from app.llm import openai_wrapper_provider as _OWP  # noqa: E402

_ORIG = _OWP._OpenAIWrapperProvider.complete

FULL_MIN_CHARS = 10_000


def _spy(self, req):  # noqa: ANN001, ANN201 - transport seam
    CALLS.append(
        (
            str(COUNTER["row"]),
            str(COUNTER["turn"]),
            len(req.user or ""),
            len(req.system or ""),
        )
    )
    return _ORIG(self, req)


_OWP._OpenAIWrapperProvider.complete = _spy

import evals.regenold.run_official_batch as _R  # noqa: E402
from evals.regenold.official_batch import load_official_batch  # noqa: E402
from evals.regenold.run_official_batch import _run_hard, select_rows  # noqa: E402
from evals.regenold.runner_v2 import _post_local  # noqa: E402

#: A handful of leading rows is the whole point: the effect is positional.
DEFAULT_IDS = "rg_001,rg_004,rg_007,rg_010,rg_013,rg_016"


class _DevNull:
    def write(self, _s: str) -> None:  # pragma: no cover - sink
        pass

    def flush(self) -> None:  # pragma: no cover - sink
        pass


def _patch_builders() -> None:
    orig_b1, orig_b2 = _R.build_hard_messages, _R.build_pushback_messages

    def build1(row, history):  # noqa: ANN001, ANN202
        COUNTER["row"], COUNTER["turn"] = row.id, "t1"
        print(
            f"\n--- {row.id}: history_msgs={len(history)} "
            f"request_msgs={len(history) + 1} "
            f"history_turn_count<=1={len(history) <= 1}",
            flush=True,
        )
        return orig_b1(row, history)

    def build2(row, history, first):  # noqa: ANN001, ANN202
        COUNTER["row"], COUNTER["turn"] = row.id, "pb"
        print(
            f"    pushback request_msgs={len(history) + 3} "
            f"history_msgs={len(history)}",
            flush=True,
        )
        return orig_b2(row, history, first)

    _R.build_hard_messages = build1
    _R.build_pushback_messages = build2


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ids", default=DEFAULT_IDS, help="comma-separated official row ids")
    rows = select_rows(list(load_official_batch()), ids=ap.parse_args().ids)
    print(f"rows: {[r.id for r in rows]}", flush=True)
    _patch_builders()
    _run_hard(rows, _post_local, "local", "unused", 300, _DevNull(), sample=0)

    print("\n=== per-dispatch (row, turn, user_chars, system_chars) ===", flush=True)
    full_rows: list[str] = []
    for row_id, turn, user_chars, system_chars in CALLS:
        if system_chars >= FULL_MIN_CHARS:
            tag = "FULL"
            if row_id not in full_rows:
                full_rows.append(row_id)
        elif system_chars < 200:
            tag = "persona"
        else:
            tag = f"OTHER({system_chars})"
        print(f"  {row_id} {turn:3s} user={user_chars:7d} system={system_chars:6d} {tag}")

    print(
        "\nVERDICT: full system prompt reached "
        f"{full_rows or 'no rows'} (of {[r.id for r in rows]}); "
        "all other dispatches carried the persona.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
