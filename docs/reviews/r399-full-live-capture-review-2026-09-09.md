# R399 — September 7 full live capture: legal review and current-code remediation

Review date: 2026-09-09. Starting checkout: `3007956`, including R398 `6b9817f`.

## Evidence and limits

The supplied `r390full110liveanswersandverdicts.md` and the workspace JSON contain **110 questions answered in each mode: 220 answers**. Recomputed counts: easy 32 non-passing rows / 54 failed criteria; hard 22 / 34; **38 distinct questions** fail somewhere. Overall 78.2692 / 76.0799 are historical scores against reconstructed criteria, not newly measured performance or the evaluator's score.

The September 7 capture predates the September 8 repairs and the September 9 R398 instrumentation changes. The six-case September 9 run is separate evidence; it cannot establish a new full-corpus score. The full capture stores majority verdicts, not prose judge remarks. The separate `r390-partial-judged-rows-with-remarks.json` contains actual later remarks for **77 easy rows and no hard rows**, judged with a different provider/model. Those are not the full-run judge's remarks.

The requested HTML (`docs/reports/r390-live-hard-questions-and-answers.html`) displays the hard results, but its “Judge Remarks” include generated summaries such as “Completely firm under pushback.” They must not be represented as original judge quotations. Its comparisons with official/frontier scores and “100% resilience” do not establish comparable accuracy: an answer can remain consistently wrong, and the answer keys differ.

Review coverage: all 54 non-passing row/mode entries, their underlying questions and answers, plus reference-mismatch examples among passing rows. This is not an independent rejudging of every passing criterion. Findings below distinguish statutory defects, debatable criteria, and defects already addressed in the current tree.

Legal authority: the adopted [Regulation (EU) 2024/1689](https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng), as preserved in `official_eu_ai_act.py` plus `official_text_patches.py`, accessed through `get_provision_text`. EUR-Lex live requests encountered its robot challenge during this review; legal checks therefore use the repository's adopted-text corpus, not an asserted verification of later amendments. The ontology is derived evidence, never a substitute for the operative text.

## Confirmed current defects to fix first

1. **Wrong Article 6 route on the wire.** Replaying the current `_deepen_one_ref` with rg_008's captured question and answer produces `Article 6.2`, although the answer explicitly applies **6(1)** to MDR safety components. The code forces paragraph 2 for any question containing “high-risk”, even without an Annex III premise. rg_091 hard similarly states the product route but emits 6.2. The fix must distinguish Annex I products from Annex III use cases; a head-preserving repair cannot drop a gold article, but strict-coordinate quality still needs checking.
2. **“Minimal risk means no mandatory duties” is false.** Both the risk overview and residual-tier canned answers still say this. **Article 4** binds providers/deployers of AI systems generally; Article 95 voluntary codes do not displace it. Repair the shared topic and active intercepts together, with tests of actual answers. Do not generalise high-risk Chapter III requirements to minimal-risk systems.
3. **Scope answer omits the operative market acts.** rg_006's current canned response gained “Both” but still describes tiers instead of clearly stating **Article 2(1)(a)**: providers placing AI systems on the market or putting them into service, and providers placing GPAI models on the market. A short correction can improve accuracy and reduce repetition while preserving the existing reference heads.

## Disposition of every question failing in either mode

“Existing repair” means code/tests address the mechanism; it does not mean the full live benchmark has been rerun successfully.

