"""R388 - the eight official axis formulas, as pure functions.

Every formula here is either quoted from Table 1 of the 2026-08-25 report or
RECOVERED from the worked cases the report's appendix prints with both their
provided and their expected reference sets.  The recovery is recorded per-axis
in the docstrings so a future reader can re-audit it rather than trust it.

Nothing in this module calls an LLM.  Criteria satisfaction and tone arrive as
already-judged booleans (see :mod:`evals.official.judge`), so the arithmetic is
deterministic and unit-testable in isolation.
"""
from __future__ import annotations

import math
import re
from typing import Any, Iterable, Sequence

# -- reference coordinate normalisation --------------------------------------

# The Act nests four deep: Article 13.3.b.iv is a real coordinate and appears
# in the reconstructed answer key, so the sub-point alternation has to accept a
# multi-character roman/alpha part, not just a single letter.
_REF_RE = re.compile(
    r"^\s*(?:the\s+)?(?P<kind>Article|Art\.?|Annex)\s*"
    r"(?P<num>\d{1,3}|[IVXLivxl]+)"
    r"(?P<rest>(?:\s*[.(\-]\s*[0-9]{1,3}\s*\)?|\s*[.(]\s*[a-zA-Z]{1,5}\s*\)?)*)"
    r"\s*[.,;:]?\s*$"
)
_PART_RE = re.compile(r"[0-9]{1,3}|[a-zA-Z]{1,5}")


def normalise_ref(ref: str) -> str | None:
    """Canonicalise one citation to ``Article N[.p[.q...]]`` / ``Annex R[.p...]``.

    Accepts the wire format (``Article 6.2``), the legislative format
    (``Article 6(2)``) and abbreviated / spaced variants, because an arm we did
    not write -- a baseline model, say -- will not use our house style.  Returns
    ``None`` for a string that is not a citation at all.
    """
    if not ref or not isinstance(ref, str):
        return None
    m = _REF_RE.match(ref.strip())
    if not m:
        return None
    kind = "Annex" if m.group("kind").lower().startswith("annex") else "Article"
    num = m.group("num")
    if kind == "Annex":
        if num.isdigit():
            return None  # "Annex 3" is not a valid coordinate; roman only
        num = num.upper()
    else:
        if not num.isdigit():
            return None
        num = str(int(num))
    parts = _PART_RE.findall(m.group("rest") or "")
    tail = "".join("." + p.lower() for p in parts)
    return f"{kind} {num}{tail}"


def ref_head(ref: str) -> str | None:
    """``Article 6.2`` -> ``Article 6``; ``Annex III.5.d`` -> ``Annex III``."""
    n = normalise_ref(ref)
    if not n:
        return None
    kind, coord = n.split(" ", 1)
    return f"{kind} {coord.split('.')[0]}"


