"""MedTech Standards Cross-Framework Bridge.

Maps EU AI Act articles to their equivalent or complementing sectoral standards
(e.g., ISO 14971, IEC 62304, MDR 2017/745) to enhance the RAG context
for medical device scenarios.
"""
from __future__ import annotations

MEDTECH_STANDARD_MAP: dict[str, dict[str, str]] = {
    "Art. 9": {
        "standard": "ISO 14971:2019",
        "name": "Application of risk management to medical devices",
        "bridge": "Article 9 risk management system aligns with ISO 14971 hazard identification, risk estimation, and risk evaluation stages.",
    },
    "Art. 10": {
        "standard": "ISO 13485:2016",
        "name": "Quality management systems for medical devices",
        "bridge": "Article 10 data governance requirements complement ISO 13485 design control and traceability requirements.",
    },
    "Art. 12": {
        "standard": "ISO 13485:2016 §4.2.5 / MDR 2017/745 Art. 10(8)",
        "name": "Control of records / technical documentation retention",
        "bridge": "Article 12 requires high-risk AI systems to technically allow automatic recording of events (logs) over their lifetime; ISO 13485 clause 4.2.5 record control and MDR Article 10(8) documentation retention supply the medical-device record regime those logs join. The retention periods differ and do not substitute for one another: Article 19(1) obliges the provider, and Article 26(6) the deployer, to keep the automatically generated logs for at least six months, while MDR Article 10(8) requires technical documentation to remain available to competent authorities for at least ten years after the last device is placed on the market (fifteen for implantables).",
    },
    "Art. 14": {
        "standard": "IEC 62366-1:2015+A1:2020",
        "name": "Medical devices — Application of usability engineering to medical devices",
        "bridge": "Article 14 human oversight is discharged through the same usability-engineering process IEC 62366-1 already requires: use-specification, identification of use-related hazards, and validation that the intended user can operate the device safely. Article 14(4)(b) awareness of automation bias maps to use-related risk analysis, and Article 14(4)(d)-(e) — the ability to disregard, override or reverse an output and to interrupt operation — are user-interface requirements that must appear in the usability engineering file. Use error identified under IEC 62366-1 feeds the ISO 14971 risk-management file, which is the same file Article 9(2)(c) updates.",
    },
    "Art. 15": {
        "standard": "IEC 62304:2006+A1:2015",
        "name": "Medical device software — Software life cycle processes",
        "bridge": "Article 15 accuracy, robustness, and cybersecurity requirements map to IEC 62304 software safety classification (Class A/B/C) and verification/validation requirements.",
    },
    "Art. 26": {
        "standard": "MDR 2017/745 Art. 87-88 (health-institution / user side)",
        "name": "Vigilance and trend reporting — the deployer's contribution",
        "bridge": "Article 26 places duties on the deployer that the MDR does not: the MDR assigns vigilance reporting to the manufacturer, so a health institution's obligations under Article 26 are additive rather than already discharged by MDR compliance. Article 26(5) requires the deployer to monitor operation against the instructions for use, to inform the provider and the market surveillance authority where use may present an Article 79(1) risk, and to suspend use; Article 26(6) requires retention of the automatically generated logs for at least six months. That monitoring record is the input a manufacturer needs for MDR Article 87 serious-incident reporting and for the Article 88 trend reporting of non-serious incidents that rise in frequency or severity.",
    },
    "Art. 43": {
        "standard": "MDR 2017/745 / IVDR 2017/746",
        "name": "Medical Device Regulation / In Vitro Diagnostic Regulation",
        "bridge": "Article 43 conformity assessment for AI medical devices runs through the MDR/IVDR notified-body route under Article 43(3), yielding a single CE marking under Article 48.",
    },
    "Art. 72": {
        "standard": "MDR 2017/745 Art. 83-86 / IVDR 2017/746 Art. 78-81",
        "name": "Post-market surveillance system and plan",
        "bridge": "Article 72 does not create a parallel surveillance system for a device that already has one. Article 72(4) provides that, for high-risk AI systems covered by the Union harmonisation legislation in Annex I Section A — which includes the MDR and IVDR — the post-market monitoring elements of Article 72(1) to (3) shall be integrated, as appropriate, into the post-market surveillance system and plan already established under that legislation. The single integrated artefact therefore serves MDR Article 83 (surveillance system), Article 84 (surveillance plan) and the Article 85 to 86 reporting cycle at the same time as the AI Act duty.",
    },
    "Art. 73": {
        "standard": "MDR 2017/745 Art. 87 (vigilance)",
        "name": "Reporting of serious incidents — the two-track split",
        "bridge": "For an AI system that is itself a device, or a safety component of one, covered by the MDR or IVDR, Article 73(10) narrows the AI Act reporting duty rather than adding to it: notification is limited to the serious incidents referred to in Article 3(49)(c) — an infringement of Union law protecting fundamental rights — and is made to the national competent authority designated for that purpose by the Member State where the incident occurred, not to the market surveillance authority in general. Death or serious deterioration of health routes through MDR Article 87 vigilance instead. A generic AI Act answer of 'notify the market surveillance authority within fifteen days' is therefore wrong for a regulated device, and the Article 73(2) to (4) clocks (15 days ordinarily, 2 days for a widespread infringement or a serious and irreversible disruption of critical infrastructure, 10 days on death) apply only to the track that remains with the AI Act.",
    },
}


def _self_check() -> None:
    """Import-time contract guard (R263).

    The consumer (``graph_rag`` MedTech bridging) reads ``standard`` / ``name``
    / ``bridge`` on every entry and keys off internal ``Art. N`` refs that must
    resolve in the canonical catalog. A future edit that drops a key or points
    at a non-existent article should fail the module load, not a live request.
    """
    from app.data.article_existence import ARTICLE_EXISTENCE

    required = {"standard", "name", "bridge"}
    for ref, data in MEDTECH_STANDARD_MAP.items():
        missing = required - set(data)
        if missing:
            raise RuntimeError(
                f"MEDTECH_STANDARD_MAP[{ref!r}] missing keys: {sorted(missing)}"
            )
        if not all(str(data[k]).strip() for k in required):
            raise RuntimeError(f"MEDTECH_STANDARD_MAP[{ref!r}] has an empty field")
        if ref not in ARTICLE_EXISTENCE:
            raise RuntimeError(
                f"MEDTECH_STANDARD_MAP key {ref!r} does not resolve in ARTICLE_EXISTENCE"
            )


_self_check()
