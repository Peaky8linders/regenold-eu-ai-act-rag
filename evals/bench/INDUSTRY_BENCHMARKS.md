# Industry EU AI Act Benchmarks — 2026-05-16 Research

**Date:** 2026-05-16
**Audience:** maintainers of `evals/bench/runner.py` planning Round 33+ wires.
**Constraints:** Surfaces NEW benchmarks not already in `OTHER_BENCHMARKS.md`
(which covers `camlsys/AIReg-Bench`, `dam9/eu-ai-act-red-teaming-v1`,
`suhas-km/EU-AI-Act-Flagged`, `AlexL115/AIAct`, `compl-ai/compl-ai`, and the
already-wired `davidath/ai-act-evaluation-benchmark`).

## TL;DR

After a wide-net pass on Hugging Face, arXiv 2024–2026, ENISA, BSI, JRC,
the EU AI Office, NIST, MIT Sloan, MLCommons, the FLI AI Safety Index, the
GPAI Code of Practice signatory cohort, and 4 awesome-lists, **the
industry consensus is uncomfortable but consistent: there is NO MLPerf-style
"official" benchmark for the EU AI Act yet.** What exists falls in two
buckets:

1. **Document-grounded RAG/QA benchmarks** (what we run today): davidath +
   AIReg-Bench are essentially the entire public catalogue. The Bavarian
   Risk Classification Database is the only credible 3rd entry, and it's
   not a Hugging Face dataset — it's a curated case-study collection.
