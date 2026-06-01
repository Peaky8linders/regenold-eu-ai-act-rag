"""
Graph-Powered Gap Reasoning Engine — Compliance analysis via graph traversal.

Implements the GraphCompliance dual-graph pattern:
  - Policy graph: regulatory obligations, articles, risk levels (seeded from KB)
  - Context graph: system profile + assessment answers (passed per request)

The reasoning engine forward-chains from risk level to applicable obligations,
marks satisfied obligations via answered questions, identifies gaps, and
computes transitive impact through obligation dependency chains.

In this bundle the engine only enters this module when the Neo4j client
is enabled (``NEO4J_URI`` set + ``neo4j`` driver installed). With Neo4j
disabled the engine's ``_retrieve_from_kb`` deterministic path is taken
instead — this module is the cache-powered fast path for the same data.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.models import AssessmentAnswer, RiskLevel

if TYPE_CHECKING:
    from app.graph.client import GraphClient

logger = logging.getLogger(__name__)


def reason_compliance(
    client: GraphClient,
    risk_level: str,
    answers: dict[str, str],
    operator_role: str | None = None,
) -> dict:
    """Run gap reasoning for a system at a given risk level.

    Args:
        client: Neo4j graph client.
        risk_level: The system's classified risk level.
        answers: Dict of question_id → answer (yes/partial/no).
        operator_role: Optional operator role for filtering.

    Returns:
        Dict with obligation_chains, gaps, satisfied, cross_framework coverage.
    """
    if not client.enabled:
        return {"status": "disabled", "message": "Graph reasoning requires Neo4j"}

    # SEC: Validate risk_level against known enum to prevent Cypher injection.
    # Even though parameters are used ($rl), defence-in-depth demands validation.
    valid_levels = {rl.value for rl in RiskLevel}
    if risk_level not in valid_levels:
        return {
            "status": "error",
            "message": f"Invalid risk level: {risk_level!r}. Valid: {sorted(valid_levels)}",
            "gaps": [],
            "satisfied": [],
            "obligation_chains": [],
        }

    # 1. Forward-chain: get all obligations applicable at this risk level
    applicable = client.execute_read(
        "MATCH (o:Obligation)-[:APPLIES_AT]->(r:RiskLevel {id: $rl}) "
        "RETURN o.id AS obl_id, o.text AS text, o.article_ref AS article, "
        "o.paragraph_ref AS para",
        {"rl": risk_level},
    )

    if not applicable:
        return {
            "status": "no_obligations",
            "message": f"No obligations found for risk level: {risk_level}",
            "gaps": [],
            "satisfied": [],
            "obligation_chains": [],
        }

    # 2. For each obligation, check if it's satisfied by answered questions
    satisfied: list[dict] = []
    gaps: list[dict] = []

    for obl in applicable:
        obl_id = obl["obl_id"]

        # Find questions that assess this obligation
        assessing = client.execute_read(
            "MATCH (q:Question)-[:ASSESSES]->(o:Obligation {id: $oid}) "
            "RETURN q.id AS qid, q.text AS text, q.weight AS weight",
            {"oid": obl_id},
        )

        if not assessing:
            gaps.append({
                "obligation_id": obl_id,
                "text": obl["text"],
                "article": obl["article"],
                "paragraph": obl["para"],
                "reason": "no_assessing_question",
                "severity": "high",
            })
            continue

        # Check answers for assessing questions
        obl_satisfied = False
        obl_partial = False
        for q in assessing:
            answer = answers.get(q["qid"])
            if answer == AssessmentAnswer.YES.value:
                obl_satisfied = True
                break
            elif answer == AssessmentAnswer.PARTIAL.value:
                obl_partial = True

        if obl_satisfied:
            satisfied.append({
                "obligation_id": obl_id,
                "text": obl["text"],
                "article": obl["article"],
                "satisfied_by": [q["qid"] for q in assessing if answers.get(q["qid"]) == AssessmentAnswer.YES.value],
            })
        else:
            gaps.append({
                "obligation_id": obl_id,
                "text": obl["text"],
                "article": obl["article"],
                "paragraph": obl["para"],
                "reason": "partial" if obl_partial else "unanswered",
                "severity": "medium" if obl_partial else "high",
                "assessing_questions": [q["qid"] for q in assessing],
            })

    # 3. Compute transitive impact: if obligation A is PREREQUISITE_FOR B,
    #    and A is a gap, flag B as transitively impacted (multi-hop)
    gap_ids = {g["obligation_id"] for g in gaps}
    transitive_gaps: list[dict] = []
    seen_transitive: set[str] = set()
    if gap_ids:
        for gap_id in list(gap_ids):
            downstream = client.execute_read(
                "MATCH (o:Obligation {id: $oid})-[:PREREQUISITE_FOR*1..]->(d:Obligation) "
                "RETURN DISTINCT d.id AS did, d.text AS text, d.article_ref AS article",
                {"oid": gap_id},
            )
            for d in downstream:
                if d["did"] not in gap_ids and d["did"] not in seen_transitive:
                    seen_transitive.add(d["did"])
                    transitive_gaps.append({
                        "obligation_id": d["did"],
                        "text": d["text"],
                        "article": d["article"],
                        "blocked_by": gap_id,
                        "reason": "transitive_dependency",
                        "severity": "medium",
                    })

    # 4. Cross-framework satisfaction: how many NIST/ISO refs are covered
    cross_framework = _compute_cross_framework_coverage(client, answers)

    # 5. Build obligation chains for gaps (remediation paths)
    obligation_chains: list[dict] = []
    for gap in gaps[:20]:  # Limit chain computation
        chain = _build_obligation_chain(client, gap["obligation_id"])
        if chain:
            obligation_chains.append(chain)

    return {
        "status": "completed",
        "risk_level": risk_level,
        "total_obligations": len(applicable),
        "satisfied_count": len(satisfied),
        "gap_count": len(gaps),
        "transitive_gap_count": len(transitive_gaps),
        "compliance_percentage": round(
            len(satisfied) / len(applicable) * 100, 1
        ) if applicable else 0.0,
        "satisfied": satisfied,
        "gaps": gaps,
        "transitive_gaps": transitive_gaps,
        "obligation_chains": obligation_chains,
        "cross_framework": cross_framework,
    }


def satisfy_once_analysis(
    client: GraphClient,
    answers: dict[str, str],
) -> dict:
    """Compute cross-framework satisfy-once analysis via graph traversal.

    For each answered question, trace MAPS_TO_NIST and MAPS_TO_ISO edges
    to determine which framework references are automatically satisfied.
    """
    if not client.enabled:
        return {"status": "disabled"}

    answered_yes = [qid for qid, a in answers.items() if a in ("yes", "partial")]

    nist_covered: set[str] = set()
    iso_covered: set[str] = set()
    satisfy_once_items: list[dict] = []

    for qid in answered_yes:
        # Get NIST mappings
        nist = client.execute_read(
            "MATCH (q:Question {id: $qid})-[:MAPS_TO_NIST]->(n:NISTSubcategory) "
            "RETURN n.id AS nid, n.name AS name, n.function_id AS func",
            {"qid": qid},
        )
        # Get ISO mappings
        iso = client.execute_read(
            "MATCH (q:Question {id: $qid})-[:MAPS_TO_ISO]->(c:ISOClause) "
            "RETURN c.id AS cid, c.name AS name, c.parent_clause AS parent",
            {"qid": qid},
        )

        nist_refs = [n["nid"] for n in nist]
        iso_refs = [c["cid"] for c in iso]

        if nist_refs or iso_refs:
            nist_covered.update(nist_refs)
            iso_covered.update(iso_refs)
            satisfy_once_items.append({
                "question_id": qid,
                "answer": answers[qid],
                "frameworks_covered": (
                    (["eu_ai_act"])
                    + (["nist_ai_rmf"] if nist_refs else [])
                    + (["iso_42001"] if iso_refs else [])
                ),
                "nist_refs": nist_refs,
                "iso_refs": iso_refs,
            })

    # Get total NIST/ISO counts
    total_nist = client.execute_read(
        "MATCH (n:NISTSubcategory) RETURN count(n) AS cnt"
    )
    total_iso = client.execute_read(
        "MATCH (c:ISOClause) RETURN count(c) AS cnt"
    )

    nist_total = total_nist[0]["cnt"] if total_nist else 0
    iso_total = total_iso[0]["cnt"] if total_iso else 0

    return {
        "status": "completed",
        "total_questions_answered": len(answered_yes),
        "satisfy_once_count": len(satisfy_once_items),
        "nist_coverage": {
            "covered": len(nist_covered),
            "total": nist_total,
            "percentage": round(len(nist_covered) / nist_total * 100, 1) if nist_total else 0,
        },
        "iso_coverage": {
            "covered": len(iso_covered),
            "total": iso_total,
            "percentage": round(len(iso_covered) / iso_total * 100, 1) if iso_total else 0,
        },
        "items": satisfy_once_items,
    }


def _compute_cross_framework_coverage(
    client: GraphClient,
    answers: dict[str, str],
) -> dict:
    """Compute NIST and ISO coverage from answered questions."""
    answered_yes = [qid for qid, a in answers.items() if a in ("yes", "partial")]
    if not answered_yes:
        return {"nist_covered": 0, "iso_covered": 0, "nist_by_function": {}, "iso_by_clause": {}}

    # Batch query: get all NIST refs covered by answered questions
    nist_covered = client.execute_read(
        "MATCH (q:Question)-[:MAPS_TO_NIST]->(n:NISTSubcategory) "
        "WHERE q.id IN $qids "
        "RETURN DISTINCT n.id AS nid, n.function_id AS func",
        {"qids": answered_yes},
    )
    iso_covered = client.execute_read(
        "MATCH (q:Question)-[:MAPS_TO_ISO]->(c:ISOClause) "
        "WHERE q.id IN $qids "
        "RETURN DISTINCT c.id AS cid, c.parent_clause AS parent",
        {"qids": answered_yes},
    )

    return {
        "nist_covered": len(nist_covered),
        "iso_covered": len(iso_covered),
        "nist_by_function": _group_by(nist_covered, "func"),
        "iso_by_clause": _group_by(iso_covered, "parent"),
    }


def _build_obligation_chain(client: GraphClient, obl_id: str) -> dict | None:
    """Build a chain showing: obligation → assessing questions → remediation tasks."""
    # Get obligation details
    obl = client.execute_read(
        "MATCH (o:Obligation {id: $oid}) "
        "RETURN o.text AS text, o.article_ref AS article, o.paragraph_ref AS para",
        {"oid": obl_id},
    )
    if not obl:
        return None

    # Get assessing questions
    questions = client.execute_read(
        "MATCH (q:Question)-[:ASSESSES]->(o:Obligation {id: $oid}) "
        "RETURN q.id AS qid, q.text AS text, q.weight AS weight",
        {"oid": obl_id},
    )

    # Get remediating tasks (if any)
    tasks = client.execute_read(
        "MATCH (t:RoadmapTask)-[:REMEDIATES]->(q:Question)-[:ASSESSES]->(o:Obligation {id: $oid}) "
        "RETURN t.id AS tid, t.task AS task, t.priority AS priority, "
        "t.effort_hours AS effort",
        {"oid": obl_id},
    )

    # Get prerequisites
    prereqs = client.execute_read(
        "MATCH (p:Obligation)-[:PREREQUISITE_FOR]->(o:Obligation {id: $oid}) "
        "RETURN p.id AS pid, p.text AS text",
        {"oid": obl_id},
    )

    return {
        "obligation_id": obl_id,
        "text": obl[0]["text"],
        "article": obl[0]["article"],
        "paragraph": obl[0]["para"],
        "assessing_questions": [
            {"id": q["qid"], "text": q["text"], "weight": q["weight"]}
            for q in questions
        ],
        "remediation_tasks": [
            {"id": t["tid"], "task": t["task"], "priority": t["priority"],
             "effort_hours": t["effort"]}
            for t in tasks
        ],
        "prerequisites": [
            {"id": p["pid"], "text": p["text"]}
            for p in prereqs
        ],
    }


def _group_by(records: list[dict], key: str) -> dict[str, int]:
    """Group records by a key and count."""
    groups: dict[str, int] = {}
    for r in records:
        k = r.get(key, "unknown")
        groups[k] = groups.get(k, 0) + 1
    return groups
