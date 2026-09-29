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
Q45     Articles 15, 14, 12   cross-references inside Article 13(3) (on 7647427)
```

## REGENOLD_DEFINITION_CITE_SCOPE (default ON, cache-keyed)

*First cut (superseded by R456b below):* after the R455c curated scope, keep an Article 3 reference
only when the question's wording asks what a term is or means. Counterfactual over 1,839 recorded
graded turns with gold (107 questions):

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

## R456b — the adversarial review of R456

A three-lens review (definition scope, clause, tests), each finding put to two skeptics, and the
production re-run of the ten cards on b8efec8, found:

* **the wording cue was the wrong signal.** It missed the role-identity shape ("Are we a provider or
  just a deployer?", Article 3 gold on the repo's own probe corpus, three rows) and elliptical
  follow-ups ("And for a deployer?"), and it matched "definitely", "within the meaning of" and "What
  are the fines" (33 of the 110 official questions), which is how Q95 kept `Article 3.2` on b8efec8.
  The scope now keys on the DEFINED TERM, read from the official text of Article 3 (67 points): a
  point is kept when the resolved question, the live turn or the flattened conversation uses its term
  (hyphen and space interchangeable, plurals count, never inside a longer hyphenated word, so "risk"
  is not in "high-risk"), or names Article 3. A point whose term is unknown is kept.
* **"terminal" was not true.** Six passes ran after it. It now runs after the terminal wire cap,
  immediately before the trace is finalised.
* **the clause's procedure sentence pointed away from rg_059's criterion** (the Article 98(2)
  implementing act, which its question does not ask about) and did not stop Q17's Article 97: removed.
  The cross-reference instruction now keeps an article that supplies a deciding condition, as the
  evidence contract says. The clause is sent on single-turn requests only, the modality the gate
  measured.
* **two tests were vacuous** (the never-empty fallback returned the input whatever the regex did) and
  the route call site had none. Every scope case now carries a non-Article-3 reference, and a route
  test pins the wire both ways.

Final rule: keep an Article 3 point when the conversation uses the term it defines, the question
names Article 3, or the question is an explicit definition ask (`_EXPLICIT_DEFINITION_ASK_RE`,
which keeps "What is the definition of General-purpose AI?" although the defined term is
"general-purpose AI model"). An unasked point is rewritten IN PLACE to the definition the question
does use when there is one (3(1) "AI system" excluded), else dropped: a probe draw's `Article 3.61`
("widespread infringement") on "Are we a provider or just a deployer?" becomes `Article 3.3`.

```
official turns (1,839)          changed 6 (Article 3.60 on Q74)   gold-satisfying dropped 0
                                ref_strict +0.00   ref_loose +0.00   ref_conc 47.93 -> 48.05 (+0.12)
easyhard probe rows (3,714)     changed 48                         gold_dropped_head delta 0
                                (the R456 wording cue: +15; term-only drop without the rewrite: +3)
```

Revised clause, paired live confirmation on the ten questions the review singled out (rg_018,
rg_034, rg_046, rg_052, rg_059, rg_065, rg_075, rg_085, rg_096, rg_105), one draw per arm:

```
criteria met 35/39 -> 35/39   tone 9 -> 9   gold-satisfied expected refs lost 0
refs/row 2.60 -> 2.30   dropped: rg_105 Article 5, rg_052 Article 72.4, rg_085 Article 50
```

Full suite: the same 27 dataset-dependent failures as main.
