"""
Graph RAG Compliance Q&A Engine — Conversational interface over the compliance graph.

Architecture (two-stage pipeline):
  Stage 1 (always): PARSE → RETRIEVE → deterministic KG-grounded answer
    1a. PARSE:    deterministic ontology/KB keyword parse → structured GraphQuery
                  (no LLM cost; fast, zero-latency)
    1b. RETRIEVE: GraphQuery → Cypher queries against Neo4j → GraphContext
                  (KB fallback when Neo4j unavailable)
    1c. ANSWER:   GraphContext → citation-exact deterministic answer

  Stage 2 (when Claude Max proxy available): ENHANCE via openai_wrapper
    2.  Pass Stage-1 answer + original question to the Claude Max proxy
        (http://127.0.0.1:8000/v1) for natural-language polish.
        Falls back to the Stage-1 answer on any proxy error.

Activate Stage 2 via env:
    OPENAI_API_BASE=http://127.0.0.1:8000/v1   (or any OpenAI-spec endpoint)
    OPENAI_API_KEY=<any non-empty string>
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from app.models import (
    AssessmentAnswer,
    CitationNode,
    GraphRAGRequest,
    GraphRAGResponse,
)

logger = logging.getLogger(__name__)


# ─── Robust JSON extraction for LLM responses ────────────────────────────────
#
# Sonnet 4.6 in particular ships markdown-fenced JSON with explanatory prose
# despite "Respond with valid JSON only. No markdown, no explanation." in the
# system prompt. The original stripper at the _llm_parse_query call site only
# handled the case where the ENTIRE response was wrapped in a fenced block —
# Sonnet's prose-before-JSON / prose-after-JSON / multiple-fences cases all
# slipped to the deterministic fallback, losing 2 simple-question scenarios
# on the eval baseline. This helper closes those holes by walking three
# strategies in order of strictness.

_JSON_FENCE_RE = re.compile(
    r"```(?:json5?|jsonc)?\s*\n?(.*?)\n?```",
    re.IGNORECASE | re.DOTALL,
)
_TRAILING_COMMA_RE = re.compile(r",\s*(?=[}\]])")

# Query-schema keys — used to disambiguate which balanced {...} span is
# the real intent payload when an LLM emits multiple objects in prose
# (e.g. an example {...} placeholder before the real answer). The
# _llm_parse_query call site expects these five keys.
_QUERY_SCHEMA_KEYS = frozenset(
    {"intent", "entities", "risk_context", "dimension_hint", "keywords"}
)


def _strip_trailing_commas(text: str) -> str:
    """Strip ``,}`` / ``,]`` Sonnet sometimes emits despite a strict JSON ask."""
    return _TRAILING_COMMA_RE.sub("", text)


def _try_parse(candidate: str) -> dict | None:
    """Best-effort json.loads; return None on any failure (incl. non-dict)."""
    candidate = candidate.strip()
    if not candidate:
        return None
    try:
        result = json.loads(candidate)
    except (ValueError, TypeError):
        try:
            result = json.loads(_strip_trailing_commas(candidate))
        except (ValueError, TypeError):
            return None
    return result if isinstance(result, dict) else None


def _balanced_brace_spans(text: str) -> list[str]:
    """Yield every balanced ``{...}`` span in the text in document order.

    Walks the string with a depth counter so a stray ``{placeholder}`` in
    prose AROUND the real JSON doesn't poison the match the way greedy
    regex does (greedy spans first ``{`` to last ``}`` regardless of
    nesting — which fails to parse when there are multiple top-level
    objects in the response).

    Eng-review round-6 fix (regenold-eu-ai-act-rag follow-up): the
    original ``re.search(r"\\{.*\\}", text, re.DOTALL)`` approach
    returned `None` for ``"Note: fmt is {x} — {\\"intent\\":\\"y\\"}"``
    because the greedy regex spans both braces and fails to parse.
    Walking braces by depth picks BOTH spans, then ``_try_parse`` filters
    to the parsable one. Bounded by string length — O(n) walk.
    """
    spans: list[str] = []
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    spans.append(text[start:i + 1])
                    start = -1
    return spans


def _score_query_dict(parsed: dict) -> int:
    """Score a candidate parsed dict by how many query-schema keys it has.

    Used to pick the RIGHT object when an LLM ships multiple balanced
    spans (an example + the real answer). The dict whose keys most
    overlap with :data:`_QUERY_SCHEMA_KEYS` wins; ties broken by
    insertion order (i.e. document order, so a tie favours the LATER
    span — LLMs ship the answer after their reasoning).
    """
    return len(_QUERY_SCHEMA_KEYS & set(parsed.keys()))


def _extract_json_object(text: str) -> dict | None:
    """Extract a parseable JSON object from an arbitrary LLM response.

    Strategy:

    1. **Direct parse**: the response is already valid JSON (the happy
       path — Mistral + the deterministic-fallback path always ship
       clean JSON, so this is the production hot path).
    2. **Fenced-block extraction**: walk every ```` ``` ```` fenced span
       (with optional ``json``/``json5``/``jsonc`` language tag). When
       multiple fences carry valid JSON, prefer the one with the most
       query-schema keys (Sonnet sometimes ships an example block before
       the real answer).
    3. **Balanced-brace fallback**: when no fence parses, walk every
       balanced ``{...}`` span in the text. Same query-schema scoring
       picks the right span; ties broken in favour of later spans (LLMs
       ship the answer AFTER their reasoning).

    Returns the parsed dict on success, or ``None`` if every strategy
    failed — the caller raises so the deterministic-parse fallback fires.
    """
    if not text:
        return None
    cleaned = text.strip()

    # 1. Direct parse — strict JSON response (HOT path on Mistral).
    direct = _try_parse(cleaned)
    if direct is not None:
        return direct

    # 2. Fenced-block extraction — collect every parsable fence, pick
    # the one with the most query-schema keys (later span wins ties).
    fenced_candidates: list[tuple[int, int, dict]] = []
    for idx, match in enumerate(_JSON_FENCE_RE.finditer(cleaned)):
        result = _try_parse(match.group(1))
        if result is not None:
            fenced_candidates.append((_score_query_dict(result), idx, result))
    if fenced_candidates:
        # Higher score wins; ties → later span (higher idx).
        fenced_candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
        return fenced_candidates[0][2]

    # 3. Balanced-brace fallback — same scoring on each balanced span.
    brace_candidates: list[tuple[int, int, dict]] = []
    for idx, span in enumerate(_balanced_brace_spans(cleaned)):
        result = _try_parse(span)
        if result is not None:
            brace_candidates.append((_score_query_dict(result), idx, result))
    if brace_candidates:
        brace_candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
        return brace_candidates[0][2]

    return None


def _graph_rag_provider() -> str:
    """Resolve the graph-RAG LLM provider per call.

    Honours an explicit ``P2P_GRAPH_RAG_PROVIDER=mistral`` /
    ``=anthropic``. When the toggle is unset or set to ``auto``, picks
    Mistral if ``MISTRAL_API_KEY`` is present in the process env, else
    falls back to the historical Anthropic path. Read on every call so a
    Railway env-var rebind takes effect on the next request.
    """
    from app.llm import resolve_provider

    return resolve_provider(
        os.getenv("P2P_GRAPH_RAG_PROVIDER"),
        default_when_auto="anthropic",
    )


def _mistral_complete_for_graph_rag(
    *, system: str, user: str, max_tokens: int, temperature: float
) -> str | None:
    """One Mistral call for graph-RAG. ``None`` on any error so callers fall back."""
    from app.llm import MistralRequest, get_mistral_provider, is_mistral_enabled

    if not is_mistral_enabled():
        return None
    try:
        from app.config import settings
        # Reuse the model knob the deploy already configures for the
        # Anthropic path so an operator who pinned a model gets a
        # Mistral-equivalent rather than a silently-different one.
        configured = settings.graph_rag.model
    except Exception:  # noqa: BLE001 — soft-fail; we'll just use the provider default
        configured = ""
    model = (
        configured if configured.startswith("mistral-") else "mistral-large-latest"
    )
    response = get_mistral_provider().complete(
        MistralRequest(
            system=system,
            user=user,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    )
    if response.error:
        logger.warning("graph_rag.mistral_call_failed: %s", response.error[:200])
        return None
    return response.text


def _openai_wrapper_complete_for_graph_rag(
    *, system: str, user: str, max_tokens: int, temperature: float
) -> str | None:
    """One OpenAI-compatible call (Claude Max via wrapper, etc.).

    Returns ``None`` on any error so callers fall back to deterministic.
    The model picks up the deploy's ``graph_rag.model`` knob; defaults
    to ``claude-sonnet-4-6`` when unset or set to a Mistral model.
    """
    from app.llm.openai_wrapper_provider import (
        OpenAIWrapperRequest,
        get_openai_wrapper_provider,
    )

    try:
        from app.config import settings
        configured = settings.graph_rag.model
    except Exception:  # noqa: BLE001
        configured = ""
    model = (
        configured
        if (configured and not configured.startswith("mistral-"))
        else "claude-sonnet-4-6"
    )

    response = get_openai_wrapper_provider().complete(
        OpenAIWrapperRequest(
            system=system,
            user=user,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    )
    if response.error:
        # Loud surface for the auth-broken case so the eval operator
        # doesn't silently A/B Sonnet against deterministic-fallback
        # for an entire round and only spot the mismatch in the JSON
        # snapshot post-hoc.
        if "not_logged_in" in response.error:
            logger.error(
                "graph_rag.openai_wrapper_not_logged_in — Sonnet path is DOWN. "
                "Re-seed the wrapper's OAuth token by running login.bat. "
                "Falling back to deterministic for this call.",
            )
        else:
            logger.warning(
                "graph_rag.openai_wrapper_call_failed: %s",
                response.error[:200],
            )
        return None
    return response.text


# ─── Internal data structures ────────────────────────────────────────────────

@dataclass
class GraphQuery:
    """Structured query extracted from a natural language question."""
    intent: str = "general_compliance"
    entities: list[str] = field(default_factory=list)
    risk_context: str | None = None
    dimension_hint: str | None = None
    keywords: list[str] = field(default_factory=list)
    raw_question: str = ""


@dataclass
class GraphContext:
    """Structured context retrieved from the compliance graph."""
    obligations: list[dict] = field(default_factory=list)
    gaps: list[dict] = field(default_factory=list)
    satisfied: list[dict] = field(default_factory=list)
    dimension_info: list[dict] = field(default_factory=list)
    cross_framework: dict = field(default_factory=dict)
    article_info: list[dict] = field(default_factory=list)
    transitive_deps: list[dict] = field(default_factory=list)
    nodes_traversed: int = 0
    edges_followed: int = 0


# ─── LLM Integration ────────────────────────────────────────────────────────

def _get_anthropic_client():
    """Lazy-load Anthropic client. Returns None if not configured."""
    try:
        from app.config import settings
        api_key = settings.graph_rag.api_key
        if not api_key:
            return None
        import anthropic
        return anthropic.Anthropic(api_key=api_key.get_secret_value())
    except ImportError:
        logger.warning("anthropic package not installed — Graph RAG LLM features disabled")
        return None
    except Exception as exc:
        logger.warning("Anthropic client init failed: %s", exc)
        return None


def _llm_parse_query(question: str) -> GraphQuery:
    """Use LLM to parse natural language question into structured query."""
    provider = _graph_rag_provider()
    try:
        from app.config import settings
        from app.data.graph_rag_prompts import QUERY_PARSE_SYSTEM
        from app.security.prompt_guard import PROMPT_HARDENING_PREFIX, sanitize_for_llm

        sanitized_question = sanitize_for_llm(question, context_type="query")
        system_prompt = PROMPT_HARDENING_PREFIX + QUERY_PARSE_SYSTEM

        if provider == "mistral":
            text_raw = _mistral_complete_for_graph_rag(
                system=system_prompt,
                user=sanitized_question,
                max_tokens=512,
                temperature=0.0,
            )
            if text_raw is None:
                return _deterministic_parse(question)
            text = text_raw.strip()
        elif provider == "openai_wrapper":
            text_raw = _openai_wrapper_complete_for_graph_rag(
                system=system_prompt,
                user=sanitized_question,
                max_tokens=512,
                temperature=0.0,
            )
            if text_raw is None:
                return _deterministic_parse(question)
            text = text_raw.strip()
        else:
            client = _get_anthropic_client()
            if client is None:
                return _deterministic_parse(question)
            response = client.messages.create(
                model=settings.graph_rag.model,
                max_tokens=512,
                temperature=0.0,
                system=system_prompt,
                messages=[{"role": "user", "content": sanitized_question}],
            )
            if not response.content:
                raise ValueError("Anthropic returned empty content block")
            text = response.content[0].text.strip()
        # Robust JSON extraction (regenold-eu-ai-act-rag follow-up #2):
        # the original stripper only handled the case where the WHOLE
        # response was wrapped in ```` ```json ... ``` ````. Claude Sonnet
        # 4.6 in particular ships markdown-fenced JSON with explanatory
        # prose before AND/OR after the block. The new helper handles:
        #   1. Full-response fenced JSON (the original happy path).
        #   2. Prose before/after the fenced block.
        #   3. Multiple fenced blocks (picks the first JSON-parsable one).
        #   4. Language tag after the backticks ("```json" / "```JSON5" / "```jsonc").
        #   5. No fences at all but a `{...}` block embedded in prose.
        #   6. Trailing commas (Sonnet occasionally emits these even when
        #      told strict JSON — strip before parsing).
        parsed = _extract_json_object(text)
        if parsed is None:
            raise ValueError(
                f"LLM returned non-parsable JSON. First 200 chars: {text[:200]!r}"
            )
        return GraphQuery(
            intent=parsed.get("intent", "general_compliance"),
            entities=parsed.get("entities", []),
            risk_context=parsed.get("risk_context"),
            dimension_hint=parsed.get("dimension_hint"),
            keywords=parsed.get("keywords", []),
            raw_question=question,
        )
    except Exception as exc:
        logger.warning("LLM query parse failed, falling back to deterministic: %s", exc)
        return _deterministic_parse(question)


