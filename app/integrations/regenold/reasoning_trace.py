"""Per-request reasoning trace for the R50 ``?include_reasoning=true`` mode.

The Regenold competition spec (page 4) says the ``reasoning`` response
field "*can always be used (e.g. with your system prompt) — but it
will not be considered and might increase latency*". The judge ignores
its content.

R50 turns that field into a self-diagnosis hook for the LLM-as-Judge
runner (`evals/judge/`). When the caller passes
``?include_reasoning=true``, every decision site in the pipeline
appends a typed record to a process-local trace held on a
``ContextVar`` — and the route serialises the whole trace as a JSON
string in ``reasoning``. The judge can then read this alongside the
predicted answer / refs to attribute failures to specific code paths
("Sonnet polish drifted off the cited Art. 13 stub", "scope-gate
refused a coreferent multi-turn final", "near_oos pattern correctly
fired", etc.).

## Hard rules

* Pure-stdlib; same-package imports only.
* Zero overhead when ``include_reasoning=False`` (default) — the
  ``ContextVar`` defaults to a sentinel ``None`` and every recorder
  call short-circuits via a single ``if trace is None: return``.
* Thread + async safe — ``ContextVar`` is the only correct mechanism
  here. FastAPI runs handlers in a thread pool by default; a
  module-level singleton would leak state between requests.
* JSON-serialisable shape — every value goes through ``json.dumps``
  with no custom encoders. Tuples render as lists; dataclasses
  flatten via ``asdict``.

## Schema (kept stable for the LLM-as-Judge)

The trace shape mirrors the design from the R50 research agent:

::

    {
        "schema_version": "r50.1",
        "scope": {"verdict": "in_scope", "evidence": "..."},
        "anchors_used": ["Article 13"],
        "intent_label": "obligational",
        "retrieval_path": "normal",
        "top_k_bm25": [{"ref": "Article 13", "score": 12.4, "source": "kb"}, ...],
        "xref_expand_added": ["Article 14"],
        "graph_2hop_added": [],
        "compound_roles": ["provider", "deployer"],
        "guards_fired": ["r48_consistency", "r49a_grounded_prose"],
        "stage2_polish": true,
        "engine_confidence": 0.81,
        "cache_hit": false,
        "notes": ["near_oos_detected=Digital Services Act", ...]
    }

Any field MAY be absent — judges should treat missing keys as
"unknown", not zero. The schema_version lets the judge runner detect
breaking changes between rounds.
"""
from __future__ import annotations

import json
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


SCHEMA_VERSION: str = "r50.1"


# ── ContextVar wiring ───────────────────────────────────────────────────


@dataclass
class ReasoningTrace:
    """Mutable per-request scratch pad.

    The route enables this when ``?include_reasoning=true`` lands;
    every recorder call below short-circuits when the active
    ``ContextVar`` slot is ``None``, so the deterministic path stays
    free of trace overhead in normal production.
    """

    scope: dict[str, Any] = field(default_factory=dict)
    anchors_used: list[str] = field(default_factory=list)
    intent_label: str | None = None
    retrieval_path: str | None = None
    top_k_bm25: list[dict[str, Any]] = field(default_factory=list)
    xref_expand_added: list[str] = field(default_factory=list)
    graph_2hop_added: list[str] = field(default_factory=list)
    compound_roles: list[str] = field(default_factory=list)
    guards_fired: list[str] = field(default_factory=list)
    stage2_polish: bool | None = None
    engine_confidence: float | None = None
    cache_hit: bool | None = None
    notes: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        """Render to a JSON-serialisable dict with the schema version."""
        out: dict[str, Any] = {"schema_version": SCHEMA_VERSION}
        # Only emit fields the route actually populated to keep the
        # payload compact and the judge prompt focused. Empty
        # collections are dropped; explicit None values are dropped.
        if self.scope:
            out["scope"] = self.scope
        if self.anchors_used:
            out["anchors_used"] = list(self.anchors_used)
        if self.intent_label is not None:
            out["intent_label"] = self.intent_label
        if self.retrieval_path is not None:
            out["retrieval_path"] = self.retrieval_path
        if self.top_k_bm25:
            out["top_k_bm25"] = list(self.top_k_bm25)
        if self.xref_expand_added:
            out["xref_expand_added"] = list(self.xref_expand_added)
        if self.graph_2hop_added:
            out["graph_2hop_added"] = list(self.graph_2hop_added)
        if self.compound_roles:
            out["compound_roles"] = list(self.compound_roles)
        if self.guards_fired:
            out["guards_fired"] = list(self.guards_fired)
        if self.stage2_polish is not None:
            out["stage2_polish"] = self.stage2_polish
        if self.engine_confidence is not None:
            out["engine_confidence"] = self.engine_confidence
        if self.cache_hit is not None:
            out["cache_hit"] = self.cache_hit
        if self.notes:
            out["notes"] = list(self.notes)
        return out

    def to_json_string(self) -> str:
        """Render to a compact JSON string suitable for the ``reasoning``
        wire field. ``separators=(',', ':')`` keeps the payload tight —
        the field is shipped on every request, so every char counts.
        """
        return json.dumps(self.to_json_dict(), separators=(",", ":"))


