# R41 — Digital Omnibus on AI: Change-list keyed to AI Act articles

Source: Council of the EU, Brussels 13 May 2026, document **9247/26 (CODEC 907)**, Interinstitutional File 2025/0359 (COD). COREPER compromise text. Amends Regulation (EU) 2024/1689 (AI Act) and (EU) 2018/1139 (civil aviation). Entry into force: third day after publication in the Official Journal.

Citation key: `Art. N` = AI Act article post-Omnibus. `(NEW)` = inserted by Omnibus. `(AMD)` = amended. `(DEL)` = deleted. Quoted text is verbatim from the compromise.

---

## A. Article-by-article table

| Article | Change Type | Effective | KB file to update | Priority |
| --- | --- | --- | --- | --- |
| **Art. 1(2)(g)** | AMD — SMC + SME wording | EIF | `kb.py`, `role_obligations.py` | LOW |
| **Art. 2(2)** | AMD — Section B Annex I products only get `Art. 6(1)`, `Art. 60a`, `Arts. 102–112`; Arts. 57–59 only if integrated | EIF | `kb.py` | MED |
| **Art. 2(13)** (NEW) | NEW — Commission may, by delegated act (by 2 Aug 2027), limit Arts. 9–15 + 17–25 requirements where Section A Annex I gives equivalent protection | 2 Aug 2027 | `kb.py`, `article_requirements_full.py` | HIGH |
| **Art. 3(14)** | AMD — narrowed definition of "safety component" (must fulfil safety function as intended purpose) | EIF | `definitions.py`, `kb.py` | **HIGH** |
| **Art. 3(14a) / (14b)** (NEW) | NEW — formal definitions of SME (Rec. 2003/361/EC) and SMC (Rec. 2025/1099) | EIF | `definitions.py`, `role_obligations.py` | **HIGH** |
| **Art. 4** (replaced) | AMD — AI literacy obligation softened to "take measures to support" (no longer "ensure") | EIF | `kb.py`, `article_requirements_full.py` | **HIGH** |
| **Art. 4a** (NEW) | NEW — legal basis for processing special-category personal data for bias detection/correction (providers of HRAIS strict; deployers + other AI models lighter regime) | EIF | `kb.py`, `article_requirements_full.py`, `definitions.py` | **HIGH** |
| **Art. 5(1)(ba) / (bb)** (NEW) | NEW — TWO new prohibitions: (ba) non-consensual intimate material ("nudification") and (bb) AI-generated/manipulated CSAM | **2 Dec 2026** | `kb.py`, `ontology.py` (Practice registry), `agentic_taxonomy.py` | **HIGH** |
| **Art. 5(1a) / (1b)** (NEW) | NEW — scope clarifications for (ba)/(bb): provider liable only if generation is intended purpose OR foreseeable + no safeguards; deployer only if used for that purpose | 2 Dec 2026 | `kb.py` | **HIGH** |
| **Art. 6(1a)** (NEW) | NEW — **safety-component carve-out**: AI systems "solely used for non-safety related aspects of user assistance, performance optimisation, service efficiency, automation or convenience or quality control shall not qualify as safety components" | EIF | `kb.py`, `article_requirements_full.py`, `scenario_classifier.py` | **HIGH** |
| **Art. 6(1b)** (NEW) | NEW — failure-or-malfunctioning-endangers-health-and-safety still qualifies (overrides 1a) | EIF | `kb.py` | **HIGH** |
| **Art. 6(1c)** (NEW) | NEW — third-party CA solely for radio-spectrum/EMI risks does NOT satisfy Art. 6(1)(b) | EIF | `kb.py` | MED |
| **Art. 6(5)** | (Implicit) Excluded from new delayed-application gate per Art. 113 — still applies on original schedule | EIF | `kb.py` | LOW |
| **Art. 10(1), 10(6)** | AMD — cross-reference to new Art. 4a(1) for bias-data quality criteria | EIF | `kb.py`, `article_requirements_full.py` | MED |
| **Art. 10(5)** | DEL — moved to Art. 4a | EIF | `kb.py` | MED |
| **Art. 11(1)** | AMD — SMEs/SMCs may use a SIMPLIFIED technical-documentation form (Commission to publish; notified bodies must accept) | EIF | `kb.py`, `article_requirements_full.py` | **HIGH** |
| **Art. 17(2)** | AMD — QMS proportionate to SME/SMC size; rigour preserved | EIF | `kb.py`, `role_obligations.py` | MED |
| **Art. 25(2)** | AMD — initial provider must hand over tech docs, share known limitations/failure modes, give technical access — UNLESS the system was explicitly not designed to become HRAIS | EIF | `kb.py`, `article_requirements_full.py` | MED |
| **Art. 25(4)** | AMD — written-agreement obligation does NOT apply to free/open-source third-party tools (except GPAI) | EIF | `kb.py` | MED |
| **Art. 27(4) / (5)** | AMD — FRIA may cross-reference DPIA; AI Office provides automated questionnaire template | EIF | `kb.py`, `article_requirements_full.py` | LOW |
| **Art. 28(8)** (NEW) | NEW — single application + unified assessment procedure for notified bodies under Section A Annex I legislation | EIF | `kb.py` | LOW |
| **Art. 29(4)** | AMD — documents from prior designations reusable | EIF | `kb.py` | LOW |
| **Art. 30(2)** | AMD — notifying authorities use Annex XIV codes; Commission may amend Annex XIV by delegated act | EIF | `kb.py` | LOW |
| **Art. 40(2)** | AMD — Commission to request joint-compliance standardisation deliverables | EIF | `kb.py` | LOW |
| **Art. 42(2a)** (NEW) | NEW — HRAIS meeting Reg. (EU) 2024/2847 (Cyber Resilience Act) Art. 12(1) deemed to comply with Art. 15 cybersecurity | EIF | `kb.py`, `article_requirements_full.py` | MED |
| **Art. 43(3)** | AMD — Section A Annex I notified bodies have 18-month window to assess HRAIS; choice of CA procedure preserved (no automatic third-party CA just because HRAIS is a safety component) | EIF + 18 mo | `kb.py`, `article_requirements_full.py` | **HIGH** |
| **Art. 50(7)** | AMD — implementing-act empowerment **removed**; codes of practice + Art. 56(6) adequacy assessment instead | EIF | `kb.py`, `article_requirements_full.py` | MED |
| **Art. 56(6)** | AMD — implementing-act empowerment **removed**; Commission publishes adequacy assessment | EIF | `kb.py` | MED |
| **Art. 57** | AMD — sandboxes operational by **2 Aug 2027**; EDPS may run Union-institutions sandbox; AI Office may run Union-level sandbox for Art. 75(1) systems (with SME/SMC priority access); sandbox plan may incorporate real-world testing plan | 2 Aug 2027 | `kb.py`, `article_requirements_full.py` | MED |
| **Art. 58(1)** | AMD — Commission implementing acts cover governance + Member-State cooperation in sandboxes | EIF | `kb.py` | LOW |
| **Art. 60** | AMD — real-world testing extended to HRAIS covered by Section A Annex I product legislation | EIF | `kb.py`, `article_requirements_full.py` | MED |
| **Art. 60a** (NEW) | NEW — Member-State-framework-based real-world testing for HRAIS under Section B Annex I (aviation, rail, marine, motor, agri etc.) | EIF | `kb.py`, `article_requirements_full.py` | **HIGH** |
| **Art. 63(1)** | AMD — simplified QMS extended from microenterprises to **all SMEs (incl. start-ups)** without partner/linked enterprises | EIF | `kb.py`, `role_obligations.py` | **HIGH** |
| **Art. 64(2a)** (NEW) | NEW — AI Office to be allocated adequate resources | EIF | `kb.py` | LOW |
| **Art. 69(2)** | AMD — Member-State expert fees aligned to Commission rates | EIF | `kb.py` | LOW |
| **Art. 70(8)** | AMD — explicit SME/SMC guidance/advice mandate for NCAs | EIF | `kb.py`, `role_obligations.py` | LOW |
| **Art. 72(3)** | AMD — implementing-act empowerment **removed**; Commission to publish guidance + voluntary template by **2 Sep 2027** | 2 Sep 2027 | `kb.py`, `article_requirements_full.py` | MED |
| **Art. 75** | AMD — AI Office exclusive competence over (a) GPAI-built systems by same provider/undertaking (with carve-outs for Annex I products, Annex III(2), law-enforcement/border/financial under Art. 74(6), Annex III(8) justice), (b) VLOPs/VLOSEs under DSA; deployer scope limited to same-undertaking | EIF | `kb.py`, `article_requirements_full.py`, `role_obligations.py` | **HIGH** |
| **Art. 75a–75e** (NEW) | NEW — AI Office investigatory + enforcement powers (info requests, on-site inspections, commitments, fines, periodic penalties, safeguards, 5-yr limitation period). Periodic penalty cap **5% average daily income/turnover per day** | EIF | `kb.py`, `article_requirements_full.py` | **HIGH** |
| **Art. 76(1)** | AMD — references to MSA construed as references to NCA under Section B Annex I where testing under Art. 60a | EIF | `kb.py` | LOW |
| **Art. 77** | AMD — fundamental-rights authorities get explicit machine-readable access to MSA-held info; mutual-cooperation duty | EIF | `kb.py`, `article_requirements_full.py` | MED |
| **Art. 95(4)** | AMD — codes of conduct must accommodate SMC needs | EIF | `kb.py` | LOW |
| **Art. 96(1)(g)** (NEW) | NEW — Commission to publish guidelines on Arts. 8(2)/9(10)/17(3) (sectoral overlap) by **1 Aug 2027** | 1 Aug 2027 | `kb.py` | LOW |
| **Art. 99(1)** | AMD — Member-State penalty regimes must take SME/SMC viability into account | EIF | `kb.py`, `role_obligations.py` | MED |
| **Art. 99(4)(da)** (NEW) | NEW — penalty bracket extended to Art. 25(2) and (4) breaches | EIF | `kb.py` | LOW |
| **Art. 99(6)** | AMD — SME-cap (lower of % or amount) applied to ALL Art. 99 fines, not just paragraphs 3/4/5 | EIF | `kb.py`, `role_obligations.py` | MED |
| **Art. 99(6a)** (NEW) | NEW — **SMC fine cap**: lower of % or amount under paragraphs 4 or 5 | EIF | `kb.py`, `role_obligations.py` | **HIGH** |
| **Art. 111(2)** | AMD — grace-period clarification: applies to TYPE-AND-MODEL of HRAIS; public-authority deployers must comply by **2 Aug 2030** | EIF | `kb.py`, `article_requirements_full.py` | MED |
| **Art. 111(4)** (NEW) | NEW — pre-existing generative-AI providers have until **2 Dec 2026** to comply with Art. 50(2) labelling | 2 Dec 2026 | `kb.py` | MED |
| **Art. 113** | AMD — **applicability cascade**: Chapter I & II from 2 Feb 2025 EXCEPT new Art. 5(1)(ba)/(bb)/(1a)/(1b) which apply from **2 Dec 2026**; Chapter III Sect. 1–3 (except Art. 6(5)) → **2 Dec 2027 for Art. 6(2)+Annex III**, **2 Aug 2028 for Art. 6(1)+Annex I**; Arts. 102–110 from EIF of Omnibus | various | `kb.py` (Art. 113), `article_existence.py` | **HIGH** |
| **Annex I.A** | AMD — point 1 (Directive 2006/42/EC machinery) **deleted from Section A** | EIF | `kb.py` | MED |
| **Annex I.B** | AMD — new point 21: **Reg. (EU) 2023/1230 (Machinery)** moved into Section B | EIF | `kb.py` | MED |
| **Annex VIII Section B** | AMD — points 7 and 9 **deleted** (simplified Art. 49(2) registration for Art. 6(3) non-high-risk systems) | EIF | `kb.py` | LOW |
| **Annex XIV** (NEW) | NEW — full list of AIP / AIB / AIH codes for notified-body designation scope. AIH 0301 = generative AI / GPAI systems. AIH 0401 = Agentic AI ("emerging AI technologies not covered by other codes, including Agentic AI") | EIF | `kb.py`, `agentic_taxonomy.py`, `ontology.py` | **HIGH** |

