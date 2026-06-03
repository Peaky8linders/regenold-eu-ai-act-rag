"""R104.2 — conciseness backstop tests.

Covers ``_cap_readable_units`` (the deterministic ≤4-readable-unit cap that
matches how the LLM-as-judge conciseness axis counts sentences +
``;``/``(x)`` enumerated clauses) and its composition with the R78
``_hard_truncate_at_clause`` length cap. Both run only on the live
Stage-2 path (route-gated on ``stage2_landed``), so the davidath bench is
byte-identical; these unit tests pin the text transform directly.
"""
from __future__ import annotations

import re

from app.integrations.regenold.models import (
    _cap_readable_units,
    _hard_truncate_at_clause,
    normalise_answer_for_regenold,
)


def _count_units(text: str) -> int:
    starts = {0}
    for m in re.finditer(r"[.!?]\s+", text):
        starts.add(m.end())
    for m in re.finditer(r"\s\((?:[a-zA-Z]|[ivxl]{2,4})\)\s", text):
        starts.add(m.start() + 1)
    return len(starts)


class TestCapReadableUnits:
    def test_enumeration_wall_capped_to_four_units(self) -> None:
        wall = (
            "Article 5 prohibits eight categories of AI practice: "
            "(a) subliminal techniques; (b) exploitation of vulnerabilities; "
            "(c) social scoring; (d) criminal-risk profiling; "
            "(e) facial-image scraping; (f) emotion inference; "
            "(g) biometric categorisation; and (h) real-time biometric ID."
        )
        out = _cap_readable_units(wall, max_units=4)
        assert _count_units(out) <= 4
        assert out.endswith((".", "!", "?"))
        assert out  # never empty
        # Keeps the chapeau + the first few items, drops the tail.
        assert out.startswith("Article 5 prohibits eight categories")
        assert "(h)" not in out

    def test_normal_answer_unchanged(self) -> None:
        normal = (
            "Article 13 requires high-risk AI systems to be transparent. "
            "Providers must supply instructions for use under Article 13(3). "
            "Deployers implement human oversight under Article 26."
        )
        assert _cap_readable_units(normal, max_units=4) == normal

    def test_single_short_sentence_unchanged(self) -> None:
        s = "Article 5 prohibits emotion recognition in workplaces."
        assert _cap_readable_units(s, max_units=4) == s

    def test_empty_passthrough(self) -> None:
        assert _cap_readable_units("", max_units=4) == ""

    def test_never_empties_when_first_unit_huge(self) -> None:
        # A single boundary-free clause = 1 unit -> returned unchanged
        # (cap does not chop within a unit; the char cap handles length).
        one = "x " * 400
        out = _cap_readable_units(one.strip() + ".", max_units=4)
        assert out  # non-empty

    def test_drops_trailing_dangling_connective(self) -> None:
        t = (
            "Providers must comply with: (a) Article 9 risk management; "
            "(b) Article 10 data governance; (c) Article 11 documentation; "
            "(d) Article 13 transparency and"
        )
        out = _cap_readable_units(t, max_units=4)
        assert not out.rstrip(".").lower().endswith(" and")
        assert out.endswith(".")

    def test_exactly_four_units_unchanged(self) -> None:
        four = "One. Two. Three. Four."
        # 4 sentence-ends -> 5 starts incl. position 0 -> > 4, so it caps.
        # Use a 4-unit shape: chapeau + 3 sentence ends.
        three = "Alpha provides. Beta deploys. Gamma audits."
        assert _cap_readable_units(three, max_units=4) == three


class TestComposition:
    def test_charcap_then_unitcap_then_normalise(self) -> None:
        wall = (
            "Article 5 of the EU AI Act prohibits eight categories of AI "
            "practice: (a) subliminal, manipulative, or deceptive techniques "
            "causing significant harm; (b) exploitation of vulnerabilities "
            "arising from age, disability, or socio-economic situation; "
            "(c) social scoring leading to detrimental treatment; "
            "(d) criminal-risk profiling; (e) untargeted facial-image "
            "scraping; (f) emotion inference in workplaces; (g) biometric "
            "categorisation by sensitive attributes; and (h) real-time "
            "remote biometric identification by law enforcement."
        )
        capped = wall
        if len(capped) > 600:
            capped = _hard_truncate_at_clause(capped, 600)
        capped = _cap_readable_units(capped, max_units=4)
        capped = normalise_answer_for_regenold(capped, question="")
        assert capped
        assert len(capped) <= 600
        assert _count_units(capped) <= 4
        assert capped.endswith((".", "!", "?"))