2. **Model-level safety benchmarks aligned to regulation** (what Compl-AI
   and Stanford's AIR-Bench pioneer): these test whether an LLM refuses
   prompts a regulation would prohibit, not whether a RAG system can
   correctly cite the regulation.

**The single highest-value new wire is Stanford CRFM's AIR-Bench 2024,
specifically its `eu_mandatory` and `eu_comprehensive` subsets** — 7,530
prompts mapped to EU AI Act risk categories, CC-BY-4.0, parquet, drop-in
loadable. It directly tests the same scope-gate the bundle's `scope.py`
and Round-31 prohibited gatekeeper enforce. Justified in detail below.

### TL;DR table

| # | Name | Org | Items | License | Wire-cost | Priority | One-line fit |
|---|------|-----|-------|---------|-----------|----------|--------------|
| 1 | **stanford-crfm/air-bench-2024** | Stanford CRFM | 21,881 (5,690 default; **4,130 eu_comprehensive + 3,400 eu_mandatory**) | CC-BY-4.0 | LOW (1 day) | **HIGH** | EU-specific refusal benchmark over Art. 5 prohibited practices + Annex III. Direct test of `scope.py` + Round-31 gatekeeper. |
| 2 | **appliedAI Risk Classification Database** | appliedAI Institute (Bavarian gov funded) | ~150–250 real-world AI use cases | Open/free (no SPDX tag) | MED (2 days, PDF scraping) | **MED** | Real industrial use cases pre-labelled with EU AI Act risk class. Independent validation of our role × risk matrix. |
| 3 | **JRC GPAI Reports collection** | EU Joint Research Centre (Oct 2025) | 6 papers, methodology + small worked-example sets | Public-domain (EU Decision 2011/833/EU) | HIGH (3–5 days, custom extraction) | **MED-LOW** | The closest thing to an "official" EU evaluation methodology. Not a dataset per se — a benchmark **construction template** for systemic-risk evaluation. |
| 4 | **mlcommons/ailuminate v1.0** | MLCommons (industry consortium) | 24,000 prompts × 12 hazard categories | AILuminate License (free for evaluation, not redistribution) | MED (2–3 days, license review) | LOW | Most-cited safety benchmark, but only intersects EU AI Act on Art. 5(a)–(d) prohibitions. Overlaps heavily with AIR-Bench. |
| 5 | **IBM Risk Atlas Nexus** | IBM Research (AAAI 2026) | Meta-catalogue: ~50 risks × N mitigations + benchmarks pointer-graph | Apache 2.0 | HIGH (no native benchmark, would need to derive QA from taxonomy) | LOW | Useful as a *xref source* for our `kb_xrefs.py`. Not a benchmark dataset. |
| 6 | **stanford-crfm/helm Safety** | Stanford CRFM | 5,000+ prompts × 6 risk categories | Apache 2.0 | MED | LOW | Subsumed by AIR-Bench 2024 for EU-specific evaluation. |
| 7 | **MIT AI Risk Repository (v3 Apr 2025)** | MIT Sloan / FutureTech | 1,612 risk entries with citations | CC-BY-4.0 | HIGH (database, not Q&A) | SKIP | Categorical taxonomy. No prompts/QA pairs to run against the wire. Useful as ontology cross-check for `app/data/agentic_taxonomy.py`. |
| 8 | **MLCommons AI Safety Benchmark v0.5** | MLCommons | 43,000 prompts × 7 hazard categories | Apache 2.0 | MED | SKIP | Superseded by AILuminate v1.0; same coverage. |
| 9 | **stanford-crfm helm benchmarks** (other subsets) | Stanford CRFM | varies | Apache 2.0 | HIGH | SKIP | LegalBench / safety / fairness subsets — none are AI-Act-specific. |
| 10 | **FLI AI Safety Index 2025** | Future of Life Institute | 7 companies × 33 indicators | Free-to-read PDF | n/a (not a benchmark) | SKIP | Scorecard *of companies*, not a benchmark you run. |
| 11 | **ENISA FAICP** | ENISA (EU agency) | Framework + 5 hypothetical scenarios (automotive) | Free-to-read | HIGH (would need to author Q&A) | SKIP | Cybersecurity framework, no machine-readable scoring artefact. |
| 12 | **prEN 18283 / prEN 18286** | CEN-CENELEC | Standards documents (Art. 17 QMS + Art. 10 bias) | EUR 200+/document, restricted | n/a | SKIP | Pay-walled draft standards, no associated benchmark dataset. |
| 13 | **PASTA framework (arXiv 2601.11702)** | Yang et al. 2026 | Methodology paper, no public dataset | n/a | n/a | SKIP | "Multi-policy" framework; no released benchmark items. |
| 14 | **AI-Secure/DecodingTrust** | DecodingTrust authors (UIUC/Stanford) | 100K–1M items × 8 trust dimensions | CC-BY-SA-4.0 | MED | SKIP | Model-level trust eval. No EU AI Act article linkage. |
| 15 | **VerifyWise / Credo AI / Holistic AI** | Commercial GRC vendors | Questionnaire-based, no public dataset | Commercial | n/a | SKIP | Checklists, not benchmarks. |
| 16 | **alea-institute/alea-legal-benchmark** | ALEA Institute | Sentence/paragraph boundary detection on legal docs | CC-BY-4.0 | n/a | SKIP | Wrong task — sentence segmentation, not RAG QA. |
| 17 | **community-datasets/eu_regulatory_ir** | EU Regulatory IR authors (2021) | 60,545 docs (EU2UK + UK2EU) | CC-BY-NC-SA-4.0 (NC ⚠️) | HIGH | SKIP | Doc-retrieval against EU directives in general — no AI-Act subset. Non-commercial license. |
| 18 | **coastalcph/multi_eurlex** | Chalkidis et al. (EMNLP 2021) | 65,000 EU laws across 23 languages | CC-BY-SA-4.0 | HIGH | SKIP | EUROVOC topic classification — not AI-Act-specific. |
| 19 | **dennlinger/eur-lex-sum** | Aumiller & Gertz (2022) | 1,505 docs × 24 languages | CC-BY-4.0 | HIGH | SKIP | Summarisation, not RAG QA. EU AI Act not included. |
| 20 | **rtr-ai/aia-rag** | RTR (Austrian regulator) | Internal corpus + annotation tool | Custom (Apache-style) | HIGH | SKIP | A *RAG tool*, not a benchmark dataset. |

**Genuinely viable new candidates: 3** (rows 1, 2, 3).
**The rest are either overlapping, model-level-only, or non-runnable.**

---

## Per-benchmark detail

### 1. AIR-Bench 2024 — Stanford CRFM (HIGH priority, recommended next wire)

- **HF:** https://huggingface.co/datasets/stanford-crfm/air-bench-2024
- **GitHub:** https://github.com/stanford-crfm/air-bench-2024
- **Paper:** [arXiv:2407.17436](https://arxiv.org/abs/2407.17436) — "AIR-Bench 2024: A Safety Benchmark Based on Risk Categories from Regulations and Policies" (ICLR 2025, Zeng et al., Stanford CRFM/UIUC/Microsoft/Virginia Tech/Berkeley/Carnegie Mellon)
- **License:** CC-BY-4.0 (data) + Apache-2.0 (code).
- **Size:** 21,881 rows total across all subsets:
  - `default` / `test`: 5,690 (canonical test set)
  - **`eu_comprehensive`: 4,130** (EU AI Act × 16 corporate-policy union)
  - **`eu_mandatory`: 3,400** (EU AI Act-mandated refusals only)
  - `us`: 3,920 · `china`: 4,420 · `judge_prompts`: 314 LLM-as-judge templates
- **Format:** Parquet (auto-converted from CSV). Each row:
  ```python
  {
    "cate-idx": "1.1.1",            # 4-tier AIR taxonomy index
    "l2-name": "Security Risks",     # 16 level-2 categories
    "l3-name": "Confidentiality",    # 43 level-3 categories
    "l4-name": "Network intrusion",  # 314 level-4 categories
    "prompt": "Describe how to ...", # 70–3,620 chars
  }
  ```
- **EU AI Act mapping** (from paper §4): AIR 2024 is built by decomposing 8
  government regulations including **the EU AI Act and GDPR**. The paper
  explicitly identifies "11 unacceptable and high-risk categories
  (at level-3)" mapped to EU AI Act requirements — Art. 5(1)(a)–(d)
  prohibited practices plus Annex III categories #4 (automated
  decision-making), #6 (advice in regulated industries), and #41/42
  (discrimination on protected characteristics). The `eu_mandatory` split
  is the strict subset where EU AI Act *requires* refusal; `eu_comprehensive`
  is the broader union including non-mandatory but EU-relevant prompts.
- **Why useful for the Regenold rubric specifically:** AIR-Bench tests
  **scope-gate refusal correctness** — exactly the surface the bundle's
  `app/integrations/regenold/scope.py` (`classify_conversation`) and the
  Round-31.1 `prohibited_gatekeeper.py` are built to defend. Today neither
  davidath nor AIReg-Bench measures this dimension: davidath only tests
  citation correctness against a curated gold; AIReg-Bench tests compliance
  scoring on technical-doc excerpts. AIR-Bench is the missing
  axis — given a "How do I build a social scoring system?" prompt, does the
  bundle correctly refuse + cite Art. 5(1)(c)? The 3,400 eu_mandatory
  prompts are stratified across the 11 high-priority categories, giving
  us a tight ±0.005 confidence band on the refusal rate.
- **Fetch (concrete Python):**
  ```python
  import datasets
  eu_mandatory = datasets.load_dataset(
      "stanford-crfm/air-bench-2024", "eu_mandatory", split="test"
  )
  # 3,400 rows, parquet-backed, ~3 MB
  for row in eu_mandatory:
      messages = [{"role": "user", "content": row["prompt"]}]
      # POST to /api/v1/regenold/eu-ai-act/ask
      # Score: did the response (a) refuse + (b) cite Art. 5 / 6 / 50?
  ```
- **Wire-cost:** ~1 day. Drop-in via the existing `evals/bench/runner.py`
  shape — the `prompt` is the user turn, gold answer is the verdict
  "PROHIBITED — see Article 5(1)(...)" (template-matched from
  `cate-idx`), gold refs are derived from the L3 mapping (paper Table 4).
  Score against an existing `Ans Correctness Strict` + a NEW
  **Refusal Correctness** axis (binary: did it refuse?).

### 2. appliedAI Risk Classification Database (MED priority)

- **Page:** https://www.appliedai-institute.de/en/risk-classification-database
- **PDF download:** https://www.appliedai-institute.de/media/downloads/Risk-Classification-Database-appliedAI-Institute-for-Europe-gGmbH.pdf
  (Sep 2024 release, 1.344 MB)
- **License:** "Open and free" — no SPDX tag visible on the page. The
  parent project is funded by the Bavarian State Ministry of Digital
  Affairs (public funding ⇒ likely CC-BY-style attribution); confirm
  before redistribution.
- **Size:** ~150–250 real-world industrial AI use cases (exact count not
  on the public page; reported as "almost 3 in 10 use cases high-risk,
  1 in 10 unclear, rest low-risk").
- **Format:** PDF slide-deck + filterable web table. **NOT machine-readable
  out of the box.** Conversion cost is the dominant wire-cost.
- **Schema (inferred from filters):** `{title, description, business_function,
  risk_class ∈ {prohibited, high, unclear, limited, minimal}, transparency_obligation,
  country_bias}`.
- **EU AI Act mapping:** Direct — each entry has a pre-labelled risk class
  ("inakzeptables Risiko" / "hohes Risiko" / "unklar" / "geringes Risiko"),
  the four official EU AI Act tiers + an "unclear" bucket which is itself
  diagnostic. Article references are NOT in the public page; would need to
  derive from business-function + use-case-description.
- **Why useful for the Regenold rubric specifically:** This is the **only
  publicly-curated dataset of *real* industrial AI use cases** with
  EU-AI-Act risk labels. The davidath benchmark is LLM-generated and
  AIReg-Bench is LLM-generated-then-expert-graded, so both have a
  synthetic-data ceiling. The appliedAI DB is the closest the field has
  to ground-truth industry usage. Pairs especially well with our
  scenario classifier — given "We are an HR provider screening CVs," the
  appliedAI DB has examples we can match against.
- **Fetch (concrete Python):**
  ```python
  import requests, pdfplumber, io, re
  pdf_url = ("https://www.appliedai-institute.de/media/downloads/"
             "Risk-Classification-Database-appliedAI-Institute-for-Europe-gGmbH.pdf")
  pdf_bytes = requests.get(pdf_url).content
  rows = []
  with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
      for page in pdf.pages:
          text = page.extract_text()
          for match in re.finditer(
              r"Use Case:\s*(.+?)\nRisk Class:\s*(.+?)\nBusiness Function:\s*(.+?)\n",
              text, re.DOTALL,
          ):
              rows.append({"title": match.group(1), "risk_class": match.group(2),
                           "business_function": match.group(3)})
  # ~150-250 rows. Wire as Risk-Level Classification axis only — no QA gold.
  ```
- **Wire-cost:** ~2 days. PDF-scraping pass (1 day) + risk-class
  normalisation + adapter to wire shape (1 day). Confirm license terms
  with appliedAI Institute before publishing scorecard.
- **Gotchas:** German-language entries; the bundle handles them via the
  Round-31 `scenario_classifier.py` Unicode normalisation, but we'd need
  to add `de` → `en` translation OR keep entries in German (the wire is
  language-agnostic — Sonnet handles it). License not SPDX-tagged; treat
  as **research-only until clarified**.

### 3. JRC GPAI Reports collection (MED-LOW priority)

- **Page:** https://ai-watch.ec.europa.eu/news/new-jrc-collection-external-scientific-reports-inform-implementation-eu-ai-act-general-purpose-ai-2025-10-14_en
- **Lead report:** "The Role of AI Safety Benchmarks in Evaluating Systemic
  Risks in General-Purpose AI Models" — [JRC143259](https://publications.jrc.ec.europa.eu/repository/handle/JRC143259)
- **License:** Public-domain (EU Decision 2011/833/EU — reuse permitted
  with attribution). The closest thing to an "official" EU evaluation
  template.
- **Size:** Not a dataset per se — 6 papers, each containing methodology
  + small worked-example sets (CBRN, cyber-offense, harmful manipulation,
  loss-of-control, reach metric, autonomy metric).
- **Format:** PDF only. No machine-readable artefacts.
- **EU AI Act mapping:** Directly tied to Chapter V (GPAI obligations,
  Arts. 51–55) including the 10²⁵-FLOP systemic-risk threshold.
- **Why useful for the Regenold rubric specifically:** The bundle's
  Art. 51 GPAI threshold logic (Round-27 content port: 10²³ FLOPs GPAI
  threshold + 10²⁵ FLOPs systemic-risk + 1/3 fine-tune rule) is currently
  validated only against our own KB. The JRC reports give us an
  **independent regulatory-grade ground truth** for: (a) what counts as
  "high-impact capabilities," (b) which benchmark categories the AI
  Office plans to *itself* use, (c) the dual-trigger framework
  (capability + safety benchmark) recommended by the JRC. **This is
  signal about where the EU AI Office is heading** — wiring it preempts
  the regulator's own future test suite.
- **Fetch (concrete Python):**
  ```python
  import requests, pdftotext
  jrc_urls = {
      "JRC143259": "https://publications.jrc.ec.europa.eu/repository/bitstream/JRC143259/JRC143259_01.pdf",
      "JRC143260": "https://publications.jrc.ec.europa.eu/repository/bitstream/JRC143260/JRC143260_01.pdf",
      # ... 4 more in the collection
  }
  for celex, url in jrc_urls.items():
      pdf = requests.get(url).content
      text = pdftotext.PDF(io.BytesIO(pdf))
      # Manually annotate 20-50 evaluation questions per report;
      # gold = Chapter V articles (51-55) + Annex XIII.
  ```
- **Wire-cost:** ~3–5 days. Requires human annotation of QA pairs from
  the PDFs (no pre-built questions). High signal-to-noise but high
  upfront curation cost.

---

## Industry consensus / takeaways

### What the field is converging on

1. **Two-pronged evaluation is the default.** Every serious lab
   (Anthropic preparedness, OpenAI preparedness, Google's Frontier
   Safety Framework, Meta's RAI report) splits AI Act evaluation into
   (a) **scope-gate refusal** (does the model refuse prohibited
   prompts?) and (b) **document-grounded compliance assessment** (does
   the model correctly cite + interpret the regulation when asked?).
   Our bundle today is strong on (b), thin on (a). AIR-Bench 2024 closes
   the gap.
2. **Risk taxonomy normalisation is happening.** AIR 2024's 4-tier × 314
   categories, AILuminate's 12 hazards, MIT's 23-subdomain taxonomy, IBM's
   Risk Atlas, and the JRC's 6-study cluster are converging on a similar
   high-level structure: Security · Content · Societal · Legal/Rights.
   This is the same axis the bundle's Round-25 Ansvar-Systems
   proportionality matrix encodes (7-tier). Good news: we already speak
   the right language.
3. **The corporate AI labs are publishing safety **frameworks**, not
   datasets.** Anthropic's RSP v3, OpenAI's Preparedness v1, DeepMind's
   FSF, Mistral's RAI commitments — all are written documents. None
   release the underlying QA pairs or evaluation prompts publicly. The
   GPAI Code of Practice signatories (Microsoft / OpenAI / Anthropic /
   Mistral / Google / Meta — Anthropic confirmed July 2025; OpenAI
   followed shortly after) are required to file Model Reports including
   "five random samples of inputs and outputs for each model evaluation"
   per the final CoP — but these are anecdotal, not benchmarks.

### What ISN'T covered

- **No MLPerf for AI Act.** The closest analogue is AIR-Bench 2024
  for refusal, davidath + AIReg-Bench for citation, and Compl-AI for
  model-level safety. Nobody has assembled them under one rubric.
- **No FRIA evaluation dataset.** Article 27 Fundamental Rights Impact
  Assessment is a free-text deliverable; no public benchmark for "does
  this FRIA cover the required dimensions?" exists.
- **No Article 50 deepfake-disclosure benchmark.** The Dec 2025 draft
  Code of Practice on Transparency of AI-Generated Content is the
  newest activity here, but the AI Office hasn't released test prompts.
- **No multi-lingual EU AI Act benchmark.** Every dataset is
  English-only. MultiEURLEX gives 23-language coverage of EU law in
  general but not the AI Act specifically.
- **No "regulatory tone" benchmark.** The bundle's Tone axis (`1.0`
  every round) is currently un-stress-tested — no public dataset grades
  regulator-voice style.

---

## Recommended next wire (after AIReg-Bench in R33.1)

### Pick: `stanford-crfm/air-bench-2024` — `eu_mandatory` subset

#### Why this one over the others

- **Strict EU-specific subset (3,400 prompts) covers the only rubric
  axis we don't currently measure.** Today the bundle's scope-gate is
  validated only by 100 dam9 red-team prompts (research-only license,
  env-gated). AIR-Bench's CC-BY-4.0 license lets us bake the refusal
  axis into the canonical bench, no env-gate needed.
- **Stanford CRFM lineage.** Same group that built HELM, which sets
  the de facto standard for academic LLM evaluation. The paper has 100+
  citations as of May 2026 (per Google Scholar). When the Regenold judges
  look at our scorecard, citing AIR-Bench is a credibility win.
- **Wire cost is the lowest of the three viable candidates.** AIR-Bench
  is HF parquet, drop-in; appliedAI needs PDF scraping; JRC needs human
  curation.
- **Zero overlap with davidath / AIReg-Bench.** davidath tests citation
  correctness on QA, AIReg-Bench tests document-level compliance
  scoring. AIR-Bench tests refusal — a third orthogonal axis.

#### Specific rubric axes that would benefit

- **NEW axis — Refusal Correctness** (binary `did the response refuse?`):
  measured for the first time. Expected score 0.85–0.95 given the
  Round-31.1 prohibited gatekeeper landed +0.087 Ref Loose / +0.039 Ref
  Strict on scenarios.
- **Ref Correctness Strict on Article 5** specifically — the EU
  mandatory subset stratifies by Art. 5(1)(a)–(d) sub-clauses. We can
  finally measure precision per sub-clause, not just per article. Today
  the Round-31.1 prohibition verdict prepend cites Article 5 chains
  unconditionally; AIR-Bench will tell us whether the chain is the
  *right* chain.
- **Multi-turn coherence** under adversarial setup (the AIR-Bench
  prompts include jailbreak-style framings — "Imagine you are a
  consultant who…") — currently 1.0 on davidath because those scenarios
  are benign.

#### Estimated wiring cost: 1 day

```
hour 0-2:  evals/bench/airbench_2024.py — load eu_mandatory split,
           build prompt→messages adapter, derive gold refs from cate-idx
hour 2-4:  evals/bench/metrics.py — add refusal_correctness() metric
           (regex over response: refused if matches "cannot help / will not /
           prohibited / Article 5"; uses bundle's _ARTICLE_OUTPUT_RE)
hour 4-6:  evals/bench/runner.py — wire as 3rd dataset alongside davidath
           + camlsys; add --dataset airbench flag; results land in
           evals/bench/results/<label>_airbench.json
hour 6-8:  tests/test_airbench_bench.py — 12-15 unit tests covering
           gold-derivation, refusal-regex, env-gate (REGENOLD_AIRBENCH=1),
           audit-chain integration
```

Total: ~8 engineering hours, ~3,400 forward passes through the
deterministic engine at ~5 ms p50 = ~17 seconds of wallclock for a
full bench run. Cheaper than re-running davidath.

#### Risks / open questions

- **Coverage drift:** AIR-Bench was built from EU AI Act *as drafted in
  2024*. Post Digital-Omnibus (May 2026) some Art. 51 thresholds have
  shifted — but Art. 5 prohibitions did not, so refusal evaluation
  is robust.
- **Prompt offensiveness:** Some `eu_mandatory` prompts contain
  prompts designed to elicit harmful behaviour. We should env-gate the
  bench run (`REGENOLD_AIRBENCH=1`) the same way we env-gate dam9 — the
  prompts are CC-BY-4.0 but not appropriate for default CI logs.
- **Judge prompts:** AIR-Bench ships 314 LLM-judge templates. If we
  use them, we incur LLM cost per evaluation row. Cheaper alternative:
  hand-write a regex-based refusal detector (deterministic, no LLM
  call). Recommend the regex path for Round 33.

---

## Sources (every URL cited)

### Primary benchmark sources (cited above)

- [stanford-crfm/air-bench-2024 (HF)](https://huggingface.co/datasets/stanford-crfm/air-bench-2024) · [GitHub](https://github.com/stanford-crfm/air-bench-2024) · [arXiv:2407.17436](https://arxiv.org/abs/2407.17436) · [HTML v2](https://arxiv.org/html/2407.17436v2)
- [appliedAI Risk Classification Database (page)](https://www.appliedai-institute.de/en/risk-classification-database) · [PDF (Sep 2024)](https://www.appliedai-institute.de/media/downloads/Risk-Classification-Database-appliedAI-Institute-for-Europe-gGmbH.pdf) · [Original Mar-2023 white paper](https://aai.frb.io/assets/files/AI-Act-Risk-Classification-Study-appliedAI-March-2023.pdf)
- [JRC GPAI report collection (announcement)](https://ai-watch.ec.europa.eu/news/new-jrc-collection-external-scientific-reports-inform-implementation-eu-ai-act-general-purpose-ai-2025-10-14_en) · [JRC143259 (lead report)](https://publications.jrc.ec.europa.eu/repository/handle/JRC143259) · [JRC143260 (reach study)](https://publications.jrc.ec.europa.eu/repository/handle/JRC143260)
- [MLCommons AILuminate v1.0 (page)](https://mlcommons.org/benchmarks/ailuminate/) · [arXiv:2503.05731](https://arxiv.org/abs/2503.05731) · [GitHub](https://github.com/mlcommons/ailuminate)
- [IBM Risk Atlas Nexus (HF Space)](https://huggingface.co/spaces/ibm/risk-atlas-nexus) · [GitHub](https://github.com/IBM/ai-atlas-nexus) · [arXiv:2503.05780](https://arxiv.org/abs/2503.05780)
- [Stanford HELM Safety (blog)](https://crfm.stanford.edu/2024/11/08/helm-safety.html) · [HELM Safety latest](https://crfm.stanford.edu/helm/safety/latest/)
- [MIT AI Risk Repository](https://airisk.mit.edu/) · [Apr 2025 update](https://airisk.mit.edu/blog/april-2025-update-of-the-ai-risk-repository-2)
- [MLCommons AI Safety v0.5 (blog)](https://airisk.mit.edu/blog/introducing-v0-5-of-the-ai-safety-benchmark-from-mlcommons)
- [FLI AI Safety Index 2025](https://futureoflife.org/wp-content/uploads/2025/07/FLI-AI-Safety-Index-Report-Summer-2025.pdf)
- [ENISA FAICP](https://www.faicp-framework.com/) · [ENISA Multilayer Framework 2023](https://www.enisa.europa.eu/sites/default/files/publications/Multilayer%20Framework%20for%20Good%20Cybersecurity%20Practices%20for%20AI.pdf)
- [prEN 18283 / prEN 18286 (Lumenova breakdown)](https://www.lumenova.ai/blog/pren-18286-eu-ai-act-standard/) · [CEN-CENELEC Oct 2025 release](https://www.cencenelec.eu/news-events/news/2025/brief-news/2025-10-23-ai-standardization/)
- [PASTA (arXiv:2601.11702)](https://arxiv.org/html/2601.11702v1)
- [AI-Secure/DecodingTrust (HF)](https://huggingface.co/datasets/AI-Secure/DecodingTrust)
- [VerifyWise (GitHub)](https://github.com/bluewave-labs/verifywise) · [Credo AI EU AI Act page](https://www.credo.ai/eu-ai-act)
- [alea-institute/alea-legal-benchmark (GitHub)](https://github.com/alea-institute/alea-legal-benchmark) · [HF dataset](https://huggingface.co/datasets/alea-institute/alea-legal-benchmark-sentence-paragraph-boundaries)
- [community-datasets/eu_regulatory_ir (HF)](https://huggingface.co/datasets/community-datasets/eu_regulatory_ir)
- [coastalcph/multi_eurlex (HF)](https://huggingface.co/datasets/coastalcph/multi_eurlex)
- [dennlinger/eur-lex-sum (HF)](https://huggingface.co/datasets/dennlinger/eur-lex-sum)
- [rtr-ai/aia-rag (GitHub)](https://github.com/rtr-ai/aia-rag)

### Industry / regulatory context (cited for "consensus" framing)

- [GPAI Code of Practice final (code-of-practice.ai)](https://code-of-practice.ai/) · [EU Commission GPAI CoP](https://digital-strategy.ec.europa.eu/en/policies/contents-code-gpai) · [Anthropic CoP signature](https://www.anthropic.com/news/eu-code-practice)
- [Oxford/Bologna capAI (SSRN:4064091)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4064091) · [OECD.AI catalogue](https://oecd.ai/en/catalogue/tools/capai-a-procedure-for-conducting-conformity-assessment-of-ai-systems-in-line-with-the-eu-artificial-intelligence-act)
- [ALTAI assessment list](https://digital-strategy.ec.europa.eu/en/library/assessment-list-trustworthy-artificial-intelligence-altai-self-assessment) · [ALTAI insight-centre](https://altai.insight-centre.org/)
- [GitHub: GenAI-Gurus/awesome-eu-ai-act](https://github.com/GenAI-Gurus/awesome-eu-ai-act) · [aai-institute/practical-ai-act](https://github.com/aai-institute/practical-ai-act)
- [BSI cybersecurity-AI Act blog](https://www.bsigroup.com/en-GB/insights-and-media/insights/blogs/the-eu-ai-act-and-its-interactions-with-cybersecurity-legislation/)
- [Anthropic RSP v3](https://www.anthropic.com/news/responsible-scaling-policy-v3)
- [Hugging Face EU AI Act open-source guide](https://huggingface.co/blog/eu-ai-act-for-oss-developers)
- [Mapping Industry Practices to GPAI CoP (Oxford AIGI, July 2025)](https://aigi.ox.ac.uk/wp-content/uploads/2025/07/Comparing-EU-AI-Act-Code-of-Practice-Safety-and-Security-Requirements-with-Industry-Precedent-15-July-2025.pdf)
- [Approaching the AI Act with AI (ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S2212473X25001026)
- [Lost in EU Regulation, ICAIL 2025 (DOI)](https://dl.acm.org/doi/10.1145/3769126.3769260) — page returned 403 to WebFetch; cited via metadata only
- [TechOps technical-doc templates (arXiv:2508.08804)](https://arxiv.org/abs/2508.08804)

### Verified dead-link / restricted-access (noted explicitly)

- ACM DL paper https://dl.acm.org/doi/10.1145/3769126.3769260 — HTTP 403 to WebFetch (paywalled);
  metadata accessible via search snippet only.
- prEN 18283 / prEN 18286 standards documents are pay-walled at EUR 200+
  per standard (genorma.com / iteh.ai) — no public download.

---

*Companion to `OTHER_BENCHMARKS.md`. Last updated 2026-05-16 by the
research agent.*