def _llm_generate_answer(
    question: str,
    context: GraphContext,
    system_description: str | None = None,
) -> str:
    """Use LLM to generate a cited answer from retrieved EU AI Act references."""
    provider = _graph_rag_provider()
    try:
        from app.config import settings
        from app.data.graph_rag_prompts import ANSWER_GENERATE_SYSTEM

        # Build context message
        context_parts = []
        if context.obligations:
            context_parts.append(
                f"APPLICABLE OBLIGATIONS ({len(context.obligations)} found):\n"
                + "\n".join(
                    f"- [{o.get('id', 'N/A')}] {o.get('text', '')} (Article: {o.get('article', 'N/A')})"
                    for o in context.obligations[:20]
                )
            )
        if context.gaps:
            context_parts.append(
                f"\nCOMPLIANCE GAPS ({len(context.gaps)} found):\n"
                + "\n".join(
                    f"- [{g.get('obligation_id', g.get('id', 'N/A'))}] {g.get('text', '')} "
                    f"(Reason: {g.get('reason', 'N/A')}, Severity: {g.get('severity', 'N/A')})"
                    for g in context.gaps[:15]
                )
            )
        if context.satisfied:
            context_parts.append(
                f"\nSATISFIED OBLIGATIONS ({len(context.satisfied)} found):\n"
                + "\n".join(
                    f"- [{s.get('obligation_id', s.get('id', 'N/A'))}] {s.get('text', '')} "
                    f"(Satisfied by: {', '.join(s.get('satisfied_by', []))})"
                    for s in context.satisfied[:10]
                )
            )
        if context.cross_framework:
            context_parts.append(
                f"\nCROSS-FRAMEWORK COVERAGE:\n"
                f"- NIST AI RMF: {context.cross_framework.get('nist_covered', 0)} refs covered\n"
                f"- ISO 42001: {context.cross_framework.get('iso_covered', 0)} refs covered"
            )
        if context.dimension_info:
            context_parts.append(
                "\nDIMENSION DETAILS:\n"
                + "\n".join(
                    f"- {d.get('dim_name', d.get('dim_id', 'N/A'))}: "
                    f"{d.get('question_count', 0)} questions, "
                    f"{d.get('obligation_count', 0)} obligations"
                    for d in context.dimension_info
                )
            )
        if context.transitive_deps:
            context_parts.append(
                f"\nTRANSITIVE DEPENDENCIES ({len(context.transitive_deps)} found):\n"
                + "\n".join(
                    f"- [{t.get('id', 'N/A')}] {t.get('text', '')} (blocked by gap)"
                    for t in context.transitive_deps[:10]
                )
            )

        context_text = "\n".join(context_parts) if context_parts else "No EU AI Act references match this query."

        from app.security.prompt_guard import (
            PROMPT_HARDENING_PREFIX,
            sanitize_for_llm,
            validate_llm_output,
        )

        sanitized_question = sanitize_for_llm(question, context_type="query")
        user_message = f"QUESTION: {sanitized_question}\n\n"
        if system_description:
            sanitized_desc = sanitize_for_llm(system_description, context_type="system_description")
            user_message += f"SYSTEM DESCRIPTION: {sanitized_desc}\n\n"
        # Label intentionally reads "EU AI ACT REFERENCES" — earlier
        # "GRAPH CONTEXT:" wording made the LLM cheerfully echo "based
        # on the graph context" / "the graph context lacks…" in the
        # answer, leaking implementation detail into user-facing prose.
        # Talking about references trains the model to write as the
        # regulation expert, not as a graph-querying agent.
        user_message += f"EU AI ACT REFERENCES:\n{context_text}"

        full_system = PROMPT_HARDENING_PREFIX + ANSWER_GENERATE_SYSTEM

        if provider == "mistral":
            text_raw = _mistral_complete_for_graph_rag(
                system=full_system,
                user=user_message,
                max_tokens=settings.graph_rag.max_tokens,
                temperature=settings.graph_rag.temperature,
            )
            if text_raw is None:
                return _deterministic_answer(question, context)
            return validate_llm_output(text_raw.strip())

        if provider == "openai_wrapper":
            text_raw = _openai_wrapper_complete_for_graph_rag(
                system=full_system,
                user=user_message,
                max_tokens=settings.graph_rag.max_tokens,
                temperature=settings.graph_rag.temperature,
            )
            if text_raw is None:
                return _deterministic_answer(question, context)
            return validate_llm_output(text_raw.strip())

        client = _get_anthropic_client()
        if client is None:
            return _deterministic_answer(question, context)
        response = client.messages.create(
            model=settings.graph_rag.model,
            max_tokens=settings.graph_rag.max_tokens,
            temperature=settings.graph_rag.temperature,
            system=full_system,
            messages=[{"role": "user", "content": user_message}],
        )

        if not response.content:
            raise ValueError("Anthropic returned empty content block")
        raw_answer = response.content[0].text.strip()
        return validate_llm_output(raw_answer)
    except Exception as exc:
        logger.warning("LLM answer generation failed, falling back to deterministic: %s", exc)
        return _deterministic_answer(question, context)