---

## B. Verbatim quotes — load-bearing new text

### B1. Art. 5(1)(ba) – non-consensual intimate material (NEW)

> "(ba) the placing on the market, the putting into service or the use of an AI system that generates or manipulates realistic images, videos, audio or similar material of an identifiable natural person's intimate parts, or of an identifiable natural person engaged in sexually explicit activities, without that person's freely-given, specific, informed, unambiguous and explicit consent for that generation or manipulation;"

### B2. Art. 5(1)(bb) – CSAM (NEW)

> "(bb) the placing on the market, the putting into service or the use of an AI system that generates or manipulates material or performance within the meaning of Article 2, points (c) and (e), of Directive 2011/93/EU, save where a 'without right' defence applies under national law;"

### B3. Art. 5(1a) – provider/deployer scope for (ba)/(bb)

> "(a) the placing on the market or putting into service of an AI system that generates or manipulates the material … is only prohibited where: (i) that generation or manipulation is the intended purpose of the AI system; or (ii) the system's design, training, architecture, capabilities or user-facing functionalities make that generation or manipulation a reasonably foreseeable reproducible outcome, without requiring significant technical modification, and the system does not have reasonable and adequate technical safety measures and other safeguards to reliably prevent that generation or manipulation … and to correct observed or reported misuse. (b) the use of an AI system that generates or manipulates the material … is only prohibited where the deployer uses the system for the purpose of generating or manipulating such material …"

