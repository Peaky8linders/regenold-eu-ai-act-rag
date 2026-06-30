"""Mixture-of-Agents (MoA) fusion Stage-2 — diverse panel + a SELECT judge.

Principle (OpenRouter "Fusion", https://openrouter.ai/openrouter/fusion):
a panel of diverse expert models answers the prompt in parallel; a judge model
reads their drafts and produces the single best final answer. We run our OWN
panel on the flat **Claude Max** subscription (Sonnet 4.6 via the
Cloudflare-tunnelled wrapper) + **Groq** Llama 3.3 70B + **Mistral** Large, and
for the hardest ~20% of questions (``complex_question`` per the existing
``is_complex_question`` logic) we **swap** the wrapper member to **Claude
Opus 4.8**. The judge is **Claude Sonnet 4.6** — so the fusion cost stays on
the Max subscription plus cheap serverless tokens, never per-completion
OpenRouter billing.

R124 — latency optimisation (the user's "gate fusion optimisation; the lever
is panel size; fire Groq, Sonnet 4.6 (or Opus 4.8 for complex) and Mistral in
parallel; parallel subprocesses even for the cloudflare tunnel"):

* **One wrapper-bound panel member, not two.** R123 *added* Opus alongside
  Sonnet on complex questions, so the panel issued TWO serialized Claude-Max
  wrapper calls (Sonnet + Opus) plus the Sonnet judge = **3 tunnel
  round-trips** on the single slow wrapper — the dominant latency cost the user
  flagged (p50 40-75 s). R124 SWAPS Sonnet→Opus on complex
  (:func:`_enabled_panel`) so the panel has exactly one wrapper member
  (Sonnet | Opus); Groq + Mistral answer on their OWN endpoints in genuine
  parallel. Consequence: the fusion NEVER issues two concurrent wrapper
  requests, so it needs no wrapper-side concurrency — the only serialized
  wrapper calls are the one panel member then the judge (panel→judge is an
  unavoidable data dependency). To parallelise the wrapper itself further (if
  an operator re-adds a second wrapper member), run the wrapper with more
  workers / a second tunnel — out of scope here because the design removes the
  need.
* **Gate the panel to where it earns its latency** (:func:`fusion_gate`,
  ``REGENOLD_FUSION_GATE``, default ``complex``). Simple questions skip the
  panel + judge (2 wrapper calls) and take the cheaper single-Sonnet Stage-2
  polish (1 wrapper call) — the production path through R80.2-R122. The
  diverse 3-way panel + judge fires on the hard ~20% (``complex_question``)
  where the OpenRouter-Fusion lift is real. Net per-question wrapper
  round-trips: ~1 on the easy majority, ~2 on the hard tail (down from 2-3).
  Set ``REGENOLD_FUSION_GATE=all`` to restore R123 fuse-everything.
* **Per-transport timeout** (:func:`_fast_timeout_seconds`,
  ``REGENOLD_FUSION_FAST_TIMEOUT``, default 25 s): the non-wrapper members
  (Groq / Mistral / Gemini) are fast (500+ tok/s), so a tighter budget stops a
  single hung serverless call from holding the panel barrier for the full
  wrapper timeout.

The SELECT-not-MERGE judge (below) is unchanged from R123 — conciseness stays
recovered (the merge-bloat that collapsed Answer-Conciseness 0.70→0.29 is gone;
the judge picks the single best draft and prefers the shortest correct one).

**The judge SELECTS, it does not MERGE.** An earlier cut told the judge to
"adopt the most accurate content AND include any correct point one draft raised
that the others missed" — a union/merge instruction that produced a fuller
answer than any single draft and collapsed the competition's Answer-Conciseness
axis (length-ratio-vs-gold, quadratic) from ~0.70 to ~0.29. The judge now picks
the SINGLE draft that best satisfies the Regenold rubric and, among drafts that
are correct + complete, prefers the SHORTEST — then emits it as the final
polished answer. Conciseness is the tie-break among correct answers, never a cut
to correctness.

**One call does judge + Stage-2 polish.** The judge call reuses the exact
Stage-2 ``system`` (full rubric) + ``user`` (which already carries the
``EU AI ACT REFERENCES`` block + query profile + cross-references) and is
instructed to emit the chosen draft as the FINAL answer, lightly tightened to
the system rules — so there is no separate polishing round-trip. Total LLM
calls = N parallel panel drafts + 1 judge-and-polish.

Wiring: :func:`app.engines.graph_rag._claude_max_enhance_answer` calls
:func:`fusion_complete` BEFORE its single-provider dispatch when
:func:`fusion_stage2_enabled`. Returns ``None`` on any degenerate / failure path
(fewer than ``min_candidates`` panel drafts, judge error / empty / truncated) so
the caller falls through to the canonical single-provider Stage-2 (which itself
falls back to the deterministic Stage-1 answer). **Never raises.**

Because the davidath bench runs with ``P2P_GRAPH_RAG_PROVIDER=cli`` →
:func:`graph_rag._stage2_provider_enabled` returns ``False`` → Stage-2 never
fires → fusion never fires → the bench is **byte-identical** regardless of this
module. The wins land on the LIVE wire (the panel + judge) and the live
LLM-judge axes.

Env:
  REGENOLD_FUSION_STAGE2          master gate (default ON; "0"/"false" disables)
  REGENOLD_FUSION_GATE            when the panel fires (R124): ``complex``
                                  (default — fuse only complex questions, single
                                  Sonnet polish on the rest), ``all`` (R123
                                  fuse-everything), ``off`` (never fuse).
  REGENOLD_FUSION_JUDGE_MODEL     judge model id (default ``claude-sonnet-4-6``)
  REGENOLD_FUSION_PANEL           comma list of panel members to enable
                                  (default ``sonnet,groq,mistral``; on a complex
                                  question the wrapper member is SWAPPED
                                  sonnet→``opus`` — one wrapper member, not two;
                                  available: sonnet, opus, groq, mistral, gemini)
  REGENOLD_FUSION_TIMEOUT         per-call timeout seconds for the wrapper
                                  member + judge (default 60)
  REGENOLD_FUSION_FAST_TIMEOUT    per-call timeout for the non-wrapper members
                                  Groq / Mistral / Gemini (default 25)
  REGENOLD_FUSION_MIN_CANDIDATES  min panel drafts required to run the judge
                                  (default 2 — below this we fall through to
                                  the trusted single-Sonnet path)
"""
from __future__ import annotations

