# Hybrid RAG Tuning for EU AI Act Q&A with RushDB

Implementation pattern: import `DOC -> CHUNK`, index both levels, run semantic and metadata retrieval in parallel, fuse by intent, then build a source-aware prompt.

## 1. Import `DOC -> CHUNK`

```python
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from rushdb import RushDB


db = RushDB(
    api_key=os.environ["RUSHDB_API_KEY"],
    base_url="https://api.rushdb.com/api/v1",
)


docs = [
    {
        "docId": "eu-ai-act-article-12",
        "title": "Article 12 - Record-keeping",
        "sourceType": "regulation",
        "jurisdiction": "EU",
        "framework": "EU_AI_ACT",
        "article": "12",
        "topic": "record-keeping",
        "appliesTo": ["provider"],
        "riskTier": "high-risk",
        "version": "2024-06-13",
        "sourceUrl": "https://ai-act-service-desk.ec.europa.eu/",
        "authority": "official",
        "content": "High-risk AI systems require logging capabilities that support traceability.",
        "CHUNK": [
            {
                "chunkId": "art12-logging",
                "chunkIndex": 1,
                "heading": "Logging",
                "text": "High-risk AI systems must technically allow automatic recording of events.",
                "article": "12",
                "controlIds": ["LOG-001"],
                "evidenceTypes": ["system_logs", "event_timestamps"],
                "keywords": ["logging", "record-keeping", "traceability"],
            }
        ],
    },
    {
        "docId": "eu-ai-act-article-14",
        "title": "Article 14 - Human oversight",
        "sourceType": "regulation",
        "jurisdiction": "EU",
        "framework": "EU_AI_ACT",
        "article": "14",
        "topic": "human oversight",
        "appliesTo": ["provider", "deployer"],
        "riskTier": "high-risk",
        "version": "2024-06-13",
        "sourceUrl": "https://ai-act-service-desk.ec.europa.eu/",
        "authority": "official",
        "content": "High-risk AI systems should support effective human oversight.",
        "CHUNK": [
            {
                "chunkId": "art14-review",
                "chunkIndex": 1,
                "heading": "Human review",
                "text": "Human oversight should reduce risks to health, safety, or fundamental rights.",
                "article": "14",
                "controlIds": ["HITL-001"],
                "evidenceTypes": ["review_queue", "override_logs"],
                "keywords": ["human oversight", "human review"],
            }
        ],
    },
    {
        "docId": "internal-control-map-v3",
        "title": "Internal Control Map v3",
        "sourceType": "internal_control",
        "jurisdiction": "EU",
        "framework": "EU_AI_ACT",
        "version": "3.0",
        "sourceUrl": "https://example.com/internal/control-map-v3",
        "authority": "internal",
        "content": "LOG-001 logs retrieval context. HITL-001 routes high-impact answers to review.",
        "CHUNK": [
            {
                "chunkId": "control-log-001",
                "chunkIndex": 1,
                "heading": "LOG-001",
                "text": "LOG-001 stores request ID, user role, source IDs, model version, and timestamp.",
                "controlIds": ["LOG-001"],
                "evidenceTypes": ["rag_query_log", "answer_log"],
                "keywords": ["request ID", "source IDs", "model version"],
            },
            {
                "chunkId": "control-hitl-001",
                "chunkIndex": 2,
                "heading": "HITL-001",
                "text": "HITL-001 routes high-impact outputs to a qualified reviewer.",
                "controlIds": ["HITL-001"],
                "evidenceTypes": ["review_queue", "reviewer_approval"],
                "keywords": ["human review", "approval"],
            },
        ],
    },
]

db.records.create_many(
    label="DOC",
    data=docs,
    options={"returnResult": False},
)
```

Keep exact identifiers as metadata: `article`, `appliesTo`, `riskTier`, `sourceType`, `version`, `controlIds`, and `evidenceTypes`.

## 2. Index both levels

```python
db.ai.indexes.create({
    "label": "DOC",
    "propertyName": "content",
})

db.ai.indexes.create({
    "label": "CHUNK",
    "propertyName": "text",
})
```

Use `DOC.content` for broad recall and `CHUNK.text` for precise passages.

## 3. Classify query intent

```python
def classify_query(query: str) -> dict:
    q = query.lower()

    if any(term in q for term in ["article", "annex", "obligation", "provider", "deployer"]):
        return {"intent": "regulatory_lookup", "sourceTypes": ["regulation"]}

    if any(term in q for term in ["evidence", "prove", "audit", "log", "record"]):
        return {"intent": "evidence_lookup", "sourceTypes": ["regulation", "internal_control"]}

    if any(term in q for term in ["control", "mitigation", "implementation", "how do we"]):
        return {"intent": "control_mapping", "sourceTypes": ["regulation", "internal_control"]}

    return {"intent": "general", "sourceTypes": ["regulation", "internal_control"]}
```

