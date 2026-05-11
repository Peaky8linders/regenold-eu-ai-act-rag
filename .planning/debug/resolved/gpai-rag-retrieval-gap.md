---
status: resolved
trigger: "GPAI queries return wrong answer content despite correct article reference"
created: 2026-05-11T00:00:00Z
updated: 2026-05-11T00:10:00Z
---

## Current Focus

hypothesis: CONFIRMED — _deterministic_parse does not recognize GPAI keywords, so query.entities stays empty, _retrieve_from_kb skips EC_CHECKER_OBLIGATION_MAP lookup, dumps all 4 generic high-risk dimensions instead
test: traced full execution path
expecting: fix: add GPAI/systemic-risk keyword detection in _deterministic_parse to populate entities=["Art. 53"] (and/or "Art. 55")
next_action: apply fix to app/engines/graph_rag.py _deterministic_parse

## Symptoms

expected: Answer covers GPAI-specific obligations (Articles 51-55), e.g. what makes a model "GPAI", systemic risk thresholds, provider obligations under Art. 53.
actual: Answer body lists high-risk AI system articles (Art. 9 risk management, Art. 10 data governance, Art. 11 technical documentation). The `references` field correctly returns "Article 53" but the answer text is wrong.
errors: No error. HTTP 200 with retrieval_path=kb_fallback, obligations_found=0, confidence=0.50
reproduction: POST /api/v1/regenold/eu-ai-act/ask with {"messages":[{"role":"user","content":"What is a GPAI model under the EU AI Act?"}]} and valid X-Regenold-Api-Key header
started: Observed during production QA. Unknown if it ever worked correctly.

## Eliminated

- hypothesis: GPAI articles missing from EC_CHECKER_OBLIGATION_MAP (kb.py)
  evidence: kb.py has Art. 53 and Art. 55 entries with correct GPAI summaries
  timestamp: 2026-05-11T00:01:00Z

- hypothesis: scope filter incorrectly rejecting GPAI queries
  evidence: scope.py _AI_ACT_ANCHORS includes "GPAI", "general-purpose ai", etc. The question passes in_scope=True. derive_anchor_articles_from_keywords correctly maps "gpai" -> "Art. 53" as anchor
  timestamp: 2026-05-11T00:01:00Z

- hypothesis: references field is wrong
  evidence: references=["Article 53"] is CORRECT. _surface_anchor_citations adds Art.53 from scope.anchor_articles. The problem is answer TEXT, not references.
  timestamp: 2026-05-11T00:01:00Z

## Evidence

- timestamp: 2026-05-11T00:01:00Z
  checked: app/data/kb.py EC_CHECKER_OBLIGATION_MAP
  found: Art. 53 entry present with GPAI summary ("GPAI provider obligations: maintain technical documentation per Annex XI..."), Art. 55 also present
  implication: KB has the right data; the problem is upstream in retrieval

- timestamp: 2026-05-11T00:01:00Z
  checked: app/engines/graph_rag.py _deterministic_parse
  found: no GPAI/general-purpose/systemic risk keywords in entity extraction. entity extraction only looks for Art.N patterns and Annex N patterns via regex. "GPAI" in question text produces entities=[] because no "Art." or "Article" token is present.
  implication: _retrieve_from_kb is called with empty entities list, skips EC_CHECKER_OBLIGATION_MAP entirely

- timestamp: 2026-05-11T00:01:00Z
  checked: app/engines/graph_rag.py _retrieve_from_kb
  found: the EC_CHECKER_OBLIGATION_MAP lookup loop is `for entity in query.entities`. If entities=[], loop never runs, context.obligations stays empty
  implication: all four generic MATURITY_DIMENSIONS get added to dimension_info, then _deterministic_answer emits the "4 compliance dimensions in scope" boilerplate listing Art.9/10/11/13

- timestamp: 2026-05-11T00:01:00Z
  checked: app/engines/graph_rag.py ask_compliance_question (line 1098)
  found: ALWAYS calls _deterministic_parse. The LLM-based _llm_parse_query is NEVER called from the main entry point. The deterministic parser is the only path.
  implication: fixing _deterministic_parse is the right and only approach; no LLM-path to rely on

- timestamp: 2026-05-11T00:01:00Z
  checked: app/integrations/regenold/scope.py KEYWORD_TO_ARTICLE
  found: scope.py maps "gpai" -> "Art. 53", "systemic risk" -> "Art. 55" in derive_anchor_articles_from_keywords. These anchor articles come back as scope.anchor_articles and get surfaced as references by _surface_anchor_citations. That is why references=["Article 53"] is correct even though the answer text is wrong.
  implication: the fix must be in _deterministic_parse to mirror the same keyword->entity mapping that scope.py already uses for anchor derivation

## Resolution

root_cause: _deterministic_parse in app/engines/graph_rag.py only extracts entities from explicit "Art. N" / "Annex N" regex matches. A query like "What is a GPAI model?" has no such token, so entities=[] and _retrieve_from_kb skips the EC_CHECKER_OBLIGATION_MAP lookup entirely, returning all 4 generic MATURITY_DIMENSIONS. The correct GPAI obligations in EC_CHECKER_OBLIGATION_MAP (Art. 53, Art. 55) are never retrieved, causing the deterministic answer to emit high-risk boilerplate instead of GPAI content.
fix: added _KEYWORD_ENTITY_MAP step in _deterministic_parse (after regex entity extraction, before building GraphQuery). Maps concept keywords (gpai, systemic risk, deepfake, fria, etc.) to their primary Art. N entities. These then trigger EC_CHECKER_OBLIGATION_MAP lookups in _retrieve_from_kb, producing topically correct obligation rows and answer text.
verification: py -3 test confirmed: "What is a GPAI model under the EU AI Act?" produces entities=["Art. 53"], obligations=[GPAI text], answer covers GPAI provider obligations. "What does Art. 9 require?" still extracts only Art. 9 (no pollution). 233 existing tests pass.
files_changed: [app/engines/graph_rag.py]