import concurrent.futures
import logging
import os
import re

logger = logging.getLogger(__name__)

# Panel registry: label -> (model id, transport key). The transport key
# selects the pooled provider singleton + its enablement gate.
_PANEL_REGISTRY: dict[str, tuple[str, str]] = {
    "sonnet": ("claude-sonnet-4-6", "wrapper"),
    "opus": ("claude-opus-4-8", "wrapper"),
    "groq": ("llama-3.3-70b-versatile", "groq"),
    "mistral": ("mistral-large-latest", "mistral"),
    "gemini": ("gemini-2.5-flash", "gemini"),
}

_DEFAULT_PANEL = ("sonnet", "groq", "mistral")
# Sonnet 4.6 is the judge (fast, tone-calibrated, picks the most concise +
# correct draft). Opus 4.8 rides the PANEL for complex questions instead.
_DEFAULT_JUDGE_MODEL = "claude-sonnet-4-6"

# R124 — transports that hit their OWN fast serverless endpoint (NOT the single
# slow Claude-Max wrapper). They answer in genuine parallel and finish fast, so
# they get a tighter per-call timeout: a hung serverless call can't hold the
# panel barrier for the full wrapper budget.
_FAST_TRANSPORTS = frozenset({"groq", "mistral", "gemini"})

# R124 — when the fusion panel fires.
_FUSION_GATE_VALUES = ("complex", "all", "off")


