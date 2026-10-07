"""R460 follow-up: the 'SLOW is not DOWN' probe rescue must be BOUNDED.

``_install_stage2_transport_guard`` aborts a live batch after five consecutive
primary failures, because a run whose Stage-2 primary cannot answer grades
deterministic Stage-1 drafts (R423: 90 minutes, 243 calls). R460 added one tiny
PRIMARY probe before the abort so a SLOW tunnel is not mistaken for a DEAD one. A
16-token ping is a much weaker question than "can a real 20-100k-char Stage-2
request be served", so a failure that spares the ping but not the real request
(read timeouts at the request budget, ``api_status_500 No response from Claude
Code``, a size-dependent 429, an HTTP-200 empty body) reset the counter forever and
the guard never fired: 40 rows drawn on deterministic drafts, no abort.

These tests drive the REAL installer over a real provider class whose transport is
faked at the class method, and assert on call counts and on where the run stops,
never on source text.
"""

from __future__ import annotations

import contextlib
import io
import json
from typing import Any

import pytest

_TIMEOUT = "network_error: The read operation timed out"
_NO_RESPONSE = "api_status_500: No response from Claude Code"
_RATE_LIMIT = "api_status_429: rate_limit_error"


def _body(served_by: str) -> dict[str, Any]:
    return {
        "reasoning": json.dumps(
            {
                "stage2_polish": served_by != "deterministic",
                "notes": [f"stage2_served_by={served_by}"],
            }
        )
    }


def _poster_result(served_by: str) -> tuple:
    """What ``_post_local`` / ``_post`` actually return: a 6-tuple, not the body."""
    return (_body(served_by), 1000.0, 200, None, 1, [])


class _Transport:
    """Stage-2 sized requests fail on the rows in ``fail_rows``; the ping answers."""

    def __init__(self, fail_rows: set[int], *, error: str, ping_text: str) -> None:
        self.fail_rows = fail_rows
        self.error = error
        self.ping_text = ping_text
        self.row = 0
        self.pings = 0
        self.abort_message = ""

    def __call__(self, _self, req):  # noqa: ANN001
        from app.llm import openai_wrapper_provider as wp

        if req.max_tokens == 16:
            self.pings += 1
            return wp.OpenAIWrapperResponse(text=self.ping_text, model="m", completion_tokens=1)
        if self.row in self.fail_rows:
            return wp.OpenAIWrapperResponse(error=self.error, model="m")
        return wp.OpenAIWrapperResponse(text="a polished answer " * 20, model="m")


def _drive(
    monkeypatch: pytest.MonkeyPatch,
    *,
    rows: int,
    fail_rows: set[int] | None = None,
    served: dict[int, str] | None = None,
    error: str = _TIMEOUT,
    ping_text: str = "alive",
    probe: str | None = None,
) -> tuple[int | None, _Transport, str]:
    """Run the guard row by row. Returns ``(aborted_at, transport, stdout)``."""
    from app.llm import openai_wrapper_provider as wp
    from evals.regenold import run_official_batch as rob

    if probe is None:
        monkeypatch.delenv("REGENOLD_BATCH_PROBE_BEFORE_ABORT", raising=False)
    else:
        monkeypatch.setenv("REGENOLD_BATCH_PROBE_BEFORE_ABORT", probe)
    provider = wp._OpenAIWrapperProvider.__new__(wp._OpenAIWrapperProvider)
    provider._base_url = "https://wrapper.example/v1"
    transport = _Transport(
        set(range(1, rows + 1)) if fail_rows is None else fail_rows,
        error=error,
        ping_text=ping_text,
    )
    monkeypatch.setattr(wp, "is_openai_wrapper_enabled", lambda: True)
    monkeypatch.setattr(wp, "get_openai_wrapper_provider", lambda: provider)
    monkeypatch.setattr(wp._OpenAIWrapperProvider, "complete", transport)
    _preflight, assert_healthy = rob._install_stage2_transport_guard(max_consecutive=5)

    out = io.StringIO()
    aborted: int | None = None
    with contextlib.redirect_stdout(out):
        for i in range(1, rows + 1):
            transport.row = i
            wp._OpenAIWrapperProvider.complete(
                provider, wp.OpenAIWrapperRequest(user="x" * 50_000, max_tokens=4096)
            )
            try:
                assert_healthy(_poster_result((served or {}).get(i, "deterministic")))
            except RuntimeError as exc:
                transport.abort_message = str(exc)
                aborted = i
                break
    return aborted, transport, out.getvalue()


