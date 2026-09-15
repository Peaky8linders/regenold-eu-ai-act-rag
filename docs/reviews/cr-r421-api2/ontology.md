## INCONSISTENT CITATION FORMAT IN EMOTION RECOGNITION GUARD
- file: `app/engines/_graph_rag_impl.py:3682`
- current code: `#: R418 â€” emotion-recognition SUBJECT guard. Article 5(1)(f) reaches inferring`
- bug: The comment uses `Article 5(1)(f)` while the ontology uses `Art. 5.1.f` as the canonical form
- evidence: `app/data/ontology.py:PRACTICE_REGISTRY["emotion_recognition_workplace"].sub_paragraph="5.1.f"` and `app/data/ids.py:_CIT_ARTICLE_RE = re.compile(r"^Art\.\s+(\d+)\s*((?:\([^)]+\))*)$")`
- impact: This creates identifier drift between the guard logic and the ontology, potentially causing mismatches in provision resolution
- fix: Change the comment to use `Art. 5.1.f` to match the ontology's canonical form
- confidence: 95

## NEEDS MORE EVIDENCE
- The evidence pack does not contain the full `app/data/article_existence.py` file which would show the complete set of valid article references and could confirm if there are other citation format inconsistencies.

## CHECKS PERFORMED
- Claim: The `_STAGE2_LEG2_SERVED` ContextVar might not be properly reset in all code paths. Refuted by: `_claude_max_enhance_answer` at line 9644 explicitly resets it to False at the start of each call.
- Claim: The `_prior_answer_floor` function might return an answer that is itself truncated. Refuted by: lines 11223-11225 explicitly check `_looks_incomplete_final_sentence(prior)` before returning the prior answer.
- Claim: The `_EMOTION_NON_WORKER_SUBJECT_RE` regex might incorrectly match worker terms in prohibited contexts. Refuted by: the implementation at lines 3790-3805 correctly uses a window around the pattern hit to distinguish subject from operator.
