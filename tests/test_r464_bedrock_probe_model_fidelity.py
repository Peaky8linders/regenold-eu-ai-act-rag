"""R464 — the Bedrock health probe must dial the FALLBACK's own chain.

The instrument bug this pins, stated as a two-sided pair. Configure a deployment
whose Bedrock fallback cannot serve anything:

    REGENOLD_BEDROCK_MODEL         = eu.anthropic.claude-opus-4-6
    REGENOLD_BEDROCK_COMPLEX_MODEL = eu.anthropic.claude-opus-4-6
    REGENOLD_BEDROCK_FALLBACK_CHAIN= eu.anthropic.claude-opus-4-6

The fallback's ordered list is now exactly ``[opus-4-6]``, and opus-4-6 is
denied — so every real Stage-2 Bedrock call returns ``None`` and the deploy
serves deterministic answers. The probe used to walk the hand-mirrored literal
``BEDROCK_FALLBACK_PROBE_MODELS`` (Qwen 3 235B, Qwen 3 32B) and report
``status: ok`` the moment either answered, because nothing ties that literal to
``REGENOLD_BEDROCK_*``. That is a healthy reading for a leg that cannot answer —
the false *negative* an operator is least able to afford, since ``/healthz/llm``
is the one instrument reached for mid-outage.

The other half matters just as much: the same configuration with opus-4-6
available must report ``ok`` and NAME opus-4-6, so the fix cannot be "always
report down". Both halves run against one stub, so the only variable is the walk.

Everything here is offline — the per-model dial is stubbed and no AWS call is
made.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.llm import bedrock_client as bc

_OPUS = "eu.anthropic.claude-opus-4-6"  # a full profile id, so resolution is identity
_QWEN_235B = "qwen.qwen3-235b-a22b-2507-v1:0"
_QWEN_32B = "qwen.qwen3-32b-v1:0"


def _pin_fallback(monkeypatch, *, model: str = _OPUS, chain: str = _OPUS) -> None:
    """Pin every Bedrock knob to one non-Qwen model, and arm the credential."""
    monkeypatch.setenv("REGENOLD_BEDROCK_MODEL", model)
    monkeypatch.setenv("REGENOLD_BEDROCK_COMPLEX_MODEL", model)
    monkeypatch.setenv("REGENOLD_BEDROCK_FALLBACK_CHAIN", chain)
    monkeypatch.delenv("REGENOLD_STAGE2_BEDROCK_MODEL", raising=False)
    monkeypatch.delenv("REGENOLD_BEDROCK_STAGE1_MODEL", raising=False)
    monkeypatch.delenv("REGENOLD_OPUS_FOR_ALL", raising=False)
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "FAKE-TOKEN-FOR-TEST")


def _dial(monkeypatch, outcomes: dict[str, str]) -> list[str]:
    """Stub the single-model dial, recording the order it was asked in.

    ``model_id is None`` delegates to the REAL walk, so the resolution and the
    short-circuit under test are the production ones.
    """
    seen: list[str] = []
    real = bc.check_connectivity_and_permissions

    def _fake(model_id: str | None = None, models: Any = None) -> dict[str, Any]:
        if model_id is None:
            return real(model_id=None, models=models)
        seen.append(model_id)
        status = outcomes.get(model_id, "error")
        return {
            "status": status,
            "model": model_id,
            "error": None if status == "ok" else "api_access_denied_403",
            "elapsed_ms": 1,
        }

    monkeypatch.setattr(bc, "check_connectivity_and_permissions", _fake)
    return seen


class TestTheWalkIsTheFallbacksChain:
    def test_the_default_walk_equals_the_engine_chain(self, monkeypatch) -> None:
        """The pin: the walk is derived, not mirrored.

        Both question classes are compared, because the fallback is invoked for
        both and each resolves a different first tier.
        """
        from app.engines._graph_rag_impl import bedrock_fallback_model_chain

        for var in (
            "REGENOLD_BEDROCK_MODEL",
            "REGENOLD_BEDROCK_COMPLEX_MODEL",
            "REGENOLD_BEDROCK_FALLBACK_CHAIN",
            "REGENOLD_STAGE2_BEDROCK_MODEL",
            "REGENOLD_BEDROCK_STAGE1_MODEL",
        ):
            monkeypatch.delenv(var, raising=False)

        expected: list[str] = []
        for complex_question in (False, True):
            for _m in bedrock_fallback_model_chain(
                stage_name="Stage 2", complex_question=complex_question
            ):
                if _m not in expected:
                    expected.append(_m)

        assert list(bc.stage2_probe_models()) == expected
        # ...and it is NOT the pinned literal, which is the whole point.
        assert list(bc.stage2_probe_models()) != list(bc.BEDROCK_FALLBACK_PROBE_MODELS)

    def test_a_custom_chain_replaces_the_pinned_literal(self, monkeypatch) -> None:
        _pin_fallback(monkeypatch)
        assert list(bc.stage2_probe_models()) == [bc.resolve_bedrock_model(_OPUS)]

    def test_the_first_probe_model_follows_the_policy_override(self, monkeypatch) -> None:
        """``REGENOLD_STAGE2_BEDROCK_MODEL`` is the lever the FALLBACK passes.

        ``_try_bedrock_fallback`` calls ``_bedrock_complete_for_graph_rag(...,
        model_override=_s2pol.stage2_fallback_model() or None)`` — i.e. this
        env var moves leg 2's first dial. A probe that ignored it would keep
        reporting on the tier model while the fallback dialled the override.
        """
        monkeypatch.setenv("REGENOLD_STAGE2_BEDROCK_MODEL", _OPUS)
        monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "FAKE-TOKEN-FOR-TEST")
        assert bc.stage2_probe_models()[0] == bc.resolve_bedrock_model(_OPUS)

    def test_the_first_probe_model_follows_the_engine_stage2_knob(
        self, monkeypatch
    ) -> None:
        """The other, similarly-named knob (BEDROCK_STAGE2 vs STAGE2_BEDROCK)
        is read by the engine's own resolver, and moves the dial too."""
        monkeypatch.setenv("REGENOLD_BEDROCK_STAGE2_MODEL", _OPUS)
        monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "FAKE-TOKEN-FOR-TEST")
        assert bc.stage2_probe_models()[0] == bc.resolve_bedrock_model(_OPUS)