_CURRENT: ContextVar["ReasoningTrace | None"] = ContextVar(
    "regenold_reasoning_trace", default=None,
)


def activate() -> ReasoningTrace:
    """Activate a fresh trace for the current request context.

    Called by the route handler when ``?include_reasoning=true`` is set.
    Returns the new trace so the route can grab a direct reference for
    final serialisation (the ``ContextVar`` get + None check would also
    work, but the direct handle keeps the route's flow obvious).
    """
    trace = ReasoningTrace()
    _CURRENT.set(trace)
    return trace


def deactivate() -> None:
    """Clear the trace from the current request context.

    Defensive — FastAPI's request-scoped middleware will normally clean
    up via ``ContextVar`` semantics on its own, but a paranoid
    ``try/finally`` in the route is cheaper than chasing a leaked
    trace from a misbehaving middleware.
    """
    _CURRENT.set(None)


def current() -> ReasoningTrace | None:
    """Return the active trace, or ``None`` when reasoning is off.

    Recorder helpers below call this and short-circuit on ``None``,
    so the deterministic pipeline pays zero cost when the caller
    didn't opt in.
    """
    return _CURRENT.get()


# ── Recorder helpers ────────────────────────────────────────────────────
#
# Each recorder is a pure-stdlib function that either appends to the
# active trace OR returns silently when no trace is active. The
# call-sites in the route / scope / engine should use these instead
# of touching the ContextVar directly — keeps the contract narrow
# and makes the JSON schema migration story tractable.


def record_scope(verdict_label: str, evidence: str = "",
                 *, near_oos_framework: str = "") -> None:
    trace = current()
    if trace is None:
        return
    payload: dict[str, Any] = {"verdict": verdict_label}
    if evidence:
        payload["evidence"] = evidence[:200]
    if near_oos_framework:
        payload["near_oos_framework"] = near_oos_framework
    trace.scope = payload


def record_anchors(anchors: list[str] | tuple[str, ...]) -> None:
    trace = current()
    if trace is None:
        return
    trace.anchors_used = list(anchors)


def record_intent(label: str | None) -> None:
    trace = current()
    if trace is None or not label:
        return
    trace.intent_label = label


def record_retrieval_path(path: str) -> None:
    trace = current()
    if trace is None:
        return
    trace.retrieval_path = path


def record_top_k(items: list[dict[str, Any]]) -> None:
    """Record the top-K BM25 hits surfaced by ``kb_search``.

    Each item should be ``{ref, score, source}``. The recorder
    truncates to 8 entries — beyond that the JSON payload bloats the
    reasoning field and the judge gets distracted from the load-
    bearing top-3.
    """
    trace = current()
    if trace is None:
        return
    trace.top_k_bm25 = list(items)[:8]


def record_xref_expand(added: list[str] | tuple[str, ...]) -> None:
    trace = current()
    if trace is None or not added:
        return
    trace.xref_expand_added = list(added)


def record_graph_2hop(added: list[str] | tuple[str, ...]) -> None:
    trace = current()
    if trace is None or not added:
        return
    trace.graph_2hop_added = list(added)


def record_compound_roles(roles: list[str] | tuple[str, ...]) -> None:
    trace = current()
    if trace is None or not roles:
        return
    trace.compound_roles = list(roles)


def record_guard(guard_id: str) -> None:
    """Append a guard-fired marker. Duplicates are dropped to keep the
    payload from blowing up when the same guard runs in a loop."""
    trace = current()
    if trace is None or not guard_id:
        return
    if guard_id not in trace.guards_fired:
        trace.guards_fired.append(guard_id)


def record_stage2(polish_landed: bool) -> None:
    trace = current()
    if trace is None:
        return
    trace.stage2_polish = polish_landed


def record_confidence(value: float) -> None:
    trace = current()
    if trace is None:
        return
    trace.engine_confidence = round(float(value), 3)


def record_cache_hit(hit: bool) -> None:
    trace = current()
    if trace is None:
        return
    trace.cache_hit = hit


def record_note(text: str) -> None:
    """Free-text annotation slot. Use sparingly — the judge prompt
    has a finite token budget and notes compete with the structured
    fields for attention."""
    trace = current()
    if trace is None or not text:
        return
    if len(trace.notes) < 12:  # cap at 12 to keep the payload bounded
        trace.notes.append(text[:200])
