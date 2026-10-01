"""R460 — the EvidenceBundle must be lossless, and inert until it is gated ON."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.engines.evidence_bundle import (
    EVIDENCE_BLOCK_HEADER,
    EVIDENCE_BUNDLE_ENV,
    EVIDENCE_BUNDLE_LEVEL_ENV,
    evidence_bundle_enabled,
    evidence_bundle_level,
    minify_evidence_block,
    parse_evidence_block,
    provision_of,
)

_REPO = Path(__file__).resolve().parents[1]
_CAPTURE = _REPO / "docs" / "measurements" / "r460" / "stage2-payloads.jsonl"

#: Shaped exactly like the renderer's output: two node ids for ONE provision
#: (the KB duplication), a "NOT ENGAGED" structure block whose members the
#: prompt says not to enumerate, and an engaged section.
_BODY = "\n".join(
    [
        "APPLICABLE OBLIGATIONS (2):",
        "- [kb-risk_mgmt-Art. 6] Classifies an AI system as high-risk on two routes. "
        "Annex I route (Article 6(1)): the system is a safety component.",
        "- [kb-xref-risk_mgmt-Art. 6] Classifies an AI system as high-risk on two routes. "
        "Annex I route (Article 6(1)): the system is a safety component.",
        "",
        "  STRUCTURE of Annex III — 32 members, NOT ENGAGED by this question: "
        "context only, do NOT enumerate or list them:",
        "    Annex III.1",
        "    Annex III.1.a",
        "    Annex III.2",
        "  VERBATIM (question-relevant): point (a): remote biometric identification systems.",
        "",
        "ARTICLE-SPECIFIC OBLIGATIONS (1):",
        "- [kb-art-Art. 13-13(1)] High-risk AI systems shall be designed and developed "
        "in such a way as to ensure that their operation is sufficiently transparent.",
        "TRAILING LINE THAT MUST SURVIVE",
    ]
)
_BLOCK = f"{EVIDENCE_BLOCK_HEADER}\n{_BODY}"


def _captured_users() -> list[str]:
    if not _CAPTURE.exists():
        return []
    out = []
    for line in _CAPTURE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line)["user"])
    return out


def _is_subsequence(kept: list[str], raw: list[str]) -> bool:
    cursor = 0
    for line in kept:
        while cursor < len(raw) and raw[cursor] != line:
            cursor += 1
        if cursor >= len(raw):
            return False
        cursor += 1
    return True


def test_gate_defaults_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(EVIDENCE_BUNDLE_ENV, raising=False)
    monkeypatch.delenv(EVIDENCE_BUNDLE_LEVEL_ENV, raising=False)
    assert evidence_bundle_enabled() is False
    assert evidence_bundle_level() == 1


@pytest.mark.parametrize("value", ["0", "false", "off", "no", "", "garbage"])
def test_gate_deny_list(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(EVIDENCE_BUNDLE_ENV, value)
    assert evidence_bundle_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "YES", "on", "On"])
def test_gate_truthy(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(EVIDENCE_BUNDLE_ENV, value)
    assert evidence_bundle_enabled() is True


def test_level_clamps_to_a_known_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(EVIDENCE_BUNDLE_LEVEL_ENV, "7")
    assert evidence_bundle_level() == 1
    monkeypatch.setenv(EVIDENCE_BUNDLE_LEVEL_ENV, "2")
    assert evidence_bundle_level() == 2


def test_render_is_byte_identical_to_the_parsed_span() -> None:
    bundle = parse_evidence_block(_BLOCK)
    assert bundle.render() == bundle.raw
    bundle.verify()


def test_render_is_byte_identical_on_the_whole_user_message() -> None:
    message = (
        f"ORIGINAL QUESTION: x\n\n{EVIDENCE_BLOCK_HEADER}\n{_BODY}\n\n"
        "ANSWER CONTRACT (evidence):\nbody\n"
    )
    bundle = parse_evidence_block(message)
    bundle.verify()
    assert bundle.render() == bundle.raw
    assert bundle.raw.startswith("APPLICABLE OBLIGATIONS")
    # The typed view never rewrites the span it was handed.
    assert bundle.render() in message


def test_items_and_sections_are_typed() -> None:
    bundle = parse_evidence_block(_BLOCK)
    assert [s for s, _ in bundle.sections] == [
        "APPLICABLE OBLIGATIONS",
        "ARTICLE-SPECIFIC OBLIGATIONS",
    ]
    assert [i.source_id for i in bundle.items] == [
        "kb-risk_mgmt-Art. 6",
        "kb-xref-risk_mgmt-Art. 6",
        "kb-art-Art. 13-13(1)",
    ]
    assert [i.provision for i in bundle.items] == ["Article 6", "Article 6", "Article 13(1)"]
    assert [i.section for i in bundle.items] == [
        "APPLICABLE OBLIGATIONS",
        "APPLICABLE OBLIGATIONS",
        "ARTICLE-SPECIFIC OBLIGATIONS",
    ]


def test_non_citable_section_marks_its_items_context_only() -> None:
    block = (
        f"{EVIDENCE_BLOCK_HEADER}\n"
        "KNOWLEDGE-GRAPH CROSS-REGULATORY MAPPINGS (framework mappings to GDPR, "
        "EU Charter, MDR/IVDR — non-citable context):\n"
        "- [kb-xref-Art. 5] GDPR mapping.\n"
    )
    bundle = parse_evidence_block(block)
    assert len(bundle.items) == 1
    assert bundle.items[0].context_only is True


def test_provision_of_handles_both_id_shapes() -> None:
    assert provision_of("kb-xref-risk_mgmt-Art. 6.3") == "Article 6.3"
    assert provision_of("kb-art-Art. 13-13(3)(b)(ii)") == "Article 13(3)(b)(ii)"
    assert provision_of("kb-risk_mgmt-Annex III") == "Annex III"
    assert provision_of("kb-governance-Art. 111") == "Article 111"
    assert provision_of("kb-xref-risk_mgmt-Art. 5") == "Article 5"
    assert provision_of("nonsense") == ""


def test_gate_off_is_a_strict_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(EVIDENCE_BUNDLE_ENV, raising=False)
    assert minify_evidence_block(_BLOCK) == _BLOCK


def test_gate_on_routes_through_the_minifier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(EVIDENCE_BUNDLE_ENV, "1")
    monkeypatch.setenv(EVIDENCE_BUNDLE_LEVEL_ENV, "1")
    out = minify_evidence_block(_BLOCK)
    assert out == parse_evidence_block(_BLOCK).minified(level=1)
    assert len(out) < len(_BLOCK)


def test_level1_drops_only_the_duplicate_provision_item() -> None:
    out = parse_evidence_block(_BLOCK).minified(level=1)
    assert "[kb-xref-risk_mgmt-Art. 6]" not in out
    assert "[kb-risk_mgmt-Art. 6]" in out
    assert "[kb-art-Art. 13-13(1)]" in out
    assert _BLOCK.count("Classifies an AI system as high-risk") == 2
    assert out.count("Classifies an AI system as high-risk") == 1
    assert len(out) < len(_BLOCK)


def test_level1_keeps_the_longer_of_two_prefix_renderings() -> None:
    # Make the FIRST item the longer rendering: the second is then a strict
    # prefix of it, so the second is the one dropped.
    block = _BLOCK.replace(
        "Annex I route (Article 6(1)): the system is a safety component.",
        "Annex I route (Article 6(1)): the system is a safety component. EXTRA TAIL.",
        1,
    )
    out = parse_evidence_block(block).minified(level=1)
    assert out.count("EXTRA TAIL") == 1
    assert "[kb-risk_mgmt-Art. 6]" in out
    assert "[kb-xref-risk_mgmt-Art. 6]" not in out


def test_level1_never_drops_a_distinct_provision() -> None:
    block = _BLOCK.replace(
        "Annex I route (Article 6(1)): the system is a safety component.",
        "A DIFFERENT body that is not a prefix of the first item.",
        1,
    )
    out = parse_evidence_block(block).minified(level=1)
    assert "[kb-xref-risk_mgmt-Art. 6]" in out
    assert "[kb-risk_mgmt-Art. 6]" in out


def test_level2_drops_non_engaged_members_but_keeps_the_heading() -> None:
    out = parse_evidence_block(_BLOCK).minified(level=2)
    assert "    Annex III.1" not in out
    assert "    Annex III.1.a" not in out
    assert "    Annex III.2" not in out
    # The heading survives: it carries the count and the ANSWER SHAPE clause
    # points at these lists.
    assert "STRUCTURE of Annex III" in out
    assert "NOT ENGAGED by this question" in out
    # A non-member line under the same block is not part of the member list.
    assert "VERBATIM (question-relevant)" in out


def test_minified_output_is_a_subsequence_of_raw_lines() -> None:
    bundle = parse_evidence_block(_BLOCK)
    for level in (1, 2):
        kept = bundle.minified(level=level).split("\n")
        assert _is_subsequence(kept, list(bundle.lines)), f"level {level} reordered a line"


def test_engaged_content_is_never_removed_at_either_level() -> None:
    bundle = parse_evidence_block(_BLOCK)
    engaged = {
        i.text
        for i in bundle.items
        if not i.context_only and "kb-xref-risk_mgmt-Art. 6" not in i.text
    }
    for level in (1, 2):
        kept = set(bundle.minified(level=level).split("\n"))
        missing = engaged - kept
        assert not missing, f"level {level} dropped an engaged item: {missing}"


def test_trailing_line_survives() -> None:
    out = parse_evidence_block(_BLOCK).minified(level=2)
    assert out.rstrip("\n").endswith("TRAILING LINE THAT MUST SURVIVE")


@pytest.mark.skipif(not _CAPTURE.exists(), reason="R460 capture not present")
def test_lossless_over_every_captured_payload() -> None:
    users = _captured_users()
    assert users, "capture file exists but is empty"
    for user in users:
        bundle = parse_evidence_block(user)
        bundle.verify()
        assert bundle.render() == bundle.raw
        assert bundle.items, "a captured Stage-2 payload carried no evidence items"
        for level in (1, 2):
            mini = bundle.minified(level=level)
            assert len(mini) <= len(bundle.raw)
            assert _is_subsequence(mini.split("\n"), list(bundle.lines))


@pytest.mark.skipif(not _CAPTURE.exists(), reason="R460 capture not present")
def test_capture_redundancy_is_measured_not_assumed() -> None:
    """The census claim: only a SMALL share of the evidence is redundant.

    This pins the finding so a later round cannot quietly re-label the evidence
    block as the dominant cost. If this threshold ever fails, the census and the
    R448 recommendation need re-reading, not the assertion relaxing.
    """
    worst = 0.0
    for user in _captured_users():
        stats = parse_evidence_block(user).stats()
        total = int(stats["total_chars"])
        redundant = int(stats["redundant_item_chars"])
        if total:
            worst = max(worst, redundant / total)
    assert worst < 0.15, f"evidence redundancy is {worst:.1%} — re-run the R460 census"
