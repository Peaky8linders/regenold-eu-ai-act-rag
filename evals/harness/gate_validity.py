"""Void-run detection for paired A/B gates — a null read is never enough.

WHY THIS MODULE EXISTS
----------------------
A paired gate answers one question: did the lever move the wire? Two failure
modes make a run structurally incapable of answering it while still printing a
clean, plausible, all-zeros delta table:

1. **The fallback leg served the arms.** Stage-2 is tunnel → Bedrock
   (``app.llm.stage2_policy``). Bedrock always receives the FULL system prompt,
   so a lever that edits the system slot delivers *identical bytes* to both arms
   once the tunnel is down. MEASURED (R412): a complete 95+95 paired run for
   ``REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN`` showed NO speedup at all — the
   honest-looking null. It was **VOID**: its log carried 189
   ``bedrock_auto_fallback`` lines. The valid re-run, same lever, same corpus,
   carried 0 and won on every axis. The void delta and a real null delta are
   the SAME SHAPE, which is why this cannot be left to the reader.

2. **The arms' system payloads were identical.** An inert lever (its call site
   never fires, R397/R398) also reads as a null. If the lever is declared to
   target the system slot, the dispatched system payloads MUST differ; if the
   recorder saw one payload, the run cannot measure the lever.

So the gate refuses to report deltas unless it can show the primary leg carried
both arms AND that a system-slot lever actually changed the system payload.

WHAT IS *NOT* A VOID (deliberately)
----------------------------------
* A non-system lever (retrieval, route post-processing, reference shaping) may
  legitimately dispatch identical system payloads; the identity check is only
  armed for system-slot levers — see :func:`lever_changes_system`.
* A remote ``--endpoint`` run cannot read this process's counters. Liveness is
  then the caller's assertion, exactly as ``easyhard_ab._transport_liveness``
  already documents; this module reports the counters it can see and says so.

USAGE
-----
    from evals.harness import gate_validity

    with gate_validity.ArmProbe("baseline") as base:
        base_rows = run_arm(...)
    with gate_validity.ArmProbe("branch") as branch:
        branch_rows = run_arm(...)

    verdict = gate_validity.assess(
        base=base.provenance(rows=base_rows),
        branch=branch.provenance(rows=branch_rows),
        lever=gate_validity.lever_changes_system(base_env, branch_env),
    )
    print(verdict.render())
    if not verdict.valid:
        ...  # do not print deltas
"""
from __future__ import annotations

import hashlib
import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "ArmProbe",
    "ArmProvenance",
    "GateVerdict",
    "SYSTEM_SLOT_FLAGS",
    "assess",
    "count_rows_served_by",
    "lever_changes_system",
    "stage2_transport_snapshot",
]

#: Stage-2 primary (the Claude Max tunnel) and fallback (AWS Bedrock) ids.
PRIMARY = "openai_wrapper"
FALLBACK = "bedrock"

#: Flags whose ONLY job is to choose which system payload Stage-2 dispatches.
#: Curated on purpose: arming the payload-identity check for a lever that edits
#: the user prompt or the retrieved evidence would VOID correct runs (Bedrock and
#: the wrapper legitimately share bytes there). Verified against the call sites —
#: ``_graph_rag_impl._claude_max_enhance_answer`` selects ``system`` from
#: ``REGENOLD_STAGE2_FULL_SYSTEM`` and ``REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN``.
#: Add a flag here only with the call site that reads it.
SYSTEM_SLOT_FLAGS: frozenset[str] = frozenset(
    {
        "REGENOLD_STAGE2_FULL_SYSTEM",
        "REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN",
    }
)

def stage2_transport_snapshot() -> dict[str, Any]:
    """Counters from ``app.llm.stage2_policy``, or an error marker.

    Never raises: a provenance probe must not take down the gate it protects,
    and it must not launder an import failure into "clean" either.
    """
    try:
        from app.llm.stage2_policy import transport_stats  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return {"_error": f"could not import transport_stats: {exc!r}"}
    try:
        return dict(transport_stats())
    except Exception as exc:  # noqa: BLE001
        return {"_error": f"transport_stats() raised: {exc!r}"}


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def _digest(hashes: list[str]) -> str:
    """Stable digest over the SET of distinct payloads an arm dispatched."""
    if not hashes:
        return ""
    return _sha("|".join(sorted(set(hashes))))


