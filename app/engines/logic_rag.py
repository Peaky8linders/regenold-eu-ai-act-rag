import json
import logging
import os
import re
import time
from typing import Any, Dict, List

from app.engines.graph_rag import (
    GraphContext,
    _deterministic_parse,
    _retrieve_from_graph,
    _build_context_references_block,
)
from app.integrations.regenold.reasoning_trace import record_note
from app.llm.openai_wrapper_provider import (
    OpenAIWrapperRequest,
    get_openai_wrapper_provider,
    is_openai_wrapper_enabled,
)
from app.llm.prompts_logic import (
    DAG_DECOMPOSITION_PROMPT_SYSTEM,
    DAG_DECOMPOSITION_USER_TEMPLATE,
    CONTEXT_PRUNING_PROMPT_SYSTEM,
    CONTEXT_PRUNING_USER_TEMPLATE,
)
from app.security.prompt_guard import sanitize_for_llm

logger = logging.getLogger(__name__)


def _max_dag_nodes() -> int:
    """R117-review — cap the number of DAG nodes LogicRAG will execute.

    Each node costs up to one deterministic retrieval plus one
    context-pruning LLM round-trip, so an unbounded (or adversarial /
    malformed) DAG could chain dozens of sequential wrapper calls. The
    cap bounds both the call count (latency) and the topological-sort
    work. Configurable via ``REGENOLD_LOGIC_RAG_MAX_NODES`` (default 6).
    """
    try:
        return max(1, int(os.getenv("REGENOLD_LOGIC_RAG_MAX_NODES", "6")))
    except (TypeError, ValueError):
        return 6


def _logic_rag_budget_seconds() -> float:
    """R117-review — total wall-clock budget for one ``execute_logic_rag``.

    DISTINCT from the per-call timeout (``REGENOLD_LOGIC_RAG_TIMEOUT``,
    15 s): this caps the SUM of the decomposition + per-rank pruning
    round-trips so a multi-rank DAG cannot chain past the route's sub-20s
    budget (and leaves headroom for the Stage-2 polish that runs AFTER
    LogicRAG). Default 12 s. On exhaustion LogicRAG stops issuing further
    LLM calls and finalises with what it has accumulated.
    """
    try:
        return max(1.0, float(os.getenv("REGENOLD_LOGIC_RAG_BUDGET", "12")))
    except (TypeError, ValueError):
        return 12.0


def _safe_fill(template: str, /, **fields: Any) -> str:
    """Brace-safe single-pass template substitution.

    R117-review — ``str.format`` raises ``KeyError`` / ``ValueError`` /
    ``IndexError`` when the substituted VALUES (the user question,
    LLM-generated subqueries, KB prose) contain a literal ``{`` / ``}`` —
    a plausible shape for a legal question ("what does '{x}' cover?") and
    common in EUR-Lex enumerations. We replace each ``{name}`` placeholder
    in ONE pass so braces inside the substituted values are inert (never
    re-scanned, never raise).
    """
    if not fields:
        return template
    pattern = re.compile(r"\{(" + "|".join(re.escape(k) for k in fields) + r")\}")
    return pattern.sub(lambda m: str(fields[m.group(1)]), template)


