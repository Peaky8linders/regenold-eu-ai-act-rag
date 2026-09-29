# R454 — Annex I points chosen by the Act; marking questions answered in the Act's terms

## Annex I: why rg_004 lost `Annex I.11`, and the fix

rg_004 asks about "a medical device that has an AI system as a safety component". Gold is
`Article 6.1, Annex I.A.11` (the MDR). Across the recorded draws the deepener shipped `Annex I.19`
(vehicle type-approval) x13, `I.20` (civil aviation) x4, `I.4` (lifts) x1 and a bare `Annex I`
x16, and never point 11.

Two mechanisms, both measured:

1. **Article 6(1)'s own words picked the point.** Every Annex I question restates the Article
   6(1) test ("intended to be used as a safety component ... third-party conformity
   assessment"). Point 19's title contains "intended", "safety" and "components", so those
   words, not the product, chose it. The same mechanism shipped `Annex I.19` for the curated
   robotic-surgery answer (R453).
2. **Without those words the MDR and the IVDR tie.** The question's remaining support is
   "medical device", which is in point 11 ("medical devices") and point 12 ("in vitro
   diagnostic medical devices") alike, so R452b's discriminating rule kept the bare head. That is
   what the first R453 attempt ran into (10 correct `I.11` picks lost). But the question states
   the WHOLE subject of point 11 and only part of point 12's; the IVDR's qualifiers are absent.

**Fix (`REGENOLD_GRAIN_ANNEX_I_ACT_SUBJECT`, default ON):** for an Annex I point, Article 6(1)'s
tokens never count as question support; and when the question states the whole subject of one or
more listed Acts, only those compete. The subject is the title after "on", with the framing
several titles share stripped ("the harmonisation of the laws of the Member States relating to",
"the making available on the market of", "the approval and market surveillance of", "common rules
in the field of", "type-approval requirements for"). Checks: rg_004 -> `I.11`; robotic surgery ->
bare `Annex I`; in vitro diagnostic -> `I.12`; toy -> `I.2`; lift -> `I.4`; civil aviation -> `I.20`
(not the aviation-security point 13).

**Measured** (`grain_question_support_replay.py RESULTS_DIR --only REGENOLD_GRAIN_ANNEX_I_ACT_SUBJECT`,
3,438 recorded graded turns with gold, real rubric):

```
coordinates changed 195: wrong picks removed 161, correct lost 0, correct gained 34
  gains: rg_004 Annex I.11 x34 (from bare x16, I.19 x13, I.20 x4, I.4 x1)
head-set violations 0
ref_loose  +0.00   ref_conc +0.00   ref_strict 62.67 -> 63.16 (+0.49)
```

## Q74: ACT TERMS

After R453 fixed the Article 50 evidence, production still opened "Yes, but only in a limited
form" to "Do I need to provide some marking?", then said the marking duty is the provider's.
`REGENOLD_ACT_TERMS_CLAUSE` (default ON) appends, when the live question uses a marking term, the
Act's allocation: machine-readable marking is the provider's Article 50(2) duty; a deployer's is
disclosure (50(3), 50(4)); for an artistic work 50(4) limits that duty to disclosing the existence
of the content, it does not remove it. Verified on the dispatched Stage-2 bytes: present with the
flag ON, absent with it OFF, on a CE-marking question and on an unrelated question. Fires on 1 of
the official 110 (rg_075).

Local live draws on this code (Opus 5.5 Stage-2 over the wrapper, Sonnet 5.5 judge, published
criteria): first wording 1/2, 2/2, 1/2 (the answer closed on "audio that is not a deep fake needs
no disclosure", which the judge read as undercutting the duty); final wording 2/2, 2/2, 2/2. Every
draw keeps the deep-fake condition and places marking on the provider.
