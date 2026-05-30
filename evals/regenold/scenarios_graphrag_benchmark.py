"""GraphRAG-paper benchmark probe set (R99 add-on).

Source: a related EU AI Act GraphRAG-system paper, Appendix B.2 dataset.
Two groups:

* ``GROUND_TRUTH`` — 10 questions each paired with an expected answer +
  reference list (Articles / Recitals). We score these.
* ``NO_GROUND_TRUTH`` — 10 questions with no predefined answer. We run them
  live and report the engine's predicted references + tone + latency only
  (there is no gold to score against).

Wire-citation note
------------------
The Regenold wire emits only ``Article N`` / ``Annex N`` references (never
Recitals — see CLAUDE.md hard rule #1 + R47-B). The paper's gold reference
lists mix Articles and Recitals; we encode the **Article/Annex heads only**
into ``expected_refs`` and record the full paper reference string in
``paper_refs`` for provenance. Two ground-truth questions (gt_06 minimal
risk → Recital 53; gt_07 guiding principles → Recitals 1/7/48) have
**recital-only** gold with no wire-citable article, flagged ``recital_only``;
the runner excludes them from the reference-correctness aggregate (keyword
recall + tone are still scored).

Schema (GROUND_TRUTH) matches runner_v2 tricky schema + extra provenance:

    {
        "id", "question", "expected_refs", "expected_keywords",
        "category", "notes", "paper_refs", "recital_only" (bool),
    }
"""
from __future__ import annotations

# ── Group 1 — questions WITH ground truth ────────────────────────────────
GROUND_TRUTH: list[dict] = [
    {
        "id": "gt_01",
        "question": "What risk categories are provided for AI systems?",
        "expected_refs": ["Article 3", "Article 5", "Article 6", "Article 50"],
        "expected_keywords": ["unacceptable risk", "limited risk", "minimal risk"],
        "category": "risk_taxonomy",
        "paper_refs": (
            "Articles: 3(39),3(40),3(41),5(1),6(1),6(2),50(1),50(2); "
            "Recitals: 26,50,52,54,55,56,57,58,59,61,64,66,132,165"
        ),
        "recital_only": False,
        "notes": "Four-tier risk pyramid. Gold spans Art. 3/5/6/50.",
    },
    {
        "id": "gt_02",
        "question": (
            "What types of AI systems or practices are explicitly prohibited "
            "by the AI Act?"
        ),
        "expected_refs": ["Article 5"],
        "expected_keywords": ["subliminal", "social scoring", "biometric"],
        "category": "prohibited",
        "paper_refs": "Articles: 5",
        "recital_only": False,
        "notes": "Art. 5 prohibited practices.",
    },
    {
        "id": "gt_03",
        "question": "What is the definition of high risk?",
        "expected_refs": ["Article 6"],
        "expected_keywords": ["health", "safety", "fundamental rights"],
        "category": "high_risk_definition",
        "paper_refs": "Articles: 6",
        "recital_only": False,
        "notes": "Art. 6 high-risk classification; answer also cites Annex III.",
    },
    {
        "id": "gt_04",
        "question": (
            "Which sectors or applications are considered high-risk under the "
            "regulation?"
        ),
        "expected_refs": ["Article 6"],
        "expected_keywords": ["safety component", "annex i", "conformity assessment"],
        "category": "high_risk_sectors",
        "paper_refs": "Articles: 6",
        "recital_only": False,
        "notes": "Art. 6(1) Annex I safety-component path + Art. 6(2) Annex III.",
    },
    {
        "id": "gt_05",
        "question": "How should users be informed when interacting with AI systems?",
        "expected_refs": ["Article 50"],
        "expected_keywords": ["informed", "interacting", "disclose"],
        "category": "transparency",
        "paper_refs": "Articles: 50",
        "recital_only": False,
        "notes": "Art. 50 transparency / interaction disclosure.",
    },
    {
        "id": "gt_06",
        "question": "What are AI systems with minimal risks?",
        "expected_refs": [],  # recital-only gold (Recital 53) — no wire-citable article
        "expected_keywords": ["structured data", "duplicates", "minimal"],
        "category": "minimal_risk",
        "paper_refs": "Recitals: 53",
        "recital_only": True,
        "notes": (
            "Recital-only gold — wire emits Articles/Annexes only, so this row "
            "is excluded from the reference-correctness aggregate."
        ),
    },
    {
        "id": "gt_07",
        "question": "What are the guiding principles established by the AI Act?",
        "expected_refs": [],  # recital-only gold (Recitals 1,7,48)
        "expected_keywords": ["fundamental rights", "democracy", "rule of law"],
        "category": "guiding_principles",
        "paper_refs": "Recitals: 1,7,48",
        "recital_only": True,
        "notes": (
            "Recital-only gold — excluded from the reference-correctness "
            "aggregate (keyword recall + tone still scored)."
        ),
    },
    {
        "id": "gt_08",
        "question": (
            "What is the definition of a \"system of artificial intelligence\"?"
        ),
        "expected_refs": ["Article 3"],
        "expected_keywords": ["machine-based", "autonomy", "infers"],
        "category": "definition",
        "paper_refs": "Articles: 3(1)",
        "recital_only": False,
        "notes": "Art. 3(1) definition of an AI system.",
    },
    {
        "id": "gt_09",
        "question": (
            "What are the penalties for violating the provisions of the "
            "regulation for high-risk AI systems?"
        ),
        "expected_refs": ["Article 99"],
        "expected_keywords": ["administrative", "fine", "turnover"],
        "category": "penalties",
        "paper_refs": "Articles: 99",
        "recital_only": False,
        "notes": "Art. 99 penalties (up to EUR 15m or 3% worldwide turnover).",
    },
    {
        "id": "gt_10",
        "question": "What is the difference between the deployer and the provider?",
        "expected_refs": ["Article 3", "Article 16"],
        "expected_keywords": ["provider", "deployer", "trademark"],
        "category": "roles",
        "paper_refs": "Articles: 3(3),3(4),16",
        "recital_only": False,
        "notes": "Art. 3(3)/(4) definitions + Art. 16 provider responsibility.",
    },
]