def _clean(refs: Iterable[str] | None) -> list[str]:
    """Normalise, drop non-citations, dedupe preserving order."""
    out: list[str] = []
    seen: set[str] = set()
    for r in refs or []:
        n = normalise_ref(r)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _heads(refs: Iterable[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for r in refs or []:
        h = ref_head(r)
        if h and h not in seen:
            seen.add(h)
            out.append(h)
    return out


def _is_descendant(pred: str, expected: str) -> bool:
    """``Article 13.3.a`` satisfies an expected ``Article 13.3``.

    A prediction strictly MORE precise than the key still identifies the
    provision the key names, so it counts.  A prediction LESS precise
    (``Article 13`` against an expected ``Article 13.3``) does not -- that is
    exactly the grain deficit the strict axis exists to measure.
    """
    return pred == expected or pred.startswith(expected + ".")


# -- axes 4 & 5: reference correctness ---------------------------------------


def reference_correctness_loose(
    pred_refs: Sequence[str], expected_refs: Sequence[str]
) -> float | None:
    """Percentage of expected references met at the level of Article and Annex
    numbers (e.g. Article 6).

    Per-question recall at HEAD grain.  Returns ``None`` when the question
    carries no annotated expected references -- the report excludes those rows
    from every reference axis rather than scoring them zero.
    """
    exp = _heads(expected_refs)
    if not exp:
        return None
    got = set(_heads(pred_refs))
    return sum(1 for e in exp if e in got) / len(exp)


def reference_correctness_strict(
    pred_refs: Sequence[str], expected_refs: Sequence[str]
) -> float | None:
    """As above, but including subpoints within the Articles/Annexes
    (e.g. Article 6.1).

    Per-question recall at FULL grain.  A predicted coordinate counts for an
    expected one when it equals it or refines it (see :func:`_is_descendant`).
    """
    exp = _clean(expected_refs)
    if not exp:
        return None
    got = _clean(pred_refs)
    return sum(1 for e in exp if any(_is_descendant(p, e) for p in got)) / len(exp)


def reference_conciseness(
    pred_refs: Sequence[str], expected_refs: Sequence[str]
) -> float | None:
    """Excess references relative to expected references.

    RECOVERED as the pure count ratio ``min(1, |expected| / |provided|)``.
    Evidence -- the five appendix cases that print both sets, scored against
    the printed 50.4::

        Q45  1/2 = 0.50     Q17  1/5 = 0.20     Q95  2/4 = 0.50
        Q104 min(1, 2/1) = 1.00                 Q74  1/4 = 0.25
        mean = 0.49  ->  49.0 vs printed 50.4, error 1.4 pp

    Competing formulations were all worse: exact-string precision 39.0
    (11.4 pp off), hierarchical precision 63.0 (12.6 pp), head-collapsed
    precision 65.0 (14.6 pp).

    Q104 is the case that pins the axis as ONE-SIDED: it provides FEWER
    references than the key and still scores 1.0.  Citing too few costs recall
    on the two correctness axes, never conciseness.
    """
    exp = _clean(expected_refs)
    if not exp:
        return None
    prov = _clean(pred_refs)
    if not prov:
        return 1.0
    return min(1.0, len(exp) / len(prov))


# -- axis 3: answer conciseness ----------------------------------------------


def answer_conciseness(answer: str, reference_answer: str) -> float | None:
    """Inverted measure of answer verbosity relative to the reference answers.

    Implemented as ``min(1, len(reference) / len(candidate))`` in characters --
    the answer-side analogue of the reference axis recovered above, and the
    algebraic form of "inverted verbosity": penalising excess length by
    ``1 - (C - R)/C`` IS ``R/C``.

    Corroboration for both the form and the scale: our live answers measured
    1233.3 chars mean (R367, over the tunnel) and the report prints AnsConc
    51.9 for easy mode.  ``min(1, 640/1233) = 0.519``.  That same 640-char
    implied reference length reproduces the hard-mode 45.2 at a candidate
    length of 1416 chars, which sits inside the 1.2-2.3x easy-to-hard growth
    R380 measured independently.

    One-sided by construction, mirroring the reference axis: an answer SHORTER
    than the reference is not penalised here.  Omission is scored on the two
    correctness axes.
    """
    if not reference_answer:
        return None
    c = len(answer or "")
    if c == 0:
        return 0.0
    return min(1.0, len(reference_answer) / c)


# -- axes 1 & 2: answer correctness ------------------------------------------


def answer_correctness_loose(criteria_results: Sequence[Sequence[bool]]) -> float:
    """Percentage of individual correctness criteria satisfied.

    MICRO average -- every criterion counts once, so a question with five
    criteria carries more weight than one with two.  That is the literal
    reading of "individual correctness criteria".  :func:`score_rows` also
    reports the macro variant so the choice stays auditable rather than
    assumed.
    """
    flat = [bool(c) for row in criteria_results for c in row]
    if not flat:
        return 0.0
    return sum(1 for c in flat if c) / len(flat)


def answer_correctness_strict(criteria_results: Sequence[Sequence[bool]]) -> float:
    """Percentage of questions for which ALL required correctness criteria are
    satisfied.

    A question with no criteria cannot be all-satisfied, so it is excluded
    rather than counted as a free pass.
    """
    rows = [r for r in criteria_results if r]
    if not rows:
        return 0.0
    return sum(1 for r in rows if all(bool(c) for c in r)) / len(rows)


# -- axes 7 & 8: tone and speed ----------------------------------------------


def regulatory_tone(judgements: Sequence[bool]) -> float:
    """Fraction of responses judged both appropriate and clear."""
    if not judgements:
        return 0.0
    return sum(1 for j in judgements if j) / len(judgements)


def response_speed(latencies_s: Sequence[float]) -> float:
    """Mean per-response score: 100 minus latency in seconds, clipped at zero.

    Returned on the 0-1 scale like every other axis here; :func:`score_rows`
    multiplies by 100 once, uniformly.
    """
    if not latencies_s:
        return 0.0
    return sum(max(0.0, 100.0 - float(s)) for s in latencies_s) / len(latencies_s) / 100.0


# -- the aggregate -----------------------------------------------------------


def overall(axes: Sequence[float]) -> float:
    """Geometric mean across all metrics.

    Reproduces all TWELVE printed Overall figures of the two reports to
    <= 0.06 pp (R381), so the aggregation is known exactly.  A single zero axis
    zeroes the whole score -- which is the point: it "penalises low scores in
    any single metric".
    """
    vals = [max(0.0, float(a)) for a in axes]
    if not vals:
        return 0.0
    if any(v == 0.0 for v in vals):
        return 0.0
    return math.exp(sum(math.log(v) for v in vals) / len(vals))


AXIS_ORDER = (
    "ans_correctness_loose",
    "ans_correctness_strict",
    "ans_conciseness",
    "ref_correctness_loose",
    "ref_correctness_strict",
    "ref_conciseness",
    "regulatory_tone",
    "resp_speed",
)


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def score_rows(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Score a captured arm.

    Each row is a dict with:

    ``criteria``          list[bool]  per-criterion satisfaction
    ``answer``            str
    ``reference_answer``  str
    ``references``        list[str]   what the arm cited
    ``expected_refs``     list[str]   the key; ``[]`` means "not annotated"
    ``tone_ok``           bool
    ``latency_s``         float

    Rows with no ``expected_refs`` are excluded from the three reference axes
    only; they still count on the answer, tone and speed axes.  That is the
    report's own rule: "questions without annotated expected references are
    excluded".
    """
    crit = [list(r.get("criteria") or []) for r in rows]

    ac = [
        answer_conciseness(r.get("answer", ""), r.get("reference_answer", ""))
        for r in rows
    ]
    ac = [v for v in ac if v is not None]

    rl = [
        reference_correctness_loose(r.get("references") or [], r.get("expected_refs") or [])
        for r in rows
    ]
    rs = [
        reference_correctness_strict(r.get("references") or [], r.get("expected_refs") or [])
        for r in rows
    ]
    rc = [
        reference_conciseness(r.get("references") or [], r.get("expected_refs") or [])
        for r in rows
    ]
    rl = [v for v in rl if v is not None]
    rs = [v for v in rs if v is not None]
    rc = [v for v in rc if v is not None]

    axes = {
        "ans_correctness_loose": answer_correctness_loose(crit),
        "ans_correctness_strict": answer_correctness_strict(crit),
        "ans_conciseness": _mean(ac),
        "ref_correctness_loose": _mean(rl),
        "ref_correctness_strict": _mean(rs),
        "ref_conciseness": _mean(rc),
        "regulatory_tone": regulatory_tone([bool(r.get("tone_ok")) for r in rows]),
        "resp_speed": response_speed([float(r.get("latency_s") or 0.0) for r in rows]),
    }
    out: dict[str, Any] = {k: round(v * 100.0, 4) for k, v in axes.items()}
    out["overall"] = round(overall([axes[k] for k in AXIS_ORDER]) * 100.0, 4)
    out["n"] = len(rows)
    out["n_ref_scored"] = len(rl)

    # Auditable alternatives and diagnostics.  None of these enter ``overall``.
    macro = [sum(1 for c in r if c) / len(r) for r in crit if r]
    out["_ans_loose_macro"] = round(_mean(macro) * 100.0, 4)
    out["_mean_answer_chars"] = round(_mean([len(r.get("answer") or "") for r in rows]), 1)
    out["_mean_reference_chars"] = round(
        _mean([len(r.get("reference_answer") or "") for r in rows]), 1
    )
    out["_mean_refs_per_row"] = round(
        _mean([len(_clean(r.get("references") or [])) for r in rows]), 3
    )
    out["_mean_expected_per_row"] = round(
        _mean([len(_clean(r.get("expected_refs") or [])) for r in rows if r.get("expected_refs")]),
        3,
    )
    out["_mean_latency_s"] = round(_mean([float(r.get("latency_s") or 0.0) for r in rows]), 3)
    return out
