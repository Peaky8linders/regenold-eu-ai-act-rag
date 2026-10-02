"""R461.6 applier - capture the row-provenance roster in the published read.

Idempotent (each edit checks its NEW text first). Run from the worktree root:

    python docs/measurements/r461/apply_captured_roster.py
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
LF = chr(10)
CRLF = chr(13) + chr(10)


def edit(path: str, old: str, new: str) -> None:
    p = REPO / path
    raw = open(p, encoding="utf-8", newline="").read()
    nl = CRLF if CRLF in raw else LF
    old_nl = old.replace(LF, nl)
    new_nl = new.replace(LF, nl)
    if new_nl in raw:
        print("already applied:", path)
        return
    found = raw.count(old_nl)
    assert found == 1, (path, found)
    open(p, "w", encoding="utf-8", newline="").write(raw.replace(old_nl, new_nl, 1))
    print("applied:", path)


# --------------------------------------------------------------------------- #
# paired_ab - the roster resolver accepts a captured fallback
# --------------------------------------------------------------------------- #
edit(
    "evals/official/paired_ab.py",
    '''def _provenance_roster(
    score_path: Path, override: str | Path | None
) -> tuple[dict[str, str] | None, str]:
    """Map row id -> eligibility reason, from the arm's own checkpoint.

    Returns ``(roster, source)``; ``roster`` is ``None`` when the checkpoint
    cannot be read, and the source string always names what was tried, so the
    report can say which file the scope was decided on.
    """
    rows, source = _ckpt_rows(score_path, override)
    if rows is None:
        return None, source
    return {qid: _row_scope_reason(row.get("provenance")) for qid, row in rows.items()}, source''',
    '''def _provenance_roster(
    score_path: Path,
    override: str | Path | None,
    provided: dict[str, str] | None = None,
) -> tuple[dict[str, str] | None, str]:
    """Map row id -> eligibility reason, from the arm's own checkpoint.

    Returns ``(roster, source)``; ``roster`` is ``None`` when the checkpoint
    cannot be read, and the source string always names what was tried, so the
    report can say which file the scope was decided on.

    ``provided`` is a roster CAPTURED by an earlier read (its ``veto.roster``
    block, R461.6). A live checkpoint always wins; the captured roster is used
    only when the file cannot be read, so a published scope stays re-applicable
    to a verdict whose gitignored checkpoint is gone.
    """
    rows, source = _ckpt_rows(score_path, override)
    if rows is not None:
        return {qid: _row_scope_reason(row.get("provenance")) for qid, row in rows.items()}, source
    if provided is not None:
        return (
            dict(provided),
            f"captured roster in the published read (checkpoint: {source})",
        )
    return None, source''',
)

# --------------------------------------------------------------------------- #
# paired_ab - _veto_block takes the captured rosters and records its own
# --------------------------------------------------------------------------- #
edit(
    "evals/official/paired_ab.py",
    '''    veto_scope: str,
    seed: int,
    draw_stability: dict | None = None,
) -> dict:
    """Hard rule #8, read on the rows the lever actually ran.''',
    '''    veto_scope: str,
    seed: int,
    draw_stability: dict | None = None,
    a_roster: dict[str, str] | None = None,
    b_roster: dict[str, str] | None = None,
) -> dict:
    """Hard rule #8, read on the rows the lever actually ran.''',
)

edit(
    "evals/official/paired_ab.py",
    '''    roster_a, src_a = _provenance_roster(a_path, a_ckpt)
    roster_b, src_b = _provenance_roster(b_path, b_ckpt)''',
    '''    roster_a, src_a = _provenance_roster(a_path, a_ckpt, a_roster)
    roster_b, src_b = _provenance_roster(b_path, b_ckpt, b_roster)''',
)

edit(
    "evals/official/paired_ab.py",
    '''        "provenance": {
            "arm_a": src_a,
            "arm_b": src_b,
            "join": "ckpt row id -> score row id",
            "bootstrap_seed": seed,
        },
        "reasons": dict(SCOPE_REASONS),''',
    '''        "provenance": {
            "arm_a": src_a,
            "arm_b": src_b,
            "join": "ckpt row id -> score row id",
            "bootstrap_seed": seed,
        },
        # R461.6 - the per-row provenance this scope was read FROM, captured so
        # the rule can be re-applied to this verdict after the gitignored
        # checkpoint is gone. `captured` is False and `reasons` empty when the
        # checkpoint could not be read; `considered` is the row set the scope
        # was actually decided on, which no roster lookup can reconstruct.
        "roster": {
            "arm_a": {
                "captured": roster_a is not None,
                "source": src_a,
                "reasons": dict(roster_a or {}),
            },
            "arm_b": {
                "captured": roster_b is not None,
                "source": src_b,
                "reasons": dict(roster_b or {}),
            },
            "considered": list(considered),
        },
        "reasons": dict(SCOPE_REASONS),''',
)