class TestTheFalseHealthy:
    def test_a_denied_custom_chain_is_not_rescued_by_a_pinned_qwen(
        self, monkeypatch
    ) -> None:
        """One stub, two walks, opposite verdicts — the defect, exactly.

        The stub answers on ``qwen.qwen3-235b-a22b-2507-v1:0`` and nothing else,
        which is the pinned literal's first entry.
        """
        _pin_fallback(monkeypatch)
        seen = _dial(monkeypatch, {_QWEN_235B: "ok"})

        now = bc.check_connectivity_and_permissions()
        assert now["models_source"] == "stage2_fallback"
        assert now["resolved_models"] == [bc.resolve_bedrock_model(_OPUS)]
        assert now["status"] != "ok", (
            "the fallback's only model is denied, so leg 2 cannot serve — a "
            "Qwen that answers on the account is not evidence for this chain"
        )
        assert _QWEN_235B not in seen, "no model outside the fallback's chain"

        # The pinned walk under the same stub is precisely the old false ok.
        old = bc.check_connectivity_and_permissions(
            models=bc.BEDROCK_FALLBACK_PROBE_MODELS
        )
        assert old["status"] == "ok"
        assert old["model"] == _QWEN_235B
        assert old["models_source"] == "explicit", (
            "the pinned literal is now reachable ONLY by asking for it"
        )

    def test_an_available_custom_model_reports_ok_and_names_it(
        self, monkeypatch
    ) -> None:
        """Two-sided: the fix must not degrade into \"always down\"."""
        _pin_fallback(monkeypatch)
        seen = _dial(monkeypatch, {_OPUS: "ok"})
        res = bc.check_connectivity_and_permissions()
        assert res["status"] == "ok"
        assert res["model"] == _OPUS
        assert seen[0] == _OPUS

    def test_the_walk_still_short_circuits_on_the_first_ok(self, monkeypatch) -> None:
        """A health probe must not spend an extra billable Converse call."""
        _pin_fallback(monkeypatch)
        seen = _dial(monkeypatch, {_OPUS: "ok"})
        res = bc.check_connectivity_and_permissions()
        assert res["status"] == "ok"
        assert seen == [_OPUS], "one ok model ends the walk"


