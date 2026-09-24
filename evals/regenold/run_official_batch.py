"""Replay the REAL regenold benchmark batch (2026-07-07) against the live system.

This is the highest-fidelity eval surface this repo has: the questions are the
ones the official report actually graded (see
:mod:`evals.regenold.official_batch` for provenance + the hard-mode recovery
caveat), not a proxy probe set.

    EASY  — 110 cold single-turn questions. Byte-exact replay.
    HARD  — the same 110 inside a rolling multi-turn conversation, each answer
            then challenged with the judge's verbatim pushback template. Two
            live requests per question; BOTH answers are recorded so the
            **pushback flip rate** (did we abandon a correct answer when told
            "I think you're hallucinating"?) is measurable.

We do NOT have the official gold references or gold answers, so this runner
deliberately does **not** invent a correctness score. It records what it can
measure objectively (tone, reference counts, answer length, latency, refusal
rate, pushback flips, answer/ref churn vs the 2026-07-07 shipped output) and
writes a sidecar shaped for :mod:`evals.judge.grounded` — the Sonnet-5 judge
that scores answer / reference / citation correctness against the **verbatim
Act text**, which is the right instrument when gold labels are unavailable.

USAGE
-----
    # single arm, live, both modes
    .venv/Scripts/python.exe -m evals.regenold.run_official_batch \\
        --label r285-head --mode both

    # A/B two env arms (sequential — never two wrapper-bound jobs at once)
    .venv/Scripts/python.exe -m evals.regenold.run_official_batch \\
        --label r285 --mode easy \\
        --baseline-env REGENOLD_VERIFY_VERDICT=1 \\
        --branch-env  REGENOLD_VERIFY_VERDICT=0

    # against deployed prod instead of the in-process route
    ... --endpoint https://<host>/api/v1/regenold/eu-ai-act/ask --api-key $KEY

Then grade a sidecar:
    .venv/Scripts/python.exe -m evals.judge.grounded \\
        --sidecar evals/bench/results/official-<label>-easy.ckpt.jsonl \\
        --label <label> --model claude-sonnet-5 --provider wrapper
"""
from __future__ import annotations

import argparse
import atexit
import json
import os
import statistics as st
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from evals.bench import metrics as bench_metrics
from evals.harness.gate_validity import (
    ArmProbe,
    assess,
    degraded_row_ids,
    lever_changes_request,
    lever_changes_system,
    lever_changes_wire,
    wire_shape_digest,
)
from evals.regenold.hard_preamble import (
    DEFAULT_MODE,
    MODE_FIXED,
    MODE_ROLLING,
    build_prefixed_messages,
    build_prefixed_pushback_messages,
    hard_preamble_mode,
    preamble_digest,
)
from evals.regenold.official_batch import (
    build_hard_messages,
    build_pushback_messages,
    load_official_batch,
    trim_history,
)

#: Digest of the fixed preamble, computed once — recorded on every row of a
#: ``REGENOLD_HARD_PREAMBLE=fixed`` arm so a reader can prove from the checkpoint
#: alone which request shape produced it.
_FIXED_PREAMBLE_DIGEST = preamble_digest()

_RESULTS = Path(__file__).resolve().parents[1] / "bench" / "results"
def acquire_run_lock(label: str) -> Path:
    """Own a label before any live draw; refuse a duplicate live runner.

    R442 — an OS-held lock (``evals.regenold.run_lock``) released by the kernel
    when this process exits by ANY route. The R440 PID check could not see an
    owner in another Windows console and read it as stale; see that module.
    """
    from evals.regenold import run_lock  # noqa: PLC0415

    lock = run_lock.acquire(_RESULTS, label)
    atexit.register(run_lock.release)
    return lock


_REFUSAL_MARKERS = (
    "i cannot answer your question from my knowledge graph",
    "from these materials, which address only obligations",
    "no matching obligation found",
    "try rephrasing",
)


def _is_refusal(answer: str) -> bool:
    low = (answer or "").lower()
    return any(m in low for m in _REFUSAL_MARKERS)


def _heads(refs: list[str]) -> set[str]:
    return set(bench_metrics.article_heads(refs or []))


def _provenance(body: dict[str, Any] | None) -> dict[str, Any]:
    """Pull Stage-2 provenance out of the ``reasoning`` trace.

    R292: without this the sidecar records only ``answer`` + ``references``, so a
    run in which the Stage-2 provider silently degraded (wrapper down, credit
    exhausted, rate-limited) is INDISTINGUISHABLE from a healthy run — the
    deterministic fallback still returns a plausible answer. That makes the
    headline scorecard unfalsifiable. Recording ``stage2_polish`` / the resolved
    model / ``retrieval_path`` per row makes a degraded run detectable after the
    fact, and the aggregate ``stage2_landed_rate`` makes it obvious at a glance.

    Fail-soft: a missing / non-JSON ``reasoning`` field yields an empty dict, so
    this can never break a run.
    """
    try:
        raw = (body or {}).get("reasoning")
        if not isinstance(raw, str) or not raw.strip():
            return {}
        trace = json.loads(raw)
        if not isinstance(trace, dict):
            return {}
        model = ""
        served_by = ""
        for note in trace.get("notes") or []:
            if not isinstance(note, str):
                continue
            if not model and "stage2_model=" in note:
                model = note.split("stage2_model=", 1)[1].split()[0]
            # R418 — the route now names the leg it shipped. Prefer this over
            # inferring from the model prefix: ``primary`` / ``fallback`` /
            # ``deterministic`` is what the cacheability guard actually read.
            if not served_by and "stage2_served_by=" in note:
                served_by = note.split("stage2_served_by=", 1)[1].split()[0]
        return {
            "stage2_polish": trace.get("stage2_polish"),
            "retrieval_path": trace.get("retrieval_path"),
            "engine_confidence": trace.get("engine_confidence"),
            "stage2_model": model,            "stage2_served_by": served_by,
        }
    except Exception:  # noqa: BLE001 — provenance is best-effort telemetry
        return {}


def _row_metrics(answer: str, refs: list[str]) -> dict[str, Any]:
    return {
        "tone": bench_metrics.regulatory_tone(answer),
        "n_refs": len(refs or []),
        "n_ref_heads": len(_heads(refs)),
        "answer_chars": len(answer or ""),
        "refused": _is_refusal(answer),
    }


def _apply_env(arm_env: dict[str, str]) -> dict[str, str | None]:
    saved: dict[str, str | None] = {}
    for k, v in arm_env.items():
        saved[k] = os.environ.get(k)
        os.environ[k] = v
    return saved


#: R409 — seconds the rerank pacer has slept, process-wide. The pacer sleeps
#: INSIDE the in-process request, so the sleep landed in the measured latency:
#: R407 ran with a 13 s gap and scored Resp. Speed on it. ``guarded_poster``
#: subtracts the delta; requests are posted sequentially, so it is exact.
_PACING_SLEPT_S = [0.0]


def _net_of_pacing(result: tuple, slept_before: float) -> tuple:
    """Remove the pacer's sleep since ``slept_before`` from a poster result."""
    slept_ms = (_PACING_SLEPT_S[0] - slept_before) * 1000.0
    if slept_ms > 0 and result[1] is not None:
        return (result[0], max(0.0, result[1] - slept_ms), *result[2:])
    return result


