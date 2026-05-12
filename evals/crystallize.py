"""Eval-failure → KB stub proposal generator (crystallization runner).

The llm-wiki pattern's **crystallization** step distills a completed
chain of work (a research thread, a debugging session) into a structured
digest that strengthens the knowledge base. For an EU AI Act compliance
Q&A system, the natural analog is: when an eval scenario fails, the
scenario's expected behaviour (verdict shape, citation set) is itself
a candidate KB entry.

This module runs the eval suite, identifies failures, and emits a
human-readable proposal markdown for each failed scenario:

* For verdict-shaped failures (``risk_classification`` category +
  scenarios whose checks include ``gives_*_verdict``), it drafts a
  candidate ``_CLASSIFICATION_TOPICS`` entry: the question keywords
  shape the regex pattern, the predicate name shapes the verdict,
  the scenario's expected references shape the cite set.

* For content-lookup failures, it drafts a candidate
  ``_KEYWORD_ENTITY_MAP`` addition mapping the most-novel keyword in
  the question to the article the expected reference list cites.

* For scope-refusal failures (scenario expected refusal but the engine
  answered), it drafts a candidate scope ``_AI_ACT_ANCHORS`` addition.

Each proposal is appended to ``evals/crystallized_proposals.md`` with a
timestamp, the scenario id, the failure mode, and the draft patch. The
human reviews the file, accepts (copies the diff in), or rejects. We
do NOT auto-mutate the KB because every entry is a regulatory claim —
the human is the last gate.

## Usage

    .venv/Scripts/python.exe -m evals.crystallize

The proposals file gets appended to (not overwritten) so multiple runs
build a backlog of candidates to triage.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from evals.regenold.runner import ScenarioResult, run_all


REPO_ROOT = Path(__file__).resolve().parent.parent
PROPOSALS_FILE = REPO_ROOT / "evals" / "crystallized_proposals.md"


@dataclass
class Proposal:
    """A draft KB stub the human should review and possibly accept."""

    scenario_id: str
    category: str
    failure_kind: str  # "verdict" / "content" / "scope_refusal" / "scope_pass"
    diagnostic: str
    proposed_patch: str


def _classify_failure(result: ScenarioResult) -> str:
    """Categorise the failure into one of four kinds.

    The category drives which kind of KB stub to draft. A scenario can
    fail for multiple reasons but we pick the dominant signal — the
    first failing check that maps to a known kind.
    """
    failed = [label for label, ok in result.check_results if not ok]
    failed_text = " ".join(failed).lower()
    if any(kw in failed_text for kw in ("verdict", "prohibited", "high_risk", "categorically")):
        return "verdict"
    if "refused" in failed_text or "refusal" in failed_text:
        # If the scenario expected refusal and got an answer, this is a
        # "scope_pass" failure (scope was too permissive).
        if "expected refusal" in failed_text or "not_refused" in failed_text:
            return "scope_pass"
        return "scope_refusal"
    if "cites" in failed_text or "reference" in failed_text:
        return "content"
    return "content"


# ── Keyword extraction (for stub regex / map generation) ───────────────

_BASIC_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "do",
    "does", "did", "have", "has", "had", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "of", "in", "on",
    "at", "to", "from", "for", "with", "by", "and", "or", "but", "if",
    "then", "than", "what", "which", "when", "where", "why", "how",
    "this", "that", "these", "those", "it", "its", "they", "them",
    "we", "our", "i", "my", "you", "your", "system", "systems", "ai",
    "act", "regulation", "obligation", "obligations", "article",
})


def _significant_keywords(text: str, max_keywords: int = 5) -> list[str]:
    """Return the top distinct concept tokens from ``text``.

    Drops stopwords, single-character / digit-only tokens, and obvious
    function words. Preserves order so the most domain-specific terms
    (typically nouns the human asked about) come first.
    """
    tokens = re.findall(r"[a-zA-Z][a-zA-Z\-]+", text.lower())
    seen: set[str] = set()
    out: list[str] = []
    for tok in tokens:
        if len(tok) <= 2 or tok in _BASIC_STOPWORDS or tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
        if len(out) >= max_keywords:
            break
    return out


# ── Proposal builders ──────────────────────────────────────────────────


def _build_verdict_proposal(result: ScenarioResult) -> Proposal:
    """Draft a ``_CLASSIFICATION_TOPICS`` entry for a verdict-shape failure."""
    answer = result.response_excerpt.get("answer", "")
    refs = result.response_excerpt.get("references") or []
    question = " ".join(
        # Re-derive the question from the scenario id when possible —
        # ScenarioResult doesn't carry the raw messages, so we fall
        # back to the description.
        [result.description]
    )
    kw = _significant_keywords(question + " " + result.description)
    pattern_alt = "|".join(kw[:3]) if kw else "REPLACE_ME"
    ref_list = ", ".join(f'"{r}"' for r in refs) if refs else '"Art. 5"'
    refs_internal = ", ".join(
        f'"Art. {ref[len("Article "):]}"' if ref.startswith("Article ")
        else f'"{ref}"' for ref in refs
    ) if refs else '"Art. 5"'

    patch = f"""# Add to `_CLASSIFICATION_TOPICS` in app/engines/graph_rag.py
{{
    "name": "{result.scenario_id}",
    "patterns": [
        re.compile(r"\\b(?:{pattern_alt})\\b", re.IGNORECASE),
    ],
    "answer": (
        # REPLACE: 1-4 sentence verdict prose. Current answer was:
        # {answer[:200]!r}
        "TODO: write the correct verdict for this scenario."
    ),
    "refs": [{refs_internal}],
}},"""

    diagnostic = (
        f"Scenario expected a classification verdict but the answer was "
        f"a {len(answer)}-char description. Failed checks: "
        f"{[label for label, ok in result.check_results if not ok]}"
    )
    return Proposal(
        scenario_id=result.scenario_id,
        category=result.category,
        failure_kind="verdict",
        diagnostic=diagnostic,
        proposed_patch=patch,
    )


def _build_content_proposal(result: ScenarioResult) -> Proposal:
    """Draft a ``_KEYWORD_ENTITY_MAP`` entry for a content-lookup failure."""
    refs = result.response_excerpt.get("references") or []
    description = result.description
    kw = _significant_keywords(description)
    # Use the most-novel token (last in the list, often the domain noun)
    # as the keyword anchor.
    keyword = kw[-1] if kw else "REPLACE_ME"
    target = refs[0] if refs else "Art. 5"
    target_internal = (
        f"Art. {target[len('Article '):]}" if target.startswith("Article ")
        else target
    )
    patch = f"""# Add to `_KEYWORD_ENTITY_MAP` in app/engines/graph_rag.py
