#!/usr/bin/env python3
"""Generate the TrustGraph artefacts for the EU AI Act, from this repo's verified data.

R397. Why this exists, and what the official docs actually say.

``trustgraph-integration/`` held exactly one file — a 1,129-line OWL/Turtle
ontology inherited from the sibling CodexAI project — with **zero call sites**
(R393). Parsed here for the first time with ``rdflib`` it is well-formed (699
triples, 27 classes, 34 object properties) and **completely inert**:

* **0 ``owl:NamedIndividual``** — a T-Box with no A-Box. It asserts nothing about
  any Article, Annex, role or obligation, so loading it would add no facts.
* **0 subjects in any EU-AI-Act namespace.** Its domain is compliance-PROGRAMME
  management (``AttackAttempt``, ``AtlasTechnique``, ``ComplianceGap``,
  ``MigrationTask``, ``SecurityCampaign``), not the Regulation.
* **27 classes**, against TrustGraph's own published guidance to "keep
  ontologies focused with 5-10 key classes rather than overly complex
  hierarchies".
* It is a ``.ttl``, and TrustGraph's configuration reference states ontologies
  load via CLI in the **native JSON format only**
  (``tg-put-config-item --type ontology``); Turtle ontologies "can only be
  imported through the Workbench Ontology Editor". So the file could never have
  been loaded by the documented CLI path in the first place.

This script builds on it rather than discarding it: the eight classes that are
genuinely Regulation structure (``Article``, ``Annex``, ``Chapter``,
``Recital``, ``Obligation``, ``OperatorRole``, ``Penalty``, ``Deadline``) and
the properties that carry over are aligned with ``owl:equivalentClass`` /
``owl:equivalentProperty``, so nothing already modelled is lost, while the
19 classes belonging to the sibling's security-campaign domain are left out.

TWO ARTEFACTS, because TrustGraph loads schema and instances by different paths:

1. ``ontology/eu-ai-act.json`` — the T-Box in TrustGraph's **native JSON**
   config format (``metadata`` / ``classes`` / ``objectProperties`` /
   ``datatypeProperties``), the only CLI-loadable ontology form:

       tg-put-config-item --type ontology --key eu-ai-act --stdin < eu-ai-act.json

2. ``knowledge/eu-ai-act-core.ttl`` — the A-Box instance triples for:

       tg-load-turtle -f default --document-id eu-ai-act-core eu-ai-act-core.ttl

   ``tg-load-turtle`` parses with ``rdflib`` (per the CLI reference), which is
   the same library used to serialise here — so a file this script emits is
   parseable by the tool that consumes it, by construction.

Both are generated from data this repo already verifies: the 126 canonical
provisions of ``article_existence``, the verbatim provision text, and the
``PHASE_REGISTRY`` / ``PRACTICE_REGISTRY`` / ``ANNEX_III_REGISTRY`` /
``ROLE_OBLIGATIONS`` registries. Nothing here is hand-asserted law.

Deterministic: sorted throughout, no clock, no network. Re-running on an
unchanged tree yields byte-identical output, so CI can diff it.

Usage::

    python scripts/build_trustgraph_core.py            # write the artefacts
    python scripts/build_trustgraph_core.py --check    # fail if out of date
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from rdflib import Graph, Literal, Namespace, URIRef  # noqa: E402
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD  # noqa: E402

from app.data import ontology as onto  # noqa: E402
from app.data.article_existence import ARTICLE_EXISTENCE  # noqa: E402
from app.data.provision_text import get_provision_text  # noqa: E402

OUT_ONTOLOGY = REPO / "trustgraph-integration" / "ontology" / "eu-ai-act.json"
OUT_KNOWLEDGE = REPO / "trustgraph-integration" / "knowledge" / "eu-ai-act-core.ttl"

BASE = "https://antifragile-ai.net/ns/eu-ai-act#"
EU = Namespace(BASE)
CODEXAI = Namespace("https://w3id.org/codexai#")

# ---------------------------------------------------------------------------
# T-Box. Nine classes, inside TrustGraph's published 5-10 guidance.
# `equivalent` aligns onto the inherited CodexAI ontology where the concept is
# genuinely the same, so the existing model is extended rather than replaced.
# ---------------------------------------------------------------------------
CLASSES: list[dict] = [
    {"name": "Provision", "label": "Provision",
     "comment": "Any citable unit of the Regulation: an Article, an Annex, or a "
                "sub-point of either. The superclass that carries the citation "
                "coordinate.",
     "equivalent": None},
    {"name": "Article", "label": "Article", "parent": "Provision",
     "comment": "One of the 113 Articles of Regulation (EU) 2024/1689.",
     "equivalent": "Article"},
    {"name": "Annex", "label": "Annex", "parent": "Provision",
     "comment": "One of the 13 Annexes of Regulation (EU) 2024/1689.",
     "equivalent": "Annex"},
    {"name": "OperatorRole", "label": "Operator role",
     "comment": "A role the Regulation binds duties to (provider, deployer, "
                "importer, distributor, authorised representative, downstream "
                "provider, notified body) or protects (affected person).",
     "equivalent": "OperatorRole"},
    {"name": "RiskClass", "label": "Risk class",
     "comment": "A risk tier: prohibited, high-risk under Annex I or Annex III, "
                "limited risk, minimal risk, GPAI, or GPAI with systemic risk.",
     "equivalent": None},
    {"name": "Obligation", "label": "Obligation",
     "comment": "A duty a provision places on an operator role at a risk class.",
     "equivalent": "Obligation"},
    {"name": "ProhibitedPractice", "label": "Prohibited practice",
     "comment": "An Article 5(1) practice prohibited outright.",
     "equivalent": None},
    {"name": "HighRiskArea", "label": "High-risk area",
     "comment": "One of the eight areas of Annex III. Note the Regulation lists "
                "AREAS, not use cases.",
     "equivalent": None},
    {"name": "CompliancePhase", "label": "Compliance phase",
     "comment": "A staged application date of the Regulation and the provisions "
                "that become applicable on it.",
     "equivalent": "Deadline"},
]

OBJECT_PROPERTIES: list[dict] = [
    {"name": "appliesToRole", "label": "applies to role",
     "domain": "Obligation", "range": "OperatorRole", "equivalent": "appliesToRole"},
    {"name": "appliesToRiskClass", "label": "applies to risk class",
     "domain": "Obligation", "range": "RiskClass", "equivalent": "appliesToRiskTier"},
    {"name": "imposedBy", "label": "imposed by",
     "domain": "Obligation", "range": "Provision", "equivalent": None},
    {"name": "partOf", "label": "part of",
     "domain": "Provision", "range": "Provision", "equivalent": None},
    {"name": "citesProvision", "label": "cites provision",
     "domain": "Provision", "range": "Provision", "equivalent": "crossReferences"},
    {"name": "prohibitedBy", "label": "prohibited by",
     "domain": "ProhibitedPractice", "range": "Provision", "equivalent": None},
    {"name": "relatedProhibition", "label": "related prohibition",
     "domain": "HighRiskArea", "range": "ProhibitedPractice", "equivalent": None},
    {"name": "applicableFrom", "label": "applicable from",
     "domain": "Provision", "range": "CompliancePhase", "equivalent": None},
]

DATATYPE_PROPERTIES: list[dict] = [
    {"name": "citation", "label": "citation", "range": "xsd:string",
     "comment": "The canonical wire citation, e.g. 'Article 13.3' or 'Annex III.1'."},
    {"name": "verbatimText", "label": "verbatim text", "range": "xsd:string",
     "comment": "The adopted text of the provision, used for grounding and "
                "quotation. Never paraphrased."},
    {"name": "effectiveDate", "label": "effective date", "range": "xsd:date",
     "comment": "The date a compliance phase begins to apply."},
    {"name": "annexNumber", "label": "annex point number", "range": "xsd:integer",
     "comment": "The numbered point within an Annex, e.g. 1 for Annex III point 1."},
]


def _slug(text: str) -> str:
    """A stable, URI-safe local name."""
    out = []
    for ch in text:
        out.append(ch if ch.isalnum() else "_")
    return "".join(out).strip("_")


def _canonical(ref: str) -> str:
    """Internal 'Art. 5.1.a' / 'Annex III' -> wire 'Article 5.1.a' / 'Annex III'.

    Invariant #1 of AGENTS.md: emitted citations are ``Article N(.subpoint)*``
    or ``Annex X(.subpoint)*``; ``Art. 13`` is never a wire form.
    """
    return f"Article {ref[len('Art. '):]}" if ref.startswith("Art. ") else ref


def _base_of(ref: str) -> str:
    """The ``article_existence`` key for a possibly sub-pointed reference."""
    if ref.startswith("Art. "):
        return "Art. " + ref[len("Art. "):].split(".")[0]
    parts = ref.split(".")
    return parts[0]


def build_ontology_json() -> dict:
    """The T-Box in TrustGraph's native ontology configuration format."""
    return {
        "metadata": {
            "name": "EU AI Act (Regulation (EU) 2024/1689)",
            "description": (
                "Focused operational ontology of the EU AI Act: provisions, "
                "operator roles, risk classes, obligations, prohibited practices, "
                "Annex III areas and staged application dates. Generated from "
                "verified repository data by scripts/build_trustgraph_core.py."
            ),
            "namespace": BASE,
            "prefixes": {
                "eu-ai-act": BASE,
                "codexai": str(CODEXAI),
                "owl": str(OWL),
                "rdf": str(RDF),
                "rdfs": str(RDFS),
                "skos": str(SKOS),
                "xsd": str(XSD),
            },
        },
        "classes": {
            c["name"]: {
                "uri": BASE + c["name"],
                "type": "owl:Class",
                "rdfs:label": [{"@language": "en", "@value": c["label"]}],
                "rdfs:comment": [{"@language": "en", "@value": c["comment"]}],
                **({"rdfs:subClassOf": [BASE + c["parent"]]} if c.get("parent") else {}),
                **({"owl:equivalentClass": [str(CODEXAI) + c["equivalent"]]}
                   if c.get("equivalent") else {}),
            }
            for c in CLASSES
        },
        "objectProperties": {
            p["name"]: {
                "uri": BASE + p["name"],
                "type": "owl:ObjectProperty",
                "rdfs:label": [{"@language": "en", "@value": p["label"]}],
                "rdfs:domain": BASE + p["domain"],
                "rdfs:range": BASE + p["range"],
                **({"owl:equivalentProperty": [str(CODEXAI) + p["equivalent"]]}
                   if p.get("equivalent") else {}),
            }
            for p in OBJECT_PROPERTIES
        },
        "datatypeProperties": {
            p["name"]: {
                "uri": BASE + p["name"],
                "type": "owl:DatatypeProperty",
                "rdfs:label": [{"@language": "en", "@value": p["label"]}],
                "rdfs:range": p["range"],
                "rdfs:comment": [{"@language": "en", "@value": p["comment"]}],
            }
            for p in DATATYPE_PROPERTIES
        },
    }


