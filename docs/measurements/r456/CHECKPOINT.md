# R456 — citation minimality without losing gold

The showcase cards on production 95b7a741 cited provisions beyond the required minimal keys, every
one of them a provision the answer itself names (the prose-consistency pass cites every provision
the prose names):

```
Q74     Article 3.60          the definition of deep fake
Case C  Article 3.39          the definition of emotion recognition system
Q17     Annex III, 97.6       the delegated-act procedure
Q95     Article 7.1, 112      the Commission's powers and the evaluation clause
Q104    Article 5             a cross-reference inside Article 111(1)
Q45     Articles 15, 14, 12   (7647427) cross-references inside Article 13(3)
```

## REGENOLD_DEFINITION_CITE_SCOPE (default ON, cache-keyed)

A terminal pass after parent collapse and the R455c curated scope: an Article 3 reference is kept
only when the question the answer answers (`resolved_question`, so a pushback reads the original
question) asks what a term is or means, or names Article 3; curated declared references are kept.
The official questions whose gold cites Article 3 (rg_019, rg_048, rg_076) all ask what a term is.

Counterfactual over 1,839 recorded graded turns with gold (107 questions; exact for the reference
axes, since the pass runs after every pass that adds a reference):

```
changed 41   gold-satisfying references dropped 0
dropped: Article 3.60 x18, 3.46 x15, 3.1 x4, 3.4 x2, 3.57 x1, 3.65 x1
ref_strict 64.98 -> 64.98   ref_loose 94.07 -> 94.07   ref_conc 47.93 -> 48.38 (+0.45)
```

## REGENOLD_PROVISIONS_TO_NAME (default ON, cache-keyed)

A Stage-2 user-channel clause appended last: name only the provisions that answer the question;
state content a cited provision takes from another article without naming that article; name an
Article 3 definition only on a definition ask and a procedure clause only when asked. It does NOT
forbid tiers the question did not raise: rg_084's criteria require ruling out neighbouring tiers
and rg_059's the Article 98(2) procedure the question asks about. Verified on the dispatched user
message (present ON, absent OFF).

Paired live gate: local route, live Stage-2 over the wrapper, arms interleaved per question, the
six showcase questions plus every third official question (41), one draw per arm, Sonnet 5.5 judge
(grouped, 3 repeats), references against gold with the real rubric:

```
criteria met     A 141/147   B 141/147
gold-satisfied expected refs lost 0, gained 0
refs/row         A 2.76      B 2.59
ref_strict 88.89 -> 88.89   ref_loose 100.00 -> 100.00   ref_conc 53.52 -> 55.40 (+1.88)
answer chars     A 804       B 806
tone ok          A 39        B 38   (rg_022 and rg_100 flagged for run-on sentences, rg_064 cleared)
```

Removed by the clause: rg_034 Articles 91.3, 92.1, 93.3; rg_052 Articles 9.2, 72.4; rg_096
Article 112.2.a; rg_085 Article 50. One draw in the rg_096 pair fell back to the Bedrock leg
(degenerate wrapper completion), so that pair is confounded.
