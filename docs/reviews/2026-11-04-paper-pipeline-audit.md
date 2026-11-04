# Pipeline audit against arXiv 2611.04546

> **Provenance (R474).** The evidence, probe outputs and `file:line` references in this
> document were produced against commit `5a64d896`, the tree BEFORE PR #510, which then edited
> the files they cite (`rubric.py`, `paired_ab.py`, `judge.py`, `score_arm.py`, `regenold.py`), so
> many line numbers no longer point where they did. The adjacent `pipeline_probe.json` was
> regenerated AFTER the fix and shows the post-fix behaviour; the pre-fix evidence this document
> describes is `docs/measurements/paper_2611_04546/pipeline_probe_pre_r473.json` (run on `beb7aeb9`,
> hospital paraphrases: 5 -> 3 and 5 -> 5 sentences, both with the single reference `Article 26.5`).

Date: 2026-11-04. Scope: executable application paths and local protocol fixtures.
No runtime code changed; no paid evaluation or full official-set replay performed.

## Evidence and limits

Read the [paper](https://arxiv.org/html/2611.04546v1), applicable repository
instructions, current route/engine/normaliser code, and recent audit notes.
The reusable offline diagnostic is
`docs/measurements/paper_2611_04546/pipeline_probe.py`; results and commit identity
are in the adjacent JSON. It prohibits application network connections and observed
zero network attempts. These are regression reproductions, not evidence of a
statistically significant improvement, and do not establish deployed settings.

Relevant existing regression files still pass: `python -m pytest
tests/test_r468_normaliser_shaping.py tests/test_r424_hard_preamble.py -q`:
**118 passed**, with Starlette deprecation and pytest-cache permission warnings.

## P0: replace the reconstructed hard history with the published stimulus

`evals/regenold/hard_preamble.py:38` explicitly says the fixture was reconstructed
because the evaluator's verbatim text was unavailable. Lines 50-73 deliberately
remove provision numbers, role words and risk words from prior USER turns to
avoid our anchor machinery. This is a useful diagnostic fixture, but a poor
substitute for an official reproduction now that Appendix B publishes the text.

The difference is executable. The current fixture produces no conversation
anchors. One short published user turn, "Is every Annex III AI system
automatically high-risk?", produces Annex III and risk anchors through the real
`_extract_conversation_anchors` (`app/routes/regenold.py:9996`). The probe records
this without asserting that it changes a final answer: later focus/denoising
guards may neutralise part of the difference.

Method: import a versioned upstream fixture, record upstream commit and content
digest, and retain the reconstruction under an explicit diagnostic identity.
Preserve the published prior assistant utterances even where legally imperfect;
the stimulus is part of the experimental protocol. Test request bytes and
18/20 prior-message counts at dispatch. Use non-official held-out questions for
the paired A/B comparison; report the fixture change separately from product
improvement. Default fixed-vs-rolling support already exists (R424); do not
reimplement it.

## P1: a benign paraphrase changes completeness, while both wordings lose references

Two new hospital-obligation phrasings reach the same curated engine draft with
five sentences:

| Question shape | Draft / wire sentences | Wire references |
| --- | --- | --- |
| One question: what obligations must the hospital meet when it deploys a high-risk system? | 5 / 3 | Article 26.5 |
| Scenario statement, then question about the hospital's obligations | 5 / 5 | Article 26.5 |

The actual HTTP endpoint returns 200 in both cases. The first loses the
Article 86 explanation-right sentence and Article 25 provider-transition
boundary. The second retains them. This is under unset sentence/character
budget environment, with CLI/offline provider and no `.env` load. Production
environment may override the sentence limit.

Mechanism: the normaliser resolves the default sentence budget at
`app/integrations/regenold/models.py:1683`, increases it based on question shape
at 1694-1712, and slices at 1841. Whole-curated-text protection at 1730 is only
enabled for the small pinned-verdict set selected in
`app/routes/regenold.py:11884`. Hospital is not in that set. The current anchor
tests in `tests/test_r468_normaliser_shaping.py:338` verify citation anchors in
draft sentences, not preservation of required claims through the endpoint.

The more serious reference loss is independent of sentence truncation. The probe
wraps the actual route helpers and records this sequence:

1. Engine declares ten citations (`app/engines/_graph_rag_impl.py:7173`).
2. Anchor surfacing adds Article 6, making eleven.
3. `_curated_budget_cut` at `app/routes/regenold.py:5294`, called at 13059,
   returns only Article 26 and its four children: 26.1, 26.2, 26.5, 26.6.
   Its `[:budget]` at 5321 counts all five representations against capacity,
   deleting Article 27, 86, 25, 13 and Annex III.
4. `_collapse_multi_leaf_clusters` at 7053, called at 14384, collapses those
   five surviving references to Article 26.
5. `_deepen_ref_grain` at 5636 chooses Article 26.5, yielding one wire citation.

The helper's "recall-safe" comment at 7068 only describes preservation of
top-level heads. It does not preserve distinct operative first sublevels.
Later deepening cannot recover siblings removed before it runs. This explains
how a complete-seeming answer can still fail strict citation checks.

Candidate repair: resolve redundant ancestor representation before applying
budgets, then preserve the distinct provisions actually supporting required
claims. Broaden whole-draft protection only after reviewing each curated draft
for unwanted content. Do not globally uncap all answers, add a smaller reference
cap, or treat every declared reference as automatically relevant. Check all
curated families through their final wire path, including short paraphrases.

Experiment: replay the same saved curated answers through both postprocessing
arms on a seeded held-out family sample. Report changed pairs, per-criterion
completeness, strict-sublevel coverage, head/sublevel losses, and deterministic
word-count cost. Use the repository's live paired judge only for genuinely
semantic differences. A tiny reproducer locates a defect; it does not clear
the merge gate.

## P1: conversation anchor extraction has substring and ordering defects

`_ANCHOR_RISK_WORDS` is a frozenset (`app/routes/regenold.py:2640`), includes
both "annex i" and "annex iii", and is tested with `risk in text_lower` at
10046. An Annex III mention therefore also adds the Annex I marker. The helper
then keeps only the first two markers at 10055. Iteration over a frozenset
makes order and sometimes retained marker identity dependent on Python's
process hash seed. Role markers use the same unordered-substring pattern at
10040-10042, with their own first-three cut.

Fix candidate: deterministic canonical ordering and token/coordinate boundaries,
preferably using the existing reference parser for Annex identities. Add tests
for Annex I/II/III/IV, negated/quoted role mentions and stable ordering across
hash seeds. Measure any resulting answer/reference movement rather than
assuming this internal correction is response-neutral.

## P2: track claim preservation at each final transformation

R468 fixed real shaping bugs but the hospital reproduction shows why inspecting
drafts is insufficient. Add a diagnostic ledger for draft -> generated answer ->
normalised answer -> final answer, alongside reference changes with pass names.
The existing opt-in reasoning trace already records useful notes and provider
provenance (`app/routes/regenold.py:11720`); extend internal diagnostics rather
than the core wire schema. Use actual fired transformations to localise loss.

Prioritise actor/duty/trigger/exception claims in held-out expert rubrics. Then
extend the existing typed `EvidenceBundle` (`app/engines/evidence_bundle.py:1`)
with claim/required-provision links if evidence packing needs improvement.
The bundle already exists and is wired at `_graph_rag_impl.py:10412`; proposing
another bundle would duplicate work. Support an evidence-first answer plan in
the existing generation call before adding a second repair round trip.

Likewise, completeness repair already exists at `_graph_rag_impl.py:12210`
and is called at 12732. Its detectors are default OFF and a broad closed-set
variant previously failed the gold-drop gate. Do not simply enable them.
Any new variant needs same-generation replay plus a fresh live gate, including
the exact hard stimulus and reference-loss veto.

## P2: preserve correctness on pushback while permitting justified correction

The route already distinguishes re-asks and challenges
(`app/routes/regenold.py:10993`, 11040), and preserves prior answers after failed
tail repair (`_graph_rag_impl.py:12162`). Therefore, "add pushback detection"
is not a new improvement. Test two directions on held-out conversations:
unsupported user pressure against an initially correct answer, and valid legal
evidence against an initially wrong answer. Score harmful reversals and justified
corrections separately, plus dropped supported claims. Citation-set Jaccard or
an apology/concession marker alone cannot distinguish these outcomes.

## Existing controls that should not be reopened casually

The temporal scope is already pinned to the original Act and 1 May 2026 in
`app/data/graph_rag_prompt_templates.py:296-298`; no blanket claim of Omnibus
contamination is supported. Single-turn full-system prompting is already
modality-gated at `_graph_rag_impl.py:1272`; historical hard-mode losses are
documented immediately above it. Compact prompts and evidence minification
already have gates. Latency improvements should be profiled by provider leg,
actual input bytes, repairs and cold/warm status; changing thinking-token
budgets repeats a closed direction.

Archived July7 input is not the same protocol snapshot as the paper:
`evals/regenold/evaluator_batch_july7.py:65-76` documents 111 historical turn-20
rows, only 67 carrying genuine adversarial pushback. This warrants a provenance
note and run-identity check, not an unsupported assertion that the paper's
published results are wrong.
