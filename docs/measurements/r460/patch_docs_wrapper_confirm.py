"""R460 - record the wrapper-transport confirmation and its verdict.

Marker-based (not transcription-based) replacements, each with a
single-occurrence assertion, so the patch cannot silently match the wrong text
in a document that carries non-ASCII characters:

1. `CONCISENESS-PROGRAM.md` section 5 (planned gate -> the two executed gates and
   the no-promotion verdict).
2. the same document's last caveat (it claimed no live board had been run).
3. `promote_conciseness_calibration.py` - mark it NOT APPLIED in its own header.
4. `CHECKPOINT.md` - append the entry.

Run:  ../../.venv/Scripts/python.exe docs/measurements/r460/patch_docs_wrapper_confirm.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DOCS = REPO / "docs" / "measurements" / "r460"
PROGRAM = DOCS / "CONCISENESS-PROGRAM.md"
PROMOTE = DOCS / "promote_conciseness_calibration.py"
CHECKPOINT = DOCS / "CHECKPOINT.md"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

NEW_S5 = """## 5. The gates that were run - and the verdict

Both levers shipped private-by-default, so the promotion question was a paired
board. The plan as written was:

> ~~`run_official_batch --mode hard --stride 3 --repeats 3 --branch-env
> REGENOLD_CONCISE_CALIBRATION=1` against the recorded `r460-cohere-hard-s3`
> baseline; score both with `--length-control`; acceptance ref_conciseness >= 85
> and ans_conciseness >= 92 with no correctness loss.~~

It was executed in a stronger shape - both arms drawn FRESH under one protocol and
one judge cache, rather than one arm against a day-old recorded baseline - and it
was executed twice, same protocol (`--mode hard --stride 3`, n=37, same judge
identity, `--length-control`), on two transports:

1. **Bedrock leg** (`eu.anthropic.claude-opus-4-6-v1`, inverted transport contract,
   both arms alike) - `GATE-CONCISENESS-BEDROCK.md`: ref_conc 59.14 -> 63.90
   (**+4.76 [+0.29, +10.43]**, the only axis whose CI excluded zero), ans_loose
   93.69 -> 95.95, ans_conc 82.99 -> 84.96, overall **+0.95**, gold heads 2 -> 2.
2. **The SHIPPED transport** (Claude Max wrapper, `claude-opus-5-5`) -
   `WRAPPER-CONFIRM.md`: ref_conc 58.43 -> 63.95 (**+5.52 [+0.71, +11.90]** - the
   count mechanism reproduces almost exactly), but **ans_conciseness 82.32 -> 77.84
   (-4.49 [-8.77, -0.68])**: on this model the block makes answers LONGER
   (+65 chars, 17/26 rows, CI [+10, +119]) and the board drops
   **86.90 -> 86.09**.

**Verdict: `REGENOLD_CONCISE_CALIBRATION` stays DEFAULT OFF.** The lever moved one
of the two conciseness axes the wrong way on the model that ships, so the
acceptance targets above are not close and are not claimed.
`promote_conciseness_calibration.py` is on disk, deliberately unapplied.

The wrapper board's correctness / tone / speed deltas are NOT lever effects, and
attributing them to the lever would be a measurement error: they are carried by
exactly two rows whose transport degraded differently (`rg_037` shipped a
`prior_turn` answer in B, `rg_049` a `deterministic` draft in A; the other 35 rows
have identical judged criteria vectors) plus B's retry-heavy draw (17 vs 5
degenerate-completion events, 8 vs 2 Bedrock fallback attempts). Section 3 of
`WRAPPER-CONFIRM.md` does that attribution row by row.

**The surviving sub-lever.** The block's two halves behaved differently: the
counted citation budget reproduces on both transports (about +5 pp ref_conc with
no other axis touched between legs), while the length battery (sentence count,
word ceiling, shape skeleton) helped on `opus-4-6` and hurt on `opus-5-5`. The
next gate is therefore the **count-only variant** - the same numeric budget with
the length clauses removed - before any default moves.

Replicates 2-3 of the wrapper gate were not spent: the tunnel's quota is the
scarce resource this round, and the deciding delta is systematic at the row level
rather than marginal. The launcher resumes them in one command
(`run_gate_wrapper.sh 3`).

"""

NEW_CAVEAT = """* Nothing in this program changes a default. Two live boards HAVE now been run
  with the lever (the Bedrock gate and the wrapper confirmation, section 5); the
  numbers in section 2 still describe the *shipped* board, because the lever was
  not promoted.
* A one-draw-per-row board (n=37) can only decide DIRECTION, and both gates were
  read that way. The wrapper verdict does not rest on a marginal delta: the
  length reversal is +65 chars on 17 of 26 same-leg rows with a CI excluding
  zero, while the delta the round was aiming at (ans_conciseness) moved against
  the intent.
"""

PROMOTE_STATUS = """**NOT APPLIED. The wrapper-transport confirmation REFUSED this promotion** (see
``WRAPPER-CONFIRM.md`` section 4): on the shipped transport the lever reverses
``ans_conciseness`` (-4.49) and drops the board overall (86.90 -> 86.09), while
its citation budget does reproduce (+5.52 ref_conciseness). Kept on disk as the
prepared patch for the count-only successor lever, which keeps this block's
numeric budget and removes its length battery.

