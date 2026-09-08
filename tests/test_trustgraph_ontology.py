"""R397 — the TrustGraph artefacts must stay true, conformant and loadable.

``trustgraph-integration/`` was a directory name for five rounds: one inherited
1,129-line CodexAI Turtle file with **zero call sites**, never once parsed. When
it finally was (``scripts/build_trustgraph_core.py`` docstring) it turned out to
be a T-Box with **0 individuals** and **0 subjects in any EU-AI-Act namespace** —
well-formed, and incapable of asserting a single fact about the Regulation.

These tests exist so the replacement cannot rot the same way. They check the
generated artefacts against three independent authorities:

* **TrustGraph's documented formats** — the ontology JSON carries the
  ``metadata`` / ``classes`` / ``objectProperties`` / ``datatypeProperties``
  sections its configuration reference requires, and the knowledge file parses
  with ``rdflib``, which is what ``tg-load-turtle`` itself uses.
* **The Regulation** — exactly 113 Articles and 13 Annexes, no more.
* **This repo's own lint floor** (AGENTS.md invariant #2) — every emitted
  citation resolves in ``article_existence``'s 126 canonical references, in the
  ``Article N`` / ``Annex X`` wire form of invariant #1.

Plus the ontology-conformance rule TrustGraph's Ontology RAG depends on: every
instance's type and every predicate must be **declared**, because type
constraints are what give it "exact matches" instead of fuzzy similarity.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

rdflib = pytest.importorskip("rdflib", reason="rdflib is a dev dependency (pyproject [dev])")
from rdflib import Graph, RDF, URIRef  # noqa: E402

_REPO = Path(__file__).resolve().parents[1]
_ONTOLOGY = _REPO / "trustgraph-integration" / "ontology" / "eu-ai-act.json"
_KNOWLEDGE = _REPO / "trustgraph-integration" / "knowledge" / "eu-ai-act-core.ttl"
_INHERITED = _REPO / "trustgraph-integration" / "ontology" / "codexai-compliance.ttl"
_BASE = "https://antifragile-ai.net/ns/eu-ai-act#"
_CODEXAI = "https://w3id.org/codexai#"


@pytest.fixture(scope="module")
def ontology() -> dict:
    return json.loads(_ONTOLOGY.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def graph() -> Graph:
    g = Graph()
    g.parse(_KNOWLEDGE, format="turtle")  # the parser tg-load-turtle uses
    return g


# -- TrustGraph's documented formats ----------------------------------------


def test_ontology_json_matches_the_documented_config_schema(ontology: dict) -> None:
    """Ontologies load via `tg-put-config-item --type ontology` in NATIVE JSON.

    Turtle ontologies are Workbench-import only, which is why the inherited
    .ttl could never have been loaded by the documented CLI path.
    """
    assert set(ontology) == {"metadata", "classes", "objectProperties", "datatypeProperties"}

    meta = ontology["metadata"]
    assert meta["namespace"] == _BASE
    for prefix in ("owl", "rdf", "rdfs", "xsd"):
        assert prefix in meta["prefixes"], f"the reference requires the {prefix} prefix"

    for name, cls in ontology["classes"].items():
        assert cls["type"] == "owl:Class", name
        assert cls["uri"] == _BASE + name
        assert cls["rdfs:label"] and cls["rdfs:label"][0]["@language"] == "en", name
    for name, prop in ontology["objectProperties"].items():
        assert prop["type"] == "owl:ObjectProperty", name
        assert prop["rdfs:domain"].startswith(_BASE) and prop["rdfs:range"].startswith(_BASE), name
    for name, prop in ontology["datatypeProperties"].items():
        assert prop["type"] == "owl:DatatypeProperty", name
        assert prop["rdfs:range"].startswith("xsd:"), name


def test_ontology_stays_inside_trustgraphs_published_size_guidance(ontology: dict) -> None:
    """"Keep ontologies focused with 5-10 key classes rather than overly complex
    hierarchies" — TrustGraph's Ontology RAG guide. The inherited file had 27."""
    assert 5 <= len(ontology["classes"]) <= 10, (
        f"{len(ontology['classes'])} classes; the guidance is 5-10 and the "
        "inherited CodexAI ontology's 27 is what this replaced"
    )


def test_the_knowledge_file_parses_with_rdflib(graph: Graph) -> None:
    """`tg-load-turtle` "parses Turtle (RDF) files using rdflib". If this passes,
    the file is loadable by construction."""
    assert len(graph) > 1000, f"only {len(graph)} triples"


# -- the alignment onto the inherited ontology is real, not decorative -------