# ─── Deterministic fallbacks (no LLM required) ──────────────────────────────

def _deterministic_parse(question: str) -> GraphQuery:
    """Parse question using keyword matching when LLM is unavailable."""
    q_lower = question.lower()

    # Detect intent
    intent = "general_compliance"
    if any(w in q_lower for w in ["gap", "missing", "lacking", "need"]):
        intent = "gap_analysis"
    elif any(w in q_lower for w in ["obligation", "require", "must", "need to"]):
        intent = "obligation_check"
    elif any(w in q_lower for w in ["article", "art."]):
        intent = "article_lookup"
    elif any(w in q_lower for w in ["risk", "classify", "classification"]):
        intent = "risk_assessment"
    elif any(w in q_lower for w in ["nist", "iso", "framework", "cross"]):
        intent = "cross_framework"

    # Extract article + annex references — accept BOTH `Art. 13` / `Art 13`
    # short-form AND `Article 13` long-form (Sonnet + the route's
    # multi-turn preamble use either, so a regex that only knows the
    # short-form silently loses the entity on common multi-turn shapes).
    # Annex refs are catalogued as `Annex IV` etc.; the route's anchor
    # surfacing depends on `query.entities` carrying them through so
    # retrieval can find article-specific obligations.
    import re
    article_nums = re.findall(
        r"\b(?:Art\.?|Article)\s*(\d{1,3})\b", question, re.IGNORECASE,
    )
    annex_romans = re.findall(
        r"\bAnnex\s+([IVXLC]+)\b", question, re.IGNORECASE,
    )
    entities: list[str] = []
    seen: set[str] = set()
    for n in article_nums:
        ent = f"Art. {n}"
        if ent not in seen:
            seen.add(ent)
            entities.append(ent)
    for r in annex_romans:
        ent = f"Annex {r.upper()}"
        if ent not in seen:
            seen.add(ent)
            entities.append(ent)

    # Detect risk context
    risk_context = None
    if "high" in q_lower and "risk" in q_lower:
        risk_context = "high"
    elif "limited" in q_lower:
        risk_context = "limited"
    elif "minimal" in q_lower:
        risk_context = "minimal"
    elif "unacceptable" in q_lower or "prohibited" in q_lower:
        risk_context = "unacceptable"

    # Detect dimension hints
    dimension_hint = None
    dim_keywords = {
        "data_gov": ["data governance", "training data", "bias"],
        "risk_mgmt": ["risk management", "risk assessment"],
        "tech_docs": ["technical documentation", "annex iv", "documentation"],
        "logging": ["record-keeping", "logging", "audit trail"],
        "transparency": ["transparency", "disclosure", "explainability"],
        "human_oversight": ["human oversight", "override", "human-in-the-loop"],
        "security": ["security", "robustness", "accuracy", "adversarial"],
        "deployer_obligations": ["deployer", "fria", "fundamental rights"],
        "conformity_assessment": ["conformity", "ce marking", "declaration"],
        "quality_management": ["quality management", "qms"],
        "decision_governance": ["decision", "behavioral rule", "interception"],
    }
    for dim_id, keywords in dim_keywords.items():
        if any(kw in q_lower for kw in keywords):
            dimension_hint = dim_id
            break

    # KB-keyword → entity injection.
    #
    # The regex above only extracts "Art. N" / "Annex N" tokens present
    # in the question text. Questions that name a CONCEPT instead of an
    # article number (e.g. "What is a GPAI model?", "What are systemic
    # risk obligations?") produce entities=[] — then _retrieve_from_kb
    # skips the EC_CHECKER_OBLIGATION_MAP lookup entirely and dumps the
    # full MATURITY_DIMENSIONS catalog, generating wrong answer text.
    #
    # Fix: mirror the KEYWORD_TO_ARTICLE mapping already used by the
    # scope filter to derive anchor articles. We add only the *primary*
    # article for each concept phrase and skip entries already present
    # via the regex path. The mapping is intentionally conservative —
    # covering the most-cited concept-anchors whose KB obligation rows
    # carry meaningfully different content from the generic high-risk
    # dimensions. A superset would include every scope.py keyword, but
    # that risks over-eager entity injection for questions whose primary
    # intent isn't the mapped article.
    _KEYWORD_ENTITY_MAP: list[tuple[str, str]] = [
        # GPAI / general-purpose AI (Arts. 51-55)
        ("gpai", "Art. 53"),
        ("general-purpose ai", "Art. 53"),
        ("general purpose ai", "Art. 53"),
        ("general-purpose ai model", "Art. 53"),
        ("general purpose ai model", "Art. 53"),
        ("gpai model", "Art. 53"),
        ("systemic risk", "Art. 55"),
        ("model evaluation", "Art. 55"),
        ("code of practice", "Art. 56"),
        # Transparency / deepfakes / chatbots (Art. 50)
        ("deepfake", "Art. 50"),
        ("deep fake", "Art. 50"),
        ("ai-generated content", "Art. 50"),
        ("ai generated content", "Art. 50"),
        ("synthetic content", "Art. 50"),
        ("watermarking", "Art. 50"),
        ("chatbot disclosure", "Art. 50"),
        # Fundamental Rights Impact Assessment (Art. 27)
        ("fundamental rights impact assessment", "Art. 27"),
        ("fria", "Art. 27"),
        # Post-market monitoring (Art. 72)
        ("post-market monitoring", "Art. 72"),
        ("pmmp", "Art. 72"),
        # Conformity assessment / CE marking / registration (Arts. 43/47/48/49)
        ("conformity assessment", "Art. 43"),
        ("declaration of conformity", "Art. 47"),
        ("ce marking", "Art. 48"),
        ("registration", "Art. 49"),
        # AI Office / governance (Arts. 64/65)
        ("ai office", "Art. 64"),
        ("european ai board", "Art. 65"),
        # Market surveillance / penalties (Arts. 74/99)
        ("market surveillance", "Art. 74"),
        ("serious incident", "Art. 73"),
        ("incident reporting", "Art. 73"),
        ("fines", "Art. 99"),
        ("penalties", "Art. 99"),
        # Prohibited practices (Art. 5) — must appear before generic high-risk keywords
        ("prohibited", "Art. 5"),
        ("prohibition", "Art. 5"),
        ("always prohibited", "Art. 5"),
        ("unacceptable risk", "Art. 5"),
        ("banned", "Art. 5"),
        ("social scoring", "Art. 5"),
        ("subliminal manipulation", "Art. 5"),
        ("predictive policing", "Art. 5"),
        ("real-time biometric", "Art. 5"),
        ("remote biometric identification", "Art. 5"),
        ("biometric categorisation", "Art. 5"),
        # Emotion recognition — prohibited in workplaces/education (Art. 5) AND
        # transparency obligation for all other contexts (Art. 50)
        ("emotion recognition", "Art. 5"),
        ("emotion recognition", "Art. 50"),
        # Technical documentation / hardware specs (Art. 11 + Annex IV)
        ("technical documentation", "Art. 11"),
        ("hardware", "Annex IV"),
        ("system architecture", "Annex IV"),
        ("training methodology", "Annex IV"),
        # High-risk classification (Art. 6 / Annex III)
        ("high-risk classification", "Art. 6"),
        ("classified as high-risk", "Art. 6"),
        ("annex iii use case", "Annex III"),
        ("annex iii use cases", "Annex III"),
        ("biometric identification", "Annex III"),
        ("healthcare", "Annex III"),
        ("transcrib", "Annex III"),
        # Definitions + scope (Arts. 1-4)
        ("definition of", "Art. 3"),
        ("what is an ai system", "Art. 3"),
        ("what is a deployer", "Art. 3"),
        ("what is a provider", "Art. 3"),
        ("substantial modification", "Art. 3"),
        ("putting into service", "Art. 3"),
        ("placing on the market", "Art. 3"),
        ("ai literacy", "Art. 4"),
        ("scope of the regulation", "Art. 2"),
        ("territorial scope", "Art. 2"),
        ("extraterritorial", "Art. 2"),
        ("military", "Art. 2"),
        ("national security", "Art. 2"),
        ("research and development", "Art. 2"),
        ("scientific research", "Art. 2"),
        ("free and open-source", "Art. 2"),
        ("open source", "Art. 2"),
        # Value chain (Arts. 16, 22-25)
        ("provider obligations", "Art. 16"),
        ("authorised representative", "Art. 22"),
        ("authorized representative", "Art. 22"),
        ("importer", "Art. 23"),
        ("importer obligations", "Art. 23"),
        ("distributor", "Art. 24"),
        ("distributor obligations", "Art. 24"),
        ("value chain", "Art. 25"),
        ("along the value chain", "Art. 25"),
        # Documentation retention (Arts. 18, 19)
        ("documentation retention", "Art. 18"),
        ("keep documentation", "Art. 18"),
        ("10 years", "Art. 18"),
        ("log retention", "Art. 19"),
        ("6 months", "Art. 19"),
        # Annex I products / safety component (high-risk under Art. 6(1))
        ("safety component", "Art. 6"),
        ("product safety", "Annex I"),
        ("union harmonisation", "Annex I"),
        ("union harmonization", "Annex I"),
        # GPAI classification + procedure (Arts. 51, 52, 54)
        ("10^25", "Art. 51"),
        ("flops threshold", "Art. 51"),
        ("training compute", "Art. 51"),
        ("classification of gpai", "Art. 51"),
        ("gpai classification", "Art. 51"),
        ("gpai authorised representative", "Art. 54"),
        ("notification procedure", "Art. 52"),
        # GPAI documentation annexes — explicit Annex N strings are caught by regex
        ("gpai technical documentation", "Annex XI"),
        ("downstream provider information", "Annex XII"),
        ("downstream provider", "Annex XII"),
        ("systemic risk designation", "Annex XIII"),
        # Conformity-assessment procedures (Annexes VI, VII)
        ("internal control", "Annex VI"),
        ("notified body", "Annex VII"),
        # Innovation support (Arts. 57, 60)
        ("regulatory sandbox", "Art. 57"),
        ("ai sandbox", "Art. 57"),
        ("sandbox", "Art. 57"),
        ("real-world testing", "Art. 60"),
        ("real world testing", "Art. 60"),
        # Governance (Arts. 66, 70, 71)
        ("board tasks", "Art. 66"),
        ("national competent authority", "Art. 70"),
        ("notifying authority", "Art. 70"),
        ("eu database", "Art. 71"),
        # Enforcement (Arts. 20, 79)
        ("corrective action", "Art. 20"),
        ("withdraw from the market", "Art. 20"),
        ("recall", "Art. 20"),
        ("non-compliance procedure", "Art. 79"),
        ("ai system presenting a risk", "Art. 79"),
        # Applicability / entry into force (Art. 113)
        ("entry into force", "Art. 113"),
        ("applicability date", "Art. 113"),
        ("when does the ai act apply", "Art. 113"),
        ("when does the eu ai act apply", "Art. 113"),
        ("when will the ai act apply", "Art. 113"),
        ("2 february 2025", "Art. 113"),
        ("2 august 2025", "Art. 113"),
        ("2 august 2026", "Art. 113"),
        ("2 august 2027", "Art. 113"),
        # Chapter III Section 2 (Art. 8 — overarching requirement)
        ("section 2 requirements", "Art. 8"),
        ("chapter iii requirements", "Art. 8"),
        # Annex III amendment (Art. 7)
        ("amend annex iii", "Art. 7"),
        ("annex iii amendment", "Art. 7"),
        ("add use case", "Art. 7"),
        # Cooperation duty (Art. 21)
        ("cooperate with authorities", "Art. 21"),
        ("cooperation with authorities", "Art. 21"),
        ("cooperation with competent", "Art. 21"),
        ("provide documentation to authorities", "Art. 21"),
        ("provider must supply", "Art. 21"),
        ("supply to a national competent", "Art. 21"),
        ("information must a provider supply", "Art. 21"),
        ("reasoned request from", "Art. 21"),
        # Art. 6(3) non-high-risk carve-out
        ("non-high-risk exception", "Art. 6.3"),
        ("art. 6(3)", "Art. 6.3"),
        ("art 6(3)", "Art. 6.3"),
        ("article 6(3)", "Art. 6.3"),
        ("narrow procedural task", "Art. 6.3"),
        # Art. 50 sub-articles
        ("ai chatbot disclosure", "Art. 50.1"),
        ("interact with natural person", "Art. 50.1"),
        ("watermark", "Art. 50.2"),
        ("synthetic audio", "Art. 50.2"),
        ("synthetic image", "Art. 50.2"),
        ("synthetic video", "Art. 50.2"),
        ("generative ai output", "Art. 50.2"),
        ("deepfake disclosure", "Art. 50.4"),
        ("inform exposed person", "Art. 50.3"),
        # Sandboxes (Arts. 58, 59, 61, 62, 63)
        ("sandbox modalities", "Art. 58"),
        ("personal data in sandbox", "Art. 59"),
        ("personal data in a sandbox", "Art. 59"),
        ("personal data inside", "Art. 59"),
        ("processed inside an ai", "Art. 59"),
        ("processed inside a sandbox", "Art. 59"),
        ("personal data processing in sandbox", "Art. 59"),
        ("gdpr sandbox", "Art. 59"),
        ("sandbox without gdpr", "Art. 59"),
        ("sandbox without consent", "Art. 59"),
        ("informed consent for testing", "Art. 61"),
        ("informed consent", "Art. 61"),
        ("sme support", "Art. 62"),
        ("sme privileges", "Art. 62"),
        ("small mid-cap", "Art. 62"),
        ("small mid cap", "Art. 62"),
        ("smc", "Art. 62"),
        ("startup support", "Art. 62"),
        ("start-up support", "Art. 62"),
        ("derogation for sme", "Art. 63"),
        # Governance bodies (Arts. 67, 68, 69)
        ("advisory forum", "Art. 67"),
        ("scientific panel", "Art. 68"),
        ("expert pool", "Art. 69"),
        # Remedies (Arts. 85, 86, 87, 89)
        ("right to lodge a complaint", "Art. 85"),
        ("right to complain", "Art. 85"),
        ("lodge a complaint", "Art. 85"),
        ("can complain", "Art. 85"),
        ("complain about", "Art. 85"),
        ("complaint about", "Art. 85"),
        ("right to explanation", "Art. 86"),
        ("right to an explanation", "Art. 86"),
        ("explanation of decision", "Art. 86"),
        ("right to know", "Art. 86"),
        ("explanation when an ai", "Art. 86"),
        ("whistleblower", "Art. 87"),
        ("whistleblowing", "Art. 87"),
        ("reporting of infringements", "Art. 87"),
        ("protections for whistle", "Art. 87"),
        ("downstream complaint", "Art. 89"),
        ("complaint to ai office", "Art. 89"),
        # Codes of conduct + penalties (Arts. 95, 100, 101)
        ("voluntary code of conduct", "Art. 95"),
        ("code of conduct", "Art. 95"),
        ("codes of conduct", "Art. 95"),
        ("penalties for eu institutions", "Art. 100"),
        ("eu institutions", "Art. 100"),
        ("eu bodies", "Art. 100"),
        ("fines for eu institutions", "Art. 100"),
        ("edps fines", "Art. 100"),
        ("gpai penalty", "Art. 101"),
        ("gpai fine", "Art. 101"),
        ("penalty for gpai", "Art. 101"),
        ("penalty for general-purpose", "Art. 101"),
        ("penalty for general purpose", "Art. 101"),
        ("commission impose", "Art. 101"),
        # Transition + review (Arts. 111, 112)
        ("transitional provision", "Art. 111"),
        ("pre-existing high-risk", "Art. 111"),
        ("review of the regulation", "Art. 112"),
        ("evaluation of the regulation", "Art. 112"),
        ("commission review", "Art. 112"),
        # Annex II / V / VIII
        ("criminal offences for biometric", "Annex II"),
        ("article 5(1)(h) offences", "Annex II"),
        ("declaration of conformity contents", "Annex V"),
        ("contents of declaration of conformity", "Annex V"),
        ("must the eu declaration", "Annex V"),
        ("must the declaration", "Annex V"),
        ("registration information", "Annex VIII"),
        ("eu database information", "Annex VIII"),
        ("eu ai database", "Annex VIII"),
        ("registered in the eu", "Annex VIII"),
        ("information must be registered", "Annex VIII"),
        # Digital Omnibus (May 2026 political agreement)
        ("digital omnibus", "Art. 113"),
        ("2 december 2027", "Art. 113"),
        ("2 august 2028", "Art. 113"),
        # New prohibited categories under Digital Omnibus
        ("ai-generated csam", "Art. 5"),
        ("ai csam", "Art. 5"),
        ("non-consensual intimate", "Art. 5"),
        ("nudification", "Art. 5"),
        ("intimate imagery", "Art. 5"),
        # Definitions (Art. 3)
        ("serious incident", "Art. 3"),
        ("definition of serious incident", "Art. 3"),
        ("definition of deepfake", "Art. 3"),
        ("definition of ai system", "Art. 3"),
        ("definition of provider", "Art. 3"),
        ("definition of deployer", "Art. 3"),
    ]
    for kw, art_ref in _KEYWORD_ENTITY_MAP:
        if kw in q_lower and art_ref not in entities:
            entities.append(art_ref)

    return GraphQuery(
        intent=intent,
        entities=entities,
        risk_context=risk_context,
        dimension_hint=dimension_hint,
        keywords=question.lower().split()[:10],
        raw_question=question,
    )


