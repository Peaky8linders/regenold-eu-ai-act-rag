# R453 — Case D (robotic surgery) and Q74 (artistic deep fake), fixed at the source

Both were the two partial cards of the 29 September showcase re-run (easy mode, production
`5ae80fce`, Sonnet 5.5 judge): Q74 1/2, Case D 3/4.

## Case D — the curated answer stated the law wrongly and its citations were cut

| defect | fix |
| :--- | :--- |
| the answer said the notified-body assessment was required "under Article 43"; it is required by the MDR, which is what Article 6(1)(b) keys on | rewritten against the verbatim text of Articles 6(1), 43(3), 14(4) and 72(4) |
| Article 43(3) (the AI Act requirements are assessed inside the MDR procedure by the MDR notified body) was never explained, which is the failed criterion | stated |
| R311 route exclusivity dropped the answer's own `Article 43.3` on a purely classificatory Annex I ask; curated answers skip Stage-2, so nothing restored it | `REGENOLD_CURATED_ROUTE_KEEP`: R311 never drops a curated answer's declared head |
| the grain deepener picked `Annex I.19` (vehicle type-approval) because its title contains "intended", "safety" and "components", the words of Article 6(1)'s own test, and the curated guard's token test let "protection" and "require" back it | `REGENOLD_CURATED_ANNEX_I_ACT_BACKING`: a curated answer backs an Annex I point only by naming that point's Act (`_annex_i_instrument_keys`: `Regulation (EU) 2017/745`, `MDR`) |

Shipped offline, which is what production ships for a curated answer:
`Article 6.1, Annex I, Article 43.3, Article 14.4, Article 72.4` (expected `Article 6.1,
Article 6, Annex I, Article 14, Article 43.3, Article 72`). `Annex I` stays bare because the
answer names the MDR, not a point number.

**Measured and not shipped:** removing Article 6(1)'s vocabulary from the deepener's question
support for every answer (not only curated ones) removed 112 wrong Annex I picks and 10
correct ones over the 3,438 recorded graded turns, Ref. Strict −0.15 pp. All 10 are rg_004
`Annex I.11`: its question says "medical device", which the MDR (point 11) and the IVDR
(point 12) share, so nothing separates them once Article 6(1)'s words are gone. Open.

## Q74 — the Article 50 evidence told Stage-2 the wrong duty

The Stage-2 payload for Q74 (captured offline at the provider seam) carries the KB summaries
of `Art. 50` and `Art. 50.4`:

* `Art. 50` said deployers "must **label** deepfakes". Article 50(4) says *disclose*; marking
  (machine-readable) is the provider's Article 50(2) duty. Production answered "Yes" to "do I
  need some marking" and then said the marking duty was the provider's.
* `Art. 50` cited the "third" and "fourth" subparagraphs of Article 50(4); it has two.
* `Art. 50.4` called the artistic limitation an "exception" to be relaxed "without
  disrupting the work"; the Act limits the duty to disclosing the existence of the content
  in a manner that does not hamper display or enjoyment.

Rule (j) of `USER_CRITICAL_RULES_CLAUSE` (not dispatched under the evidence contract) tied
the artistic regime to "use authorised by law to detect ... criminal offences", which is the
separate full exemption. Corrected.

`KB_VERSION` v22 → v23. A first rewrite dropped the second "transparency" from the `Art. 50`
summary and moved `Art. 50` from rank 2 to 3 for "transparency obligations for limited-risk
systems" (the R112 BM25 pin caught it); the Act's own wording ("the transparency obligations
... are limited to disclosure") restores it.

Local live draws on this code (Opus 5.5 Stage-2 over the wrapper, Sonnet 5.5 judge, published
criteria): 1/2, 1/2 on an earlier wording, 2/2 on the final one. Every draw keeps the legal
condition that the disclosure duty applies to a deep fake; the published criterion reads the
duty as unconditional, and the answer is not made to overstate it.

## Blast radius

Offline official 110, `main` vs this branch: reference scores identical (strict 55.39, loose
78.96, conc 54.85 on the 99 gold rows); 1 reference list changes (rg_068, retrieval, neither
version cites its gold `Article 26.4`); 5 deterministic drafts change, all the Article 50
text itself (rg_058, rg_071, rg_075, rg_080, rg_103).
