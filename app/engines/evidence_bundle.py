"""R460 — a typed, lossless ``EvidenceBundle`` over the Stage-2 evidence block.

WHY THIS EXISTS. R455 measured the Stage-2 request at the provider seam at
``system 59,647 + user 54,789 ~= 114,436`` characters. R448's audit
recommendation 4 asks for a typed request-scoped evidence bundle (canonical
source id, exact operative text, provision/subpoint, provenance, mandatory vs
optional status) and is explicit about the order of operations:

    first extract existing behaviour and require a byte-identical recorded-draw
    replay — answer, reference set/order, trace — before any gated experiment.

So this module is deliberately a PROJECTION, not a rewriter. :func:`parse_evidence_block`
builds a typed view over the evidence block the engine already renders, and
:meth:`EvidenceBundle.render` returns those exact bytes. Nothing here changes a
dispatched payload unless a caller opts in through :func:`minify_evidence_block`,
which is gated and default-OFF.

WHAT THE CENSUS FOUND, AND WHY THE MINIFIER IS SMALL. R460's census
(``docs/measurements/r460/stage2-payload-census.json``) decomposed a median hard
single-turn payload of ~101k chars: 60.6k STATIC system instruction stack, ~32k
evidence, ~6.5k instruction clauses. Inside the evidence only ~1-4% is provably
redundant (a provision surfaced under two node ids). The rest is load-bearing,
and the "STRUCTURE of ... NOT ENGAGED" member lists are REFERENCED by the ANSWER
SHAPE clause, so they are not free either. The dominant lever is the static
system prompt, which :data:`EVIDENCE_BUNDLE_NOTE` records at the call site.

THE THREE-NODE-ID DUPLICATION IS REAL, NOT HYPOTHETICAL. The KB carries one
provision under several node ids (``kb-risk_mgmt-Art. 6`` and
``kb-xref-risk_mgmt-Art. 6`` both render the same Article 6 summary), so the same
rule reaches the model two or three times inside one evidence block.

Gate: ``REGENOLD_EVIDENCE_BUNDLE`` (default ``0``, deny-list) and
``REGENOLD_EVIDENCE_BUNDLE_LEVEL`` (default ``1``). Both are read fresh per call
so an in-process two-arm A/B is valid, and both must be folded into the route's
engine cache key (R263.2) — otherwise arm A's cached answer is served to arm B.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Final

__all__ = [
    "EVIDENCE_BLOCK_HEADER",
    "EVIDENCE_BUNDLE_LEVEL_ENV",
    "EVIDENCE_BUNDLE_ENV",
    "EVIDENCE_BUNDLE_NOTE",
    "EvidenceBundle",
    "EvidenceItem",
    "evidence_bundle_enabled",
    "evidence_bundle_level",
    "minify_evidence_block",
    "parse_evidence_block",
    "provision_of",
]

EVIDENCE_BUNDLE_ENV: Final = "REGENOLD_EVIDENCE_BUNDLE"
EVIDENCE_BUNDLE_LEVEL_ENV: Final = "REGENOLD_EVIDENCE_BUNDLE_LEVEL"

#: The header the engine writes before the evidence block. Kept here so the
#: census and the engine agree on one string.
EVIDENCE_BLOCK_HEADER: Final = "EU AI ACT REFERENCES:"

#: The first marker of the instruction stack that follows the evidence block.
#: Parsing stops here: the bundle owns the evidence, not the contract.
_EVIDENCE_BLOCK_END: Final = "ANSWER CONTRACT"

EVIDENCE_BUNDLE_NOTE: Final = (
    "R460: the evidence block is ~32% of the payload; the static system prompt is "
    "~60%. Cut the system prompt first (REGENOLD_PROMPT_COMPACT, measured "
    "60,643 -> 287 chars) and treat this minifier as the second, smaller lever."
)

_TRUTHY: Final = {"1", "true", "yes", "on"}

#: Section headings rendered by ``_build_context_references_block`` and
#: ``_render_grounding_text``. A heading owns the lines until the next heading.
_HEADINGS: Final[tuple[str, ...]] = (
    "APPLICABLE OBLIGATIONS",
    "ARTICLE-SPECIFIC OBLIGATIONS",
    "BACKGROUND OBLIGATIONS",
    "DIMENSION DETAILS",
    "KNOWLEDGE-GRAPH SUB-POINT DETAIL",
    "KNOWLEDGE-GRAPH CROSS-REGULATORY MAPPINGS",
    "VERBATIM PROVISION TEXT",
    "REFERENCED ANNEXES AND RECITALS",
)

#: A heading that says, in the prompt's own words, that its members must not be
#: enumerated. The members are still rendered under it (R452/R423 machinery), so
#: level 2 drops the member lines and KEEPS the heading and its count: the
#: ANSWER SHAPE clause references these lists, so the heading must survive.
_NOT_ENGAGED_MARK: Final = "NOT ENGAGED by this question"

#: A heading whose own text declares the section non-citable.
_NON_CITABLE_MARK: Final = "non-citable"

_ITEM_RE: Final = re.compile(r"^- \[(?P<sid>[^\]]+)\]\s*(?P<body>.*)$")
_ANNEX_RE: Final = re.compile(r"\bAnnex\s+(?P<roman>[IVXLCDM]{1,7})\b", re.IGNORECASE)
_ARTICLE_RE: Final = re.compile(
    r"(?:Art\.?|Article)\s*(?P<num>\d{1,3})"
    r"(?:\.(?P<dot>\d+))?"
    r"(?:-(?P<dash>\d+)(?P<parens>(?:\([0-9a-z]+\))*))?",
    re.IGNORECASE,
)


def evidence_bundle_enabled() -> bool:
    """R460 gate. Default OFF: the minifier changes the dispatched evidence."""
    return os.getenv(EVIDENCE_BUNDLE_ENV, "0").strip().lower() in _TRUTHY


def evidence_bundle_level() -> int:
    """Minifier level. 1 = duplicate items only. 2 = also non-engaged members."""
    raw = os.getenv(EVIDENCE_BUNDLE_LEVEL_ENV, "1").strip()
    try:
        level = int(raw)
    except ValueError:
        return 1
    return level if level in (1, 2) else 1


def provision_of(source_id: str) -> str:
    """Canonical provision key for a KB node id, or ``""`` when there is none.

    Handles both id shapes the block carries:

    * grounded nodes — ``kb-xref-risk_mgmt-Art. 6.3`` -> ``Article 6.3``,
      ``kb-risk_mgmt-Annex III`` -> ``Annex III``;
    * article-specific nodes — ``kb-art-Art. 13-13(3)(b)(ii)`` ->
      ``Article 13(3)(b)(ii)``.
    """
    sid = str(source_id or "")
    annex = _ANNEX_RE.search(sid)
    if annex:
        return f"Annex {annex.group('roman').upper()}"
    art = _ARTICLE_RE.search(sid)
    if not art:
        return ""
    key = f"Article {art.group('num')}"
    if art.group("dot"):
        key += f".{art.group('dot')}"
    elif art.group("dash"):
        key += art.group("parens") or ""
    return key


@dataclass(frozen=True)
class EvidenceItem:
    """One rendered evidence bullet, with its exact bytes and its section."""

    section: str
    source_id: str
    provision: str
    text: str
    context_only: bool
    line_no: int


@dataclass(frozen=True)
class EvidenceBundle:
    """Typed projection of the evidence block. ``render`` is byte-identical."""

    raw: str
    lines: tuple[str, ...]
    items: tuple[EvidenceItem, ...]
    sections: tuple[tuple[str, int], ...]

    def render(self) -> str:
        """The exact bytes that were parsed. Never reconstructed from the view."""
        return self.raw

    def verify(self) -> None:
        """Raise when the typed view cannot reproduce ``raw`` byte-for-byte."""
        joined = "\n".join(self.lines)
        if joined != self.raw:
            raise AssertionError("evidence bundle is not lossless: raw cannot be reproduced")
        for item in self.items:
            if item.line_no >= len(self.lines):
                raise AssertionError(f"item line {item.line_no} is outside the block")
            if self.lines[item.line_no] != item.text:
                raise AssertionError(f"item line {item.line_no} text drifted from raw")

    def stats(self) -> dict[str, object]:
        """Per-section and redundancy counts, for the census and the tests."""
        by_section: dict[str, int] = {}
        for item in self.items:
            by_section[item.section] = by_section.get(item.section, 0) + len(item.text) + 1
        redundant = _redundant_item_lines(self.items)
        non_engaged = sum(
            1
            for line in self.lines
            if _NOT_ENGAGED_MARK in line and line.strip().startswith("STRUCTURE of ")
        )
        return {
            "total_chars": len(self.raw),
            "items": len(self.items),
            "item_chars_by_section": by_section,
            "redundant_item_lines": len(redundant),
            "redundant_item_chars": sum(len(self.lines[ln]) + 1 for ln in redundant),
            "non_engaged_blocks": non_engaged,
        }

    def minified(self, level: int = 1) -> str:
        """Remove only content that is provably redundant (level 1) or declared
        non-enumerable by the prompt itself (level 2). Everything else is kept
        byte-for-byte, including headings, blank lines and ordering.
        """
        drop = _redundant_item_lines(self.items)
        if level >= 2:
            drop |= _non_engaged_member_lines(self.lines)
        if not drop:
            return self.raw
        return "\n".join(line for i, line in enumerate(self.lines) if i not in drop)


def _redundant_item_lines(items: tuple[EvidenceItem, ...]) -> set[int]:
    """Lines whose content an earlier item already carries.

    Two conditions only, both information-preserving:

    * the same provision under two node ids with IDENTICAL body text (the KB's
      ``kb-risk_mgmt-Art. 6`` / ``kb-xref-risk_mgmt-Art. 6`` pair);
    * the same provision where one body is a strict PREFIX of the other — the
      longer already contains every word the shorter had.
    """
    keep: list[EvidenceItem] = []
    drop: set[int] = set()
    for item in items:
        body = " ".join(item.text.split("]", 1)[-1].split())
        superseded = False
        for prior in list(keep):
            prior_body = " ".join(prior.text.split("]", 1)[-1].split())
            if not item.provision or item.provision != prior.provision:
                continue
            if body == prior_body or prior_body.startswith(body):
                superseded = True
                break
            if body.startswith(prior_body):
                # The new item is the more complete rendering: keep it and drop
                # the earlier, shorter one.
                drop.add(prior.line_no)
                keep.remove(prior)
                break
        if superseded:
            drop.add(item.line_no)
        else:
            keep.append(item)
    return drop


def _non_engaged_member_lines(lines: tuple[str, ...]) -> set[int]:
    """Indented member coordinates under a "STRUCTURE of ... NOT ENGAGED" head.

    The heading, which carries the member count and the do-not-enumerate
    instruction, is kept: the ANSWER SHAPE clause points at these lists.
    """
    drop: set[int] = set()
    pending = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if _NOT_ENGAGED_MARK in line and stripped.startswith("STRUCTURE of "):
            pending = True
            continue
        if pending:
            if line.startswith("    ") and stripped:
                drop.add(i)
                continue
            pending = False
    return drop


def parse_evidence_block(text: str) -> EvidenceBundle:
    """Parse an evidence block into a typed, lossless projection.

    ``text`` may be the bare block (what the engine hands the builder) or a whole
    user message. When the ``EU AI ACT REFERENCES:`` header is present the span
    starts after it; when the instruction stack follows, the span stops at it.
    :meth:`EvidenceBundle.render` returns exactly that span, so a whole-message
    caller can splice the minified span back without doubling the contract.
    """
    raw = str(text or "")
    start = raw.find(EVIDENCE_BLOCK_HEADER)
    if start >= 0:
        raw = raw[start + len(EVIDENCE_BLOCK_HEADER):].lstrip("\n")
    stop = raw.find(_EVIDENCE_BLOCK_END)
    if stop >= 0:
        raw = raw[:stop]
    lines = tuple(raw.split("\n"))

    section = ""
    context_only = False
    items: list[EvidenceItem] = []
    sections: list[tuple[str, int]] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        head = next((h for h in _HEADINGS if stripped.startswith(h)), None)
        if head is not None:
            section = head
            context_only = _NON_CITABLE_MARK in stripped
            sections.append((head, i))
            continue
        if _NOT_ENGAGED_MARK in stripped:
            context_only = True
            continue
        m = _ITEM_RE.match(line)
        if m:
            items.append(
                EvidenceItem(
                    section=section,
                    source_id=m.group("sid").strip(),
                    provision=provision_of(m.group("sid")),
                    text=line,
                    context_only=context_only,
                    line_no=i,
                )
            )
    return EvidenceBundle(
        raw=raw, lines=lines, items=tuple(items), sections=tuple(sections)
    )


def minify_evidence_block(text: str, level: int | None = None) -> str:
    """Gate-aware entry point. Returns ``text`` unchanged when the gate is OFF.

    ``text`` is the evidence block itself (the engine's ``reference_block``), not
    a whole user message: the return value is the block, splice-ready.
    """
    if not evidence_bundle_enabled():
        return text
    lvl = evidence_bundle_level() if level is None else level
    return parse_evidence_block(text).minified(level=lvl)