### B4. Art. 6(1a) – safety-component non-qualification (NEW)

> "For the purposes of this Regulation including paragraph 1 of this Article, AI systems that are solely used for non-safety related aspects of user assistance, performance optimisation, service efficiency, automation or convenience or quality control shall not qualify as safety components."

### B5. Art. 6(1b) – override (NEW)

> "AI systems whose failure or malfunctioning would endanger health and safety shall qualify as safety components notwithstanding paragraph 1a."

### B6. Art. 3(14) – revised "safety component" definition

> "(14) 'safety component' means a component of a product or of an AI system which fulfils a safety function for that product or AI system, or the failure or malfunctioning of which endangers the health and safety of persons or property; for the purposes of this definition, a component fulfils a safety function where its intended purpose is to prevent or mitigate risks to health and safety of persons or property;"

### B7. Art. 3(14a) / (14b) – SME / SMC definitions (NEW)

> "(14a) 'micro, small and medium-sized enterprise' ('SME') means a micro, small or medium-sized enterprise as defined in Article 2 of the Annex to Commission Recommendation 2003/361/EC;
> (14b) 'small mid-cap enterprise' ('SMC') means a small mid-cap enterprise as defined in point (2) of the Annex to Commission Recommendation (EU) 2025/1099;"

### B8. Art. 4 (replaced) – softened AI literacy

