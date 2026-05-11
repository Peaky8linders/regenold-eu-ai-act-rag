"""Extended eval scenarios for the Digital Omnibus + newly-added KB articles.

This module supplements ``scenarios.py`` and the two earlier extension
files with scenarios that exercise:

* Articles added in the May 2026 KB expansion (Arts. 21, 50.1-50.4,
  58, 59, 61-63, 67-69, 85-87, 89, 95, 100, 101, 111, 112; Annexes II,
  V, VIII).
* Digital Omnibus political-agreement changes (7 May 2026):
  - Art. 113 deferral of Annex III high-risk to 2 Dec 2027 and Annex I
    to 2 Aug 2028.
  - New Art. 5 prohibition for AI-CSAM / non-consensual intimate
    imagery generators.
  - SME relief extended to "small mid-cap" enterprises (Art. 62).
  - EU-level sandbox + DSA bridge for VLOPs/VLOSEs.

Each scenario carries deterministic checks against the response payload,
following the pattern established in the base scenarios + the two earlier
extension files. Imported by ``scenarios.py`` lazily so this file can
be added/removed without breaking the runner.
"""
from __future__ import annotations

from evals.regenold.scenarios import (
    Scenario,
    ScenarioCheck,
    _has_reference,
    _refused,
)


EXTRA_OMNIBUS_SCENARIOS: tuple[Scenario, ...] = (
    # ═══════════════════════════════════════════════════════════════════
    # A. Newly-covered articles — must cite the right anchor.
    # ═══════════════════════════════════════════════════════════════════
    Scenario(
        id="omnibus_art21_cooperation",
        category="in_scope_basic",
        description="Art. 21 — duty to cooperate with national competent authorities.",
        messages=(
            {
                "role": "user",
                "content": (
                    "What information must a provider supply to a national "
                    "competent authority on request?"
                ),
            },
        ),
        checks=(
            ScenarioCheck("not_refused", lambda b: not _refused(b)),
            ScenarioCheck(
                "cites_art_21",
                lambda b: _has_reference(b, "Article 21"),
            ),
        ),
    ),
    Scenario(
        id="omnibus_art85_right_to_complain",
        category="in_scope_basic",
        description="Art. 85 — right to lodge a complaint with market-surveillance authority.",
        messages=(
            {
                "role": "user",
                "content": "Who can complain about an AI Act infringement?",
            },
        ),
        checks=(
            ScenarioCheck("not_refused", lambda b: not _refused(b)),
            ScenarioCheck(
                "cites_art_85",
                lambda b: _has_reference(b, "Article 85"),
            ),
        ),
    ),
    Scenario(
        id="omnibus_art86_right_to_explanation",
        category="in_scope_basic",
        description="Art. 86 — right to explanation of AI-driven decisions.",
        messages=(
            {
                "role": "user",
                "content": (
                    "Do I have a right to an explanation when an AI system makes a "
                    "decision that affects me?"
                ),
            },
        ),
        checks=(
            ScenarioCheck("not_refused", lambda b: not _refused(b)),
            ScenarioCheck(
                "cites_art_86",
                lambda b: _has_reference(b, "Article 86"),
            ),
        ),
    ),
    Scenario(
        id="omnibus_art87_whistleblower",
        category="in_scope_basic",
        description="Art. 87 — whistleblower protection under Directive 2019/1937.",
        messages=(
            {
                "role": "user",
                "content": "What protections exist for whistleblowers reporting AI Act infringements?",
            },
        ),
        checks=(
            ScenarioCheck("not_refused", lambda b: not _refused(b)),
            ScenarioCheck(
                "cites_art_87",
                lambda b: _has_reference(b, "Article 87"),
            ),
        ),
    ),
    Scenario(
        id="omnibus_art100_edps_penalties",
        category="penalties",
        description="Art. 100 — EDPS-imposed penalties on EU institutions.",
        messages=(
            {
                "role": "user",
                "content": "What fines apply to EU institutions for AI Act breaches?",
            },
        ),
        checks=(
            ScenarioCheck("not_refused", lambda b: not _refused(b)),
            ScenarioCheck(
                "cites_art_100",
                lambda b: _has_reference(b, "Article 100"),
            ),
        ),
    ),
    Scenario(
        id="omnibus_art101_gpai_penalties",
        category="penalties",
        description="Art. 101 — Commission penalties for GPAI providers.",
        messages=(
            {
                "role": "user",
                "content": "What penalty can the Commission impose on a GPAI provider?",
            },
        ),
        checks=(
            ScenarioCheck("not_refused", lambda b: not _refused(b)),
            ScenarioCheck(
                "cites_art_101",
                lambda b: _has_reference(b, "Article 101"),
            ),
        ),
    ),
    Scenario(
        id="omnibus_art112_review_clause",
        category="in_scope_basic",
        description="Art. 112 — Commission evaluation and review of the Regulation.",
        messages=(
            {
                "role": "user",
                "content": "When does the Commission review the EU AI Act?",
            },
        ),
        checks=(
            ScenarioCheck("not_refused", lambda b: not _refused(b)),
            ScenarioCheck(
                "cites_art_112",
                lambda b: _has_reference(b, "Article 112"),
            ),
        ),
    ),
    Scenario(
        id="omnibus_art95_voluntary_codes",
        category="in_scope_basic",
        description="Art. 95 — voluntary codes of conduct for non-high-risk AI.",
        messages=(
            {
                "role": "user",
                "content": "Are codes of conduct mandatory for non-high-risk AI systems?",
            },
        ),
        checks=(
            ScenarioCheck("not_refused", lambda b: not _refused(b)),
            ScenarioCheck(
                "cites_art_95",
                lambda b: _has_reference(b, "Article 95"),
            ),
        ),
    ),
    Scenario(
        id="omnibus_art59_sandbox_pii",
        category="sandbox",
        description="Art. 59 — personal data processing in AI sandbox.",
        messages=(
            {
                "role": "user",
                "content": (
                    "Can personal data be processed inside an AI regulatory "
                    "sandbox without GDPR consent?"
                ),
            },
        ),
        checks=(
            ScenarioCheck("not_refused", lambda b: not _refused(b)),
            ScenarioCheck(
                "cites_art_59",
                lambda b: _has_reference(b, "Article 59"),
            ),
        ),
    ),
    Scenario(
        id="omnibus_art61_informed_consent",
        category="in_scope_basic",
        description="Art. 61 — informed consent for real-world testing.",
        messages=(
            {
                "role": "user",
                "content": "Do real-world test subjects of an AI system need to give informed consent?",
            },
        ),
        checks=(
            ScenarioCheck("not_refused", lambda b: not _refused(b)),
            ScenarioCheck(
                "cites_art_61",
                lambda b: _has_reference(b, "Article 61"),
            ),
        ),
    ),
    Scenario(
        id="omnibus_art67_advisory_forum",
        category="in_scope_basic",
        description="Art. 67 — Advisory Forum stakeholder body.",
        messages=(
            {
                "role": "user",
                "content": "What is the Advisory Forum under the EU AI Act?",
            },
        ),
        checks=(
            ScenarioCheck("not_refused", lambda b: not _refused(b)),
            ScenarioCheck(
                "cites_art_67",
                lambda b: _has_reference(b, "Article 67"),
            ),
        ),
    ),
    Scenario(
        id="omnibus_art68_scientific_panel",
        category="in_scope_basic",
        description="Art. 68 — Scientific Panel for GPAI enforcement.",
        messages=(
            {
                "role": "user",
                "content": "What does the Scientific Panel do under the EU AI Act?",
            },
        ),
        checks=(
            ScenarioCheck("not_refused", lambda b: not _refused(b)),
            ScenarioCheck(
                "cites_art_68",
                lambda b: _has_reference(b, "Article 68"),
            ),
        ),
    ),
    Scenario(
        id="omnibus_annex_ii_offences",
        category="annex_deep_ref",
        description="Annex II — list of criminal offences for Art. 5(1)(h).",
        messages=(
            {
                "role": "user",
                "content": (
                    "Which criminal offences permit real-time remote biometric "
                    "identification by law enforcement under the AI Act?"
                ),
            },
        ),
        checks=(
            ScenarioCheck("not_refused", lambda b: not _refused(b)),
            ScenarioCheck(
                "cites_annex_ii_or_art5",
                lambda b: _has_reference(b, "Annex II") or _has_reference(b, "Article 5"),
            ),
        ),
    ),
    Scenario(
        id="omnibus_annex_v_doc_contents",
        category="annex_deep_ref",
        description="Annex V — declaration of conformity contents.",
        messages=(
            {
                "role": "user",
                "content": "What must the EU declaration of conformity contain?",
            },
        ),
        checks=(
            ScenarioCheck("not_refused", lambda b: not _refused(b)),
            ScenarioCheck(
                "cites_annex_v_or_art47",
                lambda b: _has_reference(b, "Annex V") or _has_reference(b, "Article 47"),
            ),
        ),
    ),
    Scenario(
        id="omnibus_annex_viii_registration",
        category="annex_deep_ref",
        description="Annex VIII — EU-database registration information.",
        messages=(
            {
                "role": "user",
                "content": "What information must be registered in the EU AI database?",
            },
        ),
        checks=(
            ScenarioCheck("not_refused", lambda b: not _refused(b)),
            ScenarioCheck(
                "cites_annex_viii_or_art49_71",
                lambda b: _has_reference(b, "Annex VIII")
                or _has_reference(b, "Article 49")
                or _has_reference(b, "Article 71"),
            ),
        ),
    ),
    # ═══════════════════════════════════════════════════════════════════
    # B. Digital Omnibus political-agreement scenarios (May 2026).
    # ═══════════════════════════════════════════════════════════════════
    Scenario(
        id="omnibus_csam_prohibition",
        category="in_scope_basic",
        description="New Art. 5 prohibition — AI-CSAM / non-consensual intimate imagery.",
        messages=(
            {
                "role": "user",
                "content": (
                    "Are AI systems that generate non-consensual intimate imagery "
                    "prohibited under the EU AI Act?"
                ),
            },
        ),
        checks=(
            ScenarioCheck("not_refused", lambda b: not _refused(b)),
            ScenarioCheck(
                "cites_art_5",
                lambda b: _has_reference(b, "Article 5"),
            ),
        ),
    ),
    Scenario(
        id="omnibus_small_mid_cap",
        category="in_scope_basic",
        description="Digital Omnibus — extension of SME relief to small mid-cap (SMC) firms.",
        messages=(
            {
                "role": "user",
                "content": "What support does the EU AI Act provide to SMEs and small mid-cap companies?",
            },
        ),
        checks=(
            ScenarioCheck("not_refused", lambda b: not _refused(b)),
            ScenarioCheck(
                "cites_art_62",
                lambda b: _has_reference(b, "Article 62"),
            ),
        ),
    ),
    # ═══════════════════════════════════════════════════════════════════
    # C. Art. 50 sub-article disambiguation scenarios.
    # ═══════════════════════════════════════════════════════════════════
    Scenario(
        id="omnibus_art50_watermark",
        category="transparency_art50",
        description="Art. 50(2) — generative AI watermarking obligation.",
        messages=(
            {
                "role": "user",
                "content": "Must generative AI systems watermark their output?",
            },
        ),
        checks=(
            ScenarioCheck("not_refused", lambda b: not _refused(b)),
            ScenarioCheck(
                "cites_art_50",
                lambda b: _has_reference(b, "Article 50"),
            ),
        ),
    ),
    Scenario(
        id="omnibus_art50_deepfake_disclosure",
        category="transparency_art50",
        description="Art. 50(4) — deployer must disclose deepfake content.",
        messages=(
            {
                "role": "user",
                "content": "Must someone deploying a deepfake disclose it to viewers?",
            },
        ),
        checks=(
            ScenarioCheck("not_refused", lambda b: not _refused(b)),
            ScenarioCheck(
                "cites_art_50",
                lambda b: _has_reference(b, "Article 50"),
            ),
        ),
    ),
    # ═══════════════════════════════════════════════════════════════════
    # D. Definition probes (Art. 3 anchor).
    # ═══════════════════════════════════════════════════════════════════
    Scenario(
        id="omnibus_def_deepfake",
        category="definitional",
        description="Art. 3(60) — definition of 'deep fake'.",
        messages=(
            {
                "role": "user",
                "content": "How does the EU AI Act define a deep fake?",
            },
        ),
        checks=(
            ScenarioCheck("not_refused", lambda b: not _refused(b)),
            ScenarioCheck(
                "cites_art_3_or_50",
                lambda b: _has_reference(b, "Article 3") or _has_reference(b, "Article 50"),
            ),
        ),
    ),
    Scenario(
        id="omnibus_def_serious_incident",
        category="definitional",
        description="Art. 3(49) — definition of 'serious incident'.",
        messages=(
            {
                "role": "user",
                "content": "What counts as a serious incident under the EU AI Act?",
            },
        ),
        checks=(
            ScenarioCheck("not_refused", lambda b: not _refused(b)),
            ScenarioCheck(
                "cites_art_3_or_73",
                lambda b: _has_reference(b, "Article 3") or _has_reference(b, "Article 73"),
            ),
        ),
    ),
)


EXTRA_OMNIBUS_CATEGORIES: tuple[str, ...] = tuple(
    sorted({s.category for s in EXTRA_OMNIBUS_SCENARIOS})
)