def _install_cohere_guard(
    *,
    require_embeddings: bool = True,
    min_rerank_gap_s: float = 0.0,
) -> Callable[[], None]:
    """Require real Cohere embeddings and reranking for a local live run.

    The application deliberately fails open when an optional retrieval provider
    is unavailable. That is correct production behaviour but invalid benchmark
    behaviour: a 429 would otherwise turn a labelled Cohere run into an SVD/no-op
    run. Probe both APIs, verify that the document index really selected Cohere,
    then install sticky wrappers whose health check is called after every POST.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    except ImportError:
        pass
    if not os.getenv("COHERE_API_KEY", "").strip():
        raise RuntimeError("--require-cohere needs COHERE_API_KEY")
    falsy = {"0", "false", "no", "off"}
    if (
        require_embeddings
        and os.getenv("REGENOLD_EXTERNAL_EMBEDDINGS", "1").strip().lower() in falsy
    ):
        raise RuntimeError("--require-cohere conflicts with REGENOLD_EXTERNAL_EMBEDDINGS=0")
    if os.getenv("REGENOLD_COHERE_RERANK", "1").strip().lower() in falsy:
        raise RuntimeError("--require-cohere conflicts with REGENOLD_COHERE_RERANK=0")

    from app.engines import cohere_rerank, external_embeddings, turboquant_index

    if require_embeddings:
        probe = external_embeddings.get_embedding(
            "EU AI Act benchmark Cohere preflight",
            is_query=True,
        )
        if probe is None:
            raise RuntimeError(
                "Cohere embedding preflight failed; refusing a fallback-contaminated run"
            )

        diagnostics = turboquant_index.index_diagnostics()
        if diagnostics.get("embedding_backend") != "cohere":
            backend = diagnostics.get("embedding_backend", "unavailable")
            raise RuntimeError(
                f"dense index backend is {backend!r}, not Cohere; refusing benchmark"
            )

    cohere_rerank.reset_rerank_stats()
    cohere_rerank.reset_request_budget()
    reranked = cohere_rerank.rerank_documents(
        "Which provision governs provider transparency?",
        ["Article 13 transparency obligations", "Article 99 administrative fines"],
    )
    stats = cohere_rerank.rerank_stats()
    if not reranked or stats.get("attempts") != 1 or stats.get("failed"):
        raise RuntimeError("Cohere rerank preflight failed; refusing a no-op benchmark")
    cohere_rerank.reset_rerank_stats()
    cohere_rerank.reset_request_budget()

    failures: list[str] = []
    failure_lock = threading.Lock()
    original_embed = external_embeddings.get_embedding
    original_rerank = cohere_rerank.rerank_documents
    min_gap = max(0.0, float(min_rerank_gap_s))
    pace_lock = threading.Lock()
    last_rerank_at = time.monotonic()

    def record(message: str) -> None:
        with failure_lock:
            failures.append(message)

    def guarded_embed(texts, *, is_query=False):
        result = original_embed(texts, is_query=is_query)
        if result is None:
            record("Cohere embedding call fell back")
        return result

    def guarded_rerank(query, documents, *, top_n=None):
        nonlocal last_rerank_at
        docs = [str(item) for item in documents if str(item).strip()]
        before = cohere_rerank.rerank_stats()
        if min_gap:
            with pace_lock:
                wait_s = min_gap - (time.monotonic() - last_rerank_at)
                if wait_s > 0:
                    time.sleep(wait_s)
                    _PACING_SLEPT_S[0] += wait_s
                result = original_rerank(query, documents, top_n=top_n)
                if (
                    cohere_rerank.rerank_stats().get("attempts", 0)
                    > before.get("attempts", 0)
                ):
                    last_rerank_at = time.monotonic()
        else:
            result = original_rerank(query, documents, top_n=top_n)
        after = cohere_rerank.rerank_stats()
        if len(docs) >= 2 and str(query).strip() and result is None:
            if after.get("failed", 0) > before.get("failed", 0):
                record("Cohere rerank call failed")
            elif after.get("attempts", 0) == before.get("attempts", 0):
                budget_skip = (
                    after.get("budget_skipped", 0)
                    > before.get("budget_skipped", 0)
                )
                if require_embeddings or not budget_skip:
                    record("Cohere rerank call was skipped or disabled")
        return result

    external_embeddings.get_embedding = guarded_embed
    cohere_rerank.rerank_documents = guarded_rerank

    def assert_healthy(_payload: object | None = None) -> None:
        with failure_lock:
            problem = failures[0] if failures else ""
        if problem:
            raise RuntimeError(f"{problem}; Cohere-required benchmark is invalid")

    embedding_label = (
        "cohere "
        f"({os.getenv('REGENOLD_EXTERNAL_EMBEDDING_MODEL', 'embed-english-v3.0')})"
        if require_embeddings
        else "not required"
    )
    print(
        f"Cohere strict mode: embeddings={embedding_label}, rerank=cohere "
        f"({os.getenv('REGENOLD_COHERE_RERANK_MODEL', 'rerank-v4.0-pro')}), "
        f"min_rerank_gap={min_gap:.1f}s"
    )
    return assert_healthy


#: Error substrings that mean the Stage-2 request never reached the wrapper.
#: Measured shapes from the R423 need-proportional gate, which spent 90 minutes
#: and 243 Stage-2 calls inside one DNS outage:
#: ``network_error: [Errno 11001] getaddrinfo failed`` (the wrapper hostname did
#: not resolve — the Cloudflare tunnel that publishes it was down),
#: ``[WinError 10065] A socket operation was attempted to an unreachable host``
#: and ``The read operation timed out``.
_TRANSPORT_ERROR_MARKERS = (
    "network_error",
    "getaddrinfo",
    "unreachable host",
    "timed out",
    "connection refused",
    "connection reset",
)


class _ConsecutiveTransportFailures:
    """Count Stage-2 calls that never reached a leg; reset on any success."""

    def __init__(self, limit: int, *, trip: bool = True, label: str = "") -> None:
        self._limit = max(1, int(limit))
        self._consecutive = 0
        self._last = ""
        self._lock = threading.Lock()
        #: R423.1 — an auxiliary leg is COUNTED and reported but never aborts the
        #: batch. See ``_install_stage2_transport_guard`` for why that distinction
        #: is not cosmetic.
        self._trip = bool(trip)
        self._label = label
        self._total = 0
        self._last_kind = ""

    def record_ok(self) -> None:
        with self._lock:
            self._consecutive = 0
            self._last = ""

    def record_failure(self, message: str, kind: str = "") -> None:
        with self._lock:
            self._consecutive += 1
            self._total += 1
            self._last = message
            self._last_kind = kind

    def counts(self) -> tuple[int, int]:
        """``(consecutive, total)`` — for the run's provenance."""
        with self._lock:
            return self._consecutive, self._total

    def tripped(self) -> str:
        with self._lock:
            if self._trip and self._consecutive >= self._limit:
                # ``label`` and ``kind`` are omitted when unset, so an
                # unlabelled tracker's reason string is unchanged.
                who = f" {self._label}" if self._label else ""
                kind = f" [{self._last_kind}]" if self._last_kind else ""
                return (
                    f"{self._consecutive} consecutive{who} calls failed"
                    f"{kind} (last: {self._last[:160]})"
                )
            return ""


def _probe_fallback_leg() -> str:
    """Model id if the Stage-2 FALLBACK leg answers, else ``""`` (R431).

    ``check_connectivity_and_permissions`` is the credential/model-access
    diagnostic the Bedrock client already exposes, and it walks the SAME probe
    chain the fallback leg dials, short-circuiting on the first model that
    answers. Using it here (rather than dialling a model of our own choosing) is
    what keeps the probe and the runtime from disagreeing about what "the
    fallback is up" means.

    Fail-soft by design: any import/credential/network problem reports the leg as
    unavailable, which is exactly the conservative reading.
    """
    try:
        from app.llm import bedrock_client as _bc  # noqa: PLC0415

        result = _bc.check_connectivity_and_permissions()
        if not isinstance(result, dict) or result.get("status") != "ok":
            return ""
        return str(result.get("model") or "")
    except Exception:  # noqa: BLE001 — an unusable probe means "unavailable"
        return ""