> "1. Providers and deployers of AI systems shall **take measures to support the development of AI literacy** of their staff and other persons dealing with the operation and use of AI systems on their behalf … This obligation shall not be understood as requiring providers or deployers to guarantee any specific level of AI literacy of any individual."

### B9. Art. 113 – revised applicability cascade

> "(a) Chapters I and II shall apply from 2 February 2025, except for Article 5(1), first subparagraph, points (ba) and (bb), Article 5(1a) and Article 5(1b) which shall apply from **2 December 2026**;
> (c) Chapter III, Sections 1, 2, and 3, with the exception of Article 6(5), shall apply (i) on **2 December 2027** as regards AI systems classified as high-risk pursuant to Article 6(2) and Annex III, and (ii) on **2 August 2028** as regards AI systems classified as high-risk pursuant to Article 6(1) and Annex I.
> (d) Articles 102 to 110 shall apply from [the date of entry into force of this amending Regulation]."

### B10. Annex XIV (NEW) – notified-body codes (selected)

```
AIP 0101…0112  AI systems subject to Annex I.A.1…I.A.12
AIB 0201       Remote biometric identification systems
AIB 0202       Biometric categorisation AI systems
AIB 0203       Emotion recognition AI systems
AIH 0101       Symbolic AI, expert/knowledge-based, search/optimisation
AIH 0201–0205  Machine-learning categories (structured data / signal+audio / text / image+video / RL excl. AIH 0401)
AIH 0301       Generative AI systems incl. GPAI-built
AIH 0401       Other emerging AI technologies incl. Agentic AI
```