def _deterministic_answer(question: str, context: GraphContext) -> str:
    """Generate a structured answer without LLM, using graph data directly."""
    parts: list[str] = []

    if context.obligations:
        for obl in context.obligations[:3]:
            article = obl.get("article", "N/A")
            text = obl.get("text", "N/A")
            parts.append(f"{article}: {text}")

    if context.gaps:
        parts.append(
            f"\n**Compliance Gaps** ({len(context.gaps)} identified):"
        )
        for gap in context.gaps[:5]:
            parts.append(
                f"- {gap.get('text', 'N/A')} ({gap.get('article', '')}) — "
                f"Severity: {gap.get('severity', 'N/A')}"
            )

    if context.satisfied:
        parts.append(
            f"\n**Satisfied Obligations**: {len(context.satisfied)} of "
            f"{len(context.obligations) + len(context.gaps)} total."
        )

    if context.cross_framework:
        nist = context.cross_framework.get("nist_covered", 0)
        iso = context.cross_framework.get("iso_covered", 0)
        if nist or iso:
            parts.append(
                f"\n**Cross-Framework Coverage**: "
                f"NIST AI RMF: {nist} refs, ISO 42001: {iso} refs."
            )

    # KB-projected answer surface. The compliance knowledge graph is a
    # projection of the shipped KB (articles + dimensions + obligations +
    # risk levels + crosswalks); Neo4j is just a cache layer over it.
    # When the cache is cold, dimension_info is still populated from the
    # KB itself — rather than pretending we have no data, we surface
    # those dimensions directly.
    if not parts and context.dimension_info:
        labels = [d.get("dim_name", d.get("dim_id", "")) for d in context.dimension_info[:4] if d.get("dim_name") or d.get("dim_id")]
        if labels:
            parts.append(
                f"This question touches the following EU AI Act obligations: "
                f"{', '.join(labels)}."
            )

    if not parts:
        parts.append(
            "No matching obligation found in the EU AI Act for this question. "
            "Try rephrasing with a specific Art. reference (e.g. 'Art. 11'), a "
            "risk level ('high-risk'), or a compliance dimension ('transparency')."
        )

    return "\n".join(parts)