@dataclass
class ArmProvenance:
    """What one arm actually dialled and dispatched."""

    label: str
    rows: int = 0
    #: R422 — graded answers that were served by the DETERMINISTIC Stage-1 draft,
    #: i.e. Stage-2 never landed. Read from each row's own provenance
    #: (``stage2_served_by == 'deterministic'``, or ``stage2_polish is False`` on
    #: a checkpoint that predates that field). This is the counter that catches
    #: the R422 incident: the transport counters said the run was merely quiet
    #: while 13 of 19 baseline rows had shipped a Stage-1 draft.
    deterministic_graded: int = 0
    stats: dict[str, Any] = field(default_factory=dict)
    #: Distinct system payload hashes for the graded answer call.
    system_hashes: tuple[str, ...] = ()
    #: Distinct user payload hashes for the graded answer call.
    user_hashes: tuple[str, ...] = ()
    system_lengths: tuple[int, ...] = ()
    calls: int = 0
    #: R423 — provider ids the transport policy refused, with a count each.
    #: ``refused`` counts the events; this names them, which is what tells an
    #: operator whether a Groq/Gemini escape hatch was reached (a failure path)
    #: or the wrapper's own base URL was misconfigured (every call).
    refused_by_provider: dict[str, int] = field(default_factory=dict)
    #: R423 — dials per leg as the PAYLOAD RECORDER saw them (``primary`` /
    #: ``fallback``). The counters above cannot express "the fallback was dialled
    #: 20 times and answered 0": ``fallback_ok`` is 0 in that case, so an arm
    #: whose tunnel failed on every retry and whose Bedrock credential is dead
    #: looks quiet. Measured on the R423 hard gate: arm A dialled Bedrock 20
    #: times, served 0 answers from it, and the verdict said nothing.
    legs: dict[str, int] = field(default_factory=dict)
    #: R423 — system payload lengths per leg, e.g. ``{'fallback': [59644, ...]}``.
    #: This is how the full 53 kB system prompt is attributed to a leg instead
    #: of being reported as one merged histogram.
    leg_system_lengths: dict[str, list[int]] = field(default_factory=dict)
    #: R423 — generations requested per row, and the largest byte-identical rate
    #: across consecutive generations. ``repeats > 1`` is a claim of INDEPENDENT
    #: draws; a high identical rate means they were REPLAYS.
    repeats: int = 1
    repeat_identical_rate: float | None = None
    #: R423 — deterministic Stage-1 drafts per SAMPLE, in sample order.
    #: ``deterministic_graded`` above describes sample 0 only, but every number
    #: this gate publishes is a per-row MEDIAN over all samples. So one sample
    #: that shipped drafts while its siblings were polished biases the median by
    #: an unknown amount in one direction — measured on the R423 outage run, arm
    #: A's sample 3 was 28/28 deterministic while samples 1-2 were primary-served,
    #: and the arm total (47 primary completions) made the arm read healthy.
    sample_deterministic: tuple[int, ...] = ()
    #: R423b — which leg served each GRADED row, read off the rows themselves
    #: (``provenance.stage2_served_by``) rather than off this process's counters.
    #: The counters only see calls made by THIS process, so an arm resumed from
    #: its checkpoint reads as having made no calls at all — and the R422
    #: zero-completion rule then voids a perfectly good arm. The rows are the
    #: evidence that survives a restart, and they are what the other provenance
    #: rules already read.
    rows_served: dict[str, int] = field(default_factory=dict)
    #: R423.2 — the digests this arm's payloads produced AT RUN TIME. A saved
    #: payload stores the digest, not the hash list behind it, so
    #: :meth:`from_dict` carries them across and the payload-identity rule then
    #: compares exactly the bytes it compared live. Empty on a live arm, where
    #: the digest is derived from :attr:`system_hashes` as before.
    recorded_system_digest: str = ""
    recorded_user_digest: str = ""

    @property
    def system_digest(self) -> str:
        return self.recorded_system_digest or _digest(list(self.system_hashes))

    @property
    def user_digest(self) -> str:
        return self.recorded_user_digest or _digest(list(self.user_hashes))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArmProvenance:
        """Rebuild from :meth:`as_dict`, so a SAVED run can be re-judged.

        R423.2 — when the guard itself changes (here: a caller may now ACCOUNT
        for the rows a degraded leg served, instead of voiding the whole gate),
        the verdict must be re-derivable from the draws already on disk rather
        than recomputed by re-spending hours of live quota on identical rows.
        The reconstruction is lossless for every rule this module applies:
        ``stats`` is refilled from the flattened counters the properties read,
        and the digests are carried verbatim. It cannot invent a draw.
        """
        stats: dict[str, Any] = {
            "primary_attempts": int(data.get("primary_attempts", 0) or 0),
            "primary_ok": int(data.get("primary_ok", 0) or 0),
            "primary_failed": int(data.get("primary_failed", 0) or 0),
            "fallback_attempts": int(data.get("fallback_attempts", 0) or 0),
            "fallback_ok": int(data.get("fallback_ok", 0) or 0),
            "fallback_failed": 0,
            "refused": int(data.get("refused", 0) or 0),
        }
        if data.get("stats_error"):
            stats["_error"] = str(data["stats_error"])
        return cls(
            label=str(data.get("label") or ""),
            rows=int(data.get("rows", 0) or 0),
            deterministic_graded=int(data.get("deterministic_graded", 0) or 0),
            stats=stats,
            # Placeholders of the recorded LENGTH, so the "payloads could not be
            # observed" rule still sees that the arm dispatched payloads; the
            # digests below are the recorded ones, so identity is compared on
            # what ran rather than on these stand-ins.
            system_hashes=tuple(
                f"recorded:{i}" for i in range(int(data.get("system_payloads", 0) or 0))
            ),
            user_hashes=tuple(
                f"recorded:{i}" for i in range(int(data.get("system_payloads", 0) or 0))
            ),
            system_lengths=tuple(int(x) for x in (data.get("system_lengths") or ())),
            calls=int(data.get("calls", 0) or 0),
            refused_by_provider={
                str(k): int(v) for k, v in (data.get("refused_by_provider") or {}).items()
            },
            legs={str(k): int(v) for k, v in (data.get("legs") or {}).items()},
            leg_system_lengths={
                str(k): [int(x) for x in v]
                for k, v in (data.get("leg_system_lengths") or {}).items()
            },
            repeats=int(data.get("repeats", 1) or 1),
            repeat_identical_rate=data.get("repeat_identical_rate"),
            sample_deterministic=tuple(
                int(x) for x in (data.get("sample_deterministic") or ())
            ),
            rows_served={
                str(k): int(v) for k, v in (data.get("rows_served") or {}).items()
            },
            recorded_system_digest=str(data.get("system_digest") or ""),
            recorded_user_digest=str(data.get("user_digest") or ""),
        )

    @property
    def primary_ok(self) -> int:
        return int(self.stats.get("primary_ok", 0) or 0)

    @property
    def fallback_ok(self) -> int:
        return int(self.stats.get("fallback_ok", 0) or 0)

    @property
    def primary_attempts(self) -> int:
        return int(self.stats.get("primary_attempts", 0) or 0)

    @property
    def refused(self) -> int:
        return int(self.stats.get("refused", 0) or 0)

    @property
    def fallback_attempts(self) -> int:
        return int(self.stats.get("fallback_attempts", 0) or 0)

    @property
    def primary_failed(self) -> int:
        return int(self.stats.get("primary_failed", 0) or 0)

    @property
    def stats_error(self) -> str | None:
        err = self.stats.get("_error")
        return str(err) if err else None

    @property
    def polished_graded(self) -> int:
        return max(0, self.rows - self.deterministic_graded)

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "rows": self.rows,
            "calls": self.calls,
            "deterministic_graded": self.deterministic_graded,
            "polished_graded": self.polished_graded,
            "system_payloads": len(self.system_hashes),
            "system_digest": self.system_digest,
            "system_lengths": sorted(self.system_lengths),
            "user_digest": self.user_digest,
            "primary_attempts": self.primary_attempts,
            "primary_ok": self.primary_ok,
            "primary_failed": self.primary_failed,
            "fallback_attempts": self.fallback_attempts,
            "fallback_ok": self.fallback_ok,
            "refused": self.refused,
            "refused_by_provider": dict(self.refused_by_provider),
            "legs": dict(self.legs),
            "leg_system_lengths": {
                leg: sorted(lengths)
                for leg, lengths in self.leg_system_lengths.items()
            },
            "repeats": self.repeats,
            "repeat_identical_rate": self.repeat_identical_rate,
            "sample_deterministic": list(self.sample_deterministic),
            "rows_served": dict(self.rows_served),
            "stats_error": self.stats_error,
        }