class TestTheProbeDialsTheFallbacksTransport:
    def test_the_single_model_dial_goes_through_complete_with_fallback(
        self, monkeypatch
    ) -> None:
        """The probe must use the transport the fallback uses.

        ``_bedrock_complete_for_graph_rag`` calls
        ``complete_with_fallback(req, fallbacks=())`` once per candidate; the
        diagnostic called ``BedrockProvider.complete`` directly, so anything the
        wrapper adds (alias resolution, the denied-model cache) was invisible to
        the one instrument that reports leg 2's health.
        """
        calls: list[tuple[str, Any]] = []

        def _fake_complete(req, *, fallbacks=None, record_stage2=True):
            calls.append((req.model, fallbacks))
            # Terminal punctuation on purpose: the engine rejects a completion
            # that looks cut mid-clause (``_looks_structurally_truncated``).
            return bc.BedrockResponse(model=req.model, text="OK.")

        monkeypatch.setattr(bc, "complete_with_fallback", _fake_complete)
        monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "FAKE-TOKEN-FOR-TEST")

        res = bc.check_connectivity_and_permissions(model_id=_QWEN_32B)
        assert res["status"] == "ok"
        assert calls == [(_QWEN_32B, ())]

    def test_the_first_probe_model_is_the_fallbacks_first_dial(
        self, monkeypatch
    ) -> None:
        """The reading names the model the fallback would actually dial first."""
        from app.engines import _graph_rag_impl as impl

        _pin_fallback(monkeypatch)
        dialled: list[str] = []

        def _fake_complete(req, *, fallbacks=None, record_stage2=True):
            dialled.append(req.model)
            return bc.BedrockResponse(model=req.model, text="OK.")

        monkeypatch.setattr(bc, "complete_with_fallback", _fake_complete)

        out = impl._bedrock_complete_for_graph_rag(
            system="s", user="u", max_tokens=8, temperature=0.0,
            stage_name="Stage 2",
        )
        assert out == "OK."
        assert dialled[0] == bc.stage2_probe_models()[0]
        assert dialled[0] == bc.resolve_bedrock_model(_OPUS)

    def test_the_policy_override_moves_probe_and_fallback_together(
        self, monkeypatch
    ) -> None:
        """The coupling, end to end: ONE env var, both dials, same first model.

        The override deliberately differs from ``REGENOLD_BEDROCK_MODEL`` so a
        probe that consulted the wrong knob answers with the wrong model.
        """
        from app.engines import _graph_rag_impl as impl
        from app.llm import stage2_policy as s2pol

        _pin_fallback(monkeypatch)
        monkeypatch.setenv("REGENOLD_STAGE2_BEDROCK_MODEL", _QWEN_32B)
        dialled: list[str] = []

        def _fake_complete(req, *, fallbacks=None, record_stage2=True):
            dialled.append(req.model)
            return bc.BedrockResponse(model=req.model, text="OK.")

        monkeypatch.setattr(bc, "complete_with_fallback", _fake_complete)

        # Called the way ``_try_bedrock_fallback`` calls it — the override IS its
        # argument, and the next test pins that the call site still passes it.
        assert impl._bedrock_complete_for_graph_rag(
            system="s", user="u", max_tokens=8, temperature=0.0,
            stage_name="Stage 2",
            model_override=s2pol.stage2_fallback_model() or None,
        ) == "OK."
        assert dialled[0] == bc.resolve_bedrock_model(_QWEN_32B)
        assert bc.stage2_probe_models()[0] == dialled[0]

    def test_the_fallback_call_site_actually_passes_that_override(self) -> None:
        """WIRED, not merely defined — AGENTS.md's dead-flag lesson.

        ``REGENOLD_STAGE2_BEDROCK_MODEL`` only moves leg 2's dial because the
        fallback passes ``model_override=...``; a probe that reads the override
        is faithful only while that stays true.
        """
        import inspect

        from app.engines import _graph_rag_impl as impl

        src = inspect.getsource(impl)
        assert "model_override=_s2pol.stage2_fallback_model() or None" in src, (
            "the Bedrock fallback no longer passes the Stage-2 model override, so "
            "the probe's resolved chain diverges from the real dial"
        )