def build_knowledge_graph(*, with_text: bool = True) -> Graph:
    """The A-Box: real instances, from verified repository data only."""
    g = Graph()
    g.bind("eu-ai-act", EU)
    g.bind("codexai", CODEXAI)
    g.bind("skos", SKOS)

    def provision(ref: str) -> URIRef:
        """Mint (idempotently) a Provision node for a canonical reference."""
        canon = _canonical(ref)
        node = EU[_slug(canon)]
        if (node, RDF.type, None) not in g:
            # Only a BARE head is an Article/Annex. `Article 5.1.a` is a
            # sub-point of Article 5, not an Article — typing it as one gives
            # 121 Articles for a Regulation that has 113, and TrustGraph's
            # Ontology RAG relies on type constraints for exact matching, so a
            # mistyped instance silently widens every type-filtered query.
            head = _canonical(_base_of(ref))
            if head != canon:
                g.add((node, RDF.type, EU.Provision))
            else:
                g.add((node, RDF.type, EU.Annex if canon.startswith("Annex") else EU.Article))
            g.add((node, EU.citation, Literal(canon)))
            g.add((node, SKOS.prefLabel, Literal(canon, lang="en")))
            # sub-point -> parent, so a leaf always reaches its head
            if head != canon:
                g.add((node, EU.partOf, EU[_slug(head)]))
                provision(_base_of(ref))
            if with_text:
                text = get_provision_text(canon)
                if text:
                    g.add((node, EU.verbatimText, Literal(text)))
        return node

    # --- every canonical provision, so the graph spans the whole Regulation ---
    for ref in sorted(ARTICLE_EXISTENCE):
        provision(ref)

    # --- operator roles ---
    role_node = {}
    for role in onto.ActorRole:
        n = EU["role_" + _slug(role.value)]
        role_node[role] = n
        g.add((n, RDF.type, EU.OperatorRole))
        g.add((n, SKOS.prefLabel, Literal(role.value.replace("_", " "), lang="en")))

    # --- risk classes ---
    risk_node = {}
    for rc in onto.RiskClass:
        n = EU["risk_" + _slug(rc.value)]
        risk_node[rc] = n
        g.add((n, RDF.type, EU.RiskClass))
        g.add((n, SKOS.prefLabel, Literal(rc.value.replace("_", " "), lang="en")))

    # --- obligations: role x risk class x provision -------------------------
    for role, per_class in sorted(onto.ROLE_OBLIGATIONS.items(), key=lambda kv: kv[0].value):
        for rc, refs in sorted(per_class.items(), key=lambda kv: kv[0].value):
            for ref in sorted(refs):
                p = provision(ref)
                n = EU[f"obl_{_slug(role.value)}_{_slug(rc.value)}_{_slug(_canonical(ref))}"]
                g.add((n, RDF.type, EU.Obligation))
                g.add((n, EU.appliesToRole, role_node[role]))
                g.add((n, EU.appliesToRiskClass, risk_node[rc]))
                g.add((n, EU.imposedBy, p))

    # --- Article 5 prohibited practices -------------------------------------
    practice_node = {}
    for key, pr in sorted(onto.PRACTICE_REGISTRY.items()):
        n = EU["practice_" + _slug(key)]
        practice_node[key] = n
        g.add((n, RDF.type, EU.ProhibitedPractice))
        g.add((n, SKOS.prefLabel, Literal(pr.short_name, lang="en")))
        if getattr(pr, "description", None):
            g.add((n, RDFS.comment, Literal(pr.description, lang="en")))
        for ref in sorted(pr.citation):
            g.add((n, EU.prohibitedBy, provision(ref)))

    # --- Annex III high-risk areas ------------------------------------------
    for key, area in sorted(onto.ANNEX_III_REGISTRY.items()):
        n = EU["annex_iii_area_" + _slug(key)]
        g.add((n, RDF.type, EU.HighRiskArea))
        g.add((n, SKOS.prefLabel, Literal(area.short_name, lang="en")))
        g.add((n, EU.annexNumber, Literal(int(area.number), datatype=XSD.integer)))
        g.add((n, EU.partOf, provision(f"Annex III.{area.number}")))
        for rel in sorted(getattr(area, "related_prohibitions", ()) or ()):
            if rel in practice_node:
                g.add((n, EU.relatedProhibition, practice_node[rel]))

    # --- staged application dates -------------------------------------------
    for key, phase in sorted(onto.PHASE_REGISTRY.items()):
        n = EU["phase_" + _slug(key)]
        g.add((n, RDF.type, EU.CompliancePhase))
        g.add((n, SKOS.prefLabel, Literal(phase.label, lang="en")))
        g.add((n, EU.effectiveDate, Literal(str(phase.effective_date), datatype=XSD.date)))
        for ref in sorted(phase.articles):
            g.add((provision(ref), EU.applicableFrom, n))

    return g


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the committed artefacts differ from a fresh build")
    ap.add_argument("--no-text", action="store_true",
                    help="omit verbatim provision text (smaller, for inspection)")
    args = ap.parse_args()

    ontology = json.dumps(build_ontology_json(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    graph = build_knowledge_graph(with_text=not args.no_text)
    turtle = graph.serialize(format="turtle")

    if args.check:
        stale = []
        for path, fresh in ((OUT_ONTOLOGY, ontology), (OUT_KNOWLEDGE, turtle)):
            if not path.exists():
                stale.append(f"{path.relative_to(REPO)} is missing")
            elif path.read_text(encoding="utf-8") != fresh:
                stale.append(f"{path.relative_to(REPO)} is out of date")
        if stale:
            print("STALE — re-run scripts/build_trustgraph_core.py:", file=sys.stderr)
            for s in stale:
                print("  " + s, file=sys.stderr)
            return 1
        print(f"up to date — {len(graph)} triples, {len(build_ontology_json()['classes'])} classes")
        return 0

    for path, content in ((OUT_ONTOLOGY, ontology), (OUT_KNOWLEDGE, turtle)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path.relative_to(REPO)} ({len(content):,} bytes)")
    print(f"{len(graph):,} triples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