@pytest.mark.parametrize("error", [_TIMEOUT, _NO_RESPONSE, _RATE_LIMIT])
def test_a_ping_that_answers_rescues_once_and_then_the_guard_aborts(monkeypatch, error) -> None:
    """The outage: every real Stage-2 request fails, the 16-token ping succeeds."""
    aborted, transport, out = _drive(monkeypatch, rows=40, error=error)
    assert aborted is not None, "40 rows drawn on deterministic drafts and the guard never fired"
    # One rescue (the first trip, row 5), then five more failures with no
    # primary-served row in between: abort at the SECOND trip.
    assert aborted == 10
    assert transport.pings == 1
    assert out.count("SLOW, not DOWN") == 1
    assert "deterministic Stage-1 drafts. Aborting." in transport.abort_message
    assert "already spent" in transport.abort_message


def test_a_genuinely_slow_tunnel_is_not_aborted(monkeypatch) -> None:
    """Five slow rows, the ping answers, then real calls succeed: the run finishes."""
    aborted, transport, out = _drive(
        monkeypatch,
        rows=40,
        fail_rows=set(range(1, 6)),
        served={i: "primary" for i in range(6, 41)},
    )
    assert aborted is None
    assert transport.pings == 1
    assert out.count("SLOW, not DOWN") == 1


def test_a_primary_served_row_earns_the_next_rescue(monkeypatch) -> None:
    """A slow tunnel keeps its protection across SEPARATE slow patches."""
    slow = set(range(1, 6)) | set(range(7, 12)) | set(range(13, 18)) | set(range(19, 24))
    aborted, transport, _ = _drive(
        monkeypatch,
        rows=40,
        fail_rows=slow,
        served={i: "primary" for i in (6, 12, 18, *range(24, 41))},
    )
    assert aborted is None
    assert transport.pings == 4  # one rescue per slow patch, each earned by a served row


def test_a_primary_served_row_does_not_excuse_a_later_outage(monkeypatch) -> None:
    aborted, transport, _ = _drive(
        monkeypatch,
        rows=40,
        fail_rows=set(range(1, 6)) | set(range(7, 40)),  # row 6 is served normally
        served={6: "primary"},
    )
    assert transport.pings == 2  # trip at row 5 (rescued), trip at row 11 (rescued)
    assert aborted == 16  # trip at row 16: nothing primary-served since the last rescue


def test_an_empty_200_ping_is_not_proof_the_leg_is_alive(monkeypatch) -> None:
    for blank in ("", "   \n"):
        aborted, transport, out = _drive(monkeypatch, rows=40, ping_text=blank)
        assert aborted == 5
        assert transport.pings == 1
        assert "SLOW, not DOWN" not in out


def test_probe_off_restores_the_abort_at_the_first_trip(monkeypatch) -> None:
    aborted, transport, _ = _drive(monkeypatch, rows=40, probe="0")
    assert aborted == 5
    assert transport.pings == 0


def test_the_guard_reads_the_leg_from_the_posters_tuple(monkeypatch) -> None:
    """``guarded_poster`` hands ``check`` the 6-tuple. A fallback-served row must be
    recognised through it, or the R431 leg-aware branch never runs in a real batch."""
    aborted, transport, out = _drive(
        monkeypatch,
        rows=8,
        served={i: "fallback" for i in range(1, 9)},
        error=_NO_RESPONSE,
        probe="0",
    )
    assert aborted is None
    assert transport.pings == 0
    assert "FALLBACK leg is answering" in out


def test_a_bare_body_dict_is_still_read(monkeypatch) -> None:
    """The pre-existing callers (and the R431 tests) hand the body itself."""
    from app.llm import openai_wrapper_provider as wp
    from evals.regenold import run_official_batch as rob

    provider = wp._OpenAIWrapperProvider.__new__(wp._OpenAIWrapperProvider)
    provider._base_url = "https://wrapper.example/v1"
    monkeypatch.delenv("REGENOLD_BATCH_PROBE_BEFORE_ABORT", raising=False)
    transport = _Transport(set(range(1, 9)), error=_NO_RESPONSE, ping_text="alive")
    monkeypatch.setattr(wp, "is_openai_wrapper_enabled", lambda: True)
    monkeypatch.setattr(wp, "get_openai_wrapper_provider", lambda: provider)
    monkeypatch.setattr(wp._OpenAIWrapperProvider, "complete", transport)
    _preflight, assert_healthy = rob._install_stage2_transport_guard(max_consecutive=5)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        for i in range(1, 9):
            transport.row = i
            wp._OpenAIWrapperProvider.complete(
                provider, wp.OpenAIWrapperRequest(user="x" * 50_000, max_tokens=4096)
            )
            assert_healthy(_body("fallback"))
    assert "FALLBACK leg is answering" in out.getvalue()
    assert transport.pings == 0
