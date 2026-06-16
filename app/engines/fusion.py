"""Mixture-of-Agents (MoA) fusion Stage-2 — diverse panel + a SELECT judge.

Principle (OpenRouter "Fusion", https://openrouter.ai/openrouter/fusion):
a panel of diverse expert models answers the prompt in parallel; a judge model
reads their drafts and produces the single best final answer. We run our OWN
panel on the flat **Claude Max** subscription (Sonnet 4.6 via the
Cloudflare-tunnelled wrapper) + **Groq** Llama 3.3 70B + **Mistral** Large, and
for the hardest ~20% of questions (``complex_question`` per the existing
``is_complex_question`` logic) we add **Claude Opus 4.8** as a fourth candidate.
The judge is **Claude Sonnet 4.6** — so the fusion cost stays on the Max
subscription plus cheap serverless tokens, never per-completion OpenRouter
billing.

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
  REGENOLD_FUSION_JUDGE_MODEL     judge model id (default ``claude-sonnet-4-6``)
  REGENOLD_FUSION_PANEL           comma list of panel members to enable
                                  (default ``sonnet,groq,mistral``; ``opus`` is
                                  auto-added on complex questions; available:
                                  sonnet, opus, groq, mistral, gemini)
  REGENOLD_FUSION_TIMEOUT         per-call timeout seconds (default 60)
  REGENOLD_FUSION_MIN_CANDIDATES  min panel drafts required to run the judge
                                  (default 2 — below this we fall through to
                                  the trusted single-Sonnet path)
"""
from __future__ import annotations

import concurrent.futures
import logging
import os

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


def fusion_stage2_enabled() -> bool:
    """Master gate. Default ON; explicit ``0`` / ``false`` / ``no`` / ``off``
    disables.

    Note this only matters when Stage-2 itself fires (a provider is wired via
    :func:`graph_rag._stage2_provider_enabled`). The deterministic bench runs
    ``provider=cli`` so fusion stays inert there regardless of this flag.
    """
    return os.getenv("REGENOLD_FUSION_STAGE2", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
        "",
    )


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

    On a ``complex_question`` (the existing ``is_complex_question`` gate),
    **Opus 4.8 is appended to the panel** so the hardest ~20% of questions get a
    frontier-model candidate the Sonnet judge can pick. Additive — it never
    removes a configured member, and is deduped below (no double Opus if an
    operator already listed it).
    """
    raw = os.getenv("REGENOLD_FUSION_PANEL", "").strip()
    labels = (
        [s.strip().lower() for s in raw.split(",") if s.strip()]
        if raw
        else list(_DEFAULT_PANEL)
    )
    if complex_question and "opus" not in labels:
        labels = [*labels, "opus"]
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
) -> tuple[str, str | None]:
    """Run one panel member. Returns ``(label, text_or_None)``. Never raises."""
    try:
        from app.llm.openai_wrapper_provider import OpenAIWrapperRequest  # noqa: PLC0415

        provider = _provider_for(transport)
        if provider is None:
            return label, None
        resp = provider.complete(
            OpenAIWrapperRequest(
                system=system,
                user=user,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout_seconds=timeout,
            )
        )
        if resp.error:
            logger.info("fusion.panel_member_error label=%s err=%s", label, resp.error[:120])
            return label, None
        text = (resp.text or "").strip()
        if not text:
            return label, None
        return label, text
    except Exception as exc:  # noqa: BLE001 — a panel member never breaks fusion
        logger.info("fusion.panel_member_exc label=%s exc=%s", label, exc)
        return label, None


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
    panel = _enabled_panel(complex_question)
    if len(panel) < _min_candidates():
        # Not enough diverse transports live to fuse — let the caller run the
        # trusted single-provider (Sonnet) path instead.
        _trace(f"fusion_skip insufficient_panel={len(panel)}")
        return None

    # Panel members must not truncate — give them a healthy ceiling.
    panel_max_tokens = max(int(max_tokens or 0), 1024)
    timeout = _timeout_seconds()

    drafts: list[tuple[str, str]] = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(panel)) as ex:
            futures = {
                ex.submit(
                    _one_candidate,
                    label, model, transport,
                    system=system, user=user,
                    max_tokens=panel_max_tokens, temperature=temperature,
                    timeout=timeout,
                ): label
                for (label, model, transport) in panel
            }
            for fut in concurrent.futures.as_completed(futures, timeout=timeout + 15):
                try:
                    label, text = fut.result()
                except Exception:  # noqa: BLE001
                    continue
                if text:
                    drafts.append((label, text))
    except Exception as exc:  # noqa: BLE001 — pool/timeout never breaks fusion
        logger.info("fusion.panel_pool_exc exc=%s", exc)

    if len(drafts) < _min_candidates():
        _trace(f"fusion_skip too_few_drafts={len(drafts)}/{len(panel)}")
        return None

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
    logger.info(
        "fusion.judged judge=%s panel=[%s] drafts=%d",
        judge_model, panel_labels, len(drafts),
    )
    return judged
