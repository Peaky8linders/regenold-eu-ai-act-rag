"""Antifragile review — EXACT sub-point gold refs (R130 eval surface).

The R118 ``ANTIFRAGILE_GT.gold_refs`` are head-level ("Article N" / "Annex N")
by design (sub-citation errors were captured in ``mistakes``). The Regenold
rules PDF, however, scores references that "optionally [carry] a sub-point,
after a dot symbol", and the expert reviewer's remarks in
"Antifragile AI Review Questions and Answers.docx" EXPLICITLY state the correct
sub-citations for many questions.

This module pins those EXACT sub-point refs straight from the review remarks so
a live re-run can measure sub-point reference correctness (the axis R130 lifts)
in addition to the head-level axis. Each entry quotes the reviewer's source
sentence for traceability — these are NOT invented, they are the reviewer's
own corrections.

Where the reviewer specifies no sub-point (overview / definition-at-article-
level questions), the gold equals the head refs (no sub-point applies), so the
sub-point-exact scorer treats head == gold for those rows.
"""
from __future__ import annotations

# qid -> {"refs": [...exact wire refs incl. sub-points...], "source": "<reviewer quote>"}
ANTIFRAGILE_SUBPOINT_GOLD: dict[str, dict] = {
    # Overview / framework — head-level (no single sub-point applies).
    "q01": {"refs": ["Article 5", "Article 6", "Annex I", "Annex III", "Article 50", "Article 51"],
            "source": "tiered framework: unacceptable / high-risk / limited / GPAI (overview)"},
    "q02": {"refs": ["Article 5"],
            "source": "Art. 5 prohibits eight categories outright (whole Art. 5(1) list)"},
    "q03": {"refs": ["Article 6", "Annex I", "Annex III"],
            "source": "two-route classification under Art. 6; reviewer flags Art 6(1)(b)+6(3) omissions in prose"},
    "q04": {"refs": ["Article 6", "Annex III", "Annex I"],
            "source": "'sectors or applications' = Annex III categories + Annex I route"},
    # 50(1) interaction disclosure (provider) + 50(3) deployer disclosure.
    "q05": {"refs": ["Article 50.1", "Article 50.3"],
            "source": "Art. 50(1) interaction disclosure (provider); Art. 50(3) obligation is on deployers"},
    "q06": {"refs": ["Article 5", "Article 6", "Article 50"],
            "source": "minimal-risk = residual category; contrast against Art 5/6/50 tiers"},
    "q07": {"refs": ["Article 1", "Article 4"],
            "source": "guiding principles draw on Recital 27 (not citable); anchored on Art 1 purpose + Art 4 literacy"},
    # AI-system definition = Art. 3(1).
    "q08": {"refs": ["Article 3.1"],
            "source": "definition of 'AI system' is Art. 3(1)"},
    # High-risk penalties = Art. 99(4) (reviewer: 'substantively correct answer is Art. 99(4)').
    "q09": {"refs": ["Article 99.4"],
            "source": "the substantively correct answer is Art. 99(4); SMEs Art 99(6)"},
    "q10": {"refs": ["Article 3", "Article 25"],
            "source": "provider/deployer definitions in Art. 3; Art. 25 role transitions"},
    # Hardware = Annex IV, point 1(e); compute = Annex IV.2(c). Lexy's IV.2.a was wrong.
    "q11": {"refs": ["Annex IV.1.e", "Annex IV.2.c", "Article 11"],
            "source": "Hardware specification is required in Annex IV, point 1(e); Annex IV.2(c) computational resources"},
    # Emotion recognition: Art 5(1)(f); Annex III.1(c) (NOT III.5); Art 50(3).
    "q12": {"refs": ["Article 5.1.f", "Annex III.1.c", "Article 50.3"],
            "source": "Article 5(1)(f); emotion recognition is at Annex III.1(c); for Art 50 the precise reference is 50(3)"},
    # Transcription: high-risk only via Art 6(1) MDR route; NOT Annex III.
    "q13": {"refs": ["Article 6.1", "Annex I"],
            "source": "high-risk under Art 6(1) only (medical-device safety component); Annex III.5 citation inaccurate"},
    # X-ray: Art 6(1)/Annex I + Art 43 conformity.
    "q14": {"refs": ["Article 6.1", "Annex I", "Article 43"],
            "source": "Art. 6(1)/Annex I scenario; conformity assessment Art. 43; Art 5/Annex III not relevant"},
    # Clinical-trial triage: Annex III.5(a) (selection, not III.5(d) emergency) + Art 6 + Art 5(1)(g).
    "q15": {"refs": ["Annex III.5.a", "Article 6", "Article 5.1.g"],
            "source": "clinical-trial selection might fall under Annex III.5(a); Art 5(1)(g) biometric-categorisation conditional"},
    # GPAI provider obligations Art 53(1) + systemic Art 55/51; Art 113 unrelated.
    "q16": {"refs": ["Article 53.1", "Article 55", "Article 51"],
            "source": "all four Article 53(1) GPAI provider obligations; Art 55 systemic-risk; Art 51 (10^25 FLOPs); Art 113 unrelated"},
    # R&D scope: Art 2(6) exclusion + Art 2(8) pre-market testing.
    "q17": {"refs": ["Article 2.6", "Article 2.8"],
            "source": "a more precise citation Art 2(6); also Art 2(8) on pre-market testing"},
    # Chatbot: Art 50(1) interaction + Art 50(2) synthetic-content (limited-risk; probably not high-risk).
    "q18": {"refs": ["Article 50.1", "Article 50.2"],
            "source": "Art. 50(1) (provider interaction) + Art. 50(2) (provider-of-synthetic-content); probably not high-risk"},
    # Worker emotion monitoring = Art 5(1)(f).
    "q19": {"refs": ["Article 5.1.f"],
            "source": "Article 5(1)(f) bans inferring emotions of workers in workplace settings"},
    # Robotic surgery safety component = Art 6(1) Annex I; Art 14 human oversight engaged.
    "q20": {"refs": ["Article 6.1", "Annex I", "Article 14"],
            "source": "AI components are high-risk under Article 6(1); Art. 14 human-oversight design requirements"},
}
