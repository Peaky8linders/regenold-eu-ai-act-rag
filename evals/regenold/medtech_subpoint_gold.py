"""Medtech GraphRAG-bench v124 — EXACT sub-point gold (R130 eval surface).

The R124 ``scenarios_medtech_graphrag_v124.GROUND_TRUTH`` ships head-level
``expected_refs`` ("Article 6", "Annex III"). Its ``gold_answer`` prose,
however, cites the EXACT sub-point for each scenario (the golden dataset's own
words). This module pins those sub-points straight from the v124 gold answers,
so a live re-run can measure sub-point reference correctness in addition to the
head-level axis.

Only the rows whose golden answer names a single, unambiguous operative
sub-point are listed; every other v124 row is genuinely article-level
(deployer obligations Art 26, human oversight Art 14, data governance Art 10,
post-market Art 72/73, penalties Art 99, …) and the head ``expected_refs`` IS
the gold — so the sub-point scorer treats head == gold for those.

Each entry quotes the v124 gold answer's source clause for traceability.
"""
from __future__ import annotations

# grb id -> {"refs": [...exact wire refs incl. sub-points...], "source": "<gold-answer clause>"}
MEDTECH_SUBPOINT_GOLD: dict[str, dict] = {
    "grb_01": {"refs": ["Article 6.1", "Annex I", "Article 43"],
               "source": "Under Article 6(1) an AI system that is a medical device ... covered by Annex I"},
    "grb_03": {"refs": ["Annex III.5.d", "Article 6.2"],
               "source": "Annex III point 5 lists AI systems used to dispatch ... emergency ... triage; Article 6(2) makes Annex III high-risk"},
    "grb_04": {"refs": ["Annex III.5.a", "Article 6.2"],
               "source": "Annex III point 5(a) classifies AI used to evaluate eligibility for essential public assistance ... under Article 6(2)"},
    "grb_06": {"refs": ["Article 5.1.f"],
               "source": "Article 5(1)(f) prohibits AI that infers emotions in the workplace ... but exempts medical/safety reasons"},
    "grb_09": {"refs": ["Article 43.3", "Annex I"],
               "source": "Article 43(3) ... single conformity-assessment ... Annex I medical-device legislation"},
    "grb_19": {"refs": ["Annex III.1.a", "Article 6"],
               "source": "Annex III point 1(a) makes remote biometric identification high-risk; excludes 1:1 verification"},
    "grb_21": {"refs": ["Article 6.1", "Article 43.3", "Annex I"],
               "source": "high-risk under Article 6(1) (MDR in Annex I); under Article 43(3) the single integrated assessment"},
}
