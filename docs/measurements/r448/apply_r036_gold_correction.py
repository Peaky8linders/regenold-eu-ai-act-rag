"""R448 — apply the in-place source correction of the ``rg_036`` gold row.

**Why.** The reconstructed gold for ``rg_036`` read Article 42(1) as a
presumption about **Article 10(3)**, and therefore carried
``expected_refs: ["Article 10.4"]``. The adopted text does not say that:

* Article 42(1) — *"High-risk AI systems that have been trained and tested on
  data reflecting the specific geographical, behavioural, contextual or
  functional setting within which they are intended to be used shall be
  presumed to comply with the relevant requirements laid down in **Article
  10(4)**."*
* Article 10(4) is the *characteristics or elements particular to that setting*
  duty. Article 10(3) (relevance, representativeness, freedom from errors,
  completeness, statistical properties) is a **separate paragraph the
  presumption does not name**.

The row also self-contradicted the shipped key: the R388 grain-calibrated
refkey (`official_refkey_n110.jsonl`) has carried
``expected: ["Article 42.1"], unstable: false`` for ``rg_036`` all along, while
the gold row kept the wrong criterion and the wrong pre-refkey fallback.
`load_gold` lets the refkey win, so the defect was invisible in Ref. axes and
visible only in the judged criteria.

**What this writes.** The same shape R409 used for its four in-place
corrections (`docs/reviews/r409-r408-audit-2026-09-11.md`): corrected values on
the row, the pre-correction values preserved under ``_pre_r448``, and
``_revised: "R448"`` so `score_arm._criteria_match` refuses a cached verdict
judged against the old criteria. ``criteria_unstable`` flips to ``False``: the
row was flagged because the two generation samples disagreed, and the adopted
text now decides it.

Pinned by `tests/test_r444_article42_presumption_content.py::
test_unstable_gold_is_source_corrected_with_history_preserved`.

**Serialization.** The file is one `json.dumps` (default separators,
`ensure_ascii=True`) object per CRLF-terminated line. This script rewrites the
single matching line byte-identically in that form and leaves the other 109
lines untouched, so the diff is one line. R463: the split is newline-agnostic
and is asserted lossless before anything is written, and the write itself goes
through a sibling temp file + `os.replace` so an interrupt cannot leave a
partial corpus.

Usage::

    python docs/measurements/r448/apply_r036_gold_correction.py [--check]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"

ROW_ID = "rg_036"
REVISION = "R448"
REVISION_NOTE = (
    "R448: corrected against verbatim Act text - Article 42(1) presumes "
    "compliance with Article 10(4), not 10(3); refkey already carried "
    "Article 42.1 (apply_r036_gold_correction.py)"
)

#: The corrected criteria. ``criteria[0]`` names Article 10(4) and must NOT name
#: Article 10(3) — the presumption does not reach it.
CORRECTED_CRITERIA = [
    "Presumption of conformity under Article 42(1): a high-risk AI system trained "
    "and tested on data reflecting the specific geographical, behavioural, "
    "contextual or functional setting within which it is intended to be used is "
    "presumed to comply with the relevant requirements laid down in Article 10(4)",
    "Presumption is limited to the extent required by the intended purpose",
    "Not an exemption from other Article 10 obligations (e.g., bias "
    "examination/mitigation)",
]

CORRECTED_REFERENCE_ANSWER = (
    "Under Article 42(1), a high-risk AI system that has been trained and tested on "
    "data reflecting the specific geographical, behavioural, contextual or "
    "functional setting within which it is intended to be used is presumed to "
    "comply with the relevant requirements laid down in Article 10(4) — the duty on "
    "data sets to take into account, to the extent required by the intended "
    "purpose, the characteristics or elements particular to that setting. The "
    "presumption applies only to the extent required by the intended purpose. "
    "Article 42(1) does not expressly state whether the presumption has any "
    "broader implication for the rest of Article 10; it is not an exemption from "
    "the system's other Article 10 obligations, such as the data governance "
    "practices and bias examination and mitigation under Article 10(2), points "
    "(f) and (g)."
)

CORRECTED_REFS = ["Article 42.1"]

#: Fields copied verbatim into ``_pre_r448``, in R409's order.
_PRE_FIELDS = ("expected_refs", "criteria", "reference_answer", "criteria_unstable")


def corrected_row(row: dict) -> dict:
    """The corrected record: corrected values first, history last (R409 shape)."""
    pre = {k: row[k] for k in _PRE_FIELDS}
    out = {
        "id": row["id"],
        "question": row["question"],
        "expected_refs": CORRECTED_REFS,
        "criteria": list(CORRECTED_CRITERIA),
        "reference_answer": CORRECTED_REFERENCE_ANSWER,
        "criteria_unstable": False,
        "_sample_a_n": row.get("_sample_a_n"),
        "_sample_b_n": row.get("_sample_b_n"),
        "_revised": REVISION,
        "_revision_note": REVISION_NOTE,
        f"_pre_{REVISION.lower()}": pre,
    }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report whether it is already applied")
    a = ap.parse_args()

    raw = GOLD.read_bytes()
    # R463 - newline-agnostic, with a byte-identity guard. This was
    # ``raw.split(b"\r\n")``: exact on the CRLF tree the repo ships, but on the LF
    # tree AGENTS.md tells agents to reproduce (``git -c core.autocrlf=false
    # archive``) it returns the WHOLE file as one element and the script exits 2
    # "found 0". Splitting on the newline-agnostic pattern and rejoining with this
    # checkout's own newline reproduces the bytes exactly (asserted right below),
    # so the rewrite stays a one-line diff on both trees, and a mixed-ending file
    # fails loudly instead of being silently normalised.
    newline = b"\r\n" if b"\r\n" in raw else b"\n"
    lines = re.split(rb"\r?\n", raw)
    assert newline.join(lines) == raw, "split/join is not lossless for this checkout"
    hits = [i for i, b in enumerate(lines) if b.startswith(b'{"id": "%s"' % ROW_ID.encode())]
    if len(hits) != 1:
        print(f"expected exactly one {ROW_ID} line, found {len(hits)}", file=sys.stderr)
        return 2
    idx = hits[0]
    row = json.loads(lines[idx])

    if row.get("_revised") == REVISION:
        print(f"{ROW_ID}: already revised to {REVISION}; nothing to do")
        return 0
    if a.check:
        print(f"{ROW_ID}: NOT corrected (criteria_unstable={row.get('criteria_unstable')})")
        return 1

    new = corrected_row(row)
    lines[idx] = json.dumps(new).encode("utf-8")
    # R463 - ATOMIC. This truncated and rewrote all 110 rows in place, so an
    # interrupt mid-write left a partial corpus; and this file is the source of
    # every gold ``expected_refs``/``criteria`` decision, so the damage would be
    # silent and total rather than a failed run. Write a sibling temp file and
    # ``os.replace`` it, which is atomic on one filesystem.
    tmp = GOLD.with_suffix(GOLD.suffix + ".tmp")
    tmp.write_bytes(newline.join(lines))
    os.replace(tmp, GOLD)
    print(f"{ROW_ID}: wrote {GOLD}")

    # Verify the effect from a fresh read, not from `new`.
    for b in re.split(rb"\r?\n", GOLD.read_bytes()):
        if not b.startswith(b'{"id": "%s"' % ROW_ID.encode()):
            continue
        got = json.loads(b)
        assert got["criteria_unstable"] is False, got["criteria_unstable"]
        assert got["_revised"] == REVISION, got["_revised"]
        assert "Article 10(4)" in got["criteria"][0]
        assert "Article 10(3)" not in got["criteria"][0]
        assert got["expected_refs"] == ["Article 42.1"], got["expected_refs"]
        assert f"_pre_{REVISION.lower()}" in got
        break
    else:  # pragma: no cover — the single-match guard above already ran
        raise AssertionError(f"{ROW_ID} vanished after the write")

    print(f"{ROW_ID}: revised to {REVISION} (criteria_unstable True -> False)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