# ─── Graph Retrieval ─────────────────────────────────────────────────────────

def _retrieve_from_graph(
    query: GraphQuery,
    risk_level: str | None = None,
    answers: dict[str, Any] | None = None,
) -> GraphContext:
    """Query the Neo4j graph based on the structured query."""
    from app.graph.client import get_graph_client

    client = get_graph_client()
    context = GraphContext()

    if not client.enabled:
        # Fall back to KB-based context
        return _retrieve_from_kb(query, risk_level)

    effective_risk = query.risk_context or risk_level or "high"
    answer_dict = answers or {}
    answer_strs = {
        k: (v.value if isinstance(v, AssessmentAnswer) else str(v))
        for k, v in answer_dict.items()
        if v is not None
    }

    try:
        # Get obligations for risk level
        from app.data.graph_rag_prompts import CYPHER_TEMPLATES

        obligations = client.execute_read(
            CYPHER_TEMPLATES["obligations_for_risk_level"],
            {"risk_level": effective_risk},
        )
        context.obligations = obligations
        context.nodes_traversed += len(obligations)

        # If specific article is mentioned, get article-specific obligations
        for entity in query.entities:
            if entity.startswith("Art."):
                art_id = entity.replace("Art. ", "art").replace("Art.", "art")
                art_obls = client.execute_read(
                    CYPHER_TEMPLATES["obligations_for_article"],
                    {"article_id": art_id},
                )
                if art_obls:
                    context.article_info.extend(art_obls)
                    context.nodes_traversed += len(art_obls)

        # If dimension hint, get dimension details
        if query.dimension_hint:
            dim_info = client.execute_read(
                CYPHER_TEMPLATES["dimension_summary"],
                {"dimension_id": query.dimension_hint},
            )
            if dim_info:
                context.dimension_info = dim_info
                context.nodes_traversed += len(dim_info)

        # If answers provided, run gap reasoning
        if answer_strs and query.intent in ("gap_analysis", "obligation_check", "general_compliance"):
            from app.graph.reasoning import reason_compliance
            reasoning = reason_compliance(client, effective_risk, answer_strs)
            if reasoning.get("status") == "completed":
                context.gaps = reasoning.get("gaps", [])
                context.satisfied = reasoning.get("satisfied", [])
                context.cross_framework = reasoning.get("cross_framework", {})
                context.transitive_deps = reasoning.get("transitive_gaps", [])
                context.edges_followed += reasoning.get("total_obligations", 0)

    except Exception as exc:
        logger.warning("Graph retrieval failed: %s", exc)

    return context