def test_every_codexai_alignment_target_exists_in_the_inherited_ontology(ontology: dict) -> None:
    """`owl:equivalentClass` onto a class that does not exist would make the
    "builds on the existing ontology" claim false. Check it against the file."""
    inherited = Graph()
    inherited.parse(_INHERITED, format="turtle")
    subjects = {str(s) for s in inherited.subjects()}

    targets = [
        t
        for section in ("classes", "objectProperties")
        for entry in ontology[section].values()
        for key in ("owl:equivalentClass", "owl:equivalentProperty")
        for t in entry.get(key, [])
    ]
    assert targets, "no alignment at all — the inherited ontology is not being built on"
    missing = sorted(t for t in targets if t.startswith(_CODEXAI) and t not in subjects)
    assert not missing, f"alignment points at classes absent from the inherited ontology: {missing}"


# -- ontology conformance, the mechanism Ontology RAG relies on -------------


def test_every_instance_type_and_predicate_is_declared(ontology: dict, graph: Graph) -> None:
    """"All entities conform to ontology types. All relationships use
    ontology-defined properties." Type filtering is only exact if this holds."""
    declared_classes = {c["uri"] for c in ontology["classes"].values()}
    declared_props = {p["uri"] for p in ontology["objectProperties"].values()} | {
        p["uri"] for p in ontology["datatypeProperties"].values()
    }

    undeclared_types = sorted({str(o) for o in graph.objects(None, RDF.type)} - declared_classes)
    assert not undeclared_types, f"instances typed with undeclared classes: {undeclared_types}"

    used = {str(p) for p in set(graph.predicates()) if str(p).startswith(_BASE)}
    assert not sorted(used - declared_props), f"undeclared predicates: {sorted(used - declared_props)}"


# -- the Regulation ---------------------------------------------------------


def test_the_graph_has_exactly_the_regulations_shape(graph: Graph) -> None:
    """113 Articles and 13 Annexes — no more.

    A sub-point is a Provision, not an Article. Typing `Article 5.1.a` as an
    Article read 121 Articles for a Regulation that has 113, and silently
    widened every type-filtered query.
    """
    counts = Counter(str(o).replace(_BASE, "") for o in graph.objects(None, RDF.type))
    assert counts["Article"] == 113, counts
    assert counts["Annex"] == 13, counts
    assert counts["OperatorRole"] == 9, counts
    assert counts["RiskClass"] == 7, counts
    assert counts["Provision"] > 0, "sub-point coordinates are missing entirely"


def test_every_citation_resolves_in_the_canonical_reference_set(graph: Graph) -> None:
    """AGENTS.md invariant #2, applied to the knowledge core."""
    from app.data.article_existence import ARTICLE_EXISTENCE

    def base_of(citation: str) -> str:
        if citation.startswith("Article "):
            return "Art. " + citation[len("Article "):].split(".")[0]
        return citation.split(".")[0]

    citations = [str(o) for o in graph.objects(None, URIRef(_BASE + "citation"))]
    assert citations, "no citations emitted at all"
    unresolved = sorted({c for c in citations if base_of(c) not in ARTICLE_EXISTENCE})
    assert not unresolved, f"citations outside the 126 canonical provisions: {unresolved}"


def test_citations_use_the_wire_form_never_the_internal_abbreviation(graph: Graph) -> None:
    """Invariant #1: `Article 13`, never `Art. 13`, on anything citable."""
    bad = sorted(
        c
        for c in (str(o) for o in graph.objects(None, URIRef(_BASE + "citation")))
        if not (c.startswith("Article ") or c.startswith("Annex "))
    )
    assert not bad, f"non-wire citation forms: {bad}"

    # Two-sided: the check must actually reject the abbreviation it forbids.
    assert not "Art. 13".startswith(("Article ", "Annex "))


def test_every_subpoint_reaches_its_head(graph: Graph) -> None:
    """A leaf must carry `partOf` to its head, or head-level retrieval loses it."""
    part_of = URIRef(_BASE + "partOf")
    citation = URIRef(_BASE + "citation")
    for node in graph.subjects(RDF.type, URIRef(_BASE + "Provision")):
        assert (node, part_of, None) in graph, f"{graph.value(node, citation)} has no parent"


# -- the artefacts are generated, and stay in sync --------------------------


def test_the_committed_artefacts_are_up_to_date() -> None:
    """Regenerating on an unchanged tree must be a no-op.

    The generator is deterministic (sorted, no clock, no network), so a diff
    here means someone edited a registry without rebuilding — exactly how the
    inherited ontology drifted into being decorative.
    """
    proc = subprocess.run(
        [sys.executable, str(_REPO / "scripts" / "build_trustgraph_core.py"), "--check"],
        cwd=str(_REPO), capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