class TestResolutionFailureStaysHonest:
    def test_the_pinned_list_is_the_fallback_of_last_resort(self, monkeypatch) -> None:
        """Only an engine that cannot be imported falls back to the literal."""
        from app.engines import _graph_rag_impl as impl

        def _boom(*_a, **_k):
            raise RuntimeError("engine unavailable")

        monkeypatch.setattr(impl, "bedrock_fallback_model_chain", _boom)
        walk, source = bc._stage2_probe_models_and_source()
        assert walk == bc.BEDROCK_FALLBACK_PROBE_MODELS
        assert source == "pinned_probe_list"

    def test_a_degraded_resolution_still_answers(self, monkeypatch) -> None:
        """Never raise: a probe that 500s is worse than one that reports a failure."""
        from app.engines import _graph_rag_impl as impl

        def _boom(*_a, **_k):
            raise RuntimeError("engine unavailable")

        monkeypatch.setattr(impl, "bedrock_fallback_model_chain", _boom)
        _dial(monkeypatch, {_QWEN_235B: "ok"})
        res = bc.check_connectivity_and_permissions()
        assert res["models_source"] == "pinned_probe_list"
        assert res["resolved_models"] == list(bc.BEDROCK_FALLBACK_PROBE_MODELS)
        assert res["status"] == "ok"

    def test_an_empty_chain_is_not_reported_as_a_dead_credential(
        self, monkeypatch
    ) -> None:
        """An un-resolvable chain degrades to the literal, not to an empty walk.

        ``bedrock_fallback_model_chain`` returns ``[]`` when it cannot resolve
        anything; treating that as the walk would report ``status: error,
        model: None`` for a deployment whose credential is fine.
        """
        from app.engines import _graph_rag_impl as impl

        monkeypatch.setattr(impl, "bedrock_fallback_model_chain", lambda **_k: [])
        walk, source = bc._stage2_probe_models_and_source()
        assert walk == bc.BEDROCK_FALLBACK_PROBE_MODELS
        assert source == "pinned_probe_list"


_OPS_KEY = "r464-probe-fidelity-ops-key"


def _ops_client(m):
    """R370 — ``?probe_bedrock=1`` spends, so it is operator-only."""
    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from app.config import settings

    settings.regenold.api_key = SecretStr(_OPS_KEY)
    return TestClient(m.app, headers={"X-Regenold-Api-Key": _OPS_KEY})


class TestTheResolvedChainReachesTheOperator:
    def test_the_endpoint_forwards_the_resolved_models(self, monkeypatch) -> None:
        """The reading is only useful if the operator can see WHICH list was dialled."""
        import app.main as m

        _pin_fallback(monkeypatch)
        _dial(monkeypatch, {_OPUS: "ok"})

        r = _ops_client(m).get("/healthz/llm?probe_bedrock=1")
        assert r.status_code == 200
        probe = r.json()["bedrock_probe"]
        assert probe["models_source"] == "stage2_fallback"
        assert probe["resolved_models"] == [bc.resolve_bedrock_model(_OPUS)]
        assert probe["model"] == _OPUS
        assert probe["status"] == "ok"

    def test_the_endpoint_forwards_a_masked_call_to_the_operator(
        self, monkeypatch
    ) -> None:
        """The mask verdict is only actionable if the wire carries WHO answered.

        ``_probe_bedrock_leg`` forwards an explicit key allow-list, so a key the
        client reports and the route forgets is indistinguishable from a clean
        Bedrock answer with an odd error code.
        """
        import app.main as m

        monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "FAKE-TOKEN-FOR-TEST")
        monkeypatch.setattr(
            bc,
            "check_connectivity_and_permissions",
            lambda model_id=None, models=None: {
                "status": "error",
                "model": _EXOTIC,
                "error": "bedrock_exhausted_served_by_wrapper",
                "served_by": "wrapper:claude-opus-5",
                "elapsed_ms": 3,
                "hint": "leg 2 is DOWN",
            },
        )

        probe = _ops_client(m).get("/healthz/llm?probe_bedrock=1").json()[
            "bedrock_probe"
        ]
        assert probe["status"] == "error"
        assert probe["error"] == "bedrock_exhausted_served_by_wrapper"
        assert probe["served_by"] == "wrapper:claude-opus-5"
        assert probe["hint"] == "leg 2 is DOWN", (
            "the client's own hint must win over the generic entitlement hint"
        )
        assert probe["model"] == _EXOTIC

    def test_the_endpoint_reports_a_degraded_resolution(self, monkeypatch) -> None:
        """Two-sided: when the engine is gone, the reading SAYS SO."""
        import app.main as m

        from app.engines import _graph_rag_impl as impl

        def _boom(*_a, **_k):
            raise RuntimeError("engine unavailable")

        monkeypatch.setattr(impl, "bedrock_fallback_model_chain", _boom)
        monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "FAKE-TOKEN-FOR-TEST")
        _dial(monkeypatch, {_QWEN_235B: "ok"})

        r = _ops_client(m).get("/healthz/llm?probe_bedrock=1")
        assert r.status_code == 200
        probe = r.json()["bedrock_probe"]
        assert probe["models_source"] == "pinned_probe_list"
        assert probe["resolved_models"] == list(bc.BEDROCK_FALLBACK_PROBE_MODELS)


