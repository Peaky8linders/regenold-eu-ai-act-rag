"""Centralized severity ordering.

Three engines previously invented their own severity tables:
- `app/engines/compliance_report.py::_SEVERITY_THRESHOLDS` — score → bucket
- `app/engines/attack_chain.py::_SEVERITY_ORDER` / `_SEVERITY_LABELS` — bucket → rank
- `app/engines/reports.py` — inline `{"critical": 🔴, …}` icon map

This module is the single source of truth so a new severity tier
(e.g. adding `"blocker"` above critical) is a one-line change instead
of six.

Usage:
    from app.data.severity import (
        SEVERITY_ORDER, rank, max_severity, score_to_severity,
    )

    max_severity(["high", "critical", "medium"])  # → "critical"
    score_to_severity(25.0)                        # → "high"
    rank("critical")                                # → 4

The ordering is:
    0 info   — green
    1 low    — green/blue
    2 medium — yellow
    3 high   — orange
    4 critical — red
"""

from __future__ import annotations

# Name → numeric rank. Higher rank == more severe. Lowercase canonical form.
SEVERITY_ORDER: dict[str, int] = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

# Reverse lookup — rank → name.
SEVERITY_LABELS: dict[int, str] = {v: k for k, v in SEVERITY_ORDER.items()}

# Score → severity bucket. Thresholds are <=, so score 19.9 is "critical",
# 20.0 is "high" (boundary is the ceiling of each bucket). Kept for
# back-compat with `compliance_report._score_to_severity`.
#
# 0-19   critical
# 20-39  high
# 40-69  medium
# 70-100 low
_SEVERITY_SCORE_THRESHOLDS: list[tuple[float, str]] = [
    (20.0, "critical"),
    (40.0, "high"),
    (70.0, "medium"),
    (100.0, "low"),
]


def rank(severity: str) -> int:
    """Return numeric rank for a severity name. Unknown values map to low (1)
    rather than raising, matching the existing `attack_chain._SEVERITY_ORDER.get(..., 1)` fallback.
    """
    return SEVERITY_ORDER.get((severity or "").lower(), 1)


def max_severity(severities: list[str]) -> str:
    """Return the highest-ranked severity in the list. Empty list → "medium"
    (matching the pre-refactor `attack_chain` fallback — a visible default,
    not "info", because "no signals at all" usually means "not measured"
    rather than "everything is fine").
    """
    if not severities:
        return "medium"
    return SEVERITY_LABELS.get(max(rank(s) for s in severities), "medium")


def score_to_severity(score: float) -> str:
    """Map a 0-100 compliance/risk score to a severity bucket.

    Mirrors the pre-refactor `compliance_report._score_to_severity`:
    strictly-less-than each threshold, defaults to "low" for >=70.
    """
    for threshold, severity in _SEVERITY_SCORE_THRESHOLDS:
        if score < threshold:
            return severity
    return "low"