| Question | Legal assessment and disposition |
|---|---|
| 005 | Correct negative answer on named XAI methods; missing explicit technology-neutral framing is largely elaboration. Current explainability intercept already adds it. |
| 006 | Both regimes identified, market-placement/provider scope insufficiently explicit; targeted current fix above. |
| 010 | Article 14 correctly answers “which article”; demanding an entire 14(2)–(4) summary over-specifies this narrow question. Do not lengthen automatically to satisfy the key. |
| 011 | Definition 3(32) and leakage explanation correct; 10(3) quality detail missing historically. Existing R394 repair includes it and tests normalisation survival. |
| 021 | Lifecycle duty already explicit under 15(1); key demands additional 15(4)/(5) detail. Main negative verdict correct. Adjacent 9/17 elaboration could be reduced only with coverage testing. |
| 022 | Missing voluntary codes is secondary; categorical “no mandatory duties” contradicts Article 4. Current repair required. |
| 029 | Genuine omission: Annex III 5(d) includes evaluating/classifying emergency calls. Existing R394 repair adds it. Historical answer also overstates unconditional Annex III classification. |
| 031 | Narrow procedural example should be applied explicitly, subject to 6(3)'s conditions and profiling override. Existing R394 repair; do not erase those qualifications to force an unconditional No. |
| 033 | State appointment under 65(3) only implied in easy answer; hard repairs it. Small completeness issue, not a different governance rule. |
| 035 | Article 80(2)/(3) is primary for misclassification and noncompliance; additional 79/20 discussion needs actual risk facts. Capture goes beyond what was asked. |
| 036 | 42(1) presumption limited by intended purpose; easy wording omits that express qualifier. |
| 037 | **Key defect:** generic provider-registration question graded against 49(4)'s restricted law-enforcement/migration subset. General answer belongs to 49(1), 71(2), Annex VIII A. Its thirteen-item list includes Member States (item 10) and the declaration of conformity (11), both omitted from the answer, plus specific certificate metadata (8). Do not replace it with restricted-only data. |
| 038 | 3(52) definition largely supplied; agreed plan / pre-market context from 57 can clarify. Criterion bundles several facts, so FAIL is not total definition failure. |
| 040 | Annex VII 4.6 certificate particulars were correctly given, while key demands only Article 44 language/validity. Existing R394 adds these general requirements; key should also retain the actual certificate particulars. |
| 041 | **Key defect:** Article 11(1) assigns the simplified form to the **Commission**, not the AI Office. Easy answer correctly says Commission. |
| 043 | 10(5) safeguards were abbreviated, losing confidentiality/access and processing-record detail. Existing R394 supplies safeguards and data-protection framing. |
| 044 | Registration answer missing Annex IX particulars and precise restricted/national exceptions in 60(4)(c), 49(4)/(5), 71(4). Generic “register all tests” is too broad. |
| 051 | 22(1)/(2) answered; 22(3) mandate tasks incomplete. Termination discussion is less responsive than those tasks. |
| 059 | 68(2) scientific-panel tasks and 68(3) selection requirements incomplete; repeated alert/confidentiality prose displaces them. Evidence needs the complete relevant paragraphs. |
| 060 | 60(7) reporting/mitigation/recall duties supplied; 73(6) cooperation and preservation of incident evaluation missing if covering the incorporated reporting procedure. |
| 062 | Separate pre-market 24(2) from already-marketed corrective action/authority notification in 24(4). Question is underspecified; an answer should state both conditional branches, not conflate them. |
| 066 | Missing deployer-entered Annex VIII C under 71(3). Provider A/B alone is incomplete. |
| 068 | **Key defect and hard-mode drift:** input-data relevance/representativeness under **26(4)** belongs to the deployer to the extent it controls input data. Easy gets this right; hard switches to provider/training-data Article 10 and becomes less responsive. |
| 069 | Real omission: storage/transport safeguards in 24(3) and 23(4). These concern objectively high-risk systems; absence of notification does not create an exemption. Do not claim all AI systems are covered by those paragraphs. |
| 078 | 61(1) consent record/date/copy and unique identifier/contact details missing in easy. Also retain 60(4)(j)'s law-enforcement qualification; avoid universal consent claims detached from it. |
| 080 | Text exception described, deepfake law-enforcement exception not clearly stated. Current prompt corrections distinguish the two limbs; needs fresh live coverage check. |
| 084 | Classification broadly right; absence of one named exclusion is not necessarily error. Easy's “no mandatory requirements” is overbroad because of Article 4. |
| 085 | Hard answer loses non-law-enforcement remote biometric identification under Annex III 1(a). Detection alone is not identification; toy status does not immunise the practice. |
| 086 | No model-right-sizing mandate is correct. “Environmental protection features only as a general objective” is too broad: inspect 40(2), 53/Annex XI and 95(2)(b), not only 112(6). |
| 087 | Correctly rejects invented five-harm mapping. Hard reply substitutes long Article 5/GPAI enumeration for 9(2)'s four risk-management steps, and repeats the false no-duty claim. |
| 089 | **Key overreach:** transcription need not invoke a 6(3) derogation if it does not enter an Annex III use case at all. Answer appropriately distinguishes 6(1) product route. Article 50(1) depends on direct interaction; it is not automatic for every transcription tool. |
| 091 | **Key overreach:** general clinical treatment support is not automatically Annex III healthcare-access/triage. Hard answer correctly distinguishes product route from listed uses. Its **wire 6.2** contradicts its prose 6(1): current deepener defect. |
| 099 | Wrong canned systemic-risk definition displaced cybersecurity answer. Existing R394 releases this misfire. Article 55 duties attach to systemic-risk GPAI models; distinguish general high-risk-system cybersecurity under 15. |
| 101 | Genuine error: urgency authorisation deadline is **24 hours under 5(3)**, with immediate stop and deletion/discard requirements if refused. Article 46 emergency market authorisation is a different mechanism. |
| 103 | Wrong “No” law-enforcement intercept displaced educational-deepfake answer. Existing R394 releases it. Key's automatic “educational = analogous work” is also too strong: Article 50(4) requires evidently artistic/creative/satirical/fictional or analogous work; educational purpose alone is not an explicit exemption. |
| 106 | Right verdict, hard answer omits explicit “by/on behalf of law enforcement” gate in Annex III 6. Optional human review alone is not a general exemption. |
| 107 | **Key defect:** non-binding recommendation does not itself establish 6(3) non-material influence. Profiling override and Annex III 3(b)/(c) support the answer's caution. |
| 110 | **Key defect:** becoming provider does not prove one ceases to use the system as deployer. **27(1)'s Annex III point 2 exclusion** supplies the FRIA result, correctly identified in the answer. Fine-tuning is not automatically substantial modification: apply 3(23)/25 conditions. |