def _call_llm(
    system: str,
    user: str,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    timeout_override: float | None = None,
) -> str:
    """Helper to call the wrapper LLM. Fail-soft: returns "" on any error."""
    if not is_openai_wrapper_enabled():
        logger.warning("LogicRAG: openai_wrapper not enabled. Returning empty.")
        return ""

    prov = get_openai_wrapper_provider()
    # Use a faster reasoning model to minimize latency.
    model = os.getenv("REGENOLD_LOGIC_RAG_MODEL", "claude-sonnet-4-6")
    # R117 — bound LogicRAG latency. The previous 120s timeout could hang a
    # request for two minutes; the route budget is sub-20s. Configurable via
    # REGENOLD_LOGIC_RAG_TIMEOUT (default 15s). On timeout the call fails soft
    # (returns "") and LogicRAG degrades to its single-node fallback.
    try:
        timeout = float(os.getenv("REGENOLD_LOGIC_RAG_TIMEOUT", "15"))
    except (TypeError, ValueError):
        timeout = 15.0
    # R117-review — honour the caller's remaining wall-clock budget so a
    # per-call 15s timeout can't blow the total LogicRAG deadline.
    if timeout_override is not None:
        timeout = max(1.0, min(timeout, timeout_override))

    try:
        resp = prov.complete(
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
            logger.error(f"LogicRAG LLM Error: {resp.error}")
            return ""
        # R117-review — a length-truncated response is partial output (a
        # mid-sentence rolling memory or mid-array DAG). Treat it as a soft
        # failure so the DAG falls back to single-node and the rolling
        # memory keeps its prior (complete) value — mirroring the R91
        # truncation guard on the Stage-2 path.
        if getattr(resp, "finish_reason", None) == "length":
            logger.warning(
                "LogicRAG: LLM response truncated (finish_reason=length); "
                "treating as soft failure."
            )
            return ""
        return resp.text or ""
    except Exception as e:
        logger.error(f"LogicRAG LLM Exception: {e}")
        return ""


def _finalise_dag(dag: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """R117-review — dedup duplicate node IDs and cap the node count.

    Duplicate IDs would silently collapse in ``_topological_sort``'s
    ``{n["id"]: n}`` lookup (dropping a subquery); the node cap bounds the
    sequential LLM-call count.
    """
    seen: set = set()
    deduped: List[Dict[str, Any]] = []
    for node in dag:
        nid = node.get("id")
        if nid in seen:
            logger.debug("LogicRAG: dropping duplicate DAG node id=%r", nid)
            continue
        seen.add(nid)
        deduped.append(node)
    return deduped[: _max_dag_nodes()]


def _decompose_to_dag(query: str, deadline: float | None = None) -> List[Dict[str, Any]]:
    """Decompose query into a DAG of subqueries. Fail-soft to single node."""
    fallback = [{"id": 1, "query": query, "dependencies": []}]
    # R117-review — brace-safe fill (was DAG_..._TEMPLATE.format(q=query),
    # which raised KeyError on a question containing a literal "{...}").
    user_prompt = _safe_fill(DAG_DECOMPOSITION_USER_TEMPLATE, q=query)
    timeout_override = (
        max(1.0, deadline - time.monotonic()) if deadline is not None else None
    )
    response_text = _call_llm(
        DAG_DECOMPOSITION_PROMPT_SYSTEM, user_prompt, timeout_override=timeout_override
    )

    if not response_text:
        return fallback

    try:
        # Extract JSON block
        text = response_text.strip()

        # Look for markdown JSON block first
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            text = match.group(1).strip()

        # Try to parse whatever we have as JSON
        dag = json.loads(text)

        # If it's a list, validate it
        if isinstance(dag, list) and len(dag) > 0:
            for node in dag:
                if not isinstance(node, dict) or "id" not in node or "query" not in node:
                    raise ValueError("Invalid DAG node structure (missing 'id' or 'query')")
            return _finalise_dag(dag)
        else:
            # It answered the question instead of decomposing, fallback gracefully
            if isinstance(dag, dict):
                logger.debug("Model returned a JSON object instead of a DAG list. Falling back to single query.")
                return fallback
            raise ValueError("Parsed JSON is not a list")

    except json.JSONDecodeError:
        # Fallback to regex search for array if json loads fails
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                dag = json.loads(match.group(0))
                if isinstance(dag, list) and len(dag) > 0:
                    for node in dag:
                        if not isinstance(node, dict) or "id" not in node or "query" not in node:
                            raise ValueError("Invalid DAG node structure (missing 'id' or 'query')")
                    return _finalise_dag(dag)
            except Exception as e:
                logger.error(f"Failed to parse extracted DAG array: {e}. Raw response: {response_text}")
        else:
            logger.error(f"Failed to find JSON array in response. Raw response: {response_text}")

    except Exception as e:
        logger.error(f"Failed to parse DAG JSON or invalid structure: {e}. Raw response: {response_text}")

    return fallback


def _topological_sort(dag: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Sort the DAG into ranks (subqueries executable in parallel).

    R117-review — node IDs and dependency refs are normalised to ``str``
    so an LLM that emits ``"id": 1`` (int) on one node and
    ``"dependencies": ["1"]`` (str) on another still resolves the edge
    (was: the int/str mismatch left the dependency permanently unresolved,
    so every node was dumped into a single rank, defeating the
    decomposition). A dependency referencing a NON-existent id is dropped
    rather than stalling the whole sort.
    """
    # Create lookup map
    nodes = {str(n["id"]): n for n in dag}

    # Track resolved dependencies
    resolved: set = set()
    ranks: List[List[Dict[str, Any]]] = []

    max_iters = len(nodes) + 1
    iters = 0

    while len(resolved) < len(nodes) and iters < max_iters:
        current_rank = []
        for node_id, node in nodes.items():
            if node_id in resolved:
                continue

            deps = {str(d) for d in node.get("dependencies", [])}
            # Only require deps that actually exist as nodes — a dep that
            # references a missing id must not stall the whole sort.
            deps = {d for d in deps if d in nodes}
            # If all (existing) deps are in the resolved set, execute the node
            if deps.issubset(resolved):
                current_rank.append(node)

        if not current_rank:
            # Cycle detected or missing dependency
            logger.warning("LogicRAG: Cycle detected in DAG or missing dependency.")
            # Force add remaining nodes to avoid infinite loop
            remaining = [n for nid, n in nodes.items() if nid not in resolved]
            ranks.append(remaining)
            break

        ranks.append(current_rank)
        for n in current_rank:
            resolved.add(str(n["id"]))

        iters += 1

    return ranks


def _merge_contexts(base: GraphContext, new_ctx: GraphContext) -> None:
    """In-place merge of ``new_ctx`` into ``base``.

    R117-review — previously this copied ONLY ``article_info`` (plus the two
    traversal counters and ``degraded``), silently discarding ``obligations``
    (the PRIMARY citation + answer source, consumed downstream as
    ``context.obligations + context.article_info``) and every other
    retrieval-payload field. A multi-rank DAG therefore produced an
    obligation-empty context — strictly worse than the single-rank
    deterministic path it replaces. Now every payload-bearing field is
    carried, deduplicated by id where the entries have one.
    """

    def _extend_dedup_by_id(base_list: list, new_list: list) -> None:
        seen = {
            item.get("id", "")
            for item in base_list
            if isinstance(item, dict) and item.get("id", "")
        }
        for item in new_list:
            key = item.get("id", "") if isinstance(item, dict) else None
            if key:
                if key in seen:
                    continue
                seen.add(key)
            base_list.append(item)

    _extend_dedup_by_id(base.article_info, new_ctx.article_info)
    _extend_dedup_by_id(base.obligations, new_ctx.obligations)
    _extend_dedup_by_id(base.gaps, new_ctx.gaps)
    _extend_dedup_by_id(base.satisfied, new_ctx.satisfied)
    _extend_dedup_by_id(base.dimension_info, new_ctx.dimension_info)
    _extend_dedup_by_id(base.transitive_deps, new_ctx.transitive_deps)
    _extend_dedup_by_id(
        base.referenced_annexes_and_recitals,
        new_ctx.referenced_annexes_and_recitals,
    )

    # Plain string lists — order-preserving dedup.
    for attr in ("xrefs", "semantically_relevant_statements", "web_search_results"):
        existing = getattr(base, attr)
        seen_s = set(existing)
        for s in getattr(new_ctx, attr):
            if s not in seen_s:
                seen_s.add(s)
                existing.append(s)

    # cross_framework is a dict — shallow-merge (base wins on key clash).
    for k, v in new_ctx.cross_framework.items():
        base.cross_framework.setdefault(k, v)

    base.nodes_traversed += new_ctx.nodes_traversed
    base.edges_followed += new_ctx.edges_followed
    if new_ctx.degraded:
        base.degraded = True


def _truncate_on_boundary(text: str, limit: int) -> str:
    """R117-review — clip context text on a sentence/clause boundary.

    Replaces the raw ``text[:4000]`` byte-slice that cut a regulatory
    clause mid-sentence before feeding it to the pruning model.
    """
    if len(text) <= limit:
        return text
    head = text[:limit]
    for sep in (". ", "; ", ", "):
        idx = head.rfind(sep)
        if idx >= limit // 2:
            return head[: idx + 1]
    return head


def execute_logic_rag(
    query: str, request_answers: dict | None = None, risk_level: str | None = None
) -> GraphContext | None:
    """
    Implements LogicRAG methodology:
    1. Query Logic Dependency Graph Construction
    2. Graph Reasoning Linearization (topological sort)
    3. Greedy Retrieval with Context/Graph Pruning

    R117-review — returns ``None`` (rather than an empty ``GraphContext``)
    when the decomposition yields no executable ranks OR the accumulated
    context is empty, so the route's ``if context is None`` gate falls back
    to the deterministic retrieval path instead of shipping the
    zero-retrieval floor.
    """
    record_note("LogicRAG: Starting execution")

    # R117-review — total wall-clock deadline (see _logic_rag_budget_seconds).
    deadline = time.monotonic() + _logic_rag_budget_seconds()

    # R117-review — sanitise the user query before it reaches any LLM prompt,
    # matching the Stage-1/2 paths (which call sanitize_for_llm). LogicRAG
    # previously passed the raw query straight into the DAG prompt — a
    # prompt-injection surface whose output (the rolling memory) flows into
    # the Stage-2 answer context.
    safe_query = sanitize_for_llm(query, context_type="query") or query

    dag = _decompose_to_dag(safe_query, deadline=deadline)
    record_note(f"LogicRAG: DAG generated with {len(dag)} nodes")

    ranks = _topological_sort(dag)
    record_note(f"LogicRAG: Topologically sorted into {len(ranks)} ranks")

    if not ranks:
        record_note("LogicRAG: empty DAG; deferring to deterministic retrieval")
        return None

    rolling_memory = ""
    accumulated_context = GraphContext()
    # R288.1 — the accumulated context is a BARE GraphContext, and
    # ``_merge_contexts`` carries payload fields only, so ``question`` never
    # arrived here. This object is what ``execute_logic_rag`` returns, i.e. the
    # context Stage-2 and the R113 guard render — so with REGENOLD_LOGIC_RAG=1
    # the R288 verbatim selection silently degraded from "question-relevant
    # paragraphs" to ``select_relevant_paragraphs``' leading-paragraph fallback
    # for every answer. Latent today (the flag is off by default), wrong the
    # moment it is turned on.
    accumulated_context.question = safe_query

    # Graph Pruning: Subqueries at the same rank are processed together
    for rank_idx, rank_nodes in enumerate(ranks):
        if not rank_nodes:
            continue

        # Unified query construction
        unified_query_str = " AND ".join([str(n.get("query", "")) for n in rank_nodes])
        record_note(f"LogicRAG Rank {rank_idx}: Unified Query: {unified_query_str}")

        # Retrieve context (deterministic — does not touch the LLM)
        parsed_query = _deterministic_parse(unified_query_str)
        rank_ctx = _retrieve_from_graph(
            parsed_query,
            risk_level=risk_level,
            answers=request_answers or {},
        )

        _merge_contexts(accumulated_context, rank_ctx)

        if len(ranks) == 1:
            record_note("LogicRAG: Single rank DAG, skipping context pruning to save latency.")
            continue

        # R117-review — stop issuing further LLM pruning calls once the total
        # wall-clock budget is spent; finalise with what we have.
        if time.monotonic() >= deadline:
            record_note("LogicRAG: wall-clock budget exhausted; finalising early.")
            break

        # Format the newly retrieved context into text
        new_context_text = _build_context_references_block(rank_ctx)

        # Context Pruning via Rolling Memory Update (brace-safe fill)
        user_prompt = _safe_fill(
            CONTEXT_PRUNING_USER_TEMPLATE,
            q=safe_query,
            memory=rolling_memory if rolling_memory else "None yet.",
            subq=unified_query_str,
            context=_truncate_on_boundary(new_context_text, 4000),
        )

        remaining = max(1.0, deadline - time.monotonic())
        updated_memory = _call_llm(
            CONTEXT_PRUNING_PROMPT_SYSTEM, user_prompt, max_tokens=512,
            timeout_override=remaining,
        )
        if updated_memory:
            rolling_memory = updated_memory
            record_note(f"LogicRAG: Updated rolling memory (len={len(rolling_memory)})")

    # R117-review — carry the synthesised rolling memory to Stage-2 via the
    # dedicated ``synthesis_memory`` field + ``semantically_relevant_statements``,
    # NOT a fake "LogicRAG Synthesis" ``article_info`` entry. The old fake
    # article rendered as a citable "(Article: LogicRAG Synthesis)" line in the
    # Stage-2 prompt and burned a citation-budget slot.
    if rolling_memory:
        accumulated_context.synthesis_memory = rolling_memory
        accumulated_context.semantically_relevant_statements.append(
            f"LOGIC_RAG_MEMORY: {rolling_memory}"
        )

    # R117-review — a degenerate (empty-retrieval) result defers to the
    # deterministic path so the route never ships the zero-retrieval floor
    # off the back of a content-free LogicRAG run.
    if not (accumulated_context.obligations or accumulated_context.article_info):
        record_note("LogicRAG: empty retrieval; deferring to deterministic path")
        return None

    accumulated_context.retrieval_path = "logic_rag"
    return accumulated_context