# --------------------------------------------------------------------------- #
# paired_ab - compare passes the captured rosters through
# --------------------------------------------------------------------------- #
edit(
    "evals/official/paired_ab.py",
    '''    a_redraw: str | Path | None = None,
    a_redraw_ckpt: str | Path | None = None,
) -> dict:
    """Full paired comparison; ``a`` = baseline arm, ``b`` = branch arm.''',
    '''    a_redraw: str | Path | None = None,
    a_redraw_ckpt: str | Path | None = None,
    a_roster: dict[str, str] | None = None,
    b_roster: dict[str, str] | None = None,
) -> dict:
    """Full paired comparison; ``a`` = baseline arm, ``b`` = branch arm.''',
)

edit(
    "evals/official/paired_ab.py",
    '''    in ``draw_stability.drops_unstable`` rather than silently skipped. Without
    it the single-draw reading stands - the stricter one - and the payload says
    ``stabilized: false``.
    """''',
    '''    in ``draw_stability.drops_unstable`` rather than silently skipped. Without
    it the single-draw reading stands - the stricter one - and the payload says
    ``stabilized: false``.

    ``a_roster``/``b_roster`` are rosters CAPTURED by an earlier read (its
    ``veto.roster`` block, R461.6). They are used ONLY when that arm's
    checkpoint cannot be read, so a verdict stays re-auditable after a
    gitignored checkpoint is gone; a live checkpoint always wins.
    """''',
)

edit(
    "evals/official/paired_ab.py",
    '''        veto_scope=veto_scope,
        seed=seed,
        draw_stability=draw_stability,
    )''',
    '''        veto_scope=veto_scope,
        seed=seed,
        draw_stability=draw_stability,
        a_roster=a_roster,
        b_roster=b_roster,
    )''',
)

# --------------------------------------------------------------------------- #
# the audit - fall back to the captured roster when the checkpoint is gone
# --------------------------------------------------------------------------- #
edit(
    "docs/measurements/r461/audit_published_gates.py",
    '''2. RESOLVE PROVENANCE - the checkpoint each arm's score payload records; if that
   path is gone (``evals/bench/results`` is gitignored), an exact-BASENAME copy
   preserved inside the round's own directory. Nothing is matched fuzzily: a
   guessed checkpoint is not provenance.''',
    '''2. RESOLVE PROVENANCE - the checkpoint each arm's score payload records; if that
   path is gone (``evals/bench/results`` is gitignored), an exact-BASENAME copy
   preserved inside the round's own directory, else the read's own CAPTURED
   roster (R461.6, ``veto.roster`` - reads published before it carry none, and
   a live checkpoint always wins over the capture). Nothing is matched
   fuzzily: a guessed checkpoint is not provenance.''',
)

edit(
    "docs/measurements/r461/audit_published_gates.py",
    '''    ckpt_a, why_a = resolve_ckpt(score_a, index)
    ckpt_b, why_b = resolve_ckpt(score_b, index)
    out["provenance"] = {"arm_a": why_a, "arm_b": why_b}

    res_all = compare(score_a, score_b, veto_scope="all", a_ckpt=ckpt_a, b_ckpt=ckpt_b)
    res_lever = compare(score_a, score_b, veto_scope="lever", a_ckpt=ckpt_a, b_ckpt=ckpt_b)''',
    '''    ckpt_a, why_a = resolve_ckpt(score_a, index)
    ckpt_b, why_b = resolve_ckpt(score_b, index)
    # R461.6 - a read published since the roster was captured carries the
    # per-row provenance it was decided on. It is a FALLBACK, not a source: the
    # instrument prefers a live checkpoint, so this only answers when the file
    # is gone - which is exactly the case that made old verdicts unauditable.
    captured = (d.get("veto") or {}).get("roster") or {}

    def _captured(arm: str) -> dict[str, str] | None:
        block = captured.get(arm) or {}
        if not block.get("captured"):
            return None
        return dict(block.get("reasons") or {})

    roster_a, roster_b = _captured("arm_a"), _captured("arm_b")
    if roster_a is not None and ckpt_a is None:
        why_a = f"{why_a}; re-read from the read's CAPTURED roster"
    if roster_b is not None and ckpt_b is None:
        why_b = f"{why_b}; re-read from the read's CAPTURED roster"
    out["provenance"] = {"arm_a": why_a, "arm_b": why_b}

    res_all = compare(
        score_a, score_b, veto_scope="all",
        a_ckpt=ckpt_a, b_ckpt=ckpt_b, a_roster=roster_a, b_roster=roster_b,
    )
    res_lever = compare(
        score_a, score_b, veto_scope="lever",
        a_ckpt=ckpt_a, b_ckpt=ckpt_b, a_roster=roster_a, b_roster=roster_b,
    )''',
)

print("done")