@dataclass
class GateVerdict:
    """A paired gate's eligibility to report deltas."""

    valid: bool
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    arms: dict[str, dict[str, Any]] = field(default_factory=dict)
    transport_checked: bool = True
    system_checked: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "void": not self.valid,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "transport_checked": self.transport_checked,
            "system_checked": self.system_checked,
            "arms": self.arms,
        }

    def render(self) -> str:
        lines: list[str] = []
        if self.valid:
            lines.append("GATE VALID: both arms carried by the primary leg; "
                         "system-slot identity checked." if self.system_checked
                         else "GATE VALID: both arms carried by the primary leg.")
            for w in self.warnings:
                lines.append(f"  WARNING: {w}")
            return "\n".join(lines)
        bar = "!" * 78
        lines.append(bar)
        lines.append("VOID RUN — NO DELTAS ARE REPORTED.")
        lines.append("The two arms were not measured under the lever. Any delta")
        lines.append("this run could print would be indistinguishable from a null.")
        lines.append(bar)
        for r in self.reasons:
            lines.append(f"  VOID: {r}")
        for w in self.warnings:
            lines.append(f"  (context) {w}")
        lines.append(
            "  Fix the transport (bring the tunnel up / re-run) or fix the lever,"
        )
        lines.append("  then re-run. The row checkpoints are still on disk.")
        lines.append(bar)
        return "\n".join(lines)


