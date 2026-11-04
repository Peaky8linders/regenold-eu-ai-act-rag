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
from collections.abc import Iterable, Sequence
from statistics import fmean
from typing import Any, Final

PROFILE_R391_REPORT: Final = "r391_report"
PROFILE_PUBLISHED_2026: Final = "published_2026"
RUBRIC_PROFILES: Final = (PROFILE_R391_REPORT, PROFILE_PUBLISHED_2026)

PUBLISHED_REFERENCE_RE = re.compile(
    r"^(?P<kind>Article|Annex)\s+(?P<base>[^\s.]+)(?:\.(?P<sub>[^\s.]+))?(?:\.[^\s.]+)*$",
    flags=re.IGNORECASE,
)

PUBLISHED_LABELS: Final = (
    "Answer correctness (loose)",
    "Answer correctness (strict)",
    "Answer conciseness",
    "Reference correctness (loose)",
    "Reference correctness (strict)",
    "Reference conciseness",
    "Regulatory tone",
    "Response speed",
)

# -- reference coordinate normalisation --------------------------------------

# The Act nests four deep: Article 13.3.b.iv is a real coordinate and appears
# in the reconstructed answer key, so the sub-point alternation has to accept a
# multi-character roman/alpha part, not just a single letter.
_REF_RE = re.compile(
    r"^\s*(?:the\s+)?(?P<kind>Article|Art\.?|Annex)\s*"
    r"(?P<num>\d{1,3}|[IVXLivxl]+)"
    r"(?P<rest>(?:[,\s]*(?:point|paragraph|para|item|section)?\s*(?:[.(\-]\s*[0-9]{1,3}\s*\)?|\s*[.(]\s*[a-zA-Z]{1,5}\s*\)?|[0-9]{1,3}|[a-zA-Z]))*)"
    r"\s*[.,;:]?\s*$",
    re.IGNORECASE,
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
    rest = m.group("rest") or ""
    rest_clean = re.sub(
        r"\b(point|paragraph|para|item|section)\b", "", rest, flags=re.I
    )
    parts = _PART_RE.findall(rest_clean)
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


ANNEX_SECTIONS: dict[str, dict[str, tuple[int, int]]] = {
    "I": {"a": (1, 12), "b": (13, 20)},
}


def canonical_annex_point(coord: str) -> str:
    """Normalize section-tagged Annex I points to their printed point number."""
    kind, sep, rest = coord.partition(" ")
    if not sep or kind != "Annex":
        return coord
    head, dot, tail = rest.partition(".")
    sections = ANNEX_SECTIONS.get(head.upper())
    if not sections or not dot:
        return coord
    parts = tail.split(".")
    if len(parts) < 2 or len(parts[0]) != 1 or not parts[1].isdigit():
        return coord
    bounds = sections.get(parts[0].lower())
    point = int(parts[1])
    if bounds is None or not bounds[0] <= point <= bounds[1]:
        return coord
    suffix = "." + ".".join(parts[2:]) if len(parts) > 2 else ""
    return f"Annex {head.upper()}.{point}{suffix}"


def reference_correctness_strict(
    pred_refs: Sequence[str], expected_refs: Sequence[str]
) -> float | None:
    """As above, but including subpoints within the Articles/Annexes
    (e.g. Article 6.1).

    Per-question recall at FULL grain. A predicted coordinate counts for an
    expected one when it equals it or refines it (see :func:`_is_descendant`).
    Section-tagged Annex I coordinates on either side normalize to statutory
    printed numbering before comparison.
    """
    exp = _clean(expected_refs)
    if not exp:
        return None
    # R446 — de-duplicate AFTER canonicalising: ``_clean`` de-duplicated the raw
    # forms, so a key carrying ``Annex I.a.11`` and ``Annex I.11`` counted the
    # one provision twice in the denominator.
    exp = list(dict.fromkeys(canonical_annex_point(e) for e in exp))
    got = [canonical_annex_point(p) for p in _clean(pred_refs)]
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


def _normalize_published_reference(reference: str, *, keep_sublevel: bool) -> str:
    """Published first-sublevel reference normalizer from ``src/ref_scoring.py``."""
    reference = reference.strip().lower()
    match = PUBLISHED_REFERENCE_RE.match(reference)
    if not match:
        return reference

    normalized = f"{match.group('kind').lower()} {match.group('base').lower()}"
    sublevel = match.group("sub")
    if keep_sublevel and sublevel:
        normalized += f".{sublevel.lower()}"
    return normalized


def compute_published_ref_scores(
    found: Sequence[str], expected: Sequence[str]
) -> dict[str, float | None]:
    """Exact reference-scoring implementation from released ``src/ref_scoring.py``."""
    found_refs = [ref.strip().lower() for ref in (found or []) if ref and ref.strip()]
    expected_refs = [
        ref.strip().lower() for ref in (expected or []) if ref and ref.strip()
    ]

    loose_expected = [
        _normalize_published_reference(ref, keep_sublevel=False)
        for ref in expected_refs
    ]
    loose_found = [
        _normalize_published_reference(ref, keep_sublevel=False) for ref in found_refs
    ]

    strict_expected = [
        _normalize_published_reference(ref, keep_sublevel=True)
        for ref in expected_refs
    ]
    strict_found = [
        _normalize_published_reference(ref, keep_sublevel=True) for ref in found_refs
    ]

    loose_expected_set = set(loose_expected)
    loose_found_set = set(loose_found)
    strict_expected_set = set(strict_expected)
    strict_found_set = set(strict_found)

    result: dict[str, float | None] = {}
    if loose_expected_set:
        result["loose_found_pct"] = len(
            loose_expected_set.intersection(loose_found_set)
        ) / len(loose_expected_set)
        result["loose_extra_pct"] = len(
            loose_found_set - loose_expected_set
        ) / len(loose_expected_set)
    else:
        result["loose_found_pct"] = None
        result["loose_extra_pct"] = None

    if strict_expected_set:
        matched_expected = strict_expected_set.intersection(strict_found_set)
        matched_found = set(matched_expected)

        # A specific paragraph satisfies an expected top-level Article/Annex.
        # Consume one such candidate reference; any siblings remain extras.
        for expected_ref in sorted(strict_expected_set - matched_expected):
            if expected_ref != _normalize_published_reference(
                expected_ref, keep_sublevel=False
            ):
                continue
            for found_ref in sorted(strict_found_set - matched_found):
                if (
                    _normalize_published_reference(found_ref, keep_sublevel=False)
                    == expected_ref
                ):
                    matched_expected.add(expected_ref)
                    matched_found.add(found_ref)
                    break

        result["strict_found_pct"] = len(matched_expected) / len(strict_expected_set)
        raw_extra = strict_found_set - matched_found
        # Exempt only a top-level parent of an expected sublevel.
        raw_extra = {
            ref
            for ref in raw_extra
            if not (
                ref == _normalize_published_reference(ref, keep_sublevel=False)
                and ref in loose_expected_set
            )
        }
        result["strict_extra_pct"] = len(raw_extra) / len(strict_expected_set)
    else:
        result["strict_found_pct"] = None
        result["strict_extra_pct"] = None

    return result


def reference_correctness_loose_published(
    pred_refs: Sequence[str], expected_refs: Sequence[str]
) -> float | None:
    """Published loose reference recall from ``src/ref_scoring.py``."""
    return compute_published_ref_scores(pred_refs, expected_refs)["loose_found_pct"]


def reference_correctness_strict_published(
    pred_refs: Sequence[str], expected_refs: Sequence[str]
) -> float | None:
    """Published first-sublevel strict reference recall from ``src/ref_scoring.py``."""
    return compute_published_ref_scores(pred_refs, expected_refs)["strict_found_pct"]


def reference_conciseness_published(
    pred_refs: Sequence[str], expected_refs: Sequence[str]
) -> float | None:
    """Published reference conciseness ``1 / (1 + strict_extra_pct)``."""
    extra = compute_published_ref_scores(pred_refs, expected_refs)["strict_extra_pct"]
    if extra is None:
        return None
    return 1.0 / (1.0 + extra)


# -- axis 3: answer conciseness ----------------------------------------------


# A real sentence end: a terminator, any closing quote or bracket, then whitespace
# or the end of the text. The whitespace requirement alone keeps the cut out of
# "Article 13.3" and "Annex XII.1(f)"; the lookbehinds keep it out of "Art. 5".
_SENTENCE_END = re.compile(
    r"(?<!\bArt)(?<!\bArts)(?<!\bpara)(?<!\bparas)(?<!\bcf)(?<!\be\.g)(?<!\bi\.e)"
    r"[.!?][\"')\]]*(?=\s|\Z)"
)


def truncate_to_chars(text: str, limit: int) -> str:
    """Cut ``text`` to at most ``limit`` characters AT A SENTENCE BOUNDARY.

    R460 - the length-control primitive. A correctness edge can be verbosity:
    the answer axes are judged from the answer text, and judges credit length.
    Re-judging an answer cut to its reference answer's own length separates the
    two. The cut lands on the last real sentence end that fits (a terminator
    followed by whitespace or the end of the text, not a citation coordinate or
    an abbreviation), because a mid-sentence cut would measure fluency damage
    rather than verbosity. When no sentence end fits it falls back to a whole-word
    prefix, never a mid-word cut. The result never exceeds ``limit``; an answer
    already at or under it is returned unchanged (the axis is one-sided, so there
    is nothing to control for below it).
    """
    text = text or ""
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    # Search one character past the window so a terminator that ENDS the window is
    # judged against the real next character, not against the end of the slice.
    ends = [m.end() for m in _SENTENCE_END.finditer(text[: limit + 1]) if m.end() <= limit]
    if ends:
        return text[: ends[-1]].strip()
    window = text[:limit]
    if window[-1].isspace() or text[limit].isspace():
        return window.strip()
    head = window.rsplit(None, 1)
    return head[0].strip() if len(head) == 2 else window.strip()


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


def answer_conciseness_published(answer: str, reference_answer: str) -> float | None:
    """Published word-count answer conciseness ``min(1, |ref_words| / |ans_words|)``."""
    ref_words = (reference_answer or "").split()
    if not ref_words:
        return None
    ans_words = (answer or "").split()
    if not ans_words:
        return 0.0
    return min(1.0, len(ref_words) / len(ans_words))


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


def score_rows(
    rows: Sequence[dict[str, Any]],
    *,
    profile: str = PROFILE_R391_REPORT,
) -> dict[str, Any]:
    """Score a captured arm under a versioned benchmark profile.

    ``profile="r391_report"`` (default) uses the R388/R391 formulas recovered from
    the 2026-08-25 report. ``profile="published_2026"`` uses the exact formulas
    from the released ``eu-ai-act-benchmark-2026`` repository (whitespace-word
    answer conciseness, first-sublevel strict reference recall, and
    parent-exempt excess-reference conciseness ``1 / (1 + strict_extra_pct)``).

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

    KNOWN DEVIATIONS from the released scorer under ``profile="published_2026"``
    (R474 - found by executing both on DEGENERATE inputs; on non-degenerate inputs
    they agree, 0 differences over 60,000 random reference sets and 8,000 random
    row sets): an EMPTY answer scores conciseness 0.0 here and 100 there
    (``100 / max(1, 0)``); a row with no ``latency_s`` counts as 0 s (speed 100)
    here and is excluded there; a set with no annotated references scores the
    reference axes and ``overall`` as 0.0 here and as ``None`` (dropped from the
    geometric mean) there. They are left as they are because a run that returned an
    empty answer or no latency is a failed run, which a score of 100 would reward;
    mirror the released handling only if replicating a released result file row for
    row matters more than that.
    """
    if profile not in RUBRIC_PROFILES:
        raise ValueError(
            f"Unknown rubric profile {profile!r}; expected one of {RUBRIC_PROFILES}"
        )
    crit = [list(r.get("criteria") or []) for r in rows]

    if profile == PROFILE_PUBLISHED_2026:
        ac_fn = answer_conciseness_published
        rl_fn = reference_correctness_loose_published
        rs_fn = reference_correctness_strict_published
        rc_fn = reference_conciseness_published
    else:
        ac_fn = answer_conciseness
        rl_fn = reference_correctness_loose
        rs_fn = reference_correctness_strict
        rc_fn = reference_conciseness

    ac = [
        ac_fn(r.get("answer", ""), r.get("reference_answer", ""))
        for r in rows
    ]
    ac = [v for v in ac if v is not None]

    rl = [
        rl_fn(r.get("references") or [], r.get("expected_refs") or [])
        for r in rows
    ]
    rs = [
        rs_fn(r.get("references") or [], r.get("expected_refs") or [])
        for r in rows
    ]
    rc = [
        rc_fn(r.get("references") or [], r.get("expected_refs") or [])
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
    # R474 - NOT ``out["profile"] = profile``. R473 put the profile NAME in this dict, which
    # ``score_arm`` writes verbatim as ``axes``; every consumer reads ``axes`` as numbers
    # (``docs/measurements/r423/build_need_report.py`` does ``{k: float(v) ...}`` and raised
    # ``ValueError: could not convert string to float: 'r391_report'`` on any new artifact).
    # The profile is the caller's explicit argument, not a property of the numbers.

    # Auditable alternatives and diagnostics.  None of these enter ``overall``.
    macro = [sum(1 for c in r if c) / len(r) for r in crit if r]
    out["_ans_loose_macro"] = round(_mean(macro) * 100.0, 4)
    out["_mean_answer_chars"] = round(_mean([len(r.get("answer") or "") for r in rows]), 1)
    out["_mean_reference_chars"] = round(
        _mean([len(r.get("reference_answer") or "") for r in rows]), 1
    )
    out["_mean_answer_words"] = round(
        _mean([len((r.get("answer") or "").split()) for r in rows]), 1
    )
    out["_mean_reference_words"] = round(
        _mean([len((r.get("reference_answer") or "").split()) for r in rows]), 1
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


def _mean_or_none(values: Sequence[float]) -> float | None:
    return fmean(values) if values else None


def _published_overall_score(values: Sequence[float | None]) -> float | None:
    available = [float(value) for value in values if value is not None]
    if not available:
        return None
    if any(v <= 0.0 for v in available):
        return 0.0
    return math.exp(fmean(math.log(value) for value in available))


def _validate_published_entries(entries: Sequence[dict[str, Any]], runs: int) -> None:
    """Reject missing repeats or malformed criterion lists before summarizing."""
    for idx, entry in enumerate(entries):
        jc = entry.get("judgements_correctness")
        jt = entry.get("judgements_tone")
        if not isinstance(jc, list) or not isinstance(jt, list):
            raise ValueError(
                f"Entry {idx} is missing judgements_correctness or judgements_tone list"
            )
        if len(jc) != runs or len(jt) != runs:
            raise ValueError(
                f"Entry {idx} has uneven repeat coverage: "
                f"len(judgements_correctness)={len(jc)}, len(judgements_tone)={len(jt)}, "
                f"expected={runs}"
            )
        expected_n: int | None = None
        if isinstance(entry.get("criteria_count"), int):
            expected_n = int(entry["criteria_count"])
        elif isinstance(entry.get("criteria"), list) and entry["criteria"]:
            expected_n = len(entry["criteria"])
        for r_idx, j_run in enumerate(jc):
            if not isinstance(j_run, dict) or not isinstance(j_run.get("criteria"), list):
                raise ValueError(
                    f"Entry {idx} repeat {r_idx} is missing a 'criteria' list"
                )
            c_list = j_run["criteria"]
            if not c_list:
                raise ValueError(
                    f"Entry {idx} repeat {r_idx} has an empty 'criteria' list"
                )
            if expected_n is None:
                expected_n = len(c_list)
            elif len(c_list) != expected_n:
                raise ValueError(
                    f"Entry {idx} repeat {r_idx} has {len(c_list)} criteria; "
                    f"expected {expected_n}"
                )
            for c_idx, item in enumerate(c_list):
                if not isinstance(item, dict) or not isinstance(item.get("passed"), bool):
                    raise ValueError(
                        f"Entry {idx} repeat {r_idx} criterion {c_idx} lacks boolean 'passed'"
                    )
        for r_idx, t_run in enumerate(jt):
            if (
                not isinstance(t_run, dict)
                or not isinstance(t_run.get("appropriateness_passed"), bool)
                or not isinstance(t_run.get("clarity_passed"), bool)
            ):
                raise ValueError(
                    f"Entry {idx} repeat {r_idx} tone judgement lacks boolean "
                    "'appropriateness_passed'/'clarity_passed'"
                )


def compute_published_run_metrics(
    entries: Sequence[dict[str, Any]], run_index: int
) -> list[float | None]:
    """Compute the 8 benchmark metrics for one judge repeat index (0-100 scale).

    Mirrors ``src/summarize_results.py:compute_run_metrics`` from the released
    benchmark repository, while also accepting rows carrying ``references``/
    ``expected_refs`` or ``answer``/``reference_answer`` if pre-computed
    ``strict_extra_pct`` / ``answer_conciseness_score`` keys are absent.
    """
    criteria: list[float] = []
    strict: list[float] = []
    tone: list[float] = []
    for entry in entries:
        judgements = entry.get("judgements_correctness") or []
        if run_index < len(judgements):
            flags = [
                bool(criterion["passed"])
                for criterion in (judgements[run_index].get("criteria") or [])
            ]
            if flags:
                criteria.extend(100.0 * flag for flag in flags)
                strict.append(100.0 * all(flags))
        t_judgements = entry.get("judgements_tone") or []
        if run_index < len(t_judgements):
            judgement = t_judgements[run_index]
            tone.append(
                100.0
                * bool(
                    judgement.get("appropriateness_passed")
                    and judgement.get("clarity_passed")
                )
            )

    ans_conc_vals: list[float] = []
    loose_found_vals: list[float] = []
    strict_found_vals: list[float] = []
    ref_conc_vals: list[float] = []
    speed_vals: list[float] = []

    for entry in entries:
        if entry.get("answer_conciseness_score") is not None:
            ans_conc_vals.append(100.0 / max(1.0, float(entry["answer_conciseness_score"])))
        elif "answer" in entry and "reference_answer" in entry:
            v = answer_conciseness_published(
                entry.get("answer", ""), entry.get("reference_answer", "")
            )
            if v is not None:
                ans_conc_vals.append(100.0 * v)

        if (
            "loose_found_pct" in entry
            or "strict_found_pct" in entry
            or "strict_extra_pct" in entry
        ):
            lf = entry.get("loose_found_pct")
            sf = entry.get("strict_found_pct")
            se = entry.get("strict_extra_pct")
        elif "references" in entry or "expected_refs" in entry:
            ref_scores = compute_published_ref_scores(
                entry.get("references") or [], entry.get("expected_refs") or []
            )
            lf = ref_scores["loose_found_pct"]
            sf = ref_scores["strict_found_pct"]
            se = ref_scores["strict_extra_pct"]
        else:
            lf = sf = se = None

        if lf is not None:
            loose_found_vals.append(100.0 * float(lf))
        if sf is not None:
            strict_found_vals.append(100.0 * float(sf))
        if se is not None:
            ref_conc_vals.append(100.0 / (1.0 + float(se)))

        lat = entry.get("latency_seconds", entry.get("latency_s"))
        if lat is not None:
            speed_vals.append(max(0.0, 100.0 - float(lat)))

    return [
        _mean_or_none(criteria),
        _mean_or_none(strict),
        _mean_or_none(ans_conc_vals),
        _mean_or_none(loose_found_vals),
        _mean_or_none(strict_found_vals),
        _mean_or_none(ref_conc_vals),
        _mean_or_none(tone),
        _mean_or_none(speed_vals),
    ]


def summarize_published_runs(
    entries: Sequence[dict[str, Any]],
    *,
    strict_coverage: bool = True,
) -> dict[str, Any]:
    """Summarize multi-run benchmark entries using the paper's per-run aggregation.

    Computes each metric per repeat run first, then aggregates ``mean``, ``min``,
    and ``max`` across runs (matching ``src/summarize_results.py:summarize``),
    rather than majority-voting criteria per question before scoring.

    When ``strict_coverage=True`` (default), validates that every row has the
    same number of correctness and tone judge repeats and that every repeat
    contains a complete, non-empty boolean criteria list.
    """
    if not entries:
        raise ValueError("The result file is empty")
    runs = max(
        max(
            len(entry.get("judgements_correctness") or []),
            len(entry.get("judgements_tone") or []),
        )
        for entry in entries
    )
    if runs < 1:
        raise ValueError("The result file contains no judge runs")
    if strict_coverage:
        _validate_published_entries(entries, runs)

    per_run = [compute_published_run_metrics(entries, index) for index in range(runs)]
    metrics: list[dict[str, float | None]] = []
    for index in range(len(PUBLISHED_LABELS)):
        values = [row[index] for row in per_run if row[index] is not None]
        metrics.append(
            {
                "mean": _mean_or_none(values),
                "min": min(values) if values else None,
                "max": max(values) if values else None,
            }
        )
    overall_runs = [_published_overall_score(row) for row in per_run]
    overall_valid = [score for score in overall_runs if score is not None]
    overall_summary = {
        "mean": _published_overall_score([metric["mean"] for metric in metrics]),
        "min": min(overall_valid) if overall_valid else None,
        "max": max(overall_valid) if overall_valid else None,
    }
    return {
        "rows": len(entries),
        "judge_runs": runs,
        "metrics": dict(zip(PUBLISHED_LABELS, metrics, strict=True)),
        "by_axis": dict(zip(AXIS_ORDER, metrics, strict=True)),
        "overall": overall_summary,
        "per_run": [
            {
                **dict(zip(AXIS_ORDER, row, strict=True)),
                "overall": overall_runs[idx],
            }
            for idx, row in enumerate(per_run)
        ],
    }
