"""R132 — markdown-table flattening in the answer normaliser.

Live Stage-2 (Sonnet) sometimes answers an either/or classification
question ("Is X prohibited? Or is it high-risk?") with a structured
"Verdict:" markdown table:

    Verdict:

    | Scenario | Classification |
    |---|---|
    | Standalone transcription tool | Limited-risk (Article 50) |
    | Embedded medical-device safety component | High-risk (Article 6) |

``_strip_markdown`` handled headings / list markers / emphasis but NOT
tables, so the per-line terminator loop appended a period to each
pipe-row, and the downstream caps dropped the data rows — shipping the
broken, content-free fragment the user reported:

    "... Verdict. | Scenario | Classification |. |---|---|."

These tests pin the fix: the wire answer must never carry markdown
table syntax (pipe-delimited rows, ``|---|---|`` delimiters, thematic
breaks). Delimiter / pure-punctuation rows are dropped, the header row
(content row directly above a delimiter) is dropped, and each remaining
data row is flattened to comma-joined prose so the substance survives.
"""

from __future__ import annotations

from app.integrations.regenold.models import (
    _strip_markdown,
    normalise_answer_for_regenold,
)


class TestStripMarkdownTables:
    def test_delimiter_row_dropped(self) -> None:
        out = _strip_markdown(
            "| Scenario | Classification |\n|---|---|\n"
            "| Standalone tool | Limited-risk |"
        )
        assert "|" not in out
        assert "---" not in out

    def test_header_row_dropped_when_followed_by_delimiter(self) -> None:
        out = _strip_markdown(
            "| Scenario | Classification |\n|---|---|\n"
            "| Standalone tool | Limited-risk (Article 50) |"
        )
        # The header row is metadata, not content — dropped.
        assert "Scenario, Classification" not in out
        # The data row content survives as flowing prose.
        assert "Standalone tool" in out
        assert "Limited-risk (Article 50)" in out
        assert "|" not in out

    def test_data_row_flattened_to_prose(self) -> None:
        out = _strip_markdown(
            "| Standalone transcription tool | Limited-risk (Article 50) |"
        )
        assert out == "Standalone transcription tool, Limited-risk (Article 50)."

    def test_thematic_break_dropped(self) -> None:
        out = _strip_markdown("First point.\n\n---\n\nSecond point.")
        assert "---" not in out
        assert "First point." in out
        assert "Second point." in out

    def test_plain_prose_unchanged_no_false_positive(self) -> None:
        raw = (
            "Article 5 prohibits manipulative techniques. "
            "Article 6 governs high-risk systems."
        )
        assert _strip_markdown(raw) == raw

    def test_parenthetical_prose_untouched(self) -> None:
        # A normal sentence (no pipes) must be byte-identical — guards
        # against an over-broad table detector firing on prose.
        raw = "The system (a medical device) is high-risk under Article 6."
        assert _strip_markdown(raw) == raw


class TestNormaliseNoBrokenTableFragment:
    def test_reported_failure_ships_no_pipe_fragment(self) -> None:
        raw = (
            "Article 5 does not prohibit an AI system that transcribes "
            "doctor-patient conversations. A standalone transcription tool "
            "that merely records and converts speech to text does not fall "
            "within any Annex III category and is not high-risk under "
            "Article 6(2). Article 50 transparency obligations are the "
            "operative provision for most deployments.\n\n"
            "Verdict:\n\n"
            "| Scenario | Classification |\n"
            "|---|---|\n"
            "| Standalone transcription tool | Limited-risk (Article 50) |\n"
            "| Embedded medical-device safety component | High-risk (Article 6) |"
        )
        out = normalise_answer_for_regenold(
            raw, question="Is transcription prohibited or high-risk?"
        )
        assert "|" not in out
        assert "---" not in out
        assert "Classification |" not in out
        # The prose answer survives.
        assert "Article 5" in out

    def test_bare_verdict_label_dropped(self) -> None:
        raw = (
            "Verdict. Article 5 does not prohibit transcription, which is "
            "instead governed by the Article 50 transparency obligations."
        )
        out = normalise_answer_for_regenold(raw, question="")
        assert not out.lower().lstrip().startswith("verdict")
        assert "Article 5" in out
