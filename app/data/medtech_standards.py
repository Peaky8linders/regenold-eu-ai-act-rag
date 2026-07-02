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
    "Art. 15": {
        "standard": "IEC 62304:2006+A1:2015",
        "name": "Medical device software — Software life cycle processes",
        "bridge": "Article 15 accuracy, robustness, and cybersecurity requirements map to IEC 62304 software safety classification (Class A/B/C) and verification/validation requirements.",
    },
    "Art. 43": {
        "standard": "MDR 2017/745 / IVDR 2017/746",
        "name": "Medical Device Regulation / In Vitro Diagnostic Regulation",
        "bridge": "Article 43 conformity assessment for AI medical devices runs through the MDR/IVDR notified-body route under Article 43(3), yielding a single CE marking under Article 48.",
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
