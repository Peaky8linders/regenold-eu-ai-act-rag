"""R460 - add LENGTH-CONTROLLED judging to the official instrument (opt-in).

Why this exists. The answer axes are judged from the answer TEXT, and verbosity
bias in LLM judges is a robust, well-documented effect: longer answers collect
more credit unless length is controlled for. Length-Controlled AlpacaEval is the
standard debiasing (regress the verdict on the length differential), and every
judge-bias survey lists length first. This engine ships answers 1.25x the
reference length, so part of our correctness edge over the 2026 frontier could be
verbosity rather than knowledge -- and nothing in the instrument could tell.

The reference-based analogue for a criteria rubric: re-judge every answer CUT to
its own reference answer's length, and report the answer axes again. A real
correctness edge survives the cut; one that lives in extra sentences does not.
The cut lands on a sentence boundary (cutting mid-sentence would measure fluency
damage instead), and it never expands a short answer.

The pass is opt-in (``--length-control``), not cached (it re-judges each run), and
never replaces the raw axes: both are reported, so the delta IS the measurement.

    ../../.venv/Scripts/python.exe docs/measurements/r460/apply_length_control.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

RUBRIC = ROOT / "evals" / "official" / "rubric.py"
SCORE_ARM = ROOT / "evals" / "official" / "score_arm.py"
TEST = ROOT / "tests" / "test_r460_length_control.py"

HELPER = '''
def truncate_to_chars(text: str, limit: int) -> str:
    """Cut ``text`` to at most ``limit`` characters AT A SENTENCE BOUNDARY.

    R460 - the length-control primitive. A correctness edge can be verbosity:
    the answer axes are judged from the answer text, and judges credit length.
    Re-judging an answer cut to its reference answer's own length separates the
    two. The cut lands on the last sentence terminator that fits, because a
    mid-sentence cut would measure fluency damage rather than verbosity; an
    answer already at or under the limit is returned unchanged (the axis is
    one-sided, so there is nothing to control for below it).
    """
    text = text or ""
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    window = text[:limit]
    cut = max(window.rfind("."), window.rfind("!"), window.rfind("?"))
    if cut <= 0:
        return window.strip()
    return window[: cut + 1].strip()


'''

ARG_ANCHOR = "    a = ap.parse_args()\n"

ARG_NEW = '''    ap.add_argument(
        "--length-control",
        action="store_true",
        default=False,
        help="R460 - also re-judge every answer CUT to its reference answer's "
        "length, and report those answer axes next to the raw ones. Separates a "
        "real correctness edge from one that lives in extra sentences (the "
        "length-controlled-debiasing idea applied to a criteria rubric). Not "
        "cached: this pass re-judges on every run.",
    )
    a = ap.parse_args()
'''

HELPERS_ANCHOR = "def _graded_latency_ms(r: dict) -> float:\n"

HELPERS_NEW = '''def _length_controlled_rows(rows: list[dict]) -> list[dict]:
    """The same rows with each answer cut to the row's own reference length.

    Rows whose answer is already at or under the reference length are returned
    verbatim: the conciseness axis is one-sided, so there is no excess to remove,
    and cutting would only damage the answer.
    """
    from evals.official.rubric import truncate_to_chars  # noqa: PLC0415

    out = []
    for r in rows:
        ref = r.get("reference_answer") or ""
        ans = r.get("answer") or ""
        capped = ans if (not ref or len(ans) <= len(ref)) else truncate_to_chars(ans, len(ref))
        out.append({**r, "answer": capped})
    return out


def _graded_latency_ms(r: dict) -> float:
'''

BLOCK_ANCHOR = '    ordered = [by_id[r["id"]] for r in rows if r["id"] in by_id]\n'

BLOCK_NEW = '''    ordered = [by_id[r["id"]] for r in rows if r["id"] in by_id]

    # R460 - LENGTH CONTROL (opt-in, not cached). Re-judge the answers cut to
    # their reference length, so a correctness edge that exists only because the
    # answer is longer cannot be read as knowledge. Both sets of axes ship.
    length_controlled: dict[str, Any] | None = None
    if a.length_control:
        capped = _length_controlled_rows(ordered)
        cut = sum(1 for r, c in zip(ordered, capped) if r["answer"] != c["answer"])
        print(
            f"\\nlength control: re-judging {len(capped)} rows with {cut} answers cut "
            f"to their reference length (not cached -- this pass re-judges each run)"
        )
        lc_judged = official_judge.judge_rows(
            capped, workers=a.workers, repeats=a.repeats
        )
        lc_dead = [j for j in lc_judged if not j.get("_judge_runs", 0)]
        if lc_dead:
            print(
                f"  {'!' * 68}\\n  LENGTH-CONTROL PASS DEGRADED: "
                f"{len(lc_dead)}/{len(lc_judged)} rows returned NO live judge run and "
                f"were scored all-False.\\n  The controlled axes below are NOT a "
                f"measurement; re-run with --workers 1.\\n  {'!' * 68}"
            )
        by_lc = {r["id"]: r for r in capped}
        for j in lc_judged:
            if j.get("id") in by_lc:
                by_lc[j["id"]].update(j)
        lc_order = [by_lc[r["id"]] for r in ordered if r["id"] in by_lc]
        lc_res = score_rows(lc_order)
        length_controlled = {
            "answers_cut": cut,
            "cached": False,
            "axes": {
                k: lc_res[k]
                for k in (
                    "ans_correctness_loose",
                    "ans_correctness_strict",
                    "ans_conciseness",
                    "regulatory_tone",
                )
            },
        }
        print("  length-controlled (answer cut to the reference length):")
        for k, v in length_controlled["axes"].items():
            print(f"    {k:<26}{v:>8.2f}   (raw {res[k]:.2f})")
'''

PAYLOAD_ANCHOR = '        "axes": res,\n'

PAYLOAD_NEW = '        "axes": res,\n        "length_controlled": length_controlled,\n'

TEST_SOURCE = '''"""R460 - length-controlled judging in the official instrument.