("{keyword}", "{target_internal}"),
# Also consider adding to scope.KEYWORD_TO_ARTICLE + _AI_ACT_ANCHORS."""

    diagnostic = (
        f"Content question missed expected refs. Got refs: {refs}. "
        f"Description: {description!r}"
    )
    return Proposal(
        scenario_id=result.scenario_id,
        category=result.category,
        failure_kind="content",
        diagnostic=diagnostic,
        proposed_patch=patch,
    )


def _build_scope_proposal(result: ScenarioResult, expected_refusal: bool) -> Proposal:
    """Draft a scope-adjustment proposal."""
    description = result.description
    kw = _significant_keywords(description)
    keyword = " ".join(kw[:2]) if kw else "REPLACE_ME"
    if expected_refusal:
        patch = f"""# Scope was too permissive — expected refusal but got an answer.
# Consider tightening: ensure no anchor keyword in this question's domain
# erroneously routes to the AI Act.
# Question domain keywords: {kw}"""
        diagnostic = (
            f"Expected refusal but the engine answered. Either remove an "
            f"anchor that wrongly fires on this question OR add explicit "
            f"refusal copy. Refs returned: {result.response_excerpt.get('references')}"
        )
        failure_kind = "scope_pass"
    else:
        patch = f"""# Add to `_AI_ACT_ANCHORS` in app/integrations/regenold/scope.py
"{keyword}","""
        diagnostic = (
            f"Engine refused a question that should be in-scope. Add the "
            f"keyword above as an anchor."
        )
        failure_kind = "scope_refusal"
    return Proposal(
        scenario_id=result.scenario_id,
        category=result.category,
        failure_kind=failure_kind,
        diagnostic=diagnostic,
        proposed_patch=patch,
    )


def crystallize(results: list[ScenarioResult]) -> list[Proposal]:
    """For each failed scenario, draft an appropriate KB stub proposal."""
    proposals: list[Proposal] = []
    for result in results:
        if result.passed:
            continue
        kind = _classify_failure(result)
        if kind == "verdict":
            proposals.append(_build_verdict_proposal(result))
        elif kind == "content":
            proposals.append(_build_content_proposal(result))
        elif kind == "scope_refusal":
            proposals.append(_build_scope_proposal(result, expected_refusal=False))
        elif kind == "scope_pass":
            proposals.append(_build_scope_proposal(result, expected_refusal=True))
    return proposals


def write_proposals(
    proposals: list[Proposal], target: Path = PROPOSALS_FILE,
) -> int:
    """Append proposals to the markdown file. Returns the count appended."""
    if not proposals:
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    header = f"\n\n## Crystallization run — {timestamp}\n\n"
    body_parts: list[str] = []
    for p in proposals:
        body_parts.append(
            f"### `{p.scenario_id}` ({p.category} / failure_kind=`{p.failure_kind}`)\n\n"
            f"**Diagnostic:** {p.diagnostic}\n\n"
            f"**Draft patch:**\n\n```python\n{p.proposed_patch}\n```\n\n"
            f"---\n"
        )
    body = header + "\n".join(body_parts)
    existing = target.read_text(encoding="utf-8") if target.exists() else (
        "# Crystallized KB proposals\n\n"
        "> Auto-drafted by `evals/crystallize.py` from eval failures.\n"
        "> Each entry below is a CANDIDATE — review and accept or reject.\n"
        "> Do not blindly apply. Every regulatory claim needs human gating.\n"
    )
    target.write_text(existing + body, encoding="utf-8")
    return len(proposals)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, default=PROPOSALS_FILE,
        help=f"Output markdown file (default: {PROPOSALS_FILE.name})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print proposals to stdout instead of appending to the file.",
    )
    args = parser.parse_args(argv)

    print("Running eval suite to identify failures…", file=sys.stderr)
    results = run_all()
    failed_count = sum(1 for r in results if not r.passed)
    print(f"  {failed_count}/{len(results)} scenarios failed.", file=sys.stderr)

    proposals = crystallize(results)
    if not proposals:
        print("No proposals to crystallize — every scenario passed.", file=sys.stderr)
        return 0

    if args.dry_run:
        for p in proposals:
            print(f"\n=== {p.scenario_id} ({p.failure_kind}) ===")
            print(p.diagnostic)
            print(p.proposed_patch)
    else:
        n = write_proposals(proposals, args.out)
        print(f"Appended {n} proposals to {args.out}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