#: A model id no other test dials, so the process-global denied-model cache this
#: class exercises cannot leak into a sibling suite.
_EXOTIC = "eu.anthropic.claude-haiku-4-5"


class TestTheProbesTransportSideEffects:
    """Borrowing the serving transport imports its side effects (R464).

    Two of them must NOT ride along, and both are invisible in the diff: they
    are behaviours of ``complete_with_fallback``, not of the probe. So each is
    pinned on an EFFECT — the process-global Stage-2 counters and the reported
    verdict — driven through the REAL transport with only its ends stubbed.
    """

    @pytest.fixture(autouse=True)
    def _clean(self):
        from app.llm import stage2_policy as pol

        bc.reset_bedrock_entitlement_cache()
        pol.reset_transport_stats()
        yield
        bc.reset_bedrock_entitlement_cache()
        pol.reset_transport_stats()

    def _drive(self, *, bedrock_ok: bool) -> dict[str, Any]:
        """Real ``complete_with_fallback``; Bedrock and the wrapper stubbed.

        ``bedrock_ok=False`` denies each chain entry with the durable
        entitlement marker, so the chain exhausts and the wrapper hop — the
        second side effect under test — is actually reached.
        """
        from unittest.mock import MagicMock, patch

        from app.llm.openai_wrapper_provider import OpenAIWrapperResponse

        served = bc.BedrockResponse(model=_EXOTIC, text="OK.")
        denied = bc.BedrockResponse(
            text="", model=_EXOTIC, error="api_access_denied: not entitled"
        )
        stub = MagicMock()
        stub.complete = MagicMock(return_value=served if bedrock_ok else denied)

        with (
            patch(
                "app.llm.bedrock_client.get_bedrock_provider", return_value=stub
            ),
            patch(
                "app.llm.bedrock_client.wrapper_fallback_enabled", return_value=True
            ),
            patch(
                "app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
                return_value=True,
            ),
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider"
            ) as prov,
        ):
            prov.return_value.complete.return_value = OpenAIWrapperResponse(
                text="OK.", model="claude-opus-5", elapsed_ms=1
            )
            prov.return_value._base_url = "https://wrapper.antifragile-ai.net/v1"
            return bc.check_connectivity_and_permissions(model_id=_EXOTIC)

    def test_a_probe_is_not_counted_as_stage2_traffic(self) -> None:
        """``?probe_bedrock=1`` must not be able to clear a liveness gate."""
        from app.llm import stage2_policy as pol

        self._drive(bedrock_ok=False)
        stats = pol.transport_stats()
        assert stats["primary_attempts"] == 0 and stats["primary_ok"] == 0, (
            "the probe's wrapper hop was counted as a Stage-2 primary "
            "completion, so a probe on a dead run makes it read live: "
            f"{stats}"
        )
        assert stats["fallback_attempts"] == 0, f"a probe is not leg-2 traffic: {stats}"

    def test_a_wrapper_masked_call_is_not_a_healthy_bedrock_reading(self) -> None:
        """The hop serves the probe's call; the verdict must not follow it."""
        res = self._drive(bedrock_ok=False)

        assert res["status"] != "ok", (
            "every Bedrock model refused and the WRAPPER answered — reporting "
            f"ok here is a green for a dead credential: {res}"
        )
        assert res["error"] == "bedrock_exhausted_served_by_wrapper", res
        assert res["served_by"] == "wrapper:claude-opus-5", (
            "the reading must name the provider that masked the refusal"
        )
        assert res["model"] == _EXOTIC, "the model asked of Bedrock stays identified"
        assert res["hint"], "an operator hint must accompany this verdict"

    def test_a_bedrock_served_call_is_still_ok_and_names_the_model(self) -> None:
        """Two-sided: the mask guard must not fire on a real Bedrock answer."""
        from app.llm import stage2_policy as pol

        res = self._drive(bedrock_ok=True)

        assert res["status"] == "ok"
        assert res["model"] == _EXOTIC
        assert "served_by" not in res
        assert pol.transport_stats()["primary_attempts"] == 0
