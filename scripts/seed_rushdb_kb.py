"""RushDB KB seeder for the Regenold EU AI Act RAG bundle.

Pushes the bundle's deterministic KB surface into RushDB.
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any

from app.data.article_existence import ARTICLE_EXISTENCE
from app.data.definitions import _DEFINITIONS
from app.data.eu_ai_act_corpus import ARTICLE_FULL_TEXT, ARTICLE_TITLE, RECITALS
from app.data.kb import EC_CHECKER_OBLIGATION_MAP, KB_VERSION
from app.data.kb_xrefs import MANUAL_XREFS, _build_xref_graph
from app.data.ontology import ANNEX_III_REGISTRY
from app.data.role_obligations import ROLE_OBLIGATIONS
from app.integrations.regenold.refs import to_user_facing as _ref_to_user_facing

from app.data.eu_ai_act_tree import _split_paragraphs_article, _split_annex_items

logger = logging.getLogger(__name__)

SEED_VERSION = "2026-05-25-rushdb-v1"

RISK_LEVELS: tuple[dict[str, str], ...] = (
    {
        "id": "risk_prohibited",
        "label": "prohibited",
        "description": "Art. 5 prohibited AI practices.",
    },
    {
        "id": "risk_high",
        "label": "high-risk",
        "description": "Annex I safety-component + Annex III use-case high-risk systems per Art. 6.",
    },
    {
        "id": "risk_limited",
        "label": "limited",
        "description": "Transparency-only obligations under Art. 50.",
    },
    {
        "id": "risk_minimal",
        "label": "minimal",
        "description": "Out-of-scope systems carrying voluntary code-of-conduct obligations only.",
    },
)

_ART_NUMBER_RE = re.compile(r"^Art\.\s*(\d{1,3})$")
_ANNEX_NUMBER_RE = re.compile(r"^Annex\s+([IVXLC]+)$", re.IGNORECASE)

def _slug_term(term: str) -> str:
    s = term.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s or "anon"

def _article_id(ref: str) -> str:
    m = _ART_NUMBER_RE.match(ref)
    if m:
        return f"article_{m.group(1)}"
    m = _ANNEX_NUMBER_RE.match(ref)
    if m:
        return f"annex_{m.group(1).upper()}"
    return ref.replace(" ", "_").replace(".", "")

def _article_number(ref: str) -> str:
    m = _ART_NUMBER_RE.match(ref)
    if m:
        return m.group(1)
    m = _ANNEX_NUMBER_RE.match(ref)
    if m:
        return m.group(1).upper()
    return ref

def _is_annex(ref: str) -> bool:
    return bool(_ANNEX_NUMBER_RE.match(ref))

def _short_title(ref: str) -> str:
    title = ARTICLE_TITLE.get(ref)
    if title:
        return title.replace("\xa0", " ").strip()
    body = ARTICLE_FULL_TEXT.get(ref, "")
    if body:
        first = re.split(r"(?<=[.!?])\s", body, maxsplit=1)[0]
        return first.replace("\xa0", " ").strip()[:200]
    return ref

def _classify_risk_for_article(num: str) -> str | None:
    try:
        n = int(num)
    except (TypeError, ValueError):
        return None
    if n == 5: return "risk_prohibited"
    if n == 4: return "risk_minimal"
    if n == 50: return "risk_limited"
    if 6 <= n <= 49: return "risk_high"
    return None

def build_payload() -> dict[str, list[dict]]:
    """Build the full seed payload from the in-process KB modules."""
    payload: dict[str, list[dict]] = {
        "ARTICLE": [],
        "ANNEX": [],
        "RECITAL": [],
        "DEFINITION": [],
        "OBLIGATION": [],
        "ANNEX_III_CATEGORY": [],
        "RISK_LEVEL": [],
        "OPERATOR_ROLE": [],
    }

    xref_graph = _build_xref_graph()
    
    # Recital anchors
    recital_re = re.compile(r"\bRecital\s+(\d{1,3})\b", re.IGNORECASE)
    recital_anchors: dict[int, list[str]] = {}
    for ref, entry in EC_CHECKER_OBLIGATION_MAP.items():
        if ref not in ARTICLE_EXISTENCE: continue
        summary = entry.get("summary", "")
        if not summary: continue
        for match in recital_re.finditer(summary):
            n = int(match.group(1))
            if n not in RECITALS: continue
            art_id = _article_id(ref)
            if n not in recital_anchors:
                recital_anchors[n] = []
            if art_id not in recital_anchors[n]:
                recital_anchors[n].append(art_id)

    # Articles
    for ref in sorted((r for r in ARTICLE_EXISTENCE if r.startswith("Art. ")), key=lambda r: int(_article_number(r))):
        num = _article_number(ref)
        art_id = _article_id(ref)
        
        cross_refs = list({_article_id(t) for t in xref_graph.get(ref, []) if t in ARTICLE_EXISTENCE and t != ref})
        
        body = ARTICLE_FULL_TEXT.get(ref, "")
        chunks = []
        blocks = _split_paragraphs_article(body)
        for i, (p_num, p_text) in enumerate(blocks, start=1):
            if not p_text.strip(): continue
            chunk_id = f"{art_id}_p_{p_num}" if p_num is not None else f"{art_id}_p_solo"
            chunks.append({
                "chunkId": chunk_id,
                "chunkIndex": i,
                "heading": f"Paragraph {p_num}" if p_num is not None else None,
                "text": p_text,
                "article": num,
            })
            
        payload["ARTICLE"].append({
            "id": art_id,
            "number": num,
            "title": _short_title(ref),
            "text": body[:2000], # Legacy description length to match Neo4j
            "cross_refs": cross_refs,
            "kb_version": KB_VERSION,
            "legal_type": "Article",
            "strict_citation": _ref_to_user_facing(f"Art. {num}"),
            "CHUNK": chunks,
        })

    # Annexes
    for ref in sorted(r for r in ARTICLE_EXISTENCE if r.startswith("Annex ")):
        roman = _article_number(ref)
        art_id = _article_id(ref)
        
        cross_refs = list({_article_id(t) for t in xref_graph.get(ref, []) if t in ARTICLE_EXISTENCE and t != ref})
        
        body = ARTICLE_FULL_TEXT.get(ref, "")
        chunks = []
        blocks = _split_annex_items(body)
        for i, (item_num, item_text) in enumerate(blocks, start=1):
            if not item_text.strip(): continue
            chunk_id = f"{art_id}_p_{item_num}" if item_num is not None else f"{art_id}_p_preamble"
            chunks.append({
                "chunkId": chunk_id,
                "chunkIndex": i,
                "heading": f"Item {item_num}" if item_num is not None else "Preamble",
                "text": item_text,
                "article": roman,
            })
            
        payload["ANNEX"].append({
            "id": art_id,
            "number": roman,
            "title": _short_title(ref),
            "text": body[:2000],
            "cross_refs": cross_refs,
            "kb_version": KB_VERSION,
            "legal_type": "Annex",
            "strict_citation": _ref_to_user_facing(f"Annex {roman}"),
            "CHUNK": chunks,
        })

    # Recitals
    for n in sorted(RECITALS.keys()):
        text = RECITALS[n].replace("\xa0", " ").strip()
        payload["RECITAL"].append({
            "id": f"recital_{n}",
            "recital_number": str(n),
            "text": text[:3000],
            "article_anchor": recital_anchors.get(n, []),
        })

    # Definitions
    for defn in _DEFINITIONS:
        slug = _slug_term(defn.term)
        payload["DEFINITION"].append({
            "id": f"def_{slug}",
            "term": defn.term,
            "term_slug": slug,
            "text": defn.description,
            "article_number": "3",
        })

    # Obligations
    for ref, entry in EC_CHECKER_OBLIGATION_MAP.items():
        if _is_annex(ref) or ref not in ARTICLE_EXISTENCE: continue
        num = _article_number(ref)
        risk_id = _classify_risk_for_article(num)
        payload["OBLIGATION"].append({
            "id": f"obl_{num}",
            "article_ref": num,
            "text": entry.get("summary", "")[:3000],
            "mandatory": True,
            "risk_levels": [risk_id] if risk_id else [],
            "dimension": entry.get("dimension", ""),
        })

    # Annex III
    for cat_id, cat in ANNEX_III_REGISTRY.items():
        payload["ANNEX_III_CATEGORY"].append({
            "id": f"annex_iii_{cat_id}",
            "label": cat.short_name,
            "number": cat.number,
            "description": cat.description[:2000],
            "article_ref": "6",
        })

    # Risk Levels
    for row in RISK_LEVELS:
        payload["RISK_LEVEL"].append(dict(row))

    # Operator Roles
    canonical = {"provider", "deployer", "importer", "distributor", "authorized_representative"}
    for row in ROLE_OBLIGATIONS:
        if row.get("id") not in canonical: continue
        payload["OPERATOR_ROLE"].append({
            "id": f"role_{row['id']}",
            "label": row.get("label", row["id"]),
            "art_3_definition": row.get("art_3_definition", ""),
            "summary": row.get("summary", "")[:1500],
            "primary_article": "",
        })

    return payload

def run_seed(dry_run: bool = False) -> dict:
    """Returns {"status": "ok"|"skip"|"dry_run", "counts": {...}}."""
    try:
        import rushdb
    except ImportError:
        return {"status": "error", "error": "rushdb package not installed"}
        
    auth_token = os.environ.get("RUSHDB_AUTH_TOKEN")
    if not auth_token:
        return {"status": "error", "error": "RUSHDB_AUTH_TOKEN not set"}

    try:
        db = rushdb.RushDB(auth_token, url="https://api.rushdb.com/api/v1")
    except Exception as exc:
        return {"status": "error", "error": str(exc)}

    # Check KB_METADATA idempotency
    try:
        meta_records = db.records.find({"labels": ["KB_METADATA"], "limit": 1})
        if meta_records and hasattr(meta_records, "data") and meta_records.data:
            meta = meta_records.data[0]
            if getattr(meta, "seed_version", None) == SEED_VERSION and getattr(meta, "kb_version", None) == KB_VERSION:
                return {"status": "skip"}
    except Exception as exc:
        logger.warning(f"RushDB metadata check failed: {exc}")

    payload = build_payload()
    counts = {}
    total_nodes = 0
    total_edges = 0

    if dry_run:
        for label, rows in payload.items():
            counts[label] = len(rows)
            total_nodes += len(rows)
            for row in rows:
                if "cross_refs" in row: total_edges += len(row["cross_refs"])
                if "CHUNK" in row: total_nodes += len(row["CHUNK"])
        return {"status": "dry_run", "counts": counts, "total_nodes": total_nodes, "total_edges": total_edges}

    # Push all 9 record types via db.records.create_many()
    for label, rows in payload.items():
        if not rows: continue
        try:
            # We must use set instead of create_many to upsert by id?
            # RushDB create_many is not idempotent automatically unless specified.
            # "Re-seed uses db.records.set() (upsert semantics)"
            for row in rows:
                db.records.set(
                    id=row["id"],
                    label=label,
                    data=row
                )
            counts[label] = len(rows)
            total_nodes += len(rows)
            # Count relations implicitly for stats
            for row in rows:
                if "cross_refs" in row: total_edges += len(row["cross_refs"])
                if "CHUNK" in row: total_nodes += len(row["CHUNK"])
            logger.info(f"Seeded RushDB label={label} count={len(rows)}")
        except Exception as exc:
            logger.error(f"RushDB error seeding label={label}: {exc}")
            return {"status": "error", "error": str(exc)}

    # Write KB_METADATA
    try:
        db.records.set(
            id="kb_metadata",
            label="KB_METADATA",
            data={
                "seed_version": SEED_VERSION,
                "kb_version": KB_VERSION,
                "seeded_at": datetime.now(timezone.utc).isoformat(),
                "total_nodes": total_nodes,
                "total_edges": total_edges,
            }
        )
    except Exception as exc:
        logger.error(f"RushDB error writing KB_METADATA: {exc}")
        return {"status": "error", "error": str(exc)}

    return {"status": "ok", "counts": counts}

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="seed_rushdb_kb")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)
    
    result = run_seed(dry_run=args.dry_run)
    print("Result:", result)
    return 0 if result.get("status") in ("ok", "skip", "dry_run") else 1

if __name__ == "__main__":
    raise SystemExit(main())