The answer axes are judged from the answer text and judges credit length, so a
correctness edge can be verbosity. ``--length-control`` re-judges every answer cut
to its own reference length; these tests pin the cut (sentence boundary, never
expanding, never empty) and the row builder (an answer already within the
reference length is returned verbatim).
"""
from __future__ import annotations

import inspect

from evals.official.rubric import truncate_to_chars
from evals.official.score_arm import _length_controlled_rows


def test_returns_short_text_unchanged():
    for text, limit in (("Short.", 100), ("Exactly ten.", 13), ("", 10)):
        assert truncate_to_chars(text, limit) == text


def test_cuts_at_a_sentence_boundary():
    text = "First sentence here. Second sentence here. Third one runs on and on."
    cut = truncate_to_chars(text, 40)
    assert cut == "First sentence here. Second sentence here."
    assert len(cut) <= 40


def test_never_cuts_below_one_sentence_or_leaks_past_the_limit():
    text = "A single very long sentence that has no early terminator at all"
    cut = truncate_to_chars(text, 20)
    assert cut == text[:20].strip()
    assert truncate_to_chars("No terminator anywhere in this text", 0) == ""


def test_non_positive_limit_is_empty():
    assert truncate_to_chars("anything", -5) == ""


def test_row_builder_cuts_only_over_length_answers():
    rows = [
        {"id": "a", "answer": "One. Two. Three.", "reference_answer": "One."},
        {"id": "b", "answer": "Short.", "reference_answer": "A much longer reference answer."},
        {"id": "c", "answer": "", "reference_answer": "Reference."},
        {"id": "d", "answer": "Answer without a reference answer.", "reference_answer": ""},
    ]
    out = _length_controlled_rows(rows)
    assert out[0]["answer"] == "One."            # cut to the 4-char reference
    assert out[1]["answer"] == "Short."          # already under: verbatim
    assert out[2]["answer"] == ""                # empty stays empty
    assert out[3]["answer"] == rows[3]["answer"]  # no reference: no control
    assert [r["id"] for r in out] == ["a", "b", "c", "d"]
    for original, capped in zip(rows, out):
        assert capped["question"] if "question" in capped else True
        assert original is not capped  # a copy, never an in-place mutation


def test_flag_is_wired_and_reported_in_the_payload():
    import evals.official.score_arm as score_arm

    source = inspect.getsource(score_arm)
    assert "--length-control" in source
    assert '"length_controlled": length_controlled' in source
    assert "LENGTH-CONTROL PASS DEGRADED" in source, "a dead judge must be loud"
'''


def patch(path: Path, old: str, new: str, *, label: str) -> None:
    raw = path.read_text(encoding="utf-8")
    crlf = "\r\n" in raw
    o = old.replace("\n", "\r\n") if crlf else old
    n = new.replace("\n", "\r\n") if crlf else new
    if new and n in raw and o not in raw:
        print(f"  already applied: {label}")
        return
    count = raw.count(o)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 match in {path.name}, found {count}")
    path.write_text(raw.replace(o, n, 1), encoding="utf-8")
    print(f"  applied: {label}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    print("rubric.py:")
    patch(RUBRIC, "def answer_conciseness(answer: str, reference_answer: str)",
          HELPER.lstrip("\n") + "def answer_conciseness(answer: str, reference_answer: str)",
          label="truncate_to_chars")
    print("score_arm.py:")
    patch(SCORE_ARM, ARG_ANCHOR, ARG_NEW, label="--length-control flag")
    patch(SCORE_ARM, HELPERS_ANCHOR, HELPERS_NEW, label="_length_controlled_rows")
    patch(SCORE_ARM, BLOCK_ANCHOR, BLOCK_NEW, label="controlled judging pass")
    patch(SCORE_ARM, PAYLOAD_ANCHOR, PAYLOAD_NEW, label="payload field")
    print("tests:")
    if TEST.exists() and "truncate_to_chars" in TEST.read_text(encoding="utf-8"):
        print("  already applied: test file")
    else:
        TEST.write_text(TEST_SOURCE, encoding="utf-8")
        print("  wrote tests/test_r460_length_control.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
