"""R366 — ``REGENOLD_PARENT_COLLAPSE`` is WIRED, and these tests prove it fires.

a659849 (the R320-R328 port) brought ``_parent_collapse_enabled`` and
``_collapse_parent_when_subpoint_cited`` across from the upstream evaluation
repo together with their unit tests (``test_r325_parent_collapse.py``), the
``.env.example`` row, the ``_engine_cache_key`` entry, the AGENTS.md pipeline
diagram and the CLAUDE.md flag table — but NOT the upstream call site (the
source repo calls it as the last reference pass in ``app/routes/regenold.py``).
``git log -S "_collapse_parent_when_subpoint_cited" -- app/routes/regenold.py``
returns exactly that one commit, and it adds only the two ``def`` lines. So the
flag was inert for the whole life of the branch while two doctrine documents
drew it as a live pass.

That is the R329 / R330 failure class, twice paid for: three rerank placements
all read correctly in the diff and all made ZERO calls, and the entire R327
semantic layer never executed because one call site dropped one argument. The
lesson recorded in CLAUDE.md is that default-ON + cache-keyed + unit-tested +
documented is NOT evidence a flag runs.

So these tests never assert on the shape of the route code. They assert on
observable behaviour at the wire:

  1. **The call site is REACHED.** With the flag ON, a real route request
     invokes the helper. This is the single assertion whose absence let the
     drift live.
  2. **The gate is two-sided.** With the flag OFF the helper is never called —
     a guard whose OFF state behaves like its ON state is the inert-feature
     trap R360 names explicitly.
  3. **The return value reaches the WIRE.** A stub returning a strictly
     shorter list changes ``response.references``. This is what distinguishes
     "applied" from "computed and discarded" — a failure mode that would
     survive test 1 on its own.
  4. **It runs LAST.** Nothing after the call site re-inflates the list, which
     is the whole point of the placement: ``_collapse_parent_refs`` already
     implements this rule mid-pipeline, immediately before
     ``_reemit_parents_for_subpoints`` (R87-C, default ON) re-ADDS the parent.
  5. **It is a NO-OP offline, and that is PINNED, not assumed.** Head+leaf
     clusters are minted live by ``_surface_prose_subpoints``
     (``_stage2_landed``-gated); offline, the R276-D1 ``auto`` mode has already
     resolved every mixed cluster before control reaches the collapse. Expect
     +0.0000 on any deterministic instrument and do NOT read it as a broken
     lever. If that test fails, the offline path started producing collapsible
     pairs and davidath neutrality must be re-measured before the flag moves.

The flag stays DEFAULT OFF: this pass DROPS references (R142.1 — a positional
drop lost a live pairwise judge 11-0, p=0.001) and it knowingly overrides the
R274 curated-intercept protection. Ship it only behind an
``evals.harness.easyhard_ab`` win, which is the gold-bearing harness.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.main import app
from app.rate_limit import limiter

_KEY = "regenold-r366-eval-key"

#: Returns 5 offline refs, so a stub that drops one is observable on the wire.
_MULTI_REF_Q = (
    "What obligations does a provider of a high-risk AI system have "
    "under Article 16?"
)


@pytest.fixture(autouse=True)
def _reset_rate_limit() -> None:
    try:
        limiter.reset()
    except Exception:  # noqa: BLE001 — never block a test on cleanup
        pass


@pytest.fixture
def _client():
    prev = settings.regenold.api_key
    settings.regenold.api_key = SecretStr(_KEY)
    try:
        with TestClient(app, headers={"X-Regenold-Api-Key": _KEY}) as c:
            yield c
    finally:
        settings.regenold.api_key = prev


def _ask(client: TestClient, question: str, *, reasoning: bool = False) -> dict:
    url = "/api/v1/regenold/eu-ai-act/ask"
    if reasoning:
        url += "?include_reasoning=true"
    r = client.post(url, json=[{"role": "user", "content": question}])
    assert r.status_code == 200, r.text
    return r.json()


def _spy_factory() -> tuple[list[list[str]], object]:
    seen: list[list[str]] = []

    def _spy(refs: list[str]) -> list[str]:
        seen.append(list(refs))
        return list(refs)

    return seen, _spy


class TestTheCallSiteIsReached:
    """The assertion whose absence let ``REGENOLD_PARENT_COLLAPSE`` go inert."""

    def test_flag_on_invokes_the_helper(
        self, _client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen, spy = _spy_factory()
        monkeypatch.setenv("REGENOLD_PARENT_COLLAPSE", "1")
        monkeypatch.setattr(
            "app.routes.regenold._collapse_parent_when_subpoint_cited", spy
        )
        _ask(_client, _MULTI_REF_Q)
        assert seen, (
            "REGENOLD_PARENT_COLLAPSE=1 but _collapse_parent_when_subpoint_cited "
            "was never called — the route call site is missing or unreachable "
            "(the exact R329 zero-calls failure)"
        )

    def test_flag_off_never_invokes_the_helper(
        self, _client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen, spy = _spy_factory()
        monkeypatch.setenv("REGENOLD_PARENT_COLLAPSE", "0")
        monkeypatch.setattr(
            "app.routes.regenold._collapse_parent_when_subpoint_cited", spy
        )
        _ask(_client, _MULTI_REF_Q)
        assert not seen, (
            "the pass ran with the flag OFF — a guard whose OFF state behaves "
            "like its ON state is the R360 inert-feature trap"
        )

    def test_helper_receives_the_final_reference_list(
        self, _client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """It must see the refs the route is about to ship, not an early draft."""
        seen, spy = _spy_factory()
        monkeypatch.setenv("REGENOLD_PARENT_COLLAPSE", "1")
        monkeypatch.setattr(
            "app.routes.regenold._collapse_parent_when_subpoint_cited", spy
        )
        body = _ask(_client, _MULTI_REF_Q)
        assert seen
        # No-op spy → the wire equals exactly what the helper was handed.
        assert seen[-1] == (body.get("references") or [])


class TestTheResultReachesTheWire:
    """Distinguishes "applied" from "computed and discarded"."""

    def test_a_dropping_stub_shortens_the_wire(
        self, _client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_PARENT_COLLAPSE", "0")
        baseline = _ask(_client, _MULTI_REF_Q).get("references") or []
        assert len(baseline) >= 2, (
            f"fixture question no longer returns multiple refs: {baseline}"
        )

        monkeypatch.setenv("REGENOLD_PARENT_COLLAPSE", "1")
        monkeypatch.setattr(
            "app.routes.regenold._collapse_parent_when_subpoint_cited",
            lambda refs: list(refs)[:-1],
        )
        after = _ask(_client, _MULTI_REF_Q).get("references") or []
        assert after == baseline[:-1], (
            "the collapse result did not reach the wire — nothing may re-add or "
            f"overwrite refs after the call site. baseline={baseline} after={after}"
        )

    def test_flag_off_ignores_the_same_stub(
        self, _client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_PARENT_COLLAPSE", "0")
        baseline = _ask(_client, _MULTI_REF_Q).get("references") or []
        monkeypatch.setattr(
            "app.routes.regenold._collapse_parent_when_subpoint_cited",
            lambda refs: list(refs)[:-1],
        )
        after = _ask(_client, _MULTI_REF_Q).get("references") or []
        assert after == baseline, "the OFF state must be byte-identical"

    def test_the_drop_is_recorded_in_the_reasoning_trace(
        self, _client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An operator-visible signal, per the R360 'prove it fires' rule."""
        monkeypatch.setenv("REGENOLD_PARENT_COLLAPSE", "1")
        monkeypatch.setattr(
            "app.routes.regenold._collapse_parent_when_subpoint_cited",
            lambda refs: list(refs)[:-1],
        )
        body = _ask(_client, _MULTI_REF_Q, reasoning=True)
        notes = json.loads(body.get("reasoning") or "{}").get("notes") or []
        assert any(n.startswith("parent_collapse dropped=") for n in notes), notes

    def test_the_trace_still_equals_the_wire(
        self, _client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The call site must sit BEFORE the trace finalisation."""
        monkeypatch.setenv("REGENOLD_PARENT_COLLAPSE", "1")
        monkeypatch.setattr(
            "app.routes.regenold._collapse_parent_when_subpoint_cited",
            lambda refs: list(refs)[:-1],
        )
        body = _ask(_client, _MULTI_REF_Q, reasoning=True)
        traced = json.loads(body.get("reasoning") or "{}").get("references")
        assert traced == (body.get("references") or [])


class TestFailSoft:
    def test_a_raising_helper_never_500s_the_route(
        self, _client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_PARENT_COLLAPSE", "0")
        baseline = _ask(_client, _MULTI_REF_Q).get("references") or []

        def _boom(refs: list[str]) -> list[str]:
            raise RuntimeError("guard blew up")

        monkeypatch.setenv("REGENOLD_PARENT_COLLAPSE", "1")
        monkeypatch.setattr(
            "app.routes.regenold._collapse_parent_when_subpoint_cited", _boom
        )
        assert (_ask(_client, _MULTI_REF_Q).get("references") or []) == baseline


#: Spans the sub-point-emitting topics (``SUBPOINT_TOPIC_MAP``), the
#: definitional ``Article 3.N`` path, and the multi-article obligation dumps —
#: i.e. every offline shape that could plausibly mint a head+leaf pair.
_OFFLINE_QUESTIONS = [
    "Is social scoring by a public authority prohibited?",
    "Can an employer use emotion recognition on staff?",
    "Is untargeted scraping of facial images to build a database allowed?",
    "Are subliminal manipulative techniques prohibited?",
    "Is real-time remote biometric identification in public spaces allowed?",
    "What is an AI system?",
    "What does provider mean?",
    "Which AI practices are prohibited?",
    "Is an AI system used for emergency triage in a hospital high-risk?",
    "When is a high-risk classification derogation available?",
    "What penalties apply for prohibited AI practices?",
    _MULTI_REF_Q,
]


class TestDoesNotPolluteTheR365GuardScan:
    """The R366 comment must not read as code to a neighbouring source scanner.

    `test_r365_recall_supplements.py::test_supplement_head_table_covers_every_head_the_code_can_append`
    regex-scans a SOURCE-TEXT slice of `app/routes/regenold.py` — everything
    between the R365 wire-guard marker and the R50/R131 trace-finalisation
    marker — for double-quoted `"Article N"` / `"Annex X"` literals, and
    asserts they are a subset of `RECALL_SUPPLEMENT_WIRE_HEADS`.

    The R366 block sits inside that window by construction (it is the last
    reference pass, and the window ends at the trace finalisation). So an
    illustrative ref list written with DOUBLE quotes in this block's comment is
    read as a head the R365 guard can emit. That actually happened: the comment
    quoted the R274 trade as `["Article 6.3", "Article 6", "Annex III"]` and
    the scan reported `Article 6` as an undeclared wire head. It is invisible
    to every file-scoped run of this module and only surfaces in a full-suite
    run, which is exactly how it nearly shipped.

    The fix is comment hygiene — single quotes for illustrative output — not a
    change to the R365 assertion, which is a real safety guard for a lever that
    can move wire citations. This test pins the hygiene so the trap cannot
    return via a future edit to the R366 comment.

    ⚠ The underlying brittleness is NOT fixed here and is worth fixing at the
    source: that scan treats comments as code, and its window will absorb any
    future block inserted before the trace finalisation.
    """

    def test_r366_block_adds_no_provision_literals_to_the_scan_window(self) -> None:
        import re
        from pathlib import Path

        route = (
            Path(__file__).resolve().parents[1] / "app" / "routes" / "regenold.py"
        ).read_text(encoding="utf-8")

        # The exact window the R365 test scans.
        window = route.split("# R365 — recall-supplement WIRE GUARD", 1)[1]
        window = window.split("# R50 / R131 — finalise the reasoning trace", 1)[0]
        assert "# R366 — R325 parent collapse" in window, (
            "the R366 block is no longer inside the R365 scan window — if it "
            "moved, re-check which scanner now covers it"
        )

        r366 = window.split("# R366 — R325 parent collapse", 1)[1]
        found = sorted(set(re.findall(r'"((?:Article \d+|Annex [IVX]+))"', r366)))
        assert not found, (
            "the R366 block contributes double-quoted provision literals "
            f"{found} to the R365 wire-guard scan window, which will be "
            "misread as heads the R365 guard can emit. Use single quotes for "
            "illustrative reference lists in this block's comment."
        )


class TestOfflineNoOpIsPinnedNotAssumed:
    """Why every deterministic instrument reads +0.0000 with the flag ON.

    Not a hedge — a tripwire. If these fail, the offline path started shipping
    head+leaf pairs, the flag became offline-measurable, and davidath
    neutrality (``article_heads`` invariance is unit-pinned, but the WIRE is
    not) must be re-measured before anyone flips it.
    """

    @pytest.mark.parametrize("question", _OFFLINE_QUESTIONS)
    def test_wire_is_identical_on_and_off(
        self, _client: TestClient, monkeypatch: pytest.MonkeyPatch, question: str
    ) -> None:
        monkeypatch.setenv("REGENOLD_PARENT_COLLAPSE", "0")
        off = _ask(_client, question).get("references") or []
        monkeypatch.setenv("REGENOLD_PARENT_COLLAPSE", "1")
        on = _ask(_client, question).get("references") or []
        assert on == off, (
            f"offline wire changed for {question!r}: {off} -> {on}. The offline "
            "path now mints head+leaf pairs; re-measure davidath before "
            "treating REGENOLD_PARENT_COLLAPSE as deterministically neutral."
        )

    @pytest.mark.parametrize("question", _OFFLINE_QUESTIONS)
    def test_no_offline_wire_ships_a_head_beside_its_own_leaf(
        self, _client: TestClient, question: str
    ) -> None:
        """The corollary: there is nothing offline for the pass to collapse."""
        from app.routes.regenold import _clamp_ref_head

        refs = _ask(_client, question).get("references") or []

        def _head(r: str) -> str:
            return _clamp_ref_head(r) or r.strip()

        heads_with_own_leaf = {_head(r) for r in refs if _head(r) != r.strip()}
        redundant = [
            r
            for r in refs
            if r.strip() == _head(r) and _head(r) in heads_with_own_leaf
        ]
        assert not redundant, (
            f"{question!r} ships a bare head beside its own leaf: {redundant} in "
            f"{refs} — the offline no-op premise no longer holds"
        )
