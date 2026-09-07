"""R388 — a faithful reconstruction of the OFFICIAL regenold rubric.

Why this package exists
-----------------------
``evals.bench.metrics`` is a LEXICAL PROXY and its formulas do not match the
official rubric.  Executed proof (R388)::

    appendix Q104: expected {Article 111.1, Annex X}, provided {Annex X}
        official  min(1, |E|/|P|) = min(1, 2/1) = 1.00
        local     reference_conciseness(...)     = 0.25

    appendix Q17:  expected {Article 7.1}, provided 5 refs
        official  = 0.20        local = 0.0625

The local metric is SYMMETRIC (it punishes citing FEWER refs than expected);
the official one is ONE-SIDED.  The report's own appendix proves the one-sided
reading -- Q104 cites one reference against a two-reference key and the
recovered per-case value is ``min(1, 2/1)``, i.e. 1.0, not 0.5.

The same structural error is in the answer axis::

    our live answers    1233.3 chars mean   (R367, measured over the tunnel)
    official AnsConc    51.9                (printed, 2026-08-25, easy)
    min(1, 640/1233)  = 0.519               <-- reproduces the printed number
    local answer_conciseness(1233, 640) = 0.269

Two independently-measured quantities land on the printed value, which pins
both the FORM of the axis (one-sided length ratio) and the implied mean
reference-answer length (~640 characters).

What the official rubric actually is (Table 1 of the 2026-08-25 report)
-----------------------------------------------------------------------
=========================  ====================================================
Ans. Correctness (Loose)   % of individual correctness criteria satisfied
Ans. Correctness (Strict)  % of questions where ALL criteria are satisfied
Ans. Conciseness           inverted verbosity relative to the reference answers
Ref. Correctness (Loose)   % of expected refs met at Article/Annex-number level
Ref. Correctness (Strict)  as above, including subpoints
Ref. Conciseness           excess references relative to expected references
Regulatory Tone            fraction judged appropriate and clear
Resp. speed                mean(100 - latency_s), clipped at zero
Overall                    GEOMETRIC MEAN of the eight
=========================  ====================================================

Questions without annotated expected references are EXCLUDED from all three
reference axes.

What this package is NOT
------------------------
The evaluator never published the per-question correctness criteria or the
reference answers, so those two inputs are RECONSTRUCTED here
(:mod:`evals.official.build_gold`) rather than copied.  Every number this
package produces is therefore a *reconstruction*, not the official score.  It
is calibrated against the six worked examples the report prints verbatim in
its appendix (:mod:`evals.official.calibration`) and that calibration is the
only evidence for how closely it tracks.

Use it to COMPARE ARMS under one fixed instrument.  Run the frontier baseline
through the same instrument (:mod:`evals.official.run_arm` ``--arm baseline``)
rather than comparing a local number to a printed one.
"""

from evals.official.rubric import (  # noqa: F401
    answer_conciseness,
    answer_correctness_loose,
    answer_correctness_strict,
    overall,
    reference_conciseness,
    reference_correctness_loose,
    reference_correctness_strict,
    regulatory_tone,
    response_speed,
    score_rows,
)

__all__ = [
    "answer_conciseness",
    "answer_correctness_loose",
    "answer_correctness_strict",
    "overall",
    "reference_conciseness",
    "reference_correctness_loose",
    "reference_correctness_strict",
    "regulatory_tone",
    "response_speed",
    "score_rows",
]