Use intent for weights and default filters, not as the only retrieval path.

## 4. Build filters

```python
def build_doc_where(filters: dict) -> dict:
    where = {
        "framework": filters.get("framework", "EU_AI_ACT"),
        "jurisdiction": filters.get("jurisdiction", "EU"),
    }

    if filters.get("sourceTypes"):
        where["sourceType"] = {"$in": filters["sourceTypes"]}
    if filters.get("appliesTo"):
        where["appliesTo"] = {"$in": [filters["appliesTo"]]}
    if filters.get("riskTier"):
        where["riskTier"] = filters["riskTier"]
    if filters.get("article"):
        where["article"] = filters["article"]
    if filters.get("version"):
        where["version"] = filters["version"]

    return where


def build_chunk_where(filters: dict) -> dict:
    where = {"DOC": build_doc_where(filters)}

    if filters.get("controlId"):
        where["controlIds"] = {"$in": [filters["controlId"]]}
    if filters.get("evidenceType"):
        where["evidenceTypes"] = {"$in": [filters["evidenceType"]]}
    if filters.get("article"):
        where["article"] = filters["article"]

    return where
```

## 5. Search in parallel

```python
def semantic_docs(query: str, where: dict, limit: int):
    return db.ai.search({
        "labels": ["DOC"],
        "propertyName": "content",
        "query": query,
        "where": where,
        "limit": limit,
    }).data


def semantic_chunks(query: str, where: dict, limit: int):
    return db.ai.search({
        "labels": ["CHUNK"],
        "propertyName": "text",
        "query": query,
        "where": where,
        "limit": limit,
    }).data


def metadata_search(query: str, doc_where: dict, limit: int):
    where = {
        "$and": [
            doc_where,
            {
                "$or": [
                    {"title": {"$contains": query}},
                    {"article": {"$contains": query}},
                    {"appliesTo": {"$in": [query]}},
                    {
                        "CHUNK": {
                            "$or": [
                                {"heading": {"$contains": query}},
                                {"controlIds": {"$in": [query.upper()]}},
                                {"evidenceTypes": {"$in": [query]}},
                                {"keywords": {"$in": [query]}},
                            ]
                        }
                    },
                ]
            },
        ]
    }

    return db.records.find({
        "labels": ["DOC"],
        "where": where,
        "orderBy": {"version": "desc"},
        "limit": limit,
    }).data


def retrieve(query: str, filters: dict | None = None, limit: int = 8) -> list[dict]:
    filters = filters or {}
    intent = classify_query(query)
    filters.setdefault("sourceTypes", intent["sourceTypes"])

    doc_where = build_doc_where(filters)
    chunk_where = build_chunk_where(filters)

    with ThreadPoolExecutor(max_workers=3) as pool:
        doc_future = pool.submit(semantic_docs, query, doc_where, limit)
        chunk_future = pool.submit(semantic_chunks, query, chunk_where, limit)
        metadata_future = pool.submit(metadata_search, query, doc_where, limit)

        doc_hits = doc_future.result()
        chunk_hits = chunk_future.result()
        metadata_hits = metadata_future.result()

    return fuse_results(doc_hits, chunk_hits, metadata_hits, intent["intent"], limit)
```

Metadata search should run alongside semantic search, not after it.

## 6. Enrich chunk hits

```python
def parent_doc_for_chunk(chunk_id: str):
    result = db.records.find({
        "labels": ["DOC"],
        "where": {"CHUNK": {"__id": chunk_id}},
        "limit": 1,
    })
    return result.data[0] if result.data else None
```

## 7. Fuse results

```python
SOURCE_BOOST = {
    "regulation": 0.20,
    "internal_control": 0.12,
}

INTENT_WEIGHTS = {
    "regulatory_lookup": {"doc": 0.70, "chunk": 0.80, "metadata": 0.55},
    "evidence_lookup": {"doc": 0.45, "chunk": 0.70, "metadata": 0.75},
    "control_mapping": {"doc": 0.55, "chunk": 0.75, "metadata": 0.65},
    "general": {"doc": 0.60, "chunk": 0.75, "metadata": 0.55},
}


def record_id(record) -> str:
    return record.id


def add_hit(merged: dict, key: str, record, score: float, reason: str, kind: str) -> None:
    if key not in merged:
        merged[key] = {"record": record, "score": 0.0, "reasons": [], "kind": kind}

    merged[key]["score"] += score
    merged[key]["reasons"].append(reason)


def fuse_results(doc_hits, chunk_hits, metadata_hits, intent: str, limit: int) -> list[dict]:
    merged = {}
    weights = INTENT_WEIGHTS[intent]

    for rank, doc in enumerate(doc_hits):
        score = float(doc.get("__score") or 0)
        boost = SOURCE_BOOST.get(doc.get("sourceType"), 0)
        add_hit(
            merged,
            f"doc:{record_id(doc)}",
            doc,
            weights["doc"] * score + 0.10 / (rank + 1) + boost,
            "document semantic",
            "doc",
        )

    for rank, chunk in enumerate(chunk_hits):
        score = float(chunk.get("__score") or 0)
        add_hit(
            merged,
            f"chunk:{record_id(chunk)}",
            chunk,
            weights["chunk"] * score + 0.15 / (rank + 1),
            "chunk semantic",
            "chunk",
        )

    for rank, doc in enumerate(metadata_hits):
        boost = SOURCE_BOOST.get(doc.get("sourceType"), 0)
        add_hit(
            merged,
            f"doc:{record_id(doc)}",
            doc,
            weights["metadata"] + 0.10 / (rank + 1) + boost,
            "metadata",
            "doc",
        )

    ranked = sorted(merged.values(), key=lambda item: item["score"], reverse=True)
    return [to_context_item(item) for item in ranked[:limit]]
```