---

## C. CONFLICTS WITH CURRENT KB

1. **Art. 51 GPAI thresholds (CLAUDE.md R27)**: The Omnibus text 9247/26 does **NOT** modify Art. 51. The 10²³ FLOPs / one-third fine-tune rule recorded in CLAUDE.md R27 is sourced from the 18 July 2025 Commission GPAI Guidelines, not from this Omnibus. **No conflict**, but the KB should not attribute those numbers to the Omnibus — keep them keyed to the Guidelines.
2. **Art. 113 dates (CLAUDE.md R27)**: The recorded **2 December 2027** (Annex III HRAIS) and **2 August 2028** (Annex I embedded) MATCH the compromise text. ✓ No update needed.
3. **`ROLE_SMALL_MID_CAP` (CLAUDE.md R27)**: Defined via Recommendation **2025/3500/EC** in CLAUDE.md, but the COMPROMISE text references **Recommendation (EU) 2025/1099** (Art. 3(14b)). The earlier recital still cites 2025/3500/EC. **Action**: align the citation in `role_obligations.py` and `definitions.py` to **Rec. (EU) 2025/1099** — the operative article wins over the recital.
4. **Art. 5 prohibition catalog**: The CLAUDE.md R38 note references "nudification/CSAM and other Art. 5 entries" but does not name the canonical sub-points. The Omnibus inserts them as `(ba)` and `(bb)` — verify that `ontology.py::PRACTICE_REGISTRY` keys these as new entries, not amendments to existing `5(1)(a)–(h)`.
5. **`scenario_classifier.py` safety-component fast-path**: The new Art. 6(1a) carve-out for "user assistance / performance optimisation / service efficiency / automation / convenience / quality control" is the **exact filter test the task brief mentions**. The current verb-stem marker set (`"user assistance"`, `"performance optimisation"`, `"automation"`, `"convenience"`, `"quality control"`) is likely insufficient — they currently route TO `limited`/`high_risk`; under R41 they must NOT trigger HRAIS classification absent a failure-mode endangerment.

---

## D. Predicted Regenold-probe impact

| Probe (R38 spec) | Affected by | Rubric direction |
| --- | --- | --- |
| **technical_doc / hardware (Annex IV.2.a)** | Art. 11(1) SME-simplified form + Art. 6(1a) carve-out + Art. 3(14) narrowed safety-component definition + Art. 43(3) preserved CA procedure | Answer must now distinguish "convenience / optimisation" use vs "safety function" use BEFORE invoking Annex IV.2.a. Likely **+correctness if the engine learns the new 6(1a) gate**; risk of **−strict** if it cites Annex IV.2.a for a system that's now non-HRAIS. |
| **emotion_recognition prohibition** | Art. 5(1)(ba)+(bb) NEW + Art. 5(1a)/(1b) scope clarifications; **Art. 5 emotion-recognition wording itself is NOT amended by this Omnibus** | Probe should still resolve to Art. 5(1)(f) (existing) + workplace/education carve-out. New (ba)/(bb) are orthogonal but the engine must NOT cross-fire them when the question is about emotion recognition. Risk: false-positive (ba)/(bb) anchor — verify scope.py and ontology aren't substring-matching "AI generates …" to (ba). |
| **doctor-patient transcription** | Art. 6(1a) carve-out ("user assistance, performance optimisation, automation, convenience"), Art. 4 softened literacy, Art. 11(1) simplified docs for SMEs | A standalone transcription tool for a clinician is precisely the "user assistance / convenience" case Art. 6(1a) excludes from safety-component status. If the engine still routes transcription to HRAIS, R41 will worsen its strict-correctness; the engine should route to Art. 50 transparency (if generative) + Art. 4 AI literacy (softened). **Expect a noticeable strict-correctness lift if Art. 6(1a) is wired.** |