def _retrieve_from_kb(
    query: GraphQuery,
    risk_level: str | None = None,
) -> GraphContext:
    """Fallback: retrieve context from KB when Neo4j is unavailable."""
    from app.data.kb import (
        EC_CHECKER_OBLIGATION_MAP,
        MATURITY_DIMENSIONS,
        get_dimensions_for_risk_level,
    )

    context = GraphContext()
    effective_risk = query.risk_context or risk_level or "high"

    # Get applicable dimensions
    try:
        dims = get_dimensions_for_risk_level(effective_risk)
    except ValueError:
        dims = MATURITY_DIMENSIONS

    # If dimension hint, filter
    if query.dimension_hint:
        dims = tuple(d for d in dims if d.id == query.dimension_hint) or dims

    # Build obligation-like entries from KB
    for entity in query.entities:
        mapping = EC_CHECKER_OBLIGATION_MAP.get(entity)
        if mapping:
            context.obligations.append({
                "id": f"kb-{mapping['dimension']}",
                "text": mapping["summary"],
                "article": entity,
            })

    # Add dimension info
    for dim in dims[:10]:
        context.dimension_info.append({
            "dim_id": dim.id,
            "dim_name": dim.label,
            "question_count": len(dim.questions),
            "obligation_count": 0,
        })

    context.nodes_traversed = len(context.obligations) + len(context.dimension_info)
    return context


# ─── Two-stage generation ────────────────────────────────────────────────────

