"""Coverage audit for all retrieval surfaces in the EU AI Act RAG system.

Checks all 113 articles + 13 annexes (126 total) against ARTICLE_EXISTENCE.
Also checks recitals (180) and definitions (68) where applicable.

Usage:
    .venv/Scripts/python.exe scripts/audit_coverage.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

# Make repo root importable.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.data.article_existence import ARTICLE_EXISTENCE

ARTICLES_IN_CATALOG = frozenset(r for r in ARTICLE_EXISTENCE if r.startswith("Art."))
ANNEXES_IN_CATALOG = frozenset(r for r in ARTICLE_EXISTENCE if r.startswith("Annex"))
N_ARTICLES = len(ARTICLES_IN_CATALOG)   # 113
N_ANNEXES = len(ANNEXES_IN_CATALOG)     # 13
N_TOTAL = len(ARTICLE_EXISTENCE)        # 126

print(f"Catalog: {N_ARTICLES} articles, {N_ANNEXES} annexes = {N_TOTAL} total\n")
print("=" * 80)


def _articles_covered(refs: set[str]) -> tuple[set[str], set[str]]:
    arts = {r for r in refs if r.startswith("Art.")} & ARTICLES_IN_CATALOG
    annexes = {r for r in refs if r.startswith("Annex")} & ANNEXES_IN_CATALOG
    return arts, annexes


def _verdict(arts: set, annexes: set) -> str:
    missing_arts = ARTICLES_IN_CATALOG - arts
    missing_ann = ANNEXES_IN_CATALOG - annexes
    if not missing_arts and not missing_ann:
        return "COMPLETE"
    parts = []
    if missing_arts:
        nums = sorted(int(a.split()[-1]) for a in missing_arts)
        parts.append(f"missing articles: {nums}")
    if missing_ann:
        parts.append(f"missing annexes: {sorted(missing_ann)}")
    return "GAP: " + "; ".join(parts)


# ── 1. KB ─────────────────────────────────────────────────────────────────
print("\n=== 1. KB (EC_CHECKER_OBLIGATION_MAP) ===")
from app.data.kb import EC_CHECKER_OBLIGATION_MAP
kb_refs = set(EC_CHECKER_OBLIGATION_MAP.keys())
kb_arts, kb_ann = _articles_covered(kb_refs)
print(f"  Articles covered: {len(kb_arts)}/{N_ARTICLES}")
print(f"  Annexes covered:  {len(kb_ann)}/{N_ANNEXES}")
print(f"  VERDICT: {_verdict(kb_arts, kb_ann)}")


# ── 2. BM25 index ─────────────────────────────────────────────────────────
print("\n=== 2. BM25 index (kb_search._build_index) ===")
from app.data.kb_search import _build_index
bm25 = _build_index()
bm25_refs = set(bm25.article_refs)
bm25_arts, bm25_ann = _articles_covered(bm25_refs)
print(f"  Total docs:       {len(bm25.article_refs)}")
print(f"  Distinct refs:    {len(bm25_refs)}")
print(f"  Articles covered: {len(bm25_arts)}/{N_ARTICLES}")
print(f"  Annexes covered:  {len(bm25_ann)}/{N_ANNEXES}")
# Definitions in BM25 are keyed as Art. 3 — count unique definition docs
def_docs = sum(1 for s in bm25.sources if s == "definition")
print(f"  Definition docs:  {def_docs}")
print(f"  VERDICT: {_verdict(bm25_arts, bm25_ann)}")


# ── 3. sentence_index ─────────────────────────────────────────────────────
print("\n=== 3. sentence_index (sentence_index.select_answer_sentence) ===")
from app.data.eu_ai_act_corpus import ARTICLE_FULL_TEXT
from app.engines.sentence_index import split_legal_sentences
sent_arts: set[str] = set()
sent_ann: set[str] = set()
total_sentences = 0
for ref, text in ARTICLE_FULL_TEXT.items():
    if not text:
        continue
    sents = split_legal_sentences(text)
    if sents:
        total_sentences += len(sents)
        if ref.startswith("Art."):
            sent_arts.add(ref)
        elif ref.startswith("Annex"):
            sent_ann.add(ref)
sent_arts &= ARTICLES_IN_CATALOG
sent_ann &= ANNEXES_IN_CATALOG
print(f"  Total sentences:  {total_sentences}")
print(f"  Articles covered: {len(sent_arts)}/{N_ARTICLES}")
print(f"  Annexes covered:  {len(sent_ann)}/{N_ANNEXES}")
print(f"  VERDICT: {_verdict(sent_arts, sent_ann)}")


# ── 4. turboquant_index ───────────────────────────────────────────────────
print("\n=== 4. turboquant_index (dense index over BM25 corpus) ===")
from app.engines.turboquant_index import _DenseIndex

tq_idx = _DenseIndex()
tq_idx._setup()  # triggers _build() which populates _bm25_idx_map

if tq_idx._loaded:
    # _bm25_idx_map contains original BM25 doc indices kept in the dense index
    bm25_kept = set(tq_idx._bm25_idx_map)
    tq_refs = {bm25.article_refs[i] for i in bm25_kept if i < len(bm25.article_refs)}
    tq_arts, tq_ann = _articles_covered(tq_refs)
    print(f"  Dense docs:       {len(bm25_kept)}")
    print(f"  Distinct refs:    {len(tq_refs)}")
    print(f"  Articles covered: {len(tq_arts)}/{N_ARTICLES}")
    print(f"  Annexes covered:  {len(tq_ann)}/{N_ANNEXES}")
    print(f"  VERDICT: {_verdict(tq_arts, tq_ann)}")
else:
    print("  WARN: dense index failed to load — reporting from BM25 corpus (less definitions)")
    non_def_refs = {bm25.article_refs[i] for i, s in enumerate(bm25.sources) if s != "definition"}
    tq_arts, tq_ann = _articles_covered(non_def_refs)
    print(f"  Articles covered (est.): {len(tq_arts)}/{N_ARTICLES}")
    print(f"  Annexes covered (est.):  {len(tq_ann)}/{N_ANNEXES}")
    print(f"  VERDICT (est.): {_verdict(tq_arts, tq_ann)}")


# ── 5. embeddings_index ───────────────────────────────────────────────────
print("\n=== 5. embeddings_index (pre-built sentence assets) ===")
from app.engines.embeddings_index import (
    asset_manifest,
    is_available,
    _ASSETS_DIR,
    EMBED_FILENAME,
    META_FILENAME,
    SVD_FILENAME,
    VOCAB_FILENAME,
    MANIFEST_FILENAME,
)

# 5a. Load manifest
manifest_path = _ASSETS_DIR / MANIFEST_FILENAME
if not manifest_path.exists():
    print("  WARN: manifest file not found — assets missing")
    manifest = {}
else:
    with open(manifest_path) as f:
        manifest = json.load(f)

manifest_hashes = manifest.get("sha256_hashes", {})

# 5b. SHA-256 check per asset file
asset_files = [EMBED_FILENAME, META_FILENAME, SVD_FILENAME, VOCAB_FILENAME]
sha_results: dict[str, str] = {}
for fname in asset_files:
    fpath = _ASSETS_DIR / fname
    if not fpath.exists():
        sha_results[fname] = "MISSING"
        continue
    h = hashlib.sha256()
    with open(fpath, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    computed = h.hexdigest()
    expected = manifest_hashes.get(fname, "NOT_IN_MANIFEST")
    sha_results[fname] = "OK" if computed == expected else f"MISMATCH (computed={computed[:12]}... expected={expected[:12]}...)"

print("  SHA-256 checks:")
for fname, result in sha_results.items():
    print(f"    {fname}: {result}")

# 5c. Load meta.json and count distinct article_ref values
meta_path = _ASSETS_DIR / META_FILENAME
if meta_path.exists():
    with open(meta_path) as f:
        meta_entries = json.load(f)
    embed_refs = {e["article_ref"] for e in meta_entries}
    embed_arts, embed_ann = _articles_covered(embed_refs)
    manifest_sent_count = manifest.get("total_sentences", "?")
    print(f"  Sentences in assets: {len(meta_entries)} (manifest says {manifest_sent_count})")
    print(f"  Distinct article refs: {len(embed_refs)}")
    print(f"  Articles covered: {len(embed_arts)}/{N_ARTICLES}")
    print(f"  Annexes covered:  {len(embed_ann)}/{N_ANNEXES}")
else:
    meta_entries = []
    embed_arts, embed_ann = set(), set()
    print("  WARN: meta file missing")

# 5d. Staleness check — rerun the same splitting logic as build script
MIN_SENT_TOKENS = 3  # from build script
from app.data.kb_search import _tokenize as _kb_tokenize
live_sentences = 0
for ref, text in ARTICLE_FULL_TEXT.items():
    if not text:
        continue
    sentences = split_legal_sentences(text)
    for sent in sentences:
        tokens = _kb_tokenize(sent)
        if len(tokens) >= MIN_SENT_TOKENS:
            live_sentences += 1

manifest_count = manifest.get("total_sentences", None)
stale = manifest_count is not None and live_sentences != manifest_count
print(f"  Live sentence count:     {live_sentences}")
print(f"  Manifest sentence count: {manifest_count}")
print(f"  Staleness: {'STALE — rebuild needed' if stale else 'CURRENT'}")
print(f"  VERDICT: {_verdict(embed_arts, embed_ann)}")


# ── 6. eu_ai_act_tree ─────────────────────────────────────────────────────
print("\n=== 6. eu_ai_act_tree (build_tree) ===")
from app.data.eu_ai_act_tree import build_tree
tree = build_tree()
total_nodes = len(tree)
art_roots = {nid for nid, node in tree.items() if node.kind == "article"}
annex_roots = {nid for nid, node in tree.items() if node.kind == "annex"}
# Map to canonical refs
# article_number on TreeNode is in "Article N" / "Annex N" form
tree_art_refs: set[str] = set()
tree_ann_refs: set[str] = set()
for nid, node in tree.items():
    if node.kind == "article" and node.article_number:
        # convert "Article 6" → "Art. 6"
        m = re.match(r"Article\s+(\d+)$", node.article_number)
        if m:
            tree_art_refs.add(f"Art. {m.group(1)}")
    elif node.kind == "annex" and node.article_number:
        # "Annex III" → "Annex III"
        m = re.match(r"(Annex\s+[IVXLC]+)$", node.article_number, re.IGNORECASE)
        if m:
            tree_ann_refs.add(m.group(1))

tree_arts = tree_art_refs & ARTICLES_IN_CATALOG
tree_ann = tree_ann_refs & ANNEXES_IN_CATALOG
print(f"  Total nodes:      {total_nodes}")
print(f"  Article roots:    {len(art_roots)}")
print(f"  Annex roots:      {len(annex_roots)}")
print(f"  Articles covered: {len(tree_arts)}/{N_ARTICLES}")
print(f"  Annexes covered:  {len(tree_ann)}/{N_ANNEXES}")
print(f"  VERDICT: {_verdict(tree_arts, tree_ann)}")


# ── 7. semantic_layer ─────────────────────────────────────────────────────
print("\n=== 7. semantic_layer (wraps eu_ai_act_tree) ===")
# semantic_layer is a thin wrapper over the tree + cross_reference_context
# coverage == tree coverage; just confirm the import is clean
try:
    from app.engines import semantic_layer as _sl
    print("  Import OK — coverage delegates to eu_ai_act_tree")
    print(f"  Articles covered: {len(tree_arts)}/{N_ARTICLES} (same as tree)")
    print(f"  Annexes covered:  {len(tree_ann)}/{N_ANNEXES} (same as tree)")
    print(f"  VERDICT: {_verdict(tree_arts, tree_ann)}")
except Exception as e:
    print(f"  IMPORT ERROR: {e}")


# ── 8. kb_xrefs ───────────────────────────────────────────────────────────
print("\n=== 8. kb_xrefs (xref graph) ===")
from app.data.kb_xrefs import _build_xref_graph, _build_xref_graph_core

full_graph = _build_xref_graph()
core_graph = _build_xref_graph_core()

def _xref_stats(graph: dict) -> tuple[int, int, int]:
    """Return (nodes, edges, orphan_articles)."""
    nodes = set(graph.keys())
    edges = sum(len(v) for v in graph.values())
    art_nodes = {n for n in nodes if n.startswith("Art.")} & ARTICLES_IN_CATALOG
    orphans = ARTICLES_IN_CATALOG - art_nodes
    return len(nodes), edges, len(orphans)

fn, fe, fo = _xref_stats(full_graph)
cn, ce, co = _xref_stats(core_graph)
print(f"  Full graph:  {fn} source nodes, {fe} edges, {fo} article orphans")
print(f"  Core graph:  {cn} source nodes, {ce} edges, {co} article orphans")

# Detail orphans in full graph
full_art_sources = {n for n in full_graph.keys() if n.startswith("Art.")} & ARTICLES_IN_CATALOG
full_orphans = sorted(int(a.split()[-1]) for a in (ARTICLES_IN_CATALOG - full_art_sources))
if full_orphans:
    print(f"  Full graph orphans (no outgoing edges): {full_orphans}")


# ── 9. ontology ───────────────────────────────────────────────────────────
print("\n=== 9. ontology (typed registries) ===")
from app.data.ontology import (
    PRACTICE_REGISTRY,
    ANNEX_III_REGISTRY,
    PHASE_REGISTRY,
)

practice_art_refs: set[str] = set()
for p in PRACTICE_REGISTRY.values():
    for c in p.citation:
        m = re.match(r"Art\.\s*(\d+)", c)
        if m:
            practice_art_refs.add(f"Art. {m.group(1)}")

annex_iii_refs = {"Annex III"} if ANNEX_III_REGISTRY else set()

phase_art_refs: set[str] = set()
phase_ann_refs: set[str] = set()
for ph in PHASE_REGISTRY.values():
    for a in ph.articles:
        if a.startswith("Art."):
            phase_art_refs.add(a)
        elif a.startswith("Annex"):
            phase_ann_refs.add(a)

all_onto_refs = practice_art_refs | phase_art_refs | annex_iii_refs | phase_ann_refs
onto_arts, onto_ann = _articles_covered(all_onto_refs)

print(f"  PRACTICE_REGISTRY: {len(PRACTICE_REGISTRY)} entries")
print(f"  ANNEX_III_REGISTRY: {len(ANNEX_III_REGISTRY)} categories")
print(f"  PHASE_REGISTRY: {len(PHASE_REGISTRY)} phases")
print(f"  Articles referenced: {len(onto_arts)}/{N_ARTICLES}")
print(f"  Annexes referenced:  {len(onto_ann)}/{N_ANNEXES}")
print(f"  NOTE: ontology covers a focused subset by design (Arts. 5/6/50/51/55/113 + key annexes)")

# Validate ontology_mapping_full - it's an IRI/namespace module, not article coverage
try:
    from app.data.ontology_mapping_full import NAMESPACES
    print(f"  ontology_mapping_full: {len(NAMESPACES)} namespace definitions (IRI mappings, not article coverage)")
except Exception as e:
    print(f"  ontology_mapping_full import error: {e}")


# ── 10. Neo4j seeder (dry-run) ────────────────────────────────────────────
print("\n=== 10. Neo4j seeder (dry-run, no network) ===")
from scripts.seed_neo4j_kb import run_seed, build_payload

payload = build_payload()
result = run_seed(dry_run=True)
print(f"  Status:       {result['status']}")
print(f"  Seed version: {result['seed_version']}")
print(f"  KB version:   {result['kb_version']}")
print(f"  Total nodes:  {result['total_nodes']}")
print(f"  Total edges:  {result['total_edges']}")
counts = result.get("counts", {})
if counts:
    print("  Node/edge counts:")
    for k, v in sorted(counts.items()):
        print(f"    {k}: {v}")


# ── 11. corpus ────────────────────────────────────────────────────────────
print("\n=== 11. Corpus modules ===")

# eu_ai_act_corpus
from app.data.eu_ai_act_corpus import (
    ARTICLE_FULL_TEXT as _AFT,
    ART_3_DEFINITIONS as _ART3,
    RECITALS as _RECITALS,
)
corpus_refs = set(_AFT.keys())
corpus_arts, corpus_ann = _articles_covered(corpus_refs)
print("  eu_ai_act_corpus.py:")
print(f"    ARTICLE_FULL_TEXT: {len(_AFT)} entries")
print(f"    Articles covered: {len(corpus_arts)}/{N_ARTICLES}")
print(f"    Annexes covered:  {len(corpus_ann)}/{N_ANNEXES}")
print(f"    ART_3_DEFINITIONS: {len(_ART3)} definitions")
print(f"    RECITALS: {len(_RECITALS)} recitals")
print(f"    VERDICT: {_verdict(corpus_arts, corpus_ann)}")

# official_eu_ai_act — uses "Article N" (not "Art. N") key format
from app.data.official_eu_ai_act import OFFICIAL_ARTICLE_TEXT as _OAT
off_refs_raw = set(_OAT.keys())
# Normalise "Article N" → "Art. N" for catalog comparison
off_refs_normalised: set[str] = set()
for k in off_refs_raw:
    m = re.match(r"Article\s+(\d+)$", k)
    if m:
        off_refs_normalised.add(f"Art. {m.group(1)}")
    else:
        off_refs_normalised.add(k)  # keep Annex refs as-is
off_arts, off_ann = _articles_covered(off_refs_normalised)
print("  official_eu_ai_act.py:")
print(f"    Key format: 'Article N' (not 'Art. N') — normalised for catalog comparison")
print(f"    OFFICIAL_ARTICLE_TEXT: {len(_OAT)} entries")
print(f"    Articles covered: {len(off_arts)}/{N_ARTICLES}")
print(f"    Annexes covered:  {len(off_ann)}/{N_ANNEXES}")
print(f"    VERDICT: {_verdict(off_arts, off_ann)}")


# ── Summary table ─────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("SUMMARY TABLE")
print("=" * 80)
fmt = "{:<28} {:>15} {:>14} {:>12}"
print(fmt.format("Surface", "Articles (/113)", "Annexes (/13)", "Verdict"))
print("-" * 80)

def _short_verdict(arts, annexes):
    v = _verdict(arts, annexes)
    return v if v == "COMPLETE" else v[:40] + "..." if len(v) > 40 else v

rows = [
    ("KB (obligation map)",          kb_arts,    kb_ann),
    ("BM25 index",                   bm25_arts,  bm25_ann),
    ("sentence_index",               sent_arts,  sent_ann),
    ("turboquant_index",             tq_arts,    tq_ann),
    ("embeddings_index (assets)",    embed_arts, embed_ann),
    ("eu_ai_act_tree",               tree_arts,  tree_ann),
    ("semantic_layer",               tree_arts,  tree_ann),
    ("xrefs full graph",             {n for n in full_graph if n.startswith("Art.")} & ARTICLES_IN_CATALOG,
                                     {n for n in full_graph if n.startswith("Annex")} & ANNEXES_IN_CATALOG),
    ("corpus (eu_ai_act_corpus)",    corpus_arts, corpus_ann),
    ("official_eu_ai_act (normalised)", off_arts,   off_ann),
]
for name, arts, annexes in rows:
    missing_arts = ARTICLES_IN_CATALOG - arts
    missing_ann = ANNEXES_IN_CATALOG - annexes
    if not missing_arts and not missing_ann:
        verdict = "COMPLETE"
    else:
        parts = []
        if missing_arts:
            parts.append(f"art: {len(missing_arts)} missing")
        if missing_ann:
            parts.append(f"ann: {len(missing_ann)} missing")
        verdict = "GAP: " + ", ".join(parts)
    print(fmt.format(name, f"{len(arts)}/{N_ARTICLES}", f"{len(annexes)}/{N_ANNEXES}", verdict))

print("\n--- Embeddings asset SHA check ---")
for fname, result_str in sha_results.items():
    print(f"  {fname}: {result_str}")
print(f"\n--- Embeddings staleness: live={live_sentences} vs manifest={manifest_count} -> {'STALE' if stale else 'CURRENT'} ---")
print(f"\n--- xref full graph: {fo} article orphans (zero outgoing edges) ---")
if full_orphans:
    print(f"    Orphan article numbers: {full_orphans}")