---

## E. Suggested KB update PR scope (prioritised)

**P0 — must land for R41 release:**

1. `app/data/kb.py` — replace Art. 5 stub: add (ba) nudification, (bb) CSAM, (1a) scope rule, (1b) manipulation-floor. Effective date **2 Dec 2026**.
2. `app/data/kb.py` — replace Art. 6 stub: add (1a) carve-out, (1b) override, (1c) radio-spectrum/EMI exclusion.
3. `app/data/kb.py` — replace Art. 113 stub: new cascade with three branches.
4. `app/data/article_existence.py` — confirm 113 articles + 13 annexes still hold; add **Annex XIV** (NEW). Total now 113 articles + 14 annexes.
5. `app/data/kb.py` — add Art. 4a, Art. 60a, Art. 75a–75e stubs (5 new articles).
6. `app/data/definitions.py` — replace `safety_component`; add `sme` and `smc`.
7. `app/data/role_obligations.py` — fix `ROLE_SMALL_MID_CAP` citation from `2025/3500/EC` → `Rec. (EU) 2025/1099` (Art. 3(14b)).

**P1 — strong rubric impact:**

8. `app/data/kb.py` — Art. 4 (softened literacy), Art. 11(1) (SME simplified docs), Art. 63(1) (SME QMS extension), Art. 99(6)/(6a) (SME/SMC fine caps), Art. 75 (new AI Office scope).
9. `app/engines/scenario_classifier.py` — add **Art. 6(1a) gate**: when role + intended-use phrases match `{user assistance | performance optimisation | service efficiency | automation | convenience | quality control}` AND NO `endanger | malfunction | failure` marker AND NO Annex III category match → return non-HRAIS verdict citing Art. 6(1a), not the limited/high_risk fallback.
10. `app/data/agentic_taxonomy.py` — add **AIH 0401 "Agentic AI"** as the canonical Annex XIV code; cross-link to the four-axis taxonomy.
11. `app/data/ontology.py` — add `Practice.NON_CONSENSUAL_INTIMATE_MATERIAL` (→ Art. 5(1)(ba)) and `Practice.AI_CSAM` (→ Art. 5(1)(bb)) to `PRACTICE_REGISTRY`.

**P2 — completeness:**

12. `app/data/article_requirements_full.py` — schemas for Arts. 4a, 60a, 75a–75e, plus update Arts. 11/17/25/27/43/50/56/57/72.
13. `app/data/kb.py` — Annex I.A / Annex I.B / Annex VIII Section B / new Annex XIV.
14. `app/data/kb_xrefs.py` — add manual edges: Art. 5(1)(ba) ↔ Art. 99(1) (criminal-penalty link per recital 6c); Art. 6(1a) ↔ Art. 3(14); Art. 4a ↔ Art. 10(2)(f)+(g); Art. 75 ↔ Art. 75a–75e (governance chain); Art. 60a ↔ Art. 60 ↔ Art. 76(1).
15. `app/integrations/regenold/scope.py` — add governance anchors: "AI Office investigation", "periodic penalty payment", "negotiated disclosure", "small mid-cap enterprise", "real-world testing framework", "single application unified assessment".

**P3 — operational follow-ups (not blocking R41):**

16. Update CLAUDE.md R27 paragraph to clarify the SMC role's citation source (Rec. 2025/1099, not 2025/3500/EC).
17. Track future Commission delegated acts: Art. 2(13) (by 2 Aug 2027), Art. 96(1)(g) guidelines (by 1 Aug 2027), Art. 72(3) PMM template (by 2 Sep 2027), Annex XIV updates, Reg. 2023/1230 Annex III amendments (apply by 2 Aug 2028). Add to `reasoning.py` deferred-acts registry.