# ── Group 2 — questions WITHOUT ground truth ──────────────────────────────
# Run live; report predicted refs + tone + latency only (no scoring).
# ``doctrinal_anchor`` is an informational note (NOT scored) of the primary
# AI-Act article(s) a domain expert would expect — for qualitative review.
NO_GROUND_TRUTH: list[dict] = [
    {
        "id": "ng_01",
        "question": "What criteria exist for assessing the risk of an AI system?",
        "doctrinal_anchor": "Article 7 (Annex III amendment criteria) / Article 9",
    },
    {
        "id": "ng_02",
        "question": (
            "What are the sanctions for violating the provisions of the "
            "regulation for transparency risk systems?"
        ),
        "doctrinal_anchor": "Article 99",
    },
    {
        "id": "ng_03",
        "question": "What obligations exist for deployers of high-risk AI systems?",
        "doctrinal_anchor": "Article 26 (+ Article 27 FRIA)",
    },
    {
        "id": "ng_04",
        "question": "What requirements must AI systems classified as high-risk meet?",
        "doctrinal_anchor": "Articles 8-15",
    },
    {
        "id": "ng_05",
        "question": (
            "What obligations do providers of high-risk AI systems have in terms "
            "of transparency and technical documentation?"
        ),
        "doctrinal_anchor": "Articles 11, 13 (+ Annex IV)",
    },
    {
        "id": "ng_06",
        "question": "What does a conformity assessment consist of?",
        "doctrinal_anchor": "Article 43 (+ Annex VI / VII)",
    },
    {
        "id": "ng_07",
        "question": "What does systemic-risk mean?",
        "doctrinal_anchor": "Article 3(65) / Article 51 / Article 55",
    },
    {
        "id": "ng_08",
        "question": "What is the definition of General-purpose AI?",
        "doctrinal_anchor": "Article 3(63)/(66)",
    },
    {
        "id": "ng_09",
        "question": "What are the components of a quality management system?",
        "doctrinal_anchor": "Article 17",
    },
    {
        "id": "ng_10",
        "question": (
            "What are the requirements for documenting bias mitigation measures "
            "in AI models?"
        ),
        "doctrinal_anchor": "Article 10 (+ Article 9 / Article 15)",
    },
]
