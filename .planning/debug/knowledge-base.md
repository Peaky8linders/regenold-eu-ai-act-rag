# GSD Debug Knowledge Base

Resolved debug sessions. Used by `gsd-debugger` to surface known-pattern hypotheses at the start of new investigations.

---

## gpai-rag-retrieval-gap — GPAI queries return high-risk boilerplate instead of GPAI-specific obligations
- **Date:** 2026-05-11
- **Error patterns:** GPAI, general-purpose AI, retrieval_path=kb_fallback, obligations_found=0, confidence=0.50, wrong answer text, references correct, deterministic parse, EC_CHECKER_OBLIGATION_MAP, entities empty
- **Root cause:** `_deterministic_parse` in `app/engines/graph_rag.py` only extracted entities via `Art. N` / `Annex N` regex. Concept-based queries (e.g. "What is a GPAI model?") produced `entities=[]`, so `_retrieve_from_kb` skipped `EC_CHECKER_OBLIGATION_MAP` entirely and fell back to all four generic `MATURITY_DIMENSIONS`, emitting high-risk boilerplate. `references` was already correct via `scope.anchor_articles`; only the answer body was wrong.
- **Fix:** Added `_KEYWORD_ENTITY_MAP` step after regex extraction in `_deterministic_parse`. Maps concept keywords (gpai, systemic risk, deepfake, fria, conformity assessment, etc.) to their primary `Art. N` entities, mirroring the `KEYWORD_TO_ARTICLE` mapping already used by `scope.py`.
- **Files changed:** app/engines/graph_rag.py
---