def lever_changes_system(
    base_env: dict[str, str] | None,
    branch_env: dict[str, str] | None,
    *,
    override: bool | None = None,
) -> tuple[bool, str]:
    """Does this A/B claim to change the Stage-2 SYSTEM payload?

    Returns ``(changes, why)``. The arm envs are the declaration of intent, so
    the check arms itself from the diff: if the two arms differ on a flag in
    :data:`SYSTEM_SLOT_FLAGS`, the system payload is supposed to differ and an
    identical one is a void run. ``override`` forces either answer (for a
    wrapper lever that changes the system slot through a flag not listed above).
    """
    base_env = base_env or {}
    branch_env = branch_env or {}
    if override is not None:
        return override, f"operator override: lever_changes_system={override}"
    diffs: set[str] = set()
    for key in set(base_env) | set(branch_env):
        if base_env.get(key) != branch_env.get(key):
            diffs.add(key)
    hit = sorted(diffs & SYSTEM_SLOT_FLAGS)
    if hit:
        return True, f"arm env differs on system-slot flag(s): {', '.join(hit)}"
    return False, "arm env does not name a known system-slot flag"


class _PayloadRecorder:
    """Hashes the payload each transport ACTUALLY sends.

    The seam is the provider, not the engine function. The system-slot lever is
    applied INSIDE ``_openai_wrapper_complete_for_graph_rag``
    (``wrapper_system = system if _full_system else "You are an expert…"``), so
    wrapping the engine function records the PRE-substitution text and reports
    two different arms as identical — which is how the first cut of this module
    voided a perfectly good run. ``OpenAIWrapperRequest.system`` is what the model
    receives.
    """

    #: The Stage-2 answer message carries these markers (same filter
    #: ``evals.harness.prompt_ab`` uses to identify the graded call).
    _STAGE2_USER_MARKERS = ("EU AI ACT REFERENCES:", "ANSWER CONTRACT")

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.records: list[dict[str, Any]] = []
        self.legs: dict[str, int] = {}
        self.leg_lengths: dict[str, list[int]] = {}
        self.errors: list[str] = []
        self.filter_fell_back = False
        self._patched: list[tuple[Any, str, Any]] = []

    def _record(self, leg: str, system: str, user: str) -> None:
        with self.lock:
            self.legs[leg] = self.legs.get(leg, 0) + 1
            self.leg_lengths.setdefault(leg, []).append(len(system or ""))
            self.records.append(
                {
                    "leg": leg,
                    "system": _sha(system or ""),
                    "user": _sha(user or ""),
                    "system_len": len(system or ""),
                    "_stage2": any(m in (user or "") for m in self._STAGE2_USER_MARKERS),
                }
            )

    def _wrap(self, func, leg: str):
        def recorder(request, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            try:
                system = str(getattr(request, "system", "") or "")
                user = str(getattr(request, "user", "") or "")
                self._record(leg, system, user)
            except Exception:  # noqa: BLE001 — provenance must not break a call
                pass
            return func(request, *args, **kwargs)

        return recorder

    def install(self) -> None:
        # R416 — LOAD ``.env`` BEFORE TOUCHING A PROVIDER.
        #
        # ``_OpenAIWrapperProvider`` resolves its Cloudflare Access
        # service-token headers ONCE, at construction, and caches them for the
        # life of the process (``_resolve_cf_access_headers``). ``app.config``
        # is what puts ``.env`` into ``os.environ``, and it does so lazily on
        # first import — which, without this line, happens AFTER this method has
        # already constructed the provider singletons. They then carry no
        # service token, Cloudflare Access refuses every primary call with an
        # HTTP 401, and the WHOLE paired run is served by the fallback leg.
        #
        # MEASURED (R416, hard split, 37 rows x 2 arms): 74/74 Stage-2 calls
        # fell back — `primary_attempts=37, primary_ok=0, fallback_ok=37` on BOTH
        # arms — while a direct call in the same environment, minutes apart, was
        # served 10/10 by the primary and `cloudflare_access_service_token_active`
        # never appeared in the gate's log at all. That is the R412 near-miss
        # class — a VOID run that reads as a plausible null — except self-inflicted
        # by the very module that exists to detect it. `.env` also carries
        # ``OPENAI_API_BASE``, so its absence additionally hides the destination.
        #
        # ``app.config`` honours ``REGENOLD_SKIP_DOTENV`` and deliberately skips
        # under pytest, so offline and test arms measure code defaults exactly as
        # before — this cannot leak a developer's ``.env`` into a test.
        try:
            import app.config  # noqa: F401, PLC0415
        except Exception:  # noqa: BLE001 — never block a gate on config sugar
            pass

        import importlib  # noqa: PLC0415

        targets = (
            ("app.llm.openai_wrapper_provider", "get_openai_wrapper_provider", "primary"),
            ("app.llm.bedrock_client", "get_bedrock_provider", "fallback"),
        )
        for module_path, getter, leg in targets:
            try:
                module = importlib.import_module(module_path)
                provider = getattr(module, getter)()
                original = provider.complete
                provider.complete = self._wrap(original, leg)
                self._patched.append((provider, "complete", original))
            except Exception as exc:  # noqa: BLE001 — reported via .errors
                self.errors.append(f"{leg} provider not observable: {exc!r}")

    def uninstall(self) -> None:
        for provider, attr, original in self._patched:
            try:
                setattr(provider, attr, original)
            except Exception:  # noqa: BLE001
                pass
        self._patched.clear()

    def _selected(self) -> list[dict[str, Any]]:
        """The graded Stage-2 answer calls, or all of them if the filter missed.

        A marker filter that matches nothing must not read as "the arm made no
        calls" — that would void a good run for the wrong reason.
        """
        stage2 = [r for r in self.records if r["_stage2"]]
        if stage2:
            self.filter_fell_back = False
            return stage2
        if self.records:
            self.filter_fell_back = True
        return list(self.records)


class ArmProbe:
    """Context manager: zero the counters, record payloads, then snapshot both.

    Usage::

        with ArmProbe("baseline") as probe:
            rows = _run_arm(...)
        provenance = probe.provenance(rows=rows)
    """

    def __init__(self, label: str) -> None:
        self.label = label
        self.transport_before: dict[str, Any] = {}
        self.transport_after: dict[str, Any] = {}
        self._recorder = _PayloadRecorder()
        self._reset_error: str | None = None

    def __enter__(self) -> ArmProbe:
        try:
            from app.llm.stage2_policy import reset_transport_stats  # noqa: PLC0415

            reset_transport_stats()
        except Exception as exc:  # noqa: BLE001 — reported, never swallowed
            self._reset_error = f"reset_transport_stats() failed: {exc!r}"
        self.transport_before = stage2_transport_snapshot()
        self._recorder.install()
        return self

    def __exit__(self, *exc_info: object) -> bool:
        self._recorder.uninstall()
        self.transport_after = stage2_transport_snapshot()
        return False

    def provenance(
        self,
        *,
        rows: Any = None,
        repeats: int = 1,
        repeat_identical_rate: float | None = None,
        sample_rows: Iterable[Any] | None = None,
    ) -> ArmProvenance:
        stats = dict(self.transport_after)
        if self._reset_error:
            stats["_error"] = self._reset_error
        if self._recorder.errors:
            stats.setdefault("_error", "; ".join(self._recorder.errors))
        selected = self._recorder._selected()
        refused = stats.get("refused_by_provider")
        return ArmProvenance(
            label=self.label,
            rows=len(rows) if rows is not None else 0,
            deterministic_graded=count_deterministic_rows(rows),
            stats=stats,
            system_hashes=tuple(r["system"] for r in selected),
            user_hashes=tuple(r["user"] for r in selected),
            system_lengths=tuple(r["system_len"] for r in selected),
            calls=len(selected),
            refused_by_provider=dict(refused) if isinstance(refused, dict) else {},
            legs=dict(self._recorder.legs),
            leg_system_lengths={
                leg: list(lengths)
                for leg, lengths in self._recorder.leg_lengths.items()
            },
            repeats=int(repeats),
            repeat_identical_rate=repeat_identical_rate,
            rows_served=count_rows_served_by(rows),
            sample_deterministic=(
                tuple(count_deterministic_rows(sample) for sample in sample_rows)
                if sample_rows is not None
                else ()
            ),
        )


def count_rows_served_by(rows: Any) -> dict[str, int]:
    """Which leg served each graded row, counted off the rows' own provenance.

    ``primary`` / ``fallback`` / ``deterministic`` each count rows that name
    that leg; ``unnamed`` counts rows carrying no leg at all (an older
    checkpoint, or a row whose trace was empty). The distinction matters for a
    RESUMED arm: in-process transport counters restart at zero, so a resumed arm
    looks like one that produced nothing, when in fact every row on disk records
    a primary completion.
    """
    counts: dict[str, int] = {}
    if not rows:
        return counts
    for row in rows:
        if not isinstance(row, dict):
            continue
        prov = row.get("provenance")
        if not isinstance(prov, dict):
            counts["unnamed"] = counts.get("unnamed", 0) + 1
            continue
        served = prov.get("stage2_served_by")
        if served in (None, ""):
            # A row written before the field existed: ``stage2_polish`` is the
            # only leg hint it carries.
            if prov.get("stage2_polish") is False:
                served = "deterministic"
            elif prov.get("stage2_polish") is True:
                served = "primary"
            else:
                served = "unnamed"
        counts[str(served)] = counts.get(str(served), 0) + 1
    return counts


def count_deterministic_rows(rows: Any) -> int:
    """How many graded rows were served by the deterministic Stage-1 draft.

    Reads the row's OWN recorded provenance, so it works on a checkpoint that
    was written before this gate existed — ``stage2_served_by`` when present,
    else ``stage2_polish``. Returns 0 for rows that carry neither field (an
    older checkpoint), because an unknown is not evidence of an outage.
    """
    if not rows:
        return 0
    n = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        prov = row.get("provenance")
        if not isinstance(prov, dict):
            continue
        served = prov.get("stage2_served_by")
        if served == "deterministic":
            n += 1
        elif served in (None, "") and prov.get("stage2_polish") is False:
            n += 1
    return n


def degraded_row_ids(rows: Any) -> list[str]:
    """Graded rows whose Stage-2 draw did NOT come from the primary leg.

    A row whose provenance NAMES a leg other than ``primary`` was served by a
    degraded path: a fallback transport, or the deterministic Stage-1 draft the
    engine ships once the primary AND the fallback have both failed. Those are
    the rows the R423 hard gate shipped while its transport counters read clean
    on one arm — the exact class ``assess`` has to see to exclude it.

    A row that names NO leg and did not polish is the route's own deterministic
    answer (a curated intercept): it is answered without a Stage-2 call in BOTH
    arms by construction, so it is not a degradation and is left alone. That
    distinction is the whole point — :func:`count_deterministic_rows` folds the
    two together, and a caller that excluded the curated rows would drop nine
    stable, byte-identical rows from every pair.
    """
    ids: list[str] = []
    if not rows:
        return ids
    for row in rows:
        if not isinstance(row, dict):
            continue
        prov = row.get("provenance")
        if not isinstance(prov, dict):
            continue
        served = prov.get("stage2_served_by")
        if served and str(served) != "primary":
            row_id = row.get("id")
            if row_id is not None:
                ids.append(str(row_id))
    return ids


def assess(
    *,
    base: ArmProvenance,
    branch: ArmProvenance | None = None,
    lever: tuple[bool, str] | bool = False,
    transport_checked: bool = True,
    ignore_fallback_leg: bool = False,
    excluded_rows: int = 0,
) -> GateVerdict:
    """Decide whether a paired run is eligible to report deltas.

    ``lever`` is :func:`lever_changes_system`'s result (or a bare bool). The
    transport leg is checked for BOTH arms; the payload-identity check only
    applies when the lever claims the system slot.

    ``ignore_fallback_leg`` — R416. Set by a caller that has ALREADY excluded
    the fallback-served rows from both arms symmetrically (see
    ``easyhard_ab._exclude_fallback_rows``) and is therefore reporting on a
    tunnel-served subset. The fallback reason is suppressed, and the caller
    takes on the obligation to publish the drop count and to refuse to report
    when the survivors fall below the gate floor. Default ``False`` keeps every
    existing caller's behaviour byte-identical.

    ``excluded_rows`` — R423.2. The R416 argument generalised: the count of row
    ids the caller has already excluded from BOTH arms because their graded draw
    was transport-degraded (:func:`degraded_row_ids`). A single primary
    read-timeout with a dead fallback credential ships one Stage-1 draft, and
    voiding a five-hour paired gate for that row discards every sound row beside
    it. Accounting, not assertion, is what makes the permission safe:

    * each excluded row can absorb at most ONE off-contract refusal, so the
      refusal reason is suppressed only while ``arm.refused <= excluded_rows``;
    * the excluded set must stay a minority of the arm (``excluded_rows * 4 <=
      arm.rows``), so an outage cannot be excluded away;
    * every rule that reads the arm as a whole (zero completions, per-sample
      determinism, the deterministic majority, byte-identical replays, payload
      identity) is untouched.

    The caller keeps the R416 obligations: publish the ids and the survivor
    count, and refuse to report when the survivors fall below the gate floor.
    """
    if isinstance(lever, tuple):
        lever_changes, lever_why = lever
    else:
        lever_changes, lever_why = bool(lever), "operator override"

    reasons: list[str] = []
    warnings: list[str] = []
    arms = {base.label: base.as_dict()}
    if branch is not None:
        arms[branch.label] = branch.as_dict()

    checked: list[ArmProvenance] = [base] + ([branch] if branch is not None else [])

    # R423.2 — rows the caller has already excluded from BOTH arms because their
    # graded draw was transport-degraded. ``ignore_fallback_leg`` is the R416
    # special case of this (a fallback-served row); ``excluded_rows`` generalises
    # it to any degraded leg, including the deterministic draft a dead fallback
    # credential leaves behind, and it must be ACCOUNTED for, not merely asserted.
    accounted = max(0, int(excluded_rows))
    ignore_fallback = ignore_fallback_leg or accounted > 0

    for arm in checked:
        if arm.stats_error:
            reasons.append(
                f"{arm.label}: transport provenance unavailable — {arm.stats_error}"
            )
            continue
        if (arm.fallback_ok + arm.rows_served.get("fallback", 0)) > 0 and not ignore_fallback:
            reasons.append(
                f"{arm.label} was served by the FALLBACK transport "
                f"(fallback_ok={arm.fallback_ok}, primary_ok={arm.primary_ok}, "
                f"rows_naming_fallback={arm.rows_served.get('fallback', 0)}). "
                "Bedrock always receives the full system prompt, so a "
                "system-slot lever delivers identical bytes to both arms."
            )
        if arm.refused > 0 and not (accounted and arm.refused <= accounted):
            named = ", ".join(
                f"{k}×{v}" for k, v in sorted(arm.refused_by_provider.items())
            )
            reasons.append(
                f"{arm.label}: {arm.refused} Stage-2 call(s) were refused by the "
                "transport policy (off-contract provider attempted: "
                f"{named or 'provider not named by the counter'})."
            )
        rate = arm.repeat_identical_rate
        if arm.repeats > 1 and rate is not None and rate > 0.5:
            reasons.append(
                f"{arm.label}: {rate:.0%} of rows were BYTE-IDENTICAL between "
                f"consecutive generations ({arm.repeats} requested). The "
                "generations were REPLAYS, not independent draws, so nothing "
                "about draw-to-draw stability can be read from them."
            )
        # The evidence is this process's counters PLUS what the graded rows
        # recorded. R423b: on a ``--resume`` re-launch the counters are empty by
        # construction, and reading only them voided an arm whose 37 rows each
        # name the primary leg. The rule is unchanged in the outage it was
        # written for — there, no row names a leg either.
        served_primary = arm.primary_ok + arm.rows_served.get("primary", 0)
        served_fallback = arm.fallback_ok + arm.rows_served.get("fallback", 0)
        if arm.rows > 0 and served_primary == 0 and served_fallback == 0:
            reasons.append(
                f"{arm.label}: {arm.rows} rows produced ZERO Stage-2 completions "
                "on either leg — the answers are deterministic, not the lever's."
            )
        # R422 — the transport counters alone are not enough. They counted zero
        # for the outage that voided the R422 gate, but the SAME outage can leave
        # a few completions on one arm and none on the other, and then a delta on
        # POLISH-vs-DETERMINISTIC is published as a lever result. The graded rows
        # carry their own provenance, so require most of them to have been
        # polished before either arm can be compared.
        # R423 — a degraded SAMPLE, not just a degraded arm. The published numbers
        # are medians over every generation, so a sample that shipped Stage-1
        # drafts while its siblings were polished moves every median on that arm.
        # The R423 outage proved the arm-level check below cannot see it: arm A
        # read healthy on 47 primary completions while its 3rd sample was 28/28
        # deterministic. Judged per sample, on the same majority rule.
        for index, deterministic in enumerate(arm.sample_deterministic):
            if arm.rows > 0 and deterministic * 2 > arm.rows:
                reasons.append(
                    f"{arm.label}: Stage-2 never landed on {deterministic} of "
                    f"{arm.rows} graded rows in generation {index + 1} of "
                    f"{arm.repeats} (deterministic Stage-1 drafts). Every "
                    "published number is a median across the generations, so a "
                    "degraded generation moves the arm's median by an unknown "
                    "amount — the samples were not measured under one transport."
                )
        if arm.rows > 0 and arm.deterministic_graded * 2 > arm.rows:
            reasons.append(
                f"{arm.label}: Stage-2 never landed on {arm.deterministic_graded} "
                f"of {arm.rows} graded rows (deterministic Stage-1 drafts). A "
                "delta against that arm measures the transport, not the lever."
            )

    accounting_note = ""
    if accounted:
        per_arm = ", ".join(f"{a.label} {a.rows} row(s)" for a in checked)
        accounting_note = (
            f"{accounted} transport-degraded row(s) were excluded from BOTH arms "
            f"by the caller (of {per_arm}); the deltas are reported on the "
            "survivors, and the caller owns the drop count."
        )
        if any(a.rows > 0 and accounted * 4 > a.rows for a in checked):
            reasons.append(
                f"{accounted} degraded row(s) is more than a quarter of an arm "
                "— that is an outage, not a hiccup, and the survivors cannot "
                "carry a delta."
            )

    system_checked = False
    if branch is not None:
        # R423 — a FAILED fallback dial is a primary failure on a graded path, and
        # the counter that can see it is ``fallback_attempts``, not
        # ``fallback_ok``. With a dead Bedrock credential the fallback answers
        # nothing, so ``fallback_ok`` stays 0 and the arm reads clean while rows
        # shipped Stage-1 drafts. Measured on the R423 hard gate: arm A dialled
        # the fallback 20 times and served 0 from it; the verdict said nothing,
        # and every dollar of the outage was visible only in the run log.
        a_attempts, b_attempts = base.fallback_attempts, branch.fallback_attempts
        if a_attempts != b_attempts and not ignore_fallback:
            reasons.append(
                "asymmetric fallback pressure: "
                f"{base.label} dialled the fallback leg {a_attempts} time(s), "
                f"{branch.label} {b_attempts} — the primary leg failed on one "
                "arm's graded path and not the other's, so the two arms were not "
                "measured under the same transport."
            )
        for arm in checked:
            if arm.fallback_attempts > 0 and arm.fallback_ok == 0:
                warnings.append(
                    f"{arm.label}: the fallback leg was dialled "
                    f"{arm.fallback_attempts} time(s) and answered 0 "
                    f"(primary_failed={arm.primary_failed}) — a dead or failing "
                    "fallback credential. Rows that shipped a draft because of "
                    "it belong in the excluded set, not averaged over."
                )
    if lever_changes and branch is not None:
        system_checked = True
        if not base.system_hashes or not branch.system_hashes:
            reasons.append(
                "arms' system payloads could not be observed "
                f"({base.label}={len(base.system_hashes)} call(s), "
                f"{branch.label}={len(branch.system_hashes)} call(s)) — an "
                f"unobservable system slot cannot be shown to differ ({lever_why})."
            )
        elif base.system_digest == branch.system_digest:
            reasons.append(
                "arms' system payloads were IDENTICAL "
                f"(sha={base.system_digest}, n={len(base.system_hashes)} each; "
                f"{lever_why}). The lever did not reach the system slot, so any "
                "delta is null by construction."
            )
    elif not lever_changes and branch is not None:
        if base.system_digest and base.system_digest == branch.system_digest:
            warnings.append(
                "both arms dispatched the same system payload; correct for a "
                f"non-system lever ({lever_why}), but re-run with "
                "--lever-changes-system if this lever edits the system slot."
            )

    if not transport_checked:
        warnings.append(
            "remote --endpoint run: this process cannot see the server's "
            "transport counters, so the leg is the caller's assertion."
        )
    if accounting_note:
        warnings.append(accounting_note)
    if not valid_branch(system_checked, branch):
        warnings.append(
            "single-arm run: no branch arm, so there are no deltas to refuse."
        )

    return GateVerdict(
        valid=not reasons,
        reasons=reasons,
        warnings=warnings,
        arms=arms,
        transport_checked=transport_checked,
        system_checked=system_checked,
    )


def valid_branch(system_checked: bool, branch: ArmProvenance | None) -> bool:
    """Small helper kept separate so the warning logic reads plainly."""
    return branch is not None
