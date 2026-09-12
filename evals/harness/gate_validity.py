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
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "ArmProbe",
    "ArmProvenance",
    "GateVerdict",
    "SYSTEM_SLOT_FLAGS",
    "assess",
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
    stats: dict[str, Any] = field(default_factory=dict)
    #: Distinct system payload hashes for the graded answer call.
    system_hashes: tuple[str, ...] = ()
    #: Distinct user payload hashes for the graded answer call.
    user_hashes: tuple[str, ...] = ()
    system_lengths: tuple[int, ...] = ()
    calls: int = 0

    @property
    def system_digest(self) -> str:
        return _digest(list(self.system_hashes))

    @property
    def user_digest(self) -> str:
        return _digest(list(self.user_hashes))

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
    def stats_error(self) -> str | None:
        err = self.stats.get("_error")
        return str(err) if err else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "rows": self.rows,
            "calls": self.calls,
            "system_payloads": len(self.system_hashes),
            "system_digest": self.system_digest,
            "system_lengths": sorted(self.system_lengths),
            "user_digest": self.user_digest,
            "primary_attempts": self.primary_attempts,
            "primary_ok": self.primary_ok,
            "fallback_ok": self.fallback_ok,
            "refused": self.refused,
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
        self.errors: list[str] = []
        self.filter_fell_back = False
        self._patched: list[tuple[Any, str, Any]] = []

    def _record(self, leg: str, system: str, user: str) -> None:
        with self.lock:
            self.legs[leg] = self.legs.get(leg, 0) + 1
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

    def provenance(self, *, rows: Any = None) -> ArmProvenance:
        stats = dict(self.transport_after)
        if self._reset_error:
            stats["_error"] = self._reset_error
        if self._recorder.errors:
            stats.setdefault("_error", "; ".join(self._recorder.errors))
        selected = self._recorder._selected()
        return ArmProvenance(
            label=self.label,
            rows=len(rows) if rows is not None else 0,
            stats=stats,
            system_hashes=tuple(r["system"] for r in selected),
            user_hashes=tuple(r["user"] for r in selected),
            system_lengths=tuple(r["system_len"] for r in selected),
            calls=len(selected),
        )


def assess(
    *,
    base: ArmProvenance,
    branch: ArmProvenance | None = None,
    lever: tuple[bool, str] | bool = False,
    transport_checked: bool = True,
) -> GateVerdict:
    """Decide whether a paired run is eligible to report deltas.

    ``lever`` is :func:`lever_changes_system`'s result (or a bare bool). The
    transport leg is checked for BOTH arms; the payload-identity check only
    applies when the lever claims the system slot.
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

    for arm in checked:
        if arm.stats_error:
            reasons.append(
                f"{arm.label}: transport provenance unavailable — {arm.stats_error}"
            )
            continue
        if arm.fallback_ok > 0:
            reasons.append(
                f"{arm.label} was served by the FALLBACK transport "
                f"(fallback_ok={arm.fallback_ok}, primary_ok={arm.primary_ok}). "
                "Bedrock always receives the full system prompt, so a "
                "system-slot lever delivers identical bytes to both arms."
            )
        if arm.refused > 0:
            reasons.append(
                f"{arm.label}: {arm.refused} Stage-2 call(s) were refused by the "
                "transport policy (off-contract provider attempted)."
            )
        if arm.rows > 0 and arm.primary_ok == 0 and arm.fallback_ok == 0:
            reasons.append(
                f"{arm.label}: {arm.rows} rows produced ZERO Stage-2 completions "
                "on either leg — the answers are deterministic, not the lever's."
            )

    system_checked = False
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