# Keywords whose presence in the *live* part of the question signals enough
# synthesis / comparison / remediation work that Stage-2 polish adds value.
_COMPLEX_QUESTION_KEYWORDS = frozenset({
    "compare", "comparison", "difference", "versus", " vs ", "vs.",
    "trade-off", "tradeoff", "prioritise", "prioritize", "prioritis",
    "remediat", "roadmap", "how should we", "what should we",
    "explain why", "why do", "why does", "why is",
    "what are the implications", "impact of",
})


def _needs_stage2_enhancement(
    question: str,
    context: GraphContext,  # noqa: ARG001 — reserved for future richness checks
    query: "GraphQuery | None" = None,
) -> bool:
    """Return True when the question is complex enough to benefit from Stage-2 polish.

    Fires on any of:
    - Multi-turn context embedded by the route (``"Conversation so far:"`` prefix).
    - Complex intents: gap_analysis, cross_framework (require synthesis across
      multiple obligations/frameworks, not just single-article lookup).
    - Multiple article entities (≥ 2) — implies a comparison or multi-obligation scope.
    - Long live question (> 200 chars) — nuanced questions tend to need prose polish.
    - Presence of comparison / remediation keywords.
    """
    # Multi-turn: the route threads prior turns as "Conversation so far:\n…"
    if "Conversation so far:" in question:
        return True

    if query is not None:
        # Synthesis-heavy intents always benefit from LLM polish
        if query.intent in ("gap_analysis", "cross_framework"):
            return True
        # Multiple referenced articles → comparison / multi-obligation scope
        if len(query.entities) >= 2:
            return True

    # Isolate the live part of the question (drop history preamble if present)
    live_q = (
        question.split("Latest question:", 1)[-1].strip()
        if "Latest question:" in question
        else question
    )

    if len(live_q) > 200:
        return True

    live_lower = live_q.lower()
    if any(kw in live_lower for kw in _COMPLEX_QUESTION_KEYWORDS):
        return True

    return False


def _build_context_references_block(context: GraphContext) -> str:
    """Render the GraphContext as the ``EU AI ACT REFERENCES:`` block.

    Mirrors the structured block built by :func:`_llm_generate_answer` so
    Stage-2 polish operates against the SAME ground-truth surface the
    direct-LLM path uses. Without this, the Stage-2 system prompt asks
    the LLM to "cite only articles present in the supplied references"
    while supplying no references — pure fabrication fuel.
    """
    parts: list[str] = []
    if context.obligations:
        parts.append(
            f"APPLICABLE OBLIGATIONS ({len(context.obligations)}):\n"
            + "\n".join(
                f"- [{o.get('id', 'N/A')}] {o.get('text', '')} "
                f"(Article: {o.get('article', 'N/A')})"
                for o in context.obligations[:20]
            )
        )
    if context.article_info:
        parts.append(
            f"\nARTICLE-SPECIFIC OBLIGATIONS ({len(context.article_info)}):\n"
            + "\n".join(
                f"- [{o.get('id', 'N/A')}] {o.get('text', '')} "
                f"(Article: {o.get('article', 'N/A')})"
                for o in context.article_info[:15]
            )
        )
    if context.gaps:
        parts.append(
            f"\nCOMPLIANCE GAPS ({len(context.gaps)}):\n"
            + "\n".join(
                f"- [{g.get('obligation_id', g.get('id', 'N/A'))}] "
                f"{g.get('text', '')} (Severity: {g.get('severity', 'N/A')})"
                for g in context.gaps[:15]
            )
        )
    if context.dimension_info:
        parts.append(
            "\nDIMENSION DETAILS:\n"
            + "\n".join(
                f"- {d.get('dim_name', d.get('dim_id', 'N/A'))}: "
                f"{d.get('question_count', 0)} questions, "
                f"{d.get('obligation_count', 0)} obligations"
                for d in context.dimension_info
            )
        )
    return "\n".join(parts) if parts else "No EU AI Act references match this query."


# Regexes used by the post-Stage-2 hallucination guard. Tight enough to
# pick up the citation shapes Sonnet emits in prose, loose enough not to
# false-positive on incidental digits.
_PROSE_ARTICLE_RE = re.compile(
    r"\b(?:Art\.?|Article)\s+(\d{1,3})(?![\d])",
    re.IGNORECASE,
)
_PROSE_ANNEX_RE = re.compile(r"\bAnnex\s+([IVXLC]+)\b", re.IGNORECASE)


def _polished_prose_has_unknown_citations(prose: str) -> tuple[bool, str | None]:
    """Detect citation drift in Stage-2 polished prose.

    Returns ``(drifted, first_unknown)``. ``drifted=True`` when prose
    mentions any ``Art./Article N`` or ``Annex X`` that is NOT in the EU
    AI Act catalog (:data:`ARTICLE_EXISTENCE`). The caller drops the
    polished output and falls back to the deterministic KG answer rather
    than ship a fabricated citation.

    This is the LAST line of defence against hallucination — the
    Stage-2 prompt already supplies the structured references block AND
    the system prompt forbids fabrication, but a temperature=0 Sonnet
    call still occasionally drifts. The eval scorer dings any
    references[] / prose mismatch hard, so the safer move is to drop
    the polish entirely on detection.
    """
    from app.data.article_existence import ARTICLE_EXISTENCE

    for num in _PROSE_ARTICLE_RE.findall(prose):
        ref = f"Art. {num}"
        if ref not in ARTICLE_EXISTENCE:
            return True, ref
    for roman in _PROSE_ANNEX_RE.findall(prose):
        ref = f"Annex {roman.upper()}"
        if ref not in ARTICLE_EXISTENCE:
            return True, ref
    return False, None


def _claude_max_enhance_answer(
    *,
    question: str,
    kg_answer: str,
    context: GraphContext | None = None,
    system_description: str | None = None,
) -> str | None:
    """Stage-2: polish the KG-grounded answer via the Claude Max proxy.

    Returns ``None`` on any failure so the caller falls back to the KG answer.
    Supplies the structured EU AI Act references block to the LLM so it
    has ground truth to cite from (matches the contract the
    :data:`ANSWER_GENERATE_SYSTEM` prompt expects).
    """
    try:
        from app.config import settings
        from app.data.graph_rag_prompts import ANSWER_GENERATE_SYSTEM
        from app.security.prompt_guard import (
            PROMPT_HARDENING_PREFIX,
            sanitize_for_llm,
            validate_llm_output,
        )

        sanitized_q = sanitize_for_llm(question, context_type="query")
        user_message = f"QUESTION: {sanitized_q}\n\n"
        if system_description:
            sanitized_desc = sanitize_for_llm(
                system_description, context_type="system_description"
            )
            user_message += f"SYSTEM DESCRIPTION: {sanitized_desc}\n\n"

        # Ground truth — same structured block the direct-LLM path uses.
        # Without this, the system prompt's "cite only articles present
        # in the supplied references" clause has nothing to constrain.
        if context is not None:
            user_message += (
                f"EU AI ACT REFERENCES:\n"
                f"{_build_context_references_block(context)}\n\n"
            )

        user_message += (
            f"KNOWLEDGE GRAPH ANSWER (draft):\n{kg_answer}\n\n"
            "Refine the knowledge-graph draft above into a clear, concise compliance "
            "response. Cite only articles, annexes, and obligations that appear in the "
            "EU AI ACT REFERENCES block. Lead with a direct answer, 3-4 sentences "
            "maximum."
        )
        try:
            max_tokens = settings.graph_rag.max_tokens
        except Exception:  # noqa: BLE001
            max_tokens = 512

        text_raw = _openai_wrapper_complete_for_graph_rag(
            system=PROMPT_HARDENING_PREFIX + ANSWER_GENERATE_SYSTEM,
            user=user_message,
            max_tokens=max_tokens,
            temperature=0.0,
        )
        if text_raw is None:
            return None
        return validate_llm_output(text_raw.strip())
    except Exception as exc:  # noqa: BLE001
        logger.warning("stage2_claude_max_enhance failed, keeping kg_answer: %s", exc)
        return None