def fusion_stage2_enabled() -> bool:
    """Master gate. **Default OFF as of the 2026-06-30 Sonnet-5-routing
    directive**; explicit ``1`` / ``true`` / ``yes`` / ``on`` enables.

    The operator's directive defines a clean two-tier model routing — Sonnet 5
    (with reasoning tokens) answers the simple ~80%, Opus 4.8 answers the
    complex ~20%. The R124 Mixture-of-Agents panel (Opus 4.8 + Groq Llama +
    Mistral, deterministic-judged) could let a Groq/Mistral draft win a complex
    answer, contradicting "Opus 4.8 for complex". With fusion OFF, complex
    questions take the single-provider Stage-2 path → ``complex_model``
    (Opus 4.8). Re-enable the MoA panel with
    ``railway variables --set REGENOLD_FUSION_STAGE2=1``.

    Note this only matters when Stage-2 itself fires (a provider is wired via
    :func:`graph_rag._stage2_provider_enabled`). The deterministic bench runs
    ``provider=cli`` so fusion stays inert there regardless of this flag.
    """
    return os.getenv("REGENOLD_FUSION_STAGE2", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def fusion_gate() -> str:
    """When the diverse panel fires. ``REGENOLD_FUSION_GATE`` (default
    ``complex``):

    * ``complex`` (R124 default) — fuse ONLY complex questions
      (``complex_question`` passed by the caller, computed from
      ``is_complex_question``). Simple questions skip the panel + judge (two
      wrapper round-trips) and take the cheaper single-Sonnet Stage-2 polish
      (one wrapper round-trip) — the production path through R80.2-R122. The
      OpenRouter-Fusion lift is real on hard reasoning, marginal on simple
      single-anchor QA, so this is the latency win: the panel only pays its
      cost where it earns it.
    * ``all`` — R123 behaviour: fuse every question that reaches Stage-2.
    * ``off`` — never fuse; always the single-provider Stage-2 polish.

    Unknown / empty values fall back to ``complex``. The master kill-switch is
    :func:`fusion_stage2_enabled` (``REGENOLD_FUSION_STAGE2``); this knob is the
    *when*, that one is the *whether-at-all*.
    """
    v = os.getenv("REGENOLD_FUSION_GATE", "complex").strip().lower()
    return v if v in _FUSION_GATE_VALUES else "complex"


def _fast_timeout_seconds() -> float:
    """Per-call timeout for the non-wrapper panel members (Groq / Mistral /
    Gemini). Tighter than the wrapper budget so a hung serverless call fails
    fast instead of holding the panel barrier."""
    try:
        return float(os.getenv("REGENOLD_FUSION_FAST_TIMEOUT", "25").strip())
    except (TypeError, ValueError):
        return 25.0


def _judge_model() -> str:
    return os.getenv("REGENOLD_FUSION_JUDGE_MODEL", "").strip() or _DEFAULT_JUDGE_MODEL


def _min_candidates() -> int:
    try:
        n = int(os.getenv("REGENOLD_FUSION_MIN_CANDIDATES", "2").strip())
    except (TypeError, ValueError):
        n = 2
    return max(1, n)


def _timeout_seconds() -> float:
    try:
        return float(os.getenv("REGENOLD_FUSION_TIMEOUT", "60").strip())
    except (TypeError, ValueError):
        return 60.0


def _transport_available(transport: str) -> bool:
    """True iff the pooled provider for ``transport`` has live transport."""
    from app.llm import openai_wrapper_provider as _p  # noqa: PLC0415

    if transport == "wrapper":
        return _p.is_openai_wrapper_enabled()
    if transport == "groq":
        return _p.is_groq_provider_enabled()
    if transport == "mistral":
        return _p.is_mistral_provider_enabled()
    if transport == "gemini":
        return _p.is_gemini_provider_enabled()
    return False


def _provider_for(transport: str):
    from app.llm import openai_wrapper_provider as _p  # noqa: PLC0415

    if transport == "wrapper":
        return _p.get_openai_wrapper_provider()
    if transport == "groq":
        return _p.get_groq_provider()
    if transport == "mistral":
        return _p.get_mistral_provider()
    if transport == "gemini":
        return _p.get_gemini_provider()
    return None


def _enabled_panel(complex_question: bool = False) -> list[tuple[str, str, str]]:
    """Resolve the configured panel to ``(label, model, transport)`` triples,
    keeping only members whose transport is live.

    R124 — on a ``complex_question`` (the existing ``is_complex_question``
    gate), the wrapper-bound member is **SWAPPED** Sonnet→Opus 4.8 rather than
    Opus being *added* alongside Sonnet. The hardest ~20% of questions get the
    frontier model, and the panel keeps exactly ONE wrapper-bound member so it
    never issues two concurrent calls to the single slow Claude-Max wrapper
    (Groq + Mistral run on their own endpoints in parallel). Idempotent: if an
    operator already listed ``opus`` (or there is no ``sonnet`` to swap) the
    panel is left as configured + ``opus`` ensured present — no double Opus.
    """
    raw = os.getenv("REGENOLD_FUSION_PANEL", "").strip()
    labels = (
        [s.strip().lower() for s in raw.split(",") if s.strip()]
        if raw
        else list(_DEFAULT_PANEL)
    )
    if complex_question and "opus" not in labels:
        # Swap the standard wrapper member (sonnet) for the frontier model
        # (opus). If the configured panel has no sonnet, append opus so a
        # frontier candidate is still present.
        swapped = ["opus" if lbl == "sonnet" else lbl for lbl in labels]
        labels = swapped if "opus" in swapped else [*labels, "opus"]
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for label in labels:
        spec = _PANEL_REGISTRY.get(label)
        if spec is None or label in seen:
            continue
        model, transport = spec
        if _transport_available(transport):
            out.append((label, model, transport))
            seen.add(label)
    return out


def _trace(msg: str) -> None:
    try:
        from app.integrations.regenold.reasoning_trace import record_note  # noqa: PLC0415

        record_note(msg[:200])
    except Exception:  # noqa: BLE001 — trace is optional
        pass


def _one_candidate(
    label: str, model: str, transport: str, *, system: str, user: str,
    max_tokens: int, temperature: float, timeout: float,
    thinking_budget: int = 0,
) -> tuple[str, str | None, str]:
    """Run one panel member. Returns ``(label, text_or_None, thinking)``.

    R131.3 — ``thinking`` carries the model's extended-thinking text
    (``reasoning_content``) when the member is the wrapper-bound member (the
    R124 swap-not-add Opus on a complex question) AND ``thinking_budget > 0``,
    so the real Opus chain-of-thought surfaces in the ``?include_reasoning=true``
    trace + the UI 🧠 panel on the fusion (complex) path. Empty for the
    non-wrapper members (Groq / Mistral return no separate reasoning) and when
    the budget is 0. Never raises.
    """
    try:
        from app.llm.openai_wrapper_provider import OpenAIWrapperRequest  # noqa: PLC0415

        provider = _provider_for(transport)
        if provider is None:
            return label, None, ""
        # R131.3 — request extended thinking on the wrapper-bound member when a
        # budget is configured. Only the wrapper transport honours the header;
        # Groq / Mistral ignore it. Clamp mirrors graph_rag's [1024, 16000].
        extra_headers: dict[str, str] = {}
        if transport == "wrapper" and thinking_budget > 0:
            extra_headers["X-Claude-Max-Thinking-Tokens"] = str(
                max(1024, min(thinking_budget, 16000))
            )
        resp = provider.complete(
            OpenAIWrapperRequest(
                system=system,
                user=user,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout_seconds=timeout,
                extra_headers=extra_headers,
            )
        )
        thinking = (getattr(resp, "thinking", "") or "").strip()
        if resp.error:
            logger.info("fusion.panel_member_error label=%s err=%s", label, resp.error[:120])
            return label, None, thinking
        text = (resp.text or "").strip()
        if not text:
            return label, None, thinking
        return label, text, thinking
    except Exception as exc:  # noqa: BLE001 — a panel member never breaks fusion
        logger.info("fusion.panel_member_exc label=%s exc=%s", label, exc)
        return label, None, ""


def _build_judge_user(user: str, drafts: list[tuple[str, str]]) -> str:
    """Append the panel drafts + the SELECT-and-polish instruction to the
    Stage-2 ``user`` message.

    Drafts are labelled generically (DRAFT 1..n) so the judge weighs content,
    not the model's name. The instruction is deliberately a SELECT (pick one),
    NOT a MERGE — merging coverage from multiple drafts is what bloats the
    answer and collapses the conciseness axis. The judge emits the chosen draft
    as the FINAL polished answer in this one call (judge + Stage-2 polish).
    """
    lines = [user.rstrip(), ""]
    lines.append(
        f"You are the FUSION JUDGE and final editor. Below are {len(drafts)} "
        "independent draft answers to the QUESTION above, each written by a "
        "different expert model from the SAME EU AI Act references. In ONE step, "
        "CHOOSE THE SINGLE BEST DRAFT and emit it as the final answer. Judge the "
        "drafts against the EU AI Act references block above and the system "
        "rules, in this priority order:"
    )
    lines.append(
        "1. CORRECTNESS: grounded in the references, with no claim the references "
        "do not support, no misstatement of the regulation, and the right verdict "
        "for the question."
    )
    lines.append(
        "2. REFERENCES: cites the right Articles and Annexes (only those in the "
        "references block) and DESCRIBES each cited provision in the prose, "
        "neither over-cited nor under-cited."
    )
    lines.append(
        "3. COMPLETENESS: answers every distinct sub-question the question "
        "actually asks, and only what it asks."
    )
    lines.append(
        "4. CONCISENESS: among drafts that are correct AND complete, prefer the "
        "SHORTEST. A concise answer that fully answers the question scores higher "
        "than a longer one that adds correct-but-unrequested detail. Match the "
        "length a regulator's model answer would have for THIS question: a direct "
        "single-provision or definitional lookup is one tight sentence, a "
        "scenario or multi-part question is longer, and an exhaustively "
        "enumerated closed set names every member."
    )
    lines.append(
        "5. TONE: neutral third-person regulator voice (provider, deployer, "
        "operator), no first person, no preamble."
    )
    lines.append("")
    for i, (_label, text) in enumerate(drafts, start=1):
        lines.append(f"DRAFT {i}:")
        lines.append(text.strip())
        lines.append("")
    lines.append(
        "Emit ONLY the chosen draft as the single final answer, in PLAIN TEXT — "
        "no markdown, no bold/asterisks, no headings, no 'Verdict:' / 'Bottom "
        "line:' labels, and do not mention the drafts, the panel, or that you "
        "judged. You MAY lightly tighten the chosen draft to obey the system "
        "rules: trim filler / preamble, ensure every cited Article or Annex is "
        "described, keep neutral third-person regulator voice, and use plain "
        "legal prose with no em-dashes, en-dashes, or ellipses. Do NOT blend "
        "content from the other drafts, do NOT add framework context the "
        "question did not ask for, and do NOT make the chosen draft longer."
    )
    return "\n".join(lines)


def _looks_truncated(text: str) -> bool:
    try:
        from app.engines.graph_rag import _looks_structurally_truncated  # noqa: PLC0415

        return bool(_looks_structurally_truncated(text))
    except Exception:  # noqa: BLE001
        return False


# ── R127 — deterministic SELECT judge (default; $0, no extra tunnel call) ─────

_JUDGE_MODE_VALUES = ("deterministic", "llm")

_ART_RE = re.compile(r"\bArticle\s+(\d+)", re.IGNORECASE)
_ANNEX_RE = re.compile(r"\bAnnex\s+([IVXLCDM]+)\b", re.IGNORECASE)
_FIRST_PERSON_MARKERS = (" i ", " we ", " our ", " us ", " you ", " your ", "let me", "let us")
_DASH_MARKERS = ("—", "–", "...", "…")


def fusion_judge_mode() -> str:
    """How the panel drafts are reduced to the final answer.

    ``deterministic`` (R127 DEFAULT) — SELECT the single best panel draft with
    a pure-Python rubric-proxy scorer and NO extra LLM call. The panel drafts
    are already full Stage-2 answers (each ran the complete Stage-2
    system+user prompt), so selecting one IS a complete answer. This removes
    the SECOND serialized Claude-Max-tunnel round-trip the LLM judge cost
    (panel wrapper member → judge), roughly halving complex-question latency,
    while keeping generation 100% on the Max subscription ($0 marginal). The
    downstream route normalisation (tone_guard, dash-strip, reference
    reconcile, validate_llm_output) does the "light tightening" the LLM judge
    used to do inline.

    ``llm`` — the historical Sonnet SELECT-and-polish judge (one extra wrapper
    round-trip). Restore with ``REGENOLD_FUSION_JUDGE=llm``. Unknown values
    resolve to ``deterministic``.
    """
    v = os.getenv("REGENOLD_FUSION_JUDGE", "deterministic").strip().lower()
    return v if v in _JUDGE_MODE_VALUES else "deterministic"


def _refs_in(text: str) -> set[str]:
    arts = {f"Article {m.group(1)}" for m in _ART_RE.finditer(text or "")}
    annexes = {f"Annex {m.group(1).upper()}" for m in _ANNEX_RE.finditer(text or "")}
    return arts | annexes


def _allowed_refs_from_user(user: str) -> set[str]:
    """References the drafts may cite — parsed from the Stage-2 ``user``
    message (which carries the ``EU AI ACT REFERENCES`` block). A draft citing
    a ref OUTSIDE this set hallucinated it (the retrieval never surfaced it)."""
    return _refs_in(user or "")


def _score_draft(text: str, allowed: set[str], transport: str) -> float:
    """Rubric-proxy score for SELECT (higher = better).

    Not the final word on correctness — its job is to prefer the frontier
    Claude (wrapper) draft UNLESS it is structurally broken (truncated /
    empty / cites a non-retrieved ref), in which case a clean alternative
    wins. Tone / dash penalties are light tie-breakers (downstream route
    normalisation cleans those anyway)."""
    t = (text or "").strip()
    if not t:
        return float("-inf")
    score = 0.0
    cited = _refs_in(t)
    if allowed:
        hallucinated = cited - allowed
        score -= 3.0 * len(hallucinated)       # cites a ref the retrieval never surfaced
        if cited & allowed:
            score += 1.0                        # grounds in >=1 allowed ref
    low = f" {t.lower()} "
    score -= 0.5 * sum(low.count(m) for m in _FIRST_PERSON_MARKERS)
    score -= 0.25 * sum(t.count(m) for m in _DASH_MARKERS)
    if len(t) < 40:
        score -= 3.0                            # stub / non-answer
    if transport == "wrapper":
        score += 1.5                            # frontier Claude + keeps wire on Max
    return score


def _deterministic_judge(user: str, drafts: list[tuple[str, str]]) -> str | None:
    """SELECT the best panel draft (verbatim) with no extra LLM call.

    Drops truncated / empty drafts, scores the rest, returns the top draft's
    text. ``None`` only when every draft is unusable, so the caller falls
    through to the single-provider Stage-2 path."""
    allowed = _allowed_refs_from_user(user)
    best_text: str | None = None
    best_score = float("-inf")
    # ``drafts`` arrives in ``as_completed`` (wall-clock) order, which is
    # non-deterministic across the serverless panel members. Iterating it with
    # a strict ``>`` would resolve a score TIE to whichever draft arrived first
    # → the "deterministic" judge returns different answers for byte-identical
    # inputs (and the route engine-cache assumes identical inputs → identical
    # output). Sort by panel label first so ties break on a stable key.
    for label, text in sorted(drafts, key=lambda d: d[0]):
        if not text or not text.strip() or _looks_truncated(text):
            continue
        transport = _PANEL_REGISTRY.get(label, ("", ""))[1]
        s = _score_draft(text, allowed, transport)
        if s > best_score:
            best_score, best_text = s, text.strip()
    return best_text


def fusion_complete(
    *,
    system: str,
    user: str,
    max_tokens: int,
    temperature: float = 0.0,
    complex_question: bool = False,
) -> str | None:
    """Run the MoA fusion Stage-2: diverse panel (parallel) + a SELECT judge.

    The panel members answer concurrently (Sonnet 4.6 + Groq Llama 3.3 70B +
    Mistral Large, plus Opus 4.8 when ``complex_question``); the judge (Sonnet
    4.6 by default) reads all drafts and emits the single best one as the final
    polished answer — in one call (judge + Stage-2 polish).

    Returns the judge's final answer, or ``None`` on any degenerate / failure
    path (fewer than ``min_candidates`` panel drafts, judge error / empty /
    truncated) so the caller falls through to the canonical single-provider
    Stage-2. Never raises.
    """
    # R124 — gate the panel to where it earns its latency. Default ``complex``:
    # the diverse panel + judge (two wrapper round-trips) fires only on hard
    # questions; simple questions return None here so the caller runs the
    # cheaper single-Sonnet Stage-2 polish (one wrapper round-trip).
    gate = fusion_gate()
    if gate == "off":
        _trace("fusion_skip gate=off")
        return None
    if gate == "complex" and not complex_question:
        _trace("fusion_skip gate=complex non_complex_question")
        return None

    panel = _enabled_panel(complex_question)
    if len(panel) < _min_candidates():
        # Not enough diverse transports live to fuse — let the caller run the
        # trusted single-provider (Sonnet) path instead.
        _trace(f"fusion_skip insufficient_panel={len(panel)}")
        return None

    timeout = _timeout_seconds()
    fast_timeout = _fast_timeout_seconds()

    # R131.3 / R135 — surface the wrapper member's real extended-thinking. The
    # wrapper panel member is Opus on a complex question (R124 swap), else
    # Sonnet; both reason before answering. Budget: complex → the (Opus)
    # ``complex_thinking_tokens``; non-complex (fusion only fires here under
    # ``gate=all``) → the (Sonnet) ``thinking_tokens`` so Sonnet also thinks.
    # Clamped in _one_candidate; only the wrapper transport honours the header.
    # Collected per-member and recorded into the reasoning trace in the MAIN
    # thread below (the trace ContextVar is not visible to the panel workers).
    _think_budget = 0
    try:
        from app.config import settings as _settings  # noqa: PLC0415
        _key = "complex_thinking_tokens" if complex_question else "thinking_tokens"
        _think_budget = int(getattr(_settings.graph_rag, _key, 0) or 0)
    except Exception:  # noqa: BLE001
        _think_budget = 0

    # Panel members must not truncate — give them a healthy ceiling. When the
    # wrapper member runs extended thinking, the answer needs output room ABOVE
    # the thinking budget (the API requires max_tokens > budget_tokens).
    panel_max_tokens = max(
        int(max_tokens or 0),
        (_think_budget + 512) if _think_budget > 0 else 0,
        1024,
    )
    panel_thinking: dict[str, str] = {}

    drafts: list[tuple[str, str]] = []
    try:
        # All panel members fire concurrently (one thread each). The single
        # wrapper-bound member (Sonnet | Opus) and the non-wrapper members
        # (Groq / Mistral on their own endpoints) run in genuine parallel — the
        # panel never issues two concurrent wrapper requests (R124 swap-not-add
        # keeps exactly one wrapper member), so no wrapper-side concurrency is
        # needed. Wall-clock for the panel ≈ the slowest single member.
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(panel)) as ex:
            futures = {
                ex.submit(
                    _one_candidate,
                    label, model, transport,
                    system=system, user=user,
                    max_tokens=panel_max_tokens, temperature=temperature,
                    # R124 — non-wrapper members get the tighter fast budget so a
                    # hung serverless call can't hold the barrier for the full
                    # wrapper timeout.
                    timeout=(fast_timeout if transport in _FAST_TRANSPORTS else timeout),
                    thinking_budget=_think_budget,
                ): label
                for (label, model, transport) in panel
            }
            for fut in concurrent.futures.as_completed(futures, timeout=timeout + 15):
                try:
                    label, text, thinking = fut.result()
                except Exception:  # noqa: BLE001
                    continue
                if thinking:
                    panel_thinking[label] = thinking
                if text:
                    drafts.append((label, text))
    except Exception as exc:  # noqa: BLE001 — pool/timeout never breaks fusion
        logger.info("fusion.panel_pool_exc exc=%s", exc)

    if len(drafts) < _min_candidates():
        _trace(f"fusion_skip too_few_drafts={len(drafts)}/{len(panel)}")
        return None

    # R131.3 — record the wrapper member's REAL extended-thinking (Opus CoT)
    # into the reasoning trace so ``?include_reasoning=true`` + the UI 🧠 panel
    # show genuine model reasoning on the complex/fusion path. It was empty
    # before: the deterministic-judge branch returns below without recording,
    # and the panel members never requested / captured thinking. Runs in the
    # MAIN thread (the trace ContextVar isn't visible to the panel workers) so
    # it fires for BOTH judge modes. Fail-soft — the trace is optional.
    if panel_thinking:
        try:
            from app.integrations.regenold.reasoning_trace import (  # noqa: PLC0415
                record_llm_thinking,
            )
            for _lbl, _txt in panel_thinking.items():
                record_llm_thinking(_txt, stage=f"Stage 2 (Fusion panel: {_lbl})")
        except Exception:  # noqa: BLE001 — trace is optional
            pass

    # R127 — deterministic SELECT judge (default). Pick the best panel draft
    # with NO extra LLM call, removing the second serialized Claude-Max-tunnel
    # round-trip the LLM judge cost. Generation stays 100% on the Max
    # subscription ($0). ``REGENOLD_FUSION_JUDGE=llm`` restores the Sonnet
    # SELECT-and-polish judge below.
    if fusion_judge_mode() == "deterministic":
        _panel = ",".join(label for label, _ in drafts)
        chosen = _deterministic_judge(user, drafts)
        if not chosen:
            _trace(f"fusion_judge_det_unusable panel=[{_panel}] drafts={len(drafts)}")
            return None
        _trace(
            f"fusion_judge_landed judge=deterministic panel=[{_panel}] "
            f"drafts={len(drafts)}"
        )
        logger.info(
            "fusion.judged judge=deterministic panel=[%s] drafts=%d",
            _panel, len(drafts),
        )
        return chosen

    # Judge: Sonnet 4.6 via the Max wrapper. Reuse the SAME ``system`` (carries
    # the full Stage-2 rubric) and append the drafts + the SELECT-and-polish
    # instruction. Judge temperature is 0.0 for a deterministic pick.
    judge_model = _judge_model()
    judge_user = _build_judge_user(user, drafts)
    judge_max_tokens = max(int(max_tokens or 0), 1024)
    try:
        from app.llm.openai_wrapper_provider import (  # noqa: PLC0415
            OpenAIWrapperRequest,
            get_openai_wrapper_provider,
        )

        resp = get_openai_wrapper_provider().complete(
            OpenAIWrapperRequest(
                system=system,
                user=judge_user,
                model=judge_model,
                max_tokens=judge_max_tokens,
                temperature=0.0,
                timeout_seconds=timeout,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("fusion.judge_exc exc=%s", exc)
        resp = None

    panel_labels = ",".join(label for label, _ in drafts)
    if resp is None or resp.error:
        _trace(f"fusion_judge_failed panel=[{panel_labels}] model={judge_model}")
        logger.warning(
            "fusion.judge_failed panel=[%s] err=%s",
            panel_labels, (resp.error[:120] if resp is not None and resp.error else "no_response"),
        )
        return None
    judged = (resp.text or "").strip()
    if not judged:
        _trace(f"fusion_judge_empty panel=[{panel_labels}]")
        return None
    if getattr(resp, "finish_reason", None) == "length" or _looks_truncated(judged):
        _trace(f"fusion_judge_truncated panel=[{panel_labels}]")
        logger.warning("fusion.judge_truncated panel=[%s]", panel_labels)
        return None

    _trace(
        f"fusion_judge_landed judge={judge_model} panel=[{panel_labels}] "
        f"drafts={len(drafts)}"
    )
    # R127 — populate the Stage-2 observability ("thinking") field on the
    # fusion path so it is consistent with the single-provider path (which
    # records llm_thinking in ``_openai_wrapper_complete_for_graph_rag``). The
    # gpai R125 trace showed this field EMPTY on the fusion path while the
    # non-fusion path was populated. Names the panel members whose drafts the
    # judge weighed and the judge model that SELECTed the final answer.
    try:
        from app.integrations.regenold.reasoning_trace import (  # noqa: PLC0415
            record_llm_thinking,
        )
        record_llm_thinking(
            f"Mixture-of-Agents fusion: panel [{panel_labels}] produced "
            f"{len(drafts)} drafts; judge {judge_model} SELECTed the single "
            f"best draft (correctness, references, completeness, conciseness, "
            f"tone) as the final answer.",
            stage="Stage 2 (Fusion judge)",
        )
    except Exception:  # noqa: BLE001 — trace is optional
        pass
    logger.info(
        "fusion.judged judge=%s panel=[%s] drafts=%d",
        judge_model, panel_labels, len(drafts),
    )
    return judged
