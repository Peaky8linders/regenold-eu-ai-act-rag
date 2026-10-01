"""R460 — the row writer must carry Stage-2 usage and payload shape.

The engine writes one note per successful primary dispatch::

    stage2_usage in=10175 out=192 system_chars=60643 user_chars=40700 turns=1

Why the sizes ride along with the counts: the wrapper's ``usage`` is a character
heuristic over the user message (``round(len(user)/4.0)``, verified to the digit
on 4 draws and 6 canary calls) and ignores the system stack entirely, while a
canary test shows the stack IS delivered at short/mid sizes and even at 60,774
chars for Opus 5.5 - but not for Sonnet 5. A board is only interpretable if the
row says WHICH payload shape was sent and what the transport counted it as.

Also pins the R460 harness probe: a tripped primary is confirmed with one tiny
call before a whole sample is thrown away (slow is not down).
"""

from __future__ import annotations

import json

from evals.regenold.run_official_batch import _provenance


def _body(*notes: str) -> dict:
    return {"reasoning": json.dumps({"stage2_polish": True, "notes": [*notes]})}


def test_usage_note_lands_on_the_row() -> None:
    p = _provenance(
        _body(
            "stage2_model=claude-opus-5-5 complex=False",
            "stage2_served_by=primary",
            "stage2_usage in=10175 out=192 system_chars=60643 "
            "user_chars=40700 turns=1",
        )
    )
    assert p["stage2_tokens_in"] == 10175
    assert p["stage2_tokens_out"] == 192
    assert p["stage2_system_chars"] == 60643
    assert p["stage2_user_chars"] == 40700
    assert p["stage2_history_turns"] == 1
    # R292/R418 fields must survive alongside the new ones.
    assert p["stage2_model"] == "claude-opus-5-5"
    assert p["stage2_served_by"] == "primary"


def test_missing_note_adds_no_usage_keys() -> None:
    p = _provenance(_body("stage2_model=claude-sonnet-5 complex=False"))
    for key in (
        "stage2_tokens_in",
        "stage2_tokens_out",
        "stage2_system_chars",
        "stage2_user_chars",
        "stage2_history_turns",
    ):
        assert key not in p


def test_malformed_usage_is_fail_soft() -> None:
    p = _provenance(
        _body("stage2_usage in=abc out= system_chars= user_chars=0 turns=none")
    )
    # Every unparsable field is dropped, nothing raises, and the one good
    # field still lands.
    assert p.get("stage2_tokens_in") is None
    assert p.get("stage2_user_chars") == 0


def test_the_slow_not_down_probe_is_wired_and_defaults_on() -> None:
    import inspect

    from evals.regenold import run_official_batch as rob

    src = inspect.getsource(rob._install_stage2_transport_guard)
    assert "def _primary_liveness_probe() -> bool:" in src
    assert 'REGENOLD_BATCH_PROBE_BEFORE_ABORT", "1"' in src
    assert "if _primary_liveness_probe():" in src
    # The probe must sit before the abort, not after it.
    assert src.index("if _primary_liveness_probe():") < src.index(
        "deterministic Stage-1 drafts. Aborting."
    )
