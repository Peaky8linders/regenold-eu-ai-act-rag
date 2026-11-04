# Published benchmark protocol and reproducibility audit

> **Provenance (R474).** The evidence, probe outputs and `file:line` references in this
> document were produced against commit `5a64d896`, the tree BEFORE PR #510, which then edited
> the files they cite (`rubric.py`, `paired_ab.py`, `judge.py`, `score_arm.py`, `regenold.py`), so
> many line numbers no longer point where they did. The adjacent `pipeline_probe.json` was
> regenerated AFTER the fix and shows the post-fix behaviour; the pre-fix evidence this document
> describes is `docs/measurements/paper_2611_04546/pipeline_probe_pre_r473.json` (run on `beb7aeb9`,
> hospital paraphrases: 5 -> 3 and 5 -> 5 sentences, both with the single reference `Article 26.5`).

Date: 2026-11-04. Read-only audit; no official-answer replay or scoring, provider calls, runtime edits, or changes to the deployment configuration.

## Sources and scope

- [Paper v1](https://arxiv.org/html/2611.04546v1), submitted 2026-11-03.
- [Released benchmark](https://github.com/regenold-GmbH/eu-ai-act-benchmark-2026/tree/033e98fdfb6befc0be442c2d26f9851882d9cd80), pinned at `033e98fdfb6befc0be442c2d26f9851882d9cd80` (2026-11-04).
- Local read-only clone: `tmp/paper-protocol-2611.04546`.

The release does not distribute historical contestant integrations or results. Consequently, defects demonstrated below establish vulnerabilities in the released evaluation instrument, **not** that published scores were affected. Historical comparisons require the actual evaluated service commit, raw outputs, judge traces, workbook, and scoring implementation.

## Paper observations

The evaluation freezes the law at 1 May 2026. It scores criteria satisfaction, strict question success, answer length, citation recovery, citation excess, tone, and speed; overall combines eight axes geometrically. Correctness and tone use GPT-5.4 with three repeated judgments at temperature 0.1. Hard mode prepends fixed context, then challenges the initial answer; only the final response is scored. [Sections 3-4](https://arxiv.org/html/2611.04546v1#S3).

The 50-decision calibration audit mixes informative and ordinary strata; two decisions came from inconsistent repeats. Agreement was 50/50 for sampled decisions, or 48/50 under the described alternative repeat selection. This is limited calibration evidence, not a population error guarantee. The authors acknowledge rubric bias, unmeasured hallucinations and groundedness, and a single judge provider. [Sections 5-6](https://arxiv.org/html/2611.04546v1#S5).

There are editorial denominator contradictions: section 5 prose describes 42 judgments and 14 answers, whereas Tables 6-7 use 48 and 16, respectively. Eight systems support the table denominators. These need clarification, not a conclusion that the underlying calculations are wrong.

## Release metadata independently checked

Read workbook metadata only using `openpyxl`; no system answers were generated or scored.

| Check | Result |
| --- | --- |
| Workbook SHA-256 | `c15167e6dcdcb8fac6eb6d934a02a6c851b8aa366a54fa467c63d29a0824345b` |
| Items | 110 |
| Parsed correctness criteria | 288 |
| Items with 1 / 2 / 3 / 4 / 5 criteria | 26 / 32 / 25 / 12 / 15 |
| Annotated easy / medium / hard | 34 / 58 / 18 |
| Empty expected-reference fields | 12 |
| Reference-bearing items | 98 |
| Fixed context | 18 messages, 501 whitespace-delimited words |

Nine exchanges and nine individual messages are different. The release supplies nine exchanges. Five hundred words also cannot validate behavior at genuinely long context lengths. Store exact history bytes and message counts in experiment manifests.

## Reference semantics to reproduce exactly

[Released reference scorer](https://github.com/regenold-GmbH/eu-ai-act-benchmark-2026/blob/033e98fdfb6befc0be442c2d26f9851882d9cd80/src/ref_scoring.py#L27-L99):

- Exact duplicates are deduplicated; depth beyond the first sublevel is discarded.
- An expected parent can be satisfied by one candidate child. Additional sibling paragraphs remain extras.
- A candidate parent of an expected paragraph fails strict recovery but is exempt from excess-reference penalties.
- Empty expected sets produce unavailable reference metrics, rather than perfect or zero scores.
- Matching is permissive string normalization, with no legal-existence validation.

Consequences demonstrated by pure synthetic inputs:

| Expected | Candidate | Strict recovery | Extra ratio |
| --- | --- | --- | --- |
| `Article 11` | `Article 11.2`, `Article 11.3`, `Article 11.5` | 1 | 2 |
| `Article 50.4` | `Article 50` | 0 | 0 |
| `Article 50.4` | `Article 50.4.a` | 1 | 0 |
| none | `Article 50` | unavailable | unavailable |

Use this as a compatibility oracle while retaining independent wire-format and existence checks. These are matching rules, not proof that a citation supports the answer's claim. Do not optimize toward scoring loopholes such as replacing paragraphs with parents.

## Demonstrated summary coverage failure

[Released summary](https://github.com/regenold-GmbH/eu-ai-act-benchmark-2026/blob/033e98fdfb6befc0be442c2d26f9851882d9cd80/src/summarize_results.py#L36-L99) computes each repeat from whatever judgments exist, then averages repeat scores. It does not require all rows to carry the same repeat count or complete correctness coverage.

Two synthetic rows, each with one criterion:

| Passing row repeats | Failing row repeats | Reported mean strict correctness |
| --- | --- | --- |
| 3 | 3 | 50.00% |
| 3 | 1 | 83.33% |

Only coverage changed. The apparent improvement is 33.33 percentage points. The ordinary runner completes all repeats before checkpointing a row, so this is a malformed/combined-input risk; it is not evidence of a normal-run historical failure.

The summary also excludes unavailable axes from overall. That can be appropriate for explicitly partial diagnostics, but such an overall must carry the evaluated axes and denominators and must not be compared to an eight-axis score.

Recommended acceptance invariant: exact item-ID set, repeat-ID set, criterion-ID set, expected-reference eligibility mask, and metric denominators must agree between arms. Missing coverage makes the comparison indeterminate. Report coverage separately from quality.

## Demonstrated criterion-integrity failure

[Released runner](https://github.com/regenold-GmbH/eu-ai-act-benchmark-2026/blob/033e98fdfb6befc0be442c2d26f9851882d9cd80/src/run_benchmark.py#L109-L132) allows any-length `criteria` list. Its subsequent discrepancy loop indexes that list using expected criteria positions, without checking criterion text or identity. The summary later scores every returned element.

Using the exact AST-extracted `evaluate_row` body with mocked model calls and a two-criterion synthetic fixture:

| Returned correctness results | Observed behavior |
| --- | --- |
| One | `IndexError` |
| Two, with entirely unrelated criterion strings | Accepted |
| Three | Accepted, including the extra result |

No real judge was queried. This shows contract validation weakness independently of model quality.

Require stable criterion IDs and exact one-to-one coverage. Treat duplicate, unknown, missing, reordered-without-IDs, or ungrounded verdicts as invalid evaluation output. Retry only invalid transport/schema results with bounded attempts; never convert them to a tie or pass. Add deterministic mutation fixtures so a judge cannot pass by merely restating criterion text.

## Hard-mode timing and attribution

[Runner lines 202-235](https://github.com/regenold-GmbH/eu-ai-act-benchmark-2026/blob/033e98fdfb6befc0be442c2d26f9851882d9cd80/src/run_benchmark.py#L202-L235) overwrites initial latency with the second call's latency. Only initial answer prose is appended as assistant context; its separate references and reasoning fields are omitted. The pushback repeats the original question.

For faithful comparison, report that final-call speed. For product engineering, also record initial-call latency, total conversation time, cache status, retrieval time, generation time, and reference-finalization time. Otherwise a repeated-question cache hit can look like robust low-latency reconsideration.

Use a factorial held-out diagnostic: history absent/present crossed with pushback absent/present. Add correct-initial-answer and incorrect-initial-answer strata. Measure correct-to-wrong flips separately from wrong-to-correct repairs. A single final-score comparison confounds history resistance, additional computation, and self-correction.

## Recommended evaluation design

1. Pin a compatibility profile to the published commit, workbook hash, prompts, judge model/version, repeated-judgment policy, history, and metric formulas. Use it for external comparability.
2. Maintain a distinct quality profile for legal support, contradictions, unsupported additions, and warranted uncertainty. An incorrect rubric must be flaggable here without silently rewriting the compatibility score.
3. Build an expert-adjudicated judge calibration set from new scenarios and controlled mutations: polarity, exception scope, actor, dates, paragraph numbers, unsupported extra claims, and instruction injection. Include concise and verbose paraphrases of the same answer.
4. Calibrate on independent judgments with blinded system identities. Stratify informative cases for diagnosis, and separately retain a probability sample for estimating population agreement; report stratum counts and weights.
5. Choose an independent second judge only for disagreements, borderline legal claims, and mutation failures. Repeating a single provider estimates stochastic instability, not shared bias.
6. Pre-register seeded held-out paired samples. For final-answer processing, replay identical captured generations through both arms. Report item count, discordant pairs, wins/losses, ties, invalids, and a two-sided exact sign test or confidence interval. Cluster repeated judgments and easy/hard variants by question rather than pretending each is independent.
7. Use paired bootstrap intervals for continuous metric deltas, including the complete aggregate formula; do not reinterpret min-max judge ranges as confidence intervals. Power planning should use expected discordance or a minimum useful effect, not merely a fixed sample-size floor.

All proposed quality gains remain hypotheses until these experiments are run. No full official 110-question measurement was performed in this audit.
