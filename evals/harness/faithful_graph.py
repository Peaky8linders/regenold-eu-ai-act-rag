"""A faithful in-process stand-in for the seeded Neo4j graph.

WHY THIS EXISTS. The R323/R324 knowledge-graph work only reaches the model
through the Stage-2 prompt, so its effect cannot be measured without (a) a
graph and (b) an LLM. In a container with neither — bolt/7687 and
``*.databases.neo4j.io`` are both proxy-blocked, and there are no NEO4J_*
credentials — the honest substitute is to answer the REAL Cypher queries from
the REAL seed payload, which is the same object ``scripts/seed_neo4j_kb.py``
pushes to Aura.

WHAT THIS IS NOT. It is not Aura. It executes no Cypher: it dispatches on the
query text and reproduces each query's documented semantics in Python. So it
validates the RENDER path and the CONTENT the graph contributes; it cannot
catch a Cypher syntax error or a Neo4j planner difference. Any finding about
query correctness must still be smoke-tested against a live instance.

WHY IT IS STILL WORTH TRUSTING for content: the rows come from
``build_payload()`` / ``build_hierarchy_payload()``, and the R323 handoff
records the live graph as byte-identical to those payloads (113/113 articles,
13/13 annexes, 180 recitals, 68 definitions, 658 Paragraph / 421 Point / 37
SubPoint).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


class FaithfulGraphClient:
    """Answers the five ``kg_context`` queries from the real seed payload."""

    enabled = True

    def __init__(self) -> None:
        from app.data.provision_hierarchy import build_hierarchy_payload
        from scripts.seed_neo4j_kb import build_payload

        self._p = build_payload()
        self._h = build_hierarchy_payload()

        # id -> {strict_citation, title}
        self._nodes: dict[str, dict] = {}
        for n in list(self._p.article_nodes) + list(self._p.annex_nodes):
            self._nodes[n["id"]] = n

        self._paras = {n["id"]: n for n in self._h.paragraph_nodes}
        self._points = {n["id"]: n for n in self._h.point_nodes}
        self._subs = {n["id"]: n for n in self._h.subpoint_nodes}

        # article/annex id -> [paragraph ids], preserving seeded order
        self._para_of: dict[str, list[str]] = defaultdict(list)
        for e in self._h.has_paragraph_edges:
            self._para_of[e["source_id"]].append(e["target_id"])
        self._point_of: dict[str, list[str]] = defaultdict(list)
        for e in self._h.has_point_edges:
            self._point_of[e["source_id"]].append(e["target_id"])
        self._sub_of: dict[str, list[str]] = defaultdict(list)
        for e in self._h.has_subpoint_edges:
            self._sub_of[e["source_id"]].append(e["target_id"])

        self._recitals = {n["id"]: n for n in self._p.recital_nodes}
        self._recital_of: dict[str, list[str]] = defaultdict(list)
        for e in self._p.has_recital_anchor_edges:
            # edge direction in the seeder is Article -> Recital
            self._recital_of[e["source_id"]].append(e["target_id"])

        self._by_id: dict[str, dict] = {}
        for bucket in (
            self._p.practice_nodes, self._p.annex_iii_nodes,
            self._p.operator_role_nodes, self._p.phase_nodes,
        ):
            for n in bucket:
                self._by_id[n["id"]] = n

        self._prohibited: dict[str, list[str]] = defaultdict(list)
        for e in self._p.prohibited_under_edges:
            self._prohibited[e["target_id"]].append(e["source_id"])
        self._triggers: dict[str, list[str]] = defaultdict(list)
        for e in self._p.triggers_high_risk_edges:
            self._triggers[e["target_id"]].append(e["source_id"])
        self._roles: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for e in self._p.has_obligation_article_edges:
            self._roles[e["target_id"]].append((e["source_id"], e.get("tier", "")))
        self._phases: dict[str, list[str]] = defaultdict(list)
        for e in self._p.applies_to_phase_edges:
            self._phases[e["target_id"]].append(e["source_id"])

    # ── the seam ────────────────────────────────────────────────────────────

    def execute_read(self, query: str, parameters: dict | None = None) -> list[dict]:
        p = parameters or {}
        if "HAS_PARAGRAPH|HAS_POINT" in query:
            return self._hierarchy(p)
        if "HAS_SUBPOINT" in query:
            return self._subpoints(p)
        if "PROHIBITED_UNDER" in query:
            return self._deontic(p)
        if "HAS_RECITAL_ANCHOR" in query:
            return self._recital(p)
        if "RETURN 1 AS ping" in query:
            return [{"ping": 1}]
        return []

    def _cite(self, aid: str) -> str:
        return str(self._nodes.get(aid, {}).get("strict_citation") or aid)

    def _hierarchy(self, p: dict) -> list[dict]:
        """Reproduces ``_HIERARCHY_CYPHER`` INCLUDING its dead ``|HAS_POINT`` leg.

        The R324 review measured that all 421 HAS_POINT edges have a Paragraph
        source, so with ``a`` bound to Article/Annex the alternation reaches
        zero Points. Reproducing the defect rather than silently fixing it is
        the point — otherwise this harness would measure a system that does not
        exist.
        """
        out = []
        max_units = int(p.get("max_units") or 24)
        for aid in p.get("ids") or []:
            pids = self._para_of.get(aid, [])
            units = [
                {"num": self._paras[i].get("number"), "text": self._paras[i].get("text")}
                for i in pids
                if i in self._paras
            ]
            units.sort(key=lambda u: (
                int(u["num"]) if str(u["num"] or "").isdigit() else 10**6,
                str(u["num"] or ""),
            ))
            if not units:
                continue
            out.append({
                "id": aid,
                "cite": self._cite(aid),
                "title": self._nodes.get(aid, {}).get("title") or "",
                "units": units[:max_units],
            })
        return out

    def _subpoints(self, p: dict) -> list[dict]:
        out = []
        for aid in p.get("ids") or []:
            for pid in self._para_of.get(aid, []):
                for ptid in self._point_of.get(pid, []):
                    for sid in self._sub_of.get(ptid, []):
                        s = self._subs.get(sid)
                        if not s:
                            continue
                        out.append({
                            "cite": self._cite(aid),
                            "para": self._paras.get(pid, {}).get("number"),
                            "letter": self._points.get(ptid, {}).get("letter"),
                            "sid": sid,
                            "text": s.get("text"),
                        })
        return out[: int(p.get("limit") or 24)]

    def _deontic(self, p: dict) -> list[dict]:
        out = []
        for aid in p.get("ids") or []:
            practices = [
                self._by_id.get(i, {}).get("short_name") or i
                for i in self._prohibited.get(aid, [])
            ]
            cats = [
                self._by_id.get(i, {}).get("label") or i
                for i in self._triggers.get(aid, [])
            ]
            roles = [
                f"{self._by_id.get(i, {}).get('label') or i} ({tier})"
                for i, tier in self._roles.get(aid, [])
            ]
            phases = [
                f"{self._by_id.get(i, {}).get('label') or i} from "
                f"{self._by_id.get(i, {}).get('effective_date') or ''}"
                for i in self._phases.get(aid, [])
            ]
            if practices or cats or roles or phases:
                out.append({
                    "cite": self._cite(aid), "practices": practices,
                    "annex_iii": cats, "roles": roles, "phases": phases,
                })
        return out[: int(p.get("limit") or 12)]

    def _recital(self, p: dict) -> list[dict]:
        out = []
        for aid in p.get("ids") or []:
            for rid in self._recital_of.get(aid, []):
                r = self._recitals.get(rid)
                if r:
                    out.append({
                        "cite": self._cite(aid),
                        "number": r.get("number"),
                        "text": r.get("text"),
                    })
        out.sort(key=lambda r: (
            int(r["number"]) if str(r["number"] or "").isdigit() else 10**6
        ))
        return out[: int(p.get("limit") or 5)]

    # unused by kg_context, present so the object is drop-in
    def health_check(self) -> dict[str, Any]:
        return {"status": "healthy", "ping": 1}

    def get_stats(self) -> dict[str, Any]:
        return {"nodes": self._p.total_nodes, "edges": self._p.total_edges}

    def close(self) -> None:  # pragma: no cover
        return None


def install() -> FaithfulGraphClient:
    """Patch the client factory so ``kg_context`` reads this instead of Aura."""
    client = FaithfulGraphClient()
    import app.graph.client as gc

    gc.get_graph_client = lambda *a, **k: client  # type: ignore[assignment]
    return client
