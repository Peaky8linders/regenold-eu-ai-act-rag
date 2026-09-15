"""R419 — the judge reply parser must not discard a valid judgement.

THE DEFECT THIS PINS
--------------------
``_parse``'s fallback took the FIRST opener with the LAST closer. The hosted Qwen
235B judge sometimes emits TWO objects in sequence — ``{"verdicts": ...}`` then
``{"tone": ...}`` — so that slice spanned text that is not JSON; the parser then
fell through to the ``[``/``]`` pair, which returned the INNER ``verdicts`` ARRAY
as if it were the payload. ``judge_grouped_once`` requires a dict, so the row was
recorded as having NO live run and scored all-False.

MEASURED on the R419 hard board: ``rg_045`` and ``rg_066`` had no live run on all
three repetitions, while the same prompt over the same rows parsed fine on a
correctness-only call. One dead row out of 108 is under R414's 20 % void
threshold, so the run PUBLISHED with those rows scored zero — the quiet-zero
failure shape this module exists to prevent, arriving by a third route.

The fix decodes every complete value and MERGES multiple objects, so a reply that
splits the two halves still scores both.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from evals.official import judge as J  # noqa: E402

#: The shape that broke: two objects, verdicts then tone.
_TWO_OBJECTS = (
    '{"verdicts": [{"n": 1, "satisfied": true, "why": "a"}, '
    '{"n": 2, "satisfied": false, "why": "b"}]}\n'
    '{"tone": {"appropriate": true, "clear": true}, "tone_remark": "clear"}'
)


def test_two_objects_are_merged_not_truncated_to_the_inner_array() -> None:
    d = J._parse(_TWO_OBJECTS)
    assert isinstance(d, dict), "a two-object reply must not collapse to the verdicts array"
    assert len(d["verdicts"]) == 2
    assert d["tone"] == {"appropriate": True, "clear": True}


def test_the_payload_is_never_the_inner_verdict_array() -> None:
    """The regression, stated as the property the callers depend on.

    ``judge_grouped_once`` returns ``(None, None)`` for anything that is not a
    dict, which the transport guard then reads as NO LIVE RUN. So the parsed
    payload must never be the bare verdicts array — even though that array is
    perfectly valid JSON and the old first-opener/last-closer slice returned it.
    """
    parsed = J._parse(_TWO_OBJECTS)
    assert not isinstance(parsed, list)
    assert isinstance(parsed, dict) and "verdicts" in parsed

    # And the inner array on its own still arrives as an envelope, not as a list.
    inner_only = '{"verdicts": [{"n": 1, "satisfied": true}]}'
    assert isinstance(J._parse(inner_only), dict)


def test_fenced_and_chatty_replies_still_parse() -> None:
    assert J._parse('```json\n{"a": 1}\n```') == {"a": 1}
    assert J._parse('Here is the JSON you asked for:\n{"a": 1}\nDone.') == {"a": 1}


def test_bare_verdict_list_is_normalised_into_the_envelope() -> None:
    payload = J._normalise_payload(
        [{"n": 1, "satisfied": True, "why": "a"}, {"n": 2, "satisfied": False, "why": "b"}]
    )
    assert payload is not None
    assert [v["n"] for v in payload["verdicts"]] == [1, 2]


def test_split_list_of_objects_merges() -> None:
    payload = J._normalise_payload(
        [{"verdicts": [{"n": 1, "satisfied": True}]}, {"tone": {"appropriate": False, "clear": True}}]
    )
    assert payload is not None
    assert "verdicts" in payload and "tone" in payload


def test_a_plain_object_and_nothing_parseable() -> None:
    assert J._normalise_payload({"verdicts": []}) == {"verdicts": []}
    assert J._normalise_payload("not json") is None
    assert J._normalise_payload([1, 2, 3]) is None
    assert J._parse("no json here") is None