## Reference precision and knowledge-graph implications

Passing answers are not necessarily sound references. rg_001 names Annex IV 1(e) but ships IV.2; rg_008 cites Annex I.19 (civil aviation), while MDR is **Annex I Section A point 11**. rg_003 ships Annex III.7.b on a general derogation question. A coordinate-existence oracle cannot catch any of these: the coordinate exists but supports a different proposition.

R397/R398 additions are present: generated TrustGraph ontology/instance artefacts, paragraph-coordinate catalog, graph semantic coordinate lookup, and the now-wired coordinate-map prompt. `graph_semantic.semantic_coordinates_enabled` controls a real query; `kg_context.render_kg_context` feeds bounded non-citable context. These mechanisms improve grounding opportunity but do not prove a particular captured answer used them. September 7 cannot measure changes added later.

The graph focus pass and the wire grain deepener use different evidence paths. Adding graph coordinates does not fix a later lexical deepener that overwrites a correct head with the wrong paragraph. Preserve statute hierarchy and qualifiers; do not infer legal applicability from relationship membership alone. Nested/sectioned coordinates and the permissive provision resolver need a separate systematic audit; avoid claiming the paragraph catalog validates all deeper references.

## Implementation and verification

Report written before code changes. First implementation batch targets the reproduced Article 6 coordinate error, general-duty misconception in minimal-risk canned answers, and Article 2 market-scope wording. Historical captures and reconstructed gold stay unchanged. Verification results are appended after execution; no current live score improvement is claimed from unit tests or replay.