```python
def to_context_item(item: dict) -> dict:
    record = item["record"]

    if item["kind"] == "doc":
        return {
            "id": record_id(record),
            "kind": "doc",
            "score": round(item["score"], 4),
            "reasons": item["reasons"],
            "title": record.get("title"),
            "sourceType": record.get("sourceType"),
            "version": record.get("version"),
            "authority": record.get("authority"),
            "sourceUrl": record.get("sourceUrl"),
            "article": record.get("article"),
            "text": record.get("content"),
        }

    parent = parent_doc_for_chunk(record_id(record))

    return {
        "id": record_id(record),
        "kind": "chunk",
        "score": round(item["score"], 4),
        "reasons": item["reasons"],
        "title": parent.get("title") if parent else None,
        "sourceType": parent.get("sourceType") if parent else None,
        "version": parent.get("version") if parent else None,
        "authority": parent.get("authority") if parent else None,
        "sourceUrl": parent.get("sourceUrl") if parent else None,
        "article": record.get("article"),
        "section": record.get("heading"),
        "controlIds": record.get("controlIds"),
        "evidenceTypes": record.get("evidenceTypes"),
        "text": record.get("text"),
    }
```

## 8. Build prompt context

```python
def build_context(results: list[dict]) -> str:
    blocks = []

    for index, item in enumerate(results, start=1):
        section = f" / {item['section']}" if item.get("section") else ""
        blocks.append(
            "\n".join([
                f"[{index}] {item.get('title')}{section}",
                f"Source type: {item.get('sourceType')}",
                f"Version: {item.get('version')}",
                f"Authority: {item.get('authority')}",
                f"URL: {item.get('sourceUrl')}",
                f"Article: {item.get('article')}",
                f"Controls: {item.get('controlIds')}",
                f"Evidence: {item.get('evidenceTypes')}",
                f"Match: {', '.join(item['reasons'])} | Score: {item['score']}",
                item["text"],
            ])
        )

    return "\n\n---\n\n".join(blocks)


query = "What evidence do we need to show record-keeping for a high-risk provider system?"

results = retrieve(
    query=query,
    filters={
        "framework": "EU_AI_ACT",
        "jurisdiction": "EU",
        "appliesTo": "provider",
        "riskTier": "high-risk",
    },
)

prompt = f"""Answer using only the context.
Separate official requirements from internal controls.
Cite source numbers, article numbers, control IDs, and evidence types.
Say what is missing when context is incomplete.

Context:
{build_context(results)}

Question:
{query}
"""
```

## 9. Log retrieval

```python
def log_rag_query(query: str, filters: dict, results: list[dict], model: str) -> None:
    db.records.create(
        label="RAG_QUERY_LOG",
        data={
            "query": query,
            "filters": filters,
            "retrievedRecordIds": [item["id"] for item in results],
            "retrievedSources": [
                {
                    "title": item.get("title"),
                    "sourceType": item.get("sourceType"),
                    "version": item.get("version"),
                    "url": item.get("sourceUrl"),
                }
                for item in results
            ],
            "retrievalStrategy": "doc_semantic+chunk_semantic+metadata",
            "indexes": ["DOC.content", "CHUNK.text"],
            "model": model,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        },
    )
```

## Tuning notes

- Use document search for broad recall and chunk search for precise grounding.
- Keep exact identifiers in metadata, not only in text.
- Run metadata search in parallel with semantic search.
- Boost `regulation` for requirement questions and `internal_control` for implementation questions.
- Keep source type, version, authority, article, controls, and evidence in the prompt context.
- Deduplicate aggressively when many chunks come from the same article.
- Return insufficient context when the answer lacks required role, article, control, version, or evidence fields.