def _install_stage2_transport_guard(
    *,
    max_consecutive: int = 5,
) -> tuple[Callable[[], str], Callable[[], None]]:
    """Refuse to spend a live run on a Stage-2 transport that cannot answer.

    R423 — the ``REGENOLD_NEED_PROPORTIONAL_CONTRACT`` gate ran to completion and
    was correctly VOIDED, but only after burning ~90 minutes and 243 Stage-2
    calls inside a single DNS outage (``getaddrinfo failed``: the Cloudflare
    tunnel that publishes the wrapper hostname was down). Every one of those
    calls then walked the same dead path — the legacy Groq hatch was refused by
    the strict-transport policy, the Bedrock credential was invalid, so the row
    shipped a deterministic Stage-1 draft. Both arms voided for that reason, and
    the gate's void guard (R412/R422) is what caught it.

    Catching it AFTER the fact is the expensive half. A live run whose Stage-2
    primary is unreachable measures nothing, so this guard (a) probes the
    wrapper once before the first row is spent, and (b) aborts the batch as soon
    as ``max_consecutive`` Stage-2 calls in a row fail to reach it. A single
    transient miss cannot trip it — the counter resets on any success — so it
    fires on an outage, not on noise.

    Opt out with ``--allow-degraded-transport`` for a run that deliberately
    measures the degradation path itself.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    except ImportError:
        pass

    from app.llm import openai_wrapper_provider as _wp

    if not _wp.is_openai_wrapper_enabled():
        raise RuntimeError("--require-stage2-transport needs the openai_wrapper provider")

    transport = _ConsecutiveTransportFailures(int(max_consecutive), label="primary")
    #: R423.1 — auxiliary legs (the Groq denoiser / intent classifier, Gemini,
    #: Mistral) go through the SAME provider class, so patching the class counts
    #: their failures as Stage-2 transport failures. MEASURED consequence: the
    #: R423.1 gate aborted after four rows because Groq's free-tier cap answered
    #: ``429 Rate limit reached for model `openai/gpt-oss-120b``` — on the QUERY
    #: DENOISER, whose own chain falls through to Haiku. Every row would still
    #: have been served by a healthy Claude Stage-2 leg, and the run died anyway,
    #: discarding the rows that were about to be drawn. An abort must mean "the
    #: Stage-2 primary cannot answer", because that is the only condition under
    #: which the batch would be graded on Stage-1 drafts. Auxiliary failures are
    #: counted, reported, and never abort.
    auxiliary = _ConsecutiveTransportFailures(int(max_consecutive), trip=False, label="aux")
    primary_provider = _wp.get_openai_wrapper_provider()

    def _is_primary_leg(provider: object) -> bool:
        """Is this call the Stage-2 primary, or an auxiliary leg?

        Identity first (the real getter returns a process-wide singleton), with
        the endpoint as the fallback discriminator, because every leg is built
        from this one class against its own ``base_url``. Both must be non-empty
        for the endpoint test to apply, so two uninitialised instances cannot
        match each other by both being ``None``.
        """
        if provider is primary_provider:
            return True
        mine = getattr(provider, "_base_url", None)
        theirs = getattr(primary_provider, "_base_url", None)
        return bool(mine) and bool(theirs) and mine == theirs

    #: R442 — models this run has already proven servable, so re-probing on
    #: every arm costs one live call per DISTINCT model, not one per arm.
    #:
    #: R446 — keyed on what actually reaches the transport: the WIRE id
    #: (``resolve_wrapper_model`` applies the R432 namespace prefix and the R300
    #: alias table, both env-driven per arm) plus the provider's base URL. Keyed
    #: on the bare configured id, an arm that changed only
    #: ``REGENOLD_WRAPPER_MODEL_PREFIX`` reused the other arm's verdict and its
    #: own id was never probed.
    probed: dict[tuple[str, str], str] = {}

    def preflight() -> str:
        provider = _wp.get_openai_wrapper_provider()
        # R432 — probe the CONFIGURED Stage-2 model, not the request default.
        # The old probe left ``model`` unset on the stated premise that "the
        # provider's alias map resolves it to the same effective model the
        # engine's Stage-2 calls land on" — true only while the alias table was
        # ON. It has defaulted OFF since R308, so the probe has been sending the
        # request default (``claude-opus-4-8``) verbatim: a name the wrapper
        # happens to accept by luck, and one a namespaced transport rejects with
        # a 400 — i.e. the preflight could pass (or fail) on a model the run
        # never uses. It now probes the model the run will actually send.
        #
        # R442 — "the model the run will actually send" is the ENGINE's routing
        # rule, not ``GraphRAGSettings().stage2_model``: the complex-tier model
        # (``P2P_GRAPH_RAG_COMPLEX_MODEL``, a fresh env read) wins on the
        # standard Stage-2 path too. Reading ``stage2_model`` alone probed
        # ``claude-opus-5`` for an arm running ``claude-opus-5-5`` — the model
        # Claude Code < 2.1.280 rejects with a 400 — so the probe passed on a
        # model the arm never sent. ``_arm`` now calls this AFTER applying its
        # env, so each arm's model is probed, not only the process default.
        try:
            from app.engines._graph_rag_impl import effective_stage2_model

            probe_model = str(effective_stage2_model() or "").strip()
        except Exception:  # noqa: BLE001 — a probe must never break the run
            probe_model = ""
        try:
            wire_model = _wp.resolve_wrapper_model(probe_model) if probe_model else ""
        except Exception:  # noqa: BLE001 — a probe must never break the run
            wire_model = probe_model
        memo_key = (wire_model, str(getattr(provider, "_base_url", "") or ""))
        if probe_model and memo_key in probed:
            return probed[memo_key]
        resp = provider.complete(
            _wp.OpenAIWrapperRequest(
                user="Reply with the single word: alive",
                max_tokens=16,
                **({"model": probe_model} if probe_model else {}),
            )
        )
        if resp is None:
            raise RuntimeError(
                "Stage-2 transport preflight returned no response; refusing a run "
                "that would grade deterministic Stage-1 drafts"
            )
        if getattr(resp, "error", None):
            # R431 — try the FALLBACK leg before refusing the run. A down wrapper
            # with a healthy Bedrock credential is not a reason to waste the
            # sample: it is a reason to draw the sample on the fallback and say
            # so on every row.
            fallback_model = _probe_fallback_leg()
            if fallback_model:
                print(
                    "\n[transport] PRIMARY preflight failed "
                    f"({str(resp.error)[:120]}); the FALLBACK leg answers "
                    f"(model={fallback_model}), so this run proceeds as a "
                    "FALLBACK-SERVED draw. Every row records "
                    "`stage2_served_by=fallback`; do not read it as a "
                    "primary-served measurement."
                )
                served = f"fallback:{fallback_model}"
                if probe_model:
                    probed[memo_key] = served
                return served
            raise RuntimeError(
                "Stage-2 transport preflight failed "
                f"({str(resp.error)[:160]}) and the fallback leg did not answer "
                "either, so a live run would grade Stage-1 drafts. Fix one of the "
                "two legs (tunnel / OAuth / quota, or the Bedrock credential) or "
                "pass --allow-degraded-transport to measure the degradation path "
                "on purpose."
            )
        served = str(getattr(resp, "model", "") or "")
        if probe_model:
            probed[memo_key] = served
        return served

    original_complete = _wp._OpenAIWrapperProvider.complete

    def guarded_complete(self, req):
        resp = original_complete(self, req)
        error = getattr(resp, "error", None)
        # R423.1 — WHICH LEG this call belongs to, not merely that it failed.
        # ``self is primary_provider`` is the discriminator: the auxiliary legs
        # are separate instances built against their own base_url, so this needs
        # no model-name list to keep in sync. A model-side error (quota, 4xx/5xx)
        # on the PRIMARY is not a network outage either, but five in a row there
        # still does mean every row is shipping a Stage-1 draft, so it counts.
        is_primary = _is_primary_leg(self)
        if not error:
            if is_primary:
                transport.record_ok()
            return resp
        message = str(error)
        kind = (
            "transport"
            if any(m in message.lower() for m in _TRANSPORT_ERROR_MARKERS)
            else "model_side"
        )
        if is_primary:
            transport.record_failure(message, kind)
        else:
            auxiliary.record_failure(message, kind)
        return resp

    _wp._OpenAIWrapperProvider.complete = guarded_complete

    # ── R431 — the guard is now LEG-AWARE, not primary-or-nothing ─────────────
    #
    # The abort exists for ONE condition: the rows stop being served by a Stage-2
    # leg at all, so the batch would grade deterministic Stage-1 drafts and
    # measure the transport instead of the lever. A tripped PRIMARY is not that
    # condition when the Bedrock fallback is answering — the wire is still
    # Stage-2's, each row records which leg served it, and the degradation is a
    # fact to REPORT rather than a reason to throw the sample away. Measured cost
    # of the old behaviour: the R431 hard draw lost its third generation at 12/37
    # while the fallback was healthy the whole time.
    leg_state: dict[str, Any] = {"last_leg": "", "fallback_rows": 0, "warned": False}

    def observe(payload: object | None) -> None:
        """Record which leg served the row that has just landed."""
        if not isinstance(payload, dict):
            return
        served = str((_provenance(payload) or {}).get("stage2_served_by") or "")
        if not served:
            return
        leg_state["last_leg"] = served
        if served == "fallback":
            leg_state["fallback_rows"] = int(leg_state["fallback_rows"]) + 1

    def assert_healthy(payload: object | None = None) -> None:
        observe(payload)
        tripped = transport.tripped()
        if not tripped:
            return
        _, aux_total = auxiliary.counts()
        note = (
            f" {aux_total} auxiliary-leg failure(s) were seen and did NOT trip this "
            "guard."
            if aux_total
            else ""
        )
        if leg_state["last_leg"] == "fallback":
            if not leg_state["warned"]:
                leg_state["warned"] = True
                print(
                    "\n[transport] PRIMARY is down ("
                    f"{tripped}) but the FALLBACK leg is answering: continuing on "
                    "the fallback and recording `stage2_served_by=fallback` per row "
                    f"so the draw stays separable.{note}"
                )
            return
        raise RuntimeError(
            f"Stage-2 PRIMARY transport is down: {tripped}. The fallback leg is not "
            "answering either, so the rest of the sample would be graded on "
            f"deterministic Stage-1 drafts. Aborting.{note}"
        )

    return preflight, assert_healthy


def _restore_env(saved: dict[str, str | None]) -> None:
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _run_easy(
    rows, poster, url, api_key, timeout, ckpt, *, sample: int = 0
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows, 1):
        body, latency_ms, status, err, attempts, _r = poster(
            url, api_key, row.easy_messages(), timeout
        )
        answer = str((body or {}).get("answer") or "")
        refs = list((body or {}).get("references") or [])
        rec: dict[str, Any] = {
            "id": row.id,
            # R423 — which independent generation this row is. Written HERE, not
            # patched on afterwards, so the field is on disk in the checkpoint
            # the scorer reads (a post-hoc tag left the file without it).
            "sample": sample,
            "mode": "easy",
            # R293 — official difficulty label. Distinct from `mode`: `mode` is
            # HOW we replayed it, `difficulty` is the evaluator's own label. 59
            # of the 111 single-turn rows are HARD by content.
            "difficulty": row.difficulty,
            "difficulty_category": row.difficulty_category,
            "question": row.question,
            "pred_answer": answer,
            "pred_refs": refs,
            "jul07_answer": row.jul07_answer,
            "jul07_refs": list(row.jul07_refs),
            "latency_ms": latency_ms,
            "http_status": status,
            "attempts": attempts,
            "provenance": _provenance(body),
        }
        if err or not answer:
            rec["error"] = err or "empty_answer"
        else:
            rec["scores"] = _row_metrics(answer, refs)
            jul_heads = _heads(list(row.jul07_refs))
            new_heads = _heads(refs)
            rec["vs_jul07"] = {
                "ref_head_added": sorted(new_heads - jul_heads),
                "ref_head_dropped": sorted(jul_heads - new_heads),
                "ref_head_jaccard": (
                    len(new_heads & jul_heads) / len(new_heads | jul_heads)
                    if (new_heads | jul_heads)
                    else 1.0
                ),
                "answer_changed": (answer.strip() != row.jul07_answer.strip()),
            }
        out.append(rec)
        ckpt.write(json.dumps(rec, ensure_ascii=False) + "\n")
        ckpt.flush()
        tag = "ERR " if rec.get("error") else "ok  "
        print(
            f"  [{i:3d}/{len(rows)}] easy {tag}{row.id} "
            f"{latency_ms/1000:6.1f}s refs={len(refs):2d} chars={len(answer):4d}",
            flush=True,
        )
    return out


def seed_history_from_records(records) -> list[dict[str, str]]:
    """R423.3 — the rolling conversation a RESUMED hard run must start from.

    ``_run_hard``'s rolling history is what makes a row multi-turn: the route
    reads ``history_turn_count`` off the request, and the engine's single-turn
    predicate is ``history_turn_count <= 1``. So an EMPTY history does not merely
    omit context — it changes the MODALITY. Measured with
    ``docs/measurements/r423/graded_scope_probe.py``: the first two rows of a run
    with an empty rolling history read 0 and 1, so their Stage-2 dispatches carry
    the FULL ~59.6 kB system prompt, while every later row carries the 61-char
    persona.

    ``--resume`` used to hand the pending rows a brand-new empty history, so its
    first two rows were re-graded as near-single-turn — a modality its
    uninterrupted counterpart would never have had. In the R423 need gate that
    cost arm A one full-prompt dispatch that arm B did not make, i.e. it made a
    resumed arm and a continuous arm differ in the SYSTEM slot. Rebuilding the
    seed from the rows already on disk makes a resume measure the same thing the
    first run would have.

    Only rows the runner actually rolled forward are seeded: ``_run_hard`` rolls
    the history on ``if ans1``, so a record with no turn-1 answer never
    contributed an exchange and must not be invented here.
    """
    seed: list[dict[str, str]] = []
    for record in records:
        first = str(record.get("turn1_answer") or record.get("pred_answer") or "")
        question = str(record.get("question") or "")
        if not first or not question:
            continue
        seed.append({"role": "user", "content": question})
        seed.append({"role": "assistant", "content": str(record.get("pushback_answer") or first)})
    return trim_history(seed)


def _run_hard(
    rows,
    poster,
    url,
    api_key,
    timeout,
    ckpt,
    *,
    sample: int = 0,
    seed_history: list[dict[str, str]] | None = None,
    preamble: str = DEFAULT_MODE,
) -> list[dict[str, Any]]:
    """Multi-turn conversation + the judge's pushback, per question.

    ``preamble`` selects the REQUEST SHAPE, which is the one thing the official
    hard modality specifies and the previous implementation got wrong:

    * ``fixed`` (DEFAULT since R424) — the official shape: the same pre-fixed
      9-exchange dialogue (``evals.regenold.hard_preamble``) before EVERY row, so
      every row is asked as turn 10 of an identical conversation and the modality
      is a constant of the arm rather than a function of a row's position.
    * ``rolling`` (explicit opt-in; every board on record before R424) — a window
      of our own prior questions and answers, starting EMPTY. Row 1 was therefore
      asked with no context and row 5 with four exchanges of it, so the arm mixed
      modalities: ``history_turn_count`` read 0 and 1 on the leading rows, which
      is inside the Stage-2 single-turn predicate, so those rows were dispatched
      the full system prompt while every later row got the persona. Kept so the
      pre-R424 boards can be reproduced, and because a probe that MEASURES that
      leak must be able to ask for it.

    ``seed_history`` is ignored in ``fixed`` mode by construction: the fixture IS
    the history, which is what makes a resumed fixed run identical to an
    uninterrupted one (the R423.3 leak cannot recur in this mode).
    """
    fixed = preamble == MODE_FIXED
    out: list[dict[str, Any]] = []
    history: list[dict[str, str]] = [] if fixed else list(seed_history or [])
    for i, row in enumerate(rows, 1):
        # --- turn 1: the question inside the running conversation ----------
        msgs1 = (
            build_prefixed_messages(row.question)
            if fixed
            else build_hard_messages(row, history)
        )
        body1, lat1, st1, err1, att1, _ = poster(url, api_key, msgs1, timeout)
        ans1 = str((body1 or {}).get("answer") or "")
        refs1 = list((body1 or {}).get("references") or [])

        # --- turn 2: pushback ----------------------------------------------
        ans2, refs2, lat2, st2, err2, att2 = "", [], 0.0, None, None, 0
        if ans1:
            msgs2 = (
                build_prefixed_pushback_messages(
                    row.question, ans1, row.pushback_content()
                )
                if fixed
                else build_pushback_messages(row, history, ans1)
            )
            body2, lat2, st2, err2, att2, _ = poster(url, api_key, msgs2, timeout)
            ans2 = str((body2 or {}).get("answer") or "")
            refs2 = list((body2 or {}).get("references") or [])

        rec: dict[str, Any] = {
            "id": row.id,
            # R423 — see ``_run_easy``: the generation index must be on disk.
            "sample": sample,
            "mode": "hard",
            # R424 — which REQUEST SHAPE produced this row, and the fixture's
            # digest when there was one. A board is only interpretable if the
            # shape that produced it is on the row.
            "hard_preamble": preamble,
            "hard_preamble_digest": _FIXED_PREAMBLE_DIGEST if fixed else "",
            # R293 — in hard mode every row is HARD / Multi-Turn Context &
            # Coreference by the official taxonomy, so the per-question label
            # from the single-turn export is not the operative one here; keep it
            # for cross-mode comparison of the SAME question.
            "difficulty": row.difficulty,
            "difficulty_category": row.difficulty_category,
            "question": row.question,
            # The graded answer for hard mode is the POST-pushback one; keep
            # turn 1 alongside so the flip is measurable.
            "pred_answer": ans2 or ans1,
            "pred_refs": refs2 or refs1,
            # Provenance of the GRADED turn (post-pushback when it landed).
            "provenance": _provenance(body2 if ans2 else body1),
            "turn1_answer": ans1,
            "turn1_refs": refs1,
            "pushback_answer": ans2,
            "pushback_refs": refs2,
            "jul07_answer": row.jul07_answer,
            "jul07_refs": list(row.jul07_refs),
            "latency_ms": (lat1 or 0) + (lat2 or 0),
            # R409 — per-turn latency. The official hard-mode Resp. Speed is per
            # graded response: on Aug-25 the same system scored hard 85.7 vs easy
            # 87.6, where a two-turn sum would read about twice the easy latency.
            # ``score_arm`` scores the graded turn and falls back to the sum only
            # for checkpoints written before these fields existed.
            "turn1_latency_ms": lat1 or 0,
            "pushback_latency_ms": lat2 or 0,
            "http_status": st2 or st1,
            "attempts": (att1 or 0) + (att2 or 0),
        }
        if err1 or not ans1:
            rec["error"] = err1 or "empty_answer_turn1"
        elif err2 or not ans2:
            rec["error"] = err2 or "empty_answer_pushback"
        else:
            rec["scores"] = _row_metrics(ans2, refs2)
            h1, h2 = _heads(refs1), _heads(refs2)
            rec["pushback"] = {
                # Did the pushback change the citation set at all?
                "ref_heads_changed": sorted(h1 ^ h2),
                "ref_head_jaccard": (
                    len(h1 & h2) / len(h1 | h2) if (h1 | h2) else 1.0
                ),
                "answer_changed": ans1.strip() != ans2.strip(),
                "turn1_chars": len(ans1),
                "pushback_chars": len(ans2),
                # A capitulation marker: conceding under pressure without new law.
                "conceded": any(
                    p in ans2.lower()
                    for p in (
                        "i apologise",
                        "i apologize",
                        "you are right",
                        "you're right",
                        "i was incorrect",
                        "my previous answer",
                        "correction:",
                    )
                ),
            }
        out.append(rec)
        ckpt.write(json.dumps(rec, ensure_ascii=False) + "\n")
        ckpt.flush()

        # Roll the conversation forward exactly as the judge did. In FIXED mode
        # there is nothing to roll: every row is asked inside the same fixture,
        # which is the whole point of the mode.
        if ans1 and not fixed:
            history = trim_history(
                [
                    *history,
                    {"role": "user", "content": row.question},
                    {"role": "assistant", "content": ans2 or ans1},
                ]
            )
        tag = "ERR " if rec.get("error") else "ok  "
        flip = ""
        if rec.get("pushback", {}).get("ref_heads_changed"):
            flip = "  REF-FLIP"
        if rec.get("pushback", {}).get("conceded"):
            flip += "  CONCEDED"
        print(
            f"  [{i:3d}/{len(rows)}] hard {tag}{row.id} "
            f"{(rec['latency_ms'])/1000:6.1f}s refs={len(refs2):2d}{flip}",
            flush=True,
        )
    return out


#: Axes worth breaking out per difficulty stratum. Deliberately NOT every axis —
#: a 1-row stratum (Borderline Prohibition) makes most means meaningless, and a
#: wall of noisy numbers is how a real signal gets missed.
_STRATUM_AXES = ("n", "errors", "refusal_rate", "n_refs", "tone", "latency_p50_ms")


def _stratify(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """R293 — aggregate per official difficulty label and per category.

    The point: a single blended number hides which half of the batch is weak.
    52 of the single-turn requests are EASY (direct statutory lookup) and 59 are
    HARD by content, so a mediocre blended score can mean either "we are bad at
    lookups" or "we are fine at lookups and bad at decision boundaries" — very
    different problems with very different fixes.

    Strata with n < 3 still report, but carry ``low_n: True`` so nobody reads a
    mean over one row as a trend.
    """
    out: dict[str, Any] = {}
    for key, field in (("by_difficulty", "difficulty"), ("by_category", "difficulty_category")):
        buckets: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            label = str(r.get(field) or "")
            if not label:
                label = "(unlabelled)"
            buckets.setdefault(label, []).append(r)
        section: dict[str, Any] = {}
        for label, brows in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
            agg = _aggregate(brows)
            slim = {k: agg[k] for k in _STRATUM_AXES if k in agg}
            if agg.get("n", 0) < 3:
                slim["low_n"] = True
            section[label] = slim
        out[key] = section
    return out


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if not r.get("error")]
    if not ok:
        return {"n": 0, "errors": len(rows)}
    out: dict[str, Any] = {"n": len(ok), "errors": len(rows) - len(ok)}
    for axis in ("tone", "n_refs", "n_ref_heads", "answer_chars"):
        out[axis] = st.mean(r["scores"][axis] for r in ok)
    out["refusal_rate"] = sum(1 for r in ok if r["scores"]["refused"]) / len(ok)
    # R292 — Stage-2 provenance. `stage2_landed_rate` well under 1.0 means the
    # LLM path degraded mid-run and the scorecard is measuring the deterministic
    # fallback, not the system under test. Check this BEFORE reading any axis.
    prov = [r.get("provenance") or {} for r in ok]
    seen = [p for p in prov if p.get("stage2_polish") is not None]
    if seen:
        out["stage2_landed_rate"] = sum(
            1 for p in seen if p.get("stage2_polish")
        ) / len(seen)
        models = sorted({p.get("stage2_model") or "?" for p in seen if p.get("stage2_polish")})
        out["stage2_models"] = models
        paths: dict[str, int] = {}
        for p in prov:
            key = str(p.get("retrieval_path") or "unknown")
            paths[key] = paths.get(key, 0) + 1
        out["retrieval_paths"] = dict(sorted(paths.items(), key=lambda kv: -kv[1]))
    else:
        out["stage2_landed_rate"] = None  # trace not requested / not available
    lat = sorted(r["latency_ms"] for r in ok)
    out["latency_p50_ms"] = lat[len(lat) // 2]
    out["latency_p90_ms"] = lat[int(len(lat) * 0.9)] if len(lat) > 1 else lat[0]
    pb = [r["pushback"] for r in ok if r.get("pushback")]
    if pb:
        out["pushback_ref_flip_rate"] = sum(
            1 for p in pb if p["ref_heads_changed"]
        ) / len(pb)
        out["pushback_ref_jaccard"] = st.mean(p["ref_head_jaccard"] for p in pb)
        out["pushback_conceded_rate"] = sum(1 for p in pb if p["conceded"]) / len(pb)
    vj = [r["vs_jul07"] for r in ok if r.get("vs_jul07")]
    if vj:
        out["vs_jul07_ref_jaccard"] = st.mean(v["ref_head_jaccard"] for v in vj)
        out["vs_jul07_answer_changed_rate"] = sum(
            1 for v in vj if v["answer_changed"]
        ) / len(vj)
    return out


def _print_strata(strata: dict[str, Any]) -> None:
    """R293 — print the per-difficulty / per-category breakdown."""
    for section, title in (
        ("by_difficulty", "by OFFICIAL difficulty"),
        ("by_category", "by difficulty category"),
    ):
        buckets = strata.get(section) or {}
        if len(buckets) < 2:
            continue  # nothing to compare against
        print(f"\n  --- {title} ---")
        for label, s in buckets.items():
            flag = "  [low n]" if s.get("low_n") else ""
            bits = [f"n={s.get('n', 0)}"]
            for k in ("refusal_rate", "n_refs", "tone"):
                if k in s:
                    bits.append(f"{k}={s[k]:.3f}")
            if "latency_p50_ms" in s:
                bits.append(f"p50={s['latency_p50_ms'] / 1000:.1f}s")
            print(f"    {label[:46]:<46} {'  '.join(bits)}{flag}")


def _print_agg(title: str, agg: dict[str, Any]) -> None:
    print(f"\n=== {title} (n={agg.get('n', 0)}, errors={agg.get('errors', 0)}) ===")
    for k, v in agg.items():
        if k in ("n", "errors"):
            continue
        if k.endswith("_ms"):
            print(f"  {k:<32}{v/1000:>10.1f}s")
        elif isinstance(v, float):
            print(f"  {k:<32}{v:>10.4f}")
        elif isinstance(v, (list, tuple)):
            # R292 — stage2_models etc. are lists; ">10" formatting raises.
            print(f"  {k:<32}{', '.join(str(x) for x in v) or '-':>10}")
        elif isinstance(v, dict):
            print(f"  {k:<32}{', '.join(f'{a}={b}' for a, b in v.items()):>10}")
        elif v is None:
            print(f"  {k:<32}{'n/a':>10}")
        else:
            print(f"  {k:<32}{v:>10}")


def _clear_engine_cache() -> tuple[int, str | None]:
    """Empty the route's response cache before a generation runs.

    R423 — ``repeats > 1`` is a claim that every row gets that many
    INDEPENDENT generations of Stage-2. It was not true. The route answers from
    ``app.routes.regenold._ENGINE_CACHE`` keyed on
    (question, context, history depth, env), and every generation of a row sends
    the same key, so generations 2..K replayed generation 1 without ever
    dialling a provider.

    MEASURED on the first R423 hard gate (37 rows × 3 generations, both arms):
    arm B's generations 2 and 3 were byte-identical to generation 1 on **23 of
    37 rows** at p50 latency **1.6 s** against generation 1's **43.6 s**, and the
    arm made 73 provider calls across three generations that each constitute 74
    asks. A median over duplicated values reports draw-to-draw stability it
    never measured — and it does so invisibly, which is the same failure shape
    R422 shipped (a void run read as a null).

    Returns ``(entries_cleared, error)``. The cache lives in this process: the
    harness drives the app in-process (``local://app.main:app``), so a remote
    ``--endpoint`` run reports the error instead of pretending it cleared one.
    """
    try:
        from app.routes.regenold import _ENGINE_CACHE  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        return 0, f"_ENGINE_CACHE unreachable: {exc!r}"
    try:
        cleared = len(getattr(_ENGINE_CACHE, "_data", {}) or {})
        _ENGINE_CACHE.clear()
        return cleared, None
    except Exception as exc:  # noqa: BLE001
        return 0, f"_ENGINE_CACHE.clear() raised: {exc!r}"


def _repeat_independence(
    replicates: list[list[dict[str, Any]]],
) -> float | None:
    """Largest byte-identical rate between CONSECUTIVE generations.

    ``None`` when there is only one generation (nothing to compare). Rows whose
    answer is a curated deterministic intercept are identical by design, so the
    floor is the intercept share (~24%% of the official hard split) and only a
    MAJORITY-identical pair is evidence of replay.
    """
    if len(replicates) < 2:
        return None
    rates: list[float] = []
    for first, second in zip(replicates, replicates[1:], strict=False):
        by_id = {r["id"]: r for r in second}
        common = [r for r in first if r["id"] in by_id]
        if not common:
            continue
        same = sum(
            1
            for row in common
            if str(row.get("pred_answer") or "").strip()
            == str(by_id[row["id"]].get("pred_answer") or "").strip()
        )
        rates.append(same / len(common))
    return max(rates) if rates else None


def _arm(
    label: str,
    mode: str,
    rows,
    *,
    poster,
    url: str,
    api_key: str | None,
    timeout: float,
    arm_env: dict[str, str],
    suffix: str,
    resume: bool = False,
    repeats: int = 1,
    preflight: Callable[[], str] | None = None,
) -> dict[str, Any]:
    saved = _apply_env(arm_env)
    repeats = max(1, int(repeats))
    # R424 — the REQUEST SHAPE this arm runs, resolved AFTER ``_apply_env`` so a
    # ``--baseline-env REGENOLD_HARD_PREAMBLE=…`` declaration is what the harness
    # actually posts. Raises on an unrecognised value rather than silently
    # running the other shape (see ``hard_preamble_mode``).
    preamble = hard_preamble_mode()
    print(f"  hard-mode request shape: {preamble}")
    try:
        if preflight is not None:
            # R442 — probe THIS arm's Stage-2 model under THIS arm's env. The
            # batch-level preflight runs before any arm env is applied, so an
            # A/B whose lever is the model itself (``P2P_GRAPH_RAG_COMPLEX_MODEL``)
            # never probed the branch arm's model. Inside the ``try`` so a
            # refusal still restores the environment.
            print(f"  Stage-2 preflight for this arm OK (model={preflight()})")
        result: dict[str, Any] = {}
        for m in ("easy", "hard"):
            if mode not in (m, "both"):
                continue
            replicates: list[list[dict[str, Any]]] = []
            primary: dict[str, Any] = {}
            # R423 — REPEATS>1 gives every row that many INDEPENDENT generations
            # on the same arm, which is what a length/shape lever needs: the
            # judge axes move by a criterion or two (2 of 87 rows on the R416
            # gate) and R419 already showed two rows whose credited criteria are
            # draw-dependent, so a single draw cannot separate a real delta from
            # generation noise. The FIRST sample keeps the shipped checkpoint
            # path and the shipped --resume contract; later samples land in
            # sibling ``.r{K}`` files with identical schema, so nothing that
            # reads the existing checkpoint changes shape.
            with ArmProbe(f"{label}{suffix}") as probe:
                for k in range(repeats):
                    ckpt_path = _RESULTS / (
                        f"official-{label}{suffix}-{m}.ckpt.jsonl"
                        if k == 0
                        else f"official-{label}{suffix}-{m}.r{k}.ckpt.jsonl"
                    )
                    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
                    print(
                        f"\n--- {label}{suffix} :: {m} sample {k + 1}/{repeats} "
                        f"(n={len(rows)}) -> {ckpt_path.name}"
                    )
                    # R423 — a repeat must be a NEW draw. Clear the route's
                    # response cache or generation k replays generation 1 (see
                    # `_clear_engine_cache`).
                    cleared, cache_error = _clear_engine_cache()
                    print(
                        f"  response cache: cleared {cleared} entrie(s)"
                        + (f" — NOT CLEARED: {cache_error}" if cache_error else "")
                    )
                    previous: list[dict[str, Any]] = []
                    pending = list(rows)
                    file_mode = "w"
                    # Resume applies to EVERY sample, not just the primary one.
                    # A replica's ids repeat ACROSS samples, never within one
                    # file, and the validator is per file — so the repeated-id
                    # check that catches a truncated checkpoint still holds.
                    # (Measured: a restart 15 rows into replica 2 of a 3x2 gate
                    # discarded both finished replicas of the other arm on
                    # re-launch, ~1.5 h of live provider draws for nothing.)
                    if resume and ckpt_path.exists():
                        seen: set[str] = set()
                        for line in ckpt_path.read_text(encoding="utf-8").splitlines():
                            if not line.strip():
                                continue
                            try:
                                record = json.loads(line)
                            except json.JSONDecodeError as exc:
                                raise RuntimeError(
                                    f"invalid resume checkpoint row in {ckpt_path.name}: "
                                    "truncated or corrupt JSON line"
                                ) from exc
                            row_id = str(record.get("id") or "")
                            if not row_id or row_id in seen or record.get("mode") != m:
                                raise RuntimeError(
                                    f"invalid resume checkpoint row in {ckpt_path.name}: "
                                    f"{row_id!r}"
                                )
                            seen.add(row_id)
                            previous.append(record)
                        pending = [row for row in rows if row.id not in seen]
                        file_mode = "a"
                        print(f"  resuming: {len(previous)} complete, {len(pending)} pending")
                    # Default remains overwrite (R292). Append is allowed only
                    # through the explicit, validated --resume path above.
                    with ckpt_path.open(file_mode, encoding="utf-8") as ckpt:
                        if m == "easy":
                            runner = _run_easy
                            fresh = runner(
                                pending, poster, url, api_key, timeout, ckpt, sample=k
                            )
                        else:
                            runner = _run_hard
                            # R423.3 — seed the rolling conversation from the rows
                            # already drawn, or a resumed hard run re-grades its
                            # first two rows as near-single-turn (see
                            # ``seed_history_from_records``). Continuous runs have
                            # no ``previous`` and keep the shipped empty start.
                            # R424 — only meaningful for the ROLLING shape; the
                            # fixed shape's history is the fixture, so a resumed
                            # fixed run is identical to an uninterrupted one.
                            seed = (
                                [] if preamble == MODE_FIXED
                                else seed_history_from_records(previous)
                            )
                            if previous and seed:
                                print(
                                    f"  resuming hard with {len(seed)} seeded "
                                    f"conversation message(s) from "
                                    f"{len(previous)} drawn row(s)"
                                )
                            fresh = runner(
                                pending, poster, url, api_key, timeout, ckpt,
                                sample=k, seed_history=seed, preamble=preamble,
                            )
                    by_id = {r["id"]: r for r in previous + fresh}
                    got = [by_id[row.id] for row in rows if row.id in by_id]
                    for record in got:
                        # Resume can bring back rows written before this field
                        # existed; the runner sets it on every fresh row.
                        record.setdefault("sample", k)
                    replicates.append(got)
                    if k == 0:
                        # The GRADED rows carry their own Stage-2 provenance,
                        # which is what `count_deterministic_rows` needs; the
                        # request rows do not.
                        primary = {
                            "rows": got,
                            "agg": _aggregate(got),
                            "strata": _stratify(got),
                        }
            # The probe closes once per ARM, not per sample, so its transport
            # counters and payload hashes cover every generation that ran.
            got = primary.get("rows") or []
            identical_rate = _repeat_independence(replicates)
            # R423.2 — the rows whose graded draw did NOT come from the primary
            # leg, across EVERY generation. A single primary read-timeout with a
            # dead fallback credential ships one Stage-1 draft; the guard needs
            # those ids to EXCLUDE them from both arms instead of voiding a
            # five-hour paired gate for a hiccup the caller can account for.
            primary["degraded_ids"] = sorted({
                row_id
                for sample in replicates
                for row_id in degraded_row_ids(sample)
            })
            # R423 — per-sample determinism, not just sample 0's. The gate's
            # numbers are medians across the generations, so a generation that
            # shipped Stage-1 drafts while its siblings were polished has to be
            # visible on its own; the arm total hides it (measured: arm A read
            # healthy on 47 primary completions while sample 3 was 28/28 drafts).
            primary["provenance"] = probe.provenance(
                rows=got,
                repeats=repeats,
                repeat_identical_rate=identical_rate,
                sample_rows=replicates,
                request_shape=(
                    f"{preamble}:{_FIXED_PREAMBLE_DIGEST}"
                    if preamble == MODE_FIXED
                    else MODE_ROLLING
                ),
                # R425 — what this arm actually EMITTED. A route pass that
                # rewrites the references after Stage-2 leaves every dispatched
                # byte identical, so this is the only place its effect can be
                # seen before scoring; without it an inert call site would read
                # as a clean null (``lever_slot="wire"``).
                wire_shape=wire_shape_digest(got),
            )
            if repeats > 1:
                primary["samples"] = [[r["id"] for r in sample] for sample in replicates]
                primary["n_samples"] = len(replicates)
                primary["agg_first_sample_only"] = True
                primary["repeat_identical_rate"] = identical_rate
                print(
                    f"  generations: {repeats} per row; largest byte-identical "
                    f"rate between consecutive generations "
                    f"{'n/a' if identical_rate is None else f'{identical_rate:.0%}'}"
                )
                if identical_rate is not None and identical_rate > 0.5:
                    print(
                        "  WARNING: most rows were replayed between generations — "
                        "the generations are NOT independent draws and the gate "
                        "will void this arm."
                    )
            result[m] = primary
            _print_agg(f"{label}{suffix} {m}", result[m]["agg"])
            _print_strata(result[m]["strata"])
        return result
    finally:
        _restore_env(saved)


def _parse_env(pairs: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"--*-env expects KEY=VALUE, got {p!r}")
        k, v = p.split("=", 1)
        out[k.strip()] = v
    return out


def select_rows(
    rows: list[Any],
    *,
    ids: str | None = None,
    stride: int = 0,
    limit: int = 0,
) -> list[Any]:
    """R423.1 — the row selection, as a function so it can be pinned by a test.

    Order is ``--ids``, then ``--stride``, then ``--limit``.

    ``--ids`` exists because a stride reaches a specific row only by luck, and
    the rows a gate LOST are the first rows a fix has to be tested on: without
    it, a targeted regression screen has to run the whole board again. It also
    must resolve — an unknown id raises rather than silently shrinking the run,
    which is the R422 failure shape (a sample read as the board).
    """
    if ids:
        wanted = [x.strip() for x in ids.replace(",", " ").split() if x.strip()]
        by_id = {r.id: r for r in rows}
        missing = [x for x in wanted if x not in by_id]
        if missing:
            raise SystemExit(f"--ids not in the official batch: {missing}")
        rows = [by_id[x] for x in wanted]
    if stride:
        if stride < 1:
            raise SystemExit("--stride must be >= 1")
        rows = rows[::stride]
    if limit:
        rows = rows[:limit]
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--label", required=True)
    ap.add_argument("--mode", choices=("easy", "hard", "both"), default="easy")
    ap.add_argument("--endpoint", default=None)
    ap.add_argument("--api-key", default=os.environ.get("REGENOLD_API_KEY"))
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--limit", type=int, default=0, help="first N questions only")
    ap.add_argument(
        "--ids",
        default=None,
        help=(
            "R423.1 — comma/space separated question ids to run INSTEAD of a "
            "stride, so a regression screen can be aimed at the rows a previous "
            "gate lost. Every id must exist; an unknown id aborts the run."
        ),
    )
    ap.add_argument(
        "--stride",
        type=int,
        default=0,
        help=(
            "take every Nth question instead of the first N — a REPRESENTATIVE sample "
            "across the send order. The send order is front-loaded with the easy rows, "
            "so a prefix is NOT the board's mix: the full 110 are 51 easy / 59 hard "
            # ``%`` is argparse's help-interpolation character: a bare percent
            # here makes ``--help`` raise "must be real number, not dict" and
            # takes the whole runner's CLI down with it. Doubled, as argparse
            # requires (caught by tests/test_r423_harness_repeats.py).
            "(46%% easy) while --limit 40 is 27 easy / 13 hard (68%% easy), and "
            "--stride 6 gives 6 easy / 13 hard. A skewed prefix has already produced "
            "misleading readings (R422). Applied BEFORE --limit, so the two compose "
            "as 'every Nth question, first M of those'."
        ),
    )
    ap.add_argument(
        "--resume",
        action="store_true",
        help="validate and continue this label's existing checkpoint",
    )
    ap.add_argument(
        "--repeats",
        type=int,
        default=1,
        help=(
            "R423 — independent generations per row PER ARM. The first sample "
            "writes the shipped checkpoint; later samples write sibling "
            ".r{K}.ckpt.jsonl files with the same schema and a `sample` key on "
            "each row. Use 3+ for a length/shape lever: the judged axes move by "
            "a criterion or two, and R419 measured rows whose credited criteria "
            "are draw-dependent, so one draw cannot separate a delta from noise."
        ),
    )
    ap.add_argument("--baseline-env", action="append", default=None)
    ap.add_argument("--branch-env", action="append", default=None)
    ap.add_argument(
        "--allow-degraded-transport",
        action="store_true",
        help=(
            "skip the Stage-2 transport preflight and the abort-on-outage guard "
            "(R423). Only for a run that deliberately measures the degradation "
            "path; without it a live run refuses to grade Stage-1 drafts."
        ),
    )
    ap.add_argument(
        "--require-cohere",
        action="store_true",
        help="fail closed unless local embeddings and eligible reranks use Cohere",
    )
    ap.add_argument(
        "--require-cohere-rerank",
        action="store_true",
        help="fail closed unless eligible reranks use Cohere; embeddings may stay offline",
    )
    ap.add_argument(
        "--cohere-rerank-min-gap",
        type=float,
        default=0.0,
        help="minimum seconds between Cohere rerank calls (use 6.5 for trial keys)",
    )
    args = ap.parse_args()
    acquire_run_lock(args.label)

    if args.require_cohere and args.require_cohere_rerank:
        raise SystemExit("choose only one of --require-cohere and --require-cohere-rerank")
    require_any_cohere = args.require_cohere or args.require_cohere_rerank
    if require_any_cohere and args.endpoint:
        raise SystemExit(
            "Cohere strict modes support local-live evaluation only: the deployed "
            "wire response does not expose provider provenance"
        )
    if args.cohere_rerank_min_gap and not require_any_cohere:
        raise SystemExit("--cohere-rerank-min-gap requires a Cohere strict mode")

    rows = select_rows(
        list(load_official_batch()),
        ids=args.ids,
        stride=args.stride,
        limit=args.limit,
    )

    from evals.regenold.runner_v2 import _post, _post_local

    local = not args.endpoint
    poster = _post_local if local else _post
    # Health checks that abort the batch the moment the run stops being
    # measurable. They are composed into ONE poster wrapper so a run can carry
    # both without the second replacement discarding the first.
    health_checks: list[Callable[[], None]] = []
    if require_any_cohere:
        health_checks.append(
            _install_cohere_guard(
                require_embeddings=args.require_cohere,
                min_rerank_gap_s=args.cohere_rerank_min_gap,
            )
        )
    arm_preflight: Callable[[], str] | None = None
    if local and not args.allow_degraded_transport:
        # R423 — a live run whose Stage-2 primary cannot answer grades Stage-1
        # drafts, so it measures the transport, not the lever. Probe once now
        # (before a single row is spent) and abort if the leg later goes down.
        preflight, assert_stage2_healthy = _install_stage2_transport_guard()
        arm_preflight = preflight
        served_by = preflight()
        print(
            "Stage-2 transport preflight OK"
            + (f" (model={served_by})" if served_by else "")
            + "; aborting the batch after 5 consecutive Stage-2 failures."
        )
        health_checks.append(assert_stage2_healthy)
    if health_checks:
        base_poster = poster

        def guarded_poster(*poster_args, **poster_kwargs):
            slept_before = _PACING_SLEPT_S[0]
            result = base_poster(*poster_args, **poster_kwargs)
            for check in health_checks:
                # R431 — the Stage-2 guard needs the row it just drew in order to
                # tell "the primary is down" from "the primary is down AND the
                # fallback is carrying the run". The Cohere guard ignores it.
                check(result)
            return _net_of_pacing(result, slept_before)

        poster = guarded_poster
    url = (
        "local://app.main:app/api/v1/regenold/eu-ai-act/ask"
        if local
        else str(args.endpoint)
    )
    # R292 — ask for the reasoning trace so `_provenance` can record whether
    # Stage-2 actually landed (see `_provenance`). The rubric ignores the
    # `reasoning` field, so this cannot affect a score; it only makes a
    # silently-degraded run detectable.
    if "include_reasoning" not in url:
        url = f"{url}{'&' if '?' in url else '?'}include_reasoning=true"

    base_env = _parse_env(args.baseline_env)
    branch_env = _parse_env(args.branch_env)
    ab = bool(base_env or branch_env)

    payload: dict[str, Any] = {
        "label": args.label,
        "batch": "regenold-official-2026-07-07",
        "n_questions": len(rows),
        "mode": args.mode,
        "endpoint": url,
        "repeats": args.repeats,
        "baseline_env": base_env,
        "branch_env": branch_env,
    }

    baseline = _arm(
        args.label, args.mode, rows,
        poster=poster, url=url, api_key=args.api_key, timeout=args.timeout,
        arm_env=base_env, suffix="-A" if ab else "", resume=args.resume,
        repeats=args.repeats, preflight=arm_preflight,
    )
    payload["baseline"] = {m: v["agg"] for m, v in baseline.items()}

    if ab:
        # SEQUENTIAL — one local Claude Max backs every wrapper call.
        branch = _arm(
            args.label, args.mode, rows,
            poster=poster, url=url, api_key=args.api_key, timeout=args.timeout,
            arm_env=branch_env, suffix="-B", resume=args.resume,
            repeats=args.repeats, preflight=arm_preflight,
        )
        payload["branch"] = {m: v["agg"] for m, v in branch.items()}
        lever = lever_changes_system(base_env, branch_env)
        # R424 — a lever can live ABOVE the engine: the conversation the harness
        # posts before the question. Then the system slot is SUPPOSED to be
        # byte-identical across the arms, and the guard's non-vacuity check has to
        # move to the request shape (see ``gate_validity.assess``). If both slots
        # differ, the system check wins — it is the stronger of the two and
        # relaxing it would be a real weakening.
        request_lever = lever_changes_request(base_env, branch_env)
        # R425 — the third slot. A route pass that rewrites the emitted
        # references changes no dispatched byte, so it must be declared here or
        # the guard has nothing to check non-vacuity against.
        wire_lever = lever_changes_wire(base_env, branch_env)
        if lever[0]:
            lever_slot = "system"  # strongest: the system slot is under test
        elif wire_lever[0]:
            lever_slot = "wire"
        elif request_lever[0]:
            lever_slot = "request"
        else:
            lever_slot = "system"
        payload["lever_changes_system"] = {"changes": lever[0], "why": lever[1]}
        payload["lever_changes_request"] = {
            "changes": request_lever[0], "why": request_lever[1]
        }
        payload["lever_changes_wire"] = {
            "changes": wire_lever[0], "why": wire_lever[1]
        }
        payload["lever_slot"] = lever_slot
        for m in baseline:
            b, c = baseline[m]["agg"], branch.get(m, {}).get("agg", {})
            if not c:
                continue
            # R422 — REFUSE TO PUBLISH A VOID DELTA. This runner printed a
            # +560-char "skeleton" delta off a run where the wrapper returned
            # 500 'No response from Claude Code' through the whole baseline arm
            # and Bedrock's fallback leg answered 403 on every model, so the
            # baseline arm shipped deterministic Stage-1 drafts on 13 of 19 rows
            # while the branch arm was polished. The delta was transport
            # recovery, not the lever. `assess` reads the counters this process
            # itself incremented (`app.llm.stage2_policy`) plus the payload
            # hashes, so the same outage can never be read as a result again.
            base_prov = baseline[m].get("provenance")
            branch_prov = branch[m].get("provenance")
            if base_prov is not None and branch_prov is not None:
                # R423.2 — EXCLUDE, SYMMETRICALLY, THE ROWS A DEGRADED LEG
                # SERVED. The void guard's own prescription: "rows that shipped
                # a draft because of it belong in the excluded set, not averaged
                # over". A row dropped from one arm must leave the other arm too,
                # or the comparison stops being paired. ``assess`` then checks
                # the accounting (each excluded row absorbs at most one
                # off-contract refusal; the set must stay a minority) and every
                # arm-level rule still applies to what remains.
                excluded = sorted(
                    set(baseline[m].get("degraded_ids") or [])
                    | set(branch.get(m, {}).get("degraded_ids") or [])
                )
                if excluded:
                    print(
                        f"\n=== R423.2 EXCLUDED (degraded leg, dropped from BOTH "
                        f"arms): n={len(excluded)} {', '.join(excluded[:8])}"
                        f"{'…' if len(excluded) > 8 else ''}"
                    )
                verdict = assess(
                    base=base_prov,
                    branch=branch_prov,
                    lever=lever,
                    excluded_rows=len(excluded),
                    lever_slot=lever_slot,
                )
                payload.setdefault("gate", {})[m] = verdict.as_dict()
                payload["gate"][m]["excluded_rows"] = excluded
                print(f"\n=== GATE VALIDITY {m} ===")
                print(verdict.render())
                if not verdict.valid:
                    payload["void"] = payload.get("void", []) + [m]
                    continue
            print(f"\n=== DELTA {m} (baseline -> branch) ===")
            for k in sorted(set(b) & set(c)):
                if k in ("n", "errors") or not isinstance(b[k], (int, float)):
                    continue
                print(f"  {k:<32}{b[k]:>10.4f}{c[k]:>10.4f}{c[k]-b[k]:>+10.4f}")

    out = _RESULTS / f"official-{args.label}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