"""

CHECKPOINT_ENTRY = """
---

## 2026-10-01 (Conciseness gate on the SHIPPED transport) -- REFUSED, default stays OFF

The Bedrock gate's stated confirmation step, executed on the transport and model
that actually ship: Claude Max wrapper, `claude-opus-5-5`, n=37 (`--stride 3`),
both arms drawn fresh under one protocol, one judge identity and one cache
(`bedrock:qwen.qwen3-235b-a22b-2507-v1:0:t=0.1:grouped:r=3`), scored with
`--length-control`. Tunnel liveness probed first (one call: `claude-opus-5-5`,
7.3 s, stop, `wrapper_tunnel_probe.py`). Arms `r460-tunnel-off-s3` (flag absent)
and `r460-tunnel-on-s3` (`REGENOLD_CONCISE_CALIBRATION=1`), 37/37 rows and 0
errors each, p50 21.4 s / 22.0 s. `WRAPPER-CONFIRM.md`; launcher
`run_gate_wrapper.sh`, scorer `score_gate_wrapper.sh`.

* Paired: **ref_conciseness 58.43 -> 63.95 (+5.52, CI [+0.71, +11.90], McNemar
  7/1)** -- the count mechanism REPRODUCES (Bedrock gate: +4.76 [+0.29, +10.43]),
  refs/row 2.78 -> 2.51, and the axis never touches the judge.
* But **ans_conciseness 82.32 -> 77.84 (-4.49, CI [-8.77, -0.68])**: on Opus 5.5
  the block makes answers LONGER (+65 chars, 17/26 rows, CI [+10, +119]; the
  Bedrock gate's opus-4-6 SHORTENED them 786.7 -> 755.8). Overall
  **86.90 -> 86.09 (-0.81)**; speed -1.96 (p<0.0001) is CONFOUNDED, not a lever
  result - B logged 17 degenerate-completion events and 8 Bedrock-fallback
  attempts against A's 5 and 2, so B paid more retries.
* Attribution, because the board alone misleads: the correctness / tone /
  gold-head deltas are NOT the lever. They are carried by exactly two rows whose
  transport degraded differently (`rg_037` shipped a `prior_turn` answer in B --
  its refs `Article 49.4/71.4/6.3` against the key's `Annex VIII.a`; `rg_049`
  shipped a `deterministic` draft in A), and the other 35 rows have identical
  judged criteria vectors (`wrapper_gate_subset.py`, recomputation asserted
  against the scored axis before it is used).
* **Verdict: NOT promoted.** `calibration_enabled()` keeps its allow-list; the
  prepared `promote_conciseness_calibration.py` is deliberately unapplied, and
  `CONCISENESS-PROGRAM.md` section 5 records the refusal plus the acceptance
  targets that are not claimed. Next gate: the COUNT-ONLY variant of the block
  (the citation budget without the length battery), the half that survived two
  transports.
* Replicates 2-3 were not spent (tunnel quota is the scarce resource; the
  deciding delta is systematic, not marginal). `run_gate_wrapper.sh 3` resumes
  them from the existing checkpoints if a draw-stability check is wanted.
"""


def _replace_section(path: Path, head_marker: str, tail_marker: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new.splitlines()[0] in text:
        print(f"already applied: {path.name} ({new.splitlines()[0]})")
        return
    assert text.count(head_marker) == 1, f"{path.name}: {head_marker!r} not unique"
    assert text.count(tail_marker) == 1, f"{path.name}: {tail_marker!r} not unique"
    i, j = text.index(head_marker), text.index(tail_marker)
    assert i < j, f"{path.name}: markers out of order"
    path.write_text(text[:i] + new + text[j:], encoding="utf-8")
    print(f"patched {path.name}: section {head_marker.strip()}")


def _replace_last_bullet(path: Path, marker: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new.splitlines()[0] in text:
        print(f"already applied: {path.name} (caveat)")
        return
    assert text.count(marker) == 1, f"{path.name}: caveat marker not unique"
    i = text.index(marker)
    path.write_text(text[:i] + new, encoding="utf-8")
    print(f"patched {path.name}: final caveat bullet")


def main() -> int:
    _replace_section(PROGRAM, "## 5. ", "## 6. ", NEW_S5)
    _replace_last_bullet(PROGRAM, "* Nothing in this program changes a default", NEW_CAVEAT)

    text = PROMOTE.read_text(encoding="utf-8")
    if "**NOT APPLIED." in text:
        print("already applied: promote_conciseness_calibration.py status")
    else:
        marker = '"""R460 promotion - ``REGENOLD_CONCISE_CALIBRATION`` allow-list -> default ON.\n\n'
        assert text.count(marker) == 1, "promotion docstring marker not unique"
        PROMOTE.write_text(text.replace(marker, marker + PROMOTE_STATUS, 1), encoding="utf-8")
        print("patched promote_conciseness_calibration.py status")

    text = CHECKPOINT.read_text(encoding="utf-8")
    if "Conciseness gate on the SHIPPED transport" in text:
        print("already applied: CHECKPOINT.md")
    else:
        assert text.endswith("\n"), "CHECKPOINT.md does not end with a newline"
        CHECKPOINT.write_text(text + CHECKPOINT_ENTRY, encoding="utf-8")
        print("appended CHECKPOINT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