def _two_stage_generate(
    question: str,
    context: GraphContext,
    query: "GraphQuery | None" = None,
    system_description: str | None = None,
) -> tuple[str, bool]:
    """Two-stage answer generation.

    Stage 1 (always): deterministic KG-grounded answer — fast, citation-exact,
    zero LLM cost.  Returns (answer, False) when Stage 2 is skipped.

    Stage 2 fires when ALL of these hold:
    - The Claude Max proxy is wired (``is_openai_wrapper_enabled()``).
    - The question is complex enough to benefit from LLM polish per
      :func:`_needs_stage2_enhancement` — multi-turn conversation history,
      gap-analysis / cross-framework intent, multiple article entities,
      long question, or synthesis/remediation keywords.

    Returns (enhanced, True) on success or (kg_answer, False) on fallback /
    skip.
    """
    from app.llm.openai_wrapper_provider import is_openai_wrapper_enabled

    kg_answer = _deterministic_answer(question, context)

    if not is_openai_wrapper_enabled():
        return kg_answer, False

    if not _needs_stage2_enhancement(question, context, query):
        return kg_answer, False

    enhanced = _claude_max_enhance_answer(
        question=question,
        kg_answer=kg_answer,
        context=context,
        system_description=system_description,
    )
    if enhanced is None:
        return kg_answer, False

    # Post-Stage-2 hallucination guard: every Art./Annex mention in the
    # polished prose must resolve to a real provision in ARTICLE_EXISTENCE.
    # On drift, drop the polish and ship the Stage-1 KG answer.
    drifted, bad_ref = _polished_prose_has_unknown_citations(enhanced)
    if drifted:
        logger.warning(
            "stage2_drift_detected: prose cites %s (not in catalog) — "
            "falling back to kg_answer",
            bad_ref,
        )
        return kg_answer, False

    return enhanced, True


# ─── Main entry point ────────────────────────────────────────────────────────

def ask_compliance_question(request: GraphRAGRequest) -> GraphRAGResponse:
    """Main entry point: answer a natural language compliance question.

    Two-stage pipeline:
    1. PARSE (deterministic, always): ontology/KB-based keyword parse — no LLM cost.
    2. RETRIEVE: Neo4j graph traversal / KB fallback.
    3. GENERATE Stage 1: citation-exact deterministic answer from retrieved context.
    4. GENERATE Stage 2 (when Claude Max proxy wired): polish via openai_wrapper.
    5. Extract citations and compute confidence from the graph context.
    """
    # Stage 1 — Parse: always deterministic (ontology/taxonomy/KB, no LLM cost)
    query = _deterministic_parse(request.question)

    # Override risk context if provided in request
    if request.risk_level:
        query.risk_context = request.risk_level.value

    # Stage 1 — Retrieve
    answer_dict = {k: v for k, v in request.answers.items()} if request.answers else {}
    context = _retrieve_from_graph(
        query,
        risk_level=request.risk_level.value if request.risk_level else None,
        answers=answer_dict,
    )

    # Stage 1 + 2 — Generate
    answer_text, stage2_used = _two_stage_generate(
        request.question, context, query, request.system_description,
    )

    reasoning_trace = [
        f"Intent: {query.intent}",
        f"Entities: {query.entities}",
        f"Risk context: {query.risk_context or 'not specified'}",
        f"Dimension hint: {query.dimension_hint or 'none'}",
        f"Graph nodes traversed: {context.nodes_traversed}",
        f"Graph edges followed: {context.edges_followed}",
        f"Stage 2 (Claude Max enhanced): {stage2_used}",
    ]

    # Stage 4 — Extract citations from context
    citations: list[CitationNode] = []
    seen_ids: set[str] = set()

    for obl in (context.obligations + context.article_info)[:15]:
        oid = obl.get("id", obl.get("obligation_id", ""))
        if oid and oid not in seen_ids:
            seen_ids.add(oid)
            citations.append(CitationNode(
                node_type="Obligation",
                node_id=oid,
                text=obl.get("text", ""),
                article_ref=obl.get("article", ""),
            ))

    for gap in context.gaps[:10]:
        gid = gap.get("obligation_id", gap.get("id", ""))
        if gid and gid not in seen_ids:
            seen_ids.add(gid)
            citations.append(CitationNode(
                node_type="Gap",
                node_id=gid,
                text=gap.get("text", ""),
                article_ref=gap.get("article", ""),
            ))

    # Suggested follow-ups based on intent
    from app.data.graph_rag_prompts import SUGGESTED_QUESTIONS
    followups = _suggest_followups(query, context, SUGGESTED_QUESTIONS)

    # Confidence based on data richness
    confidence = _compute_confidence(context)

    return GraphRAGResponse(
        answer=answer_text,
        citations=citations,
        confidence=confidence,
        reasoning_trace=reasoning_trace,
        suggested_followups=followups,
        graph_stats={
            "nodes_traversed": context.nodes_traversed,
            "edges_followed": context.edges_followed,
            "obligations_found": len(context.obligations),
            "gaps_found": len(context.gaps),
            "satisfied_found": len(context.satisfied),
        },
    )


def _suggest_followups(
    query: GraphQuery,
    context: GraphContext,
    all_questions: list[str],
) -> list[str]:
    """Suggest 2-3 follow-up questions based on the current query and results."""
    followups: list[str] = []

    if context.gaps:
        followups.append("What remediation tasks should we prioritise for these gaps?")
    if query.intent == "obligation_check" and not context.cross_framework:
        followups.append("How do our compliance answers map to NIST AI RMF?")
    if query.intent == "gap_analysis":
        followups.append("Are there any transitive gaps blocking our compliance?")
    if query.dimension_hint and query.intent != "gap_analysis":
        followups.append(f"What gaps do we have in {query.dimension_hint}?")

    # Add a general suggestion if we don't have enough
    if len(followups) < 2:
        for q in all_questions:
            if q not in followups and q.lower() != query.raw_question.lower():
                followups.append(q)
                if len(followups) >= 3:
                    break

    return followups[:3]


def _compute_confidence(context: GraphContext) -> float:
    """Compute answer confidence based on graph data richness."""
    if context.nodes_traversed == 0:
        return 0.3  # No graph data — low confidence
    if context.nodes_traversed < 5:
        return 0.5  # Sparse data
    if context.gaps or context.satisfied:
        return 0.85  # Rich data with gap analysis
    return 0.7  # Moderate data
