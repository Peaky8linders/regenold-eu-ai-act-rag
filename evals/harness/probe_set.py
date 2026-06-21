"""R138-eval — consolidated weakness-targeted gold probe set.

Replaces davidath as the PRIMARY win-measure corpus (davidath stays the cheap
deterministic regression guard). Folds the manually-authored, weakness-mapped,
keyword-gold probe sets into one loader so the pairwise harness scores ONE
corpus that covers every documented live-weak axis:

* paper-V4 (52) — `scenarios_paper_singleturn_v4` (20, the 4 risk tiers) +
  `scenarios_paper_tricky_v4` (20, decision-boundary) + `..._multiturn_v4`
  (12, role-flip / coref).
* V2 (56) — `scenarios_tricky_v2` (31, 7 weakness categories: omnibus /
  role_ambiguity / conflict / borderline_prohibition / gpai / cross_framework /
  near_oos) + `scenarios_multiturn_v2` (25, multi-framework coref + role flip).

Each row is normalised to a single shape so the runner + judge are
source-agnostic::

    {
      "id": str,                 # globally unique (source-prefixed)
      "source": str,             # paper_st_v4 | paper_tricky_v4 | ... | tricky_v2 | mt_v2
      "category": str,           # weakness axis (omnibus / role_ambiguity / ...)
      "is_multiturn": bool,
      "messages": [{"role","content"}],   # the conversation to POST
      "expected_refs": [str],    # user-facing "Article N" / "Annex N"
      "expected_keywords": [str],
      "gold_answer": str,        # "" when the source carries only keyword-gold
    }

The OOS suite (`scenarios_oos`) is deliberately NOT folded in — it is a binary
must-refuse gate (`runner_v2 --probe-oos`), not a soft win-measure.

Pure stdlib + the existing scenario modules. No I/O at import time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProbeRow:
    id: str
    source: str
    category: str
    is_multiturn: bool
    messages: tuple[dict[str, str], ...]
    expected_refs: tuple[str, ...]
    expected_keywords: tuple[str, ...]
    gold_answer: str = ""

    @property
    def live_question(self) -> str:
        """The final user turn — what the answer must actually address."""
        for m in reversed(self.messages):
            if m.get("role") == "user":
                return m.get("content", "")
        return self.messages[-1].get("content", "") if self.messages else ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "category": self.category,
            "is_multiturn": self.is_multiturn,
            "messages": [dict(m) for m in self.messages],
            "expected_refs": list(self.expected_refs),
            "expected_keywords": list(self.expected_keywords),
            "gold_answer": self.gold_answer,
        }


def _norm_single(row: dict, source: str) -> ProbeRow:
    return ProbeRow(
        id=f"{source}:{row.get('id', '')}",
        source=source,
        category=str(row.get("category") or source),
        is_multiturn=False,
        messages=({"role": "user", "content": row.get("question", "")},),
        expected_refs=tuple(row.get("expected_refs") or ()),
        expected_keywords=tuple(row.get("expected_keywords") or ()),
        gold_answer=str(row.get("gold_answer") or ""),
    )


def _norm_multi(row: dict, source: str) -> ProbeRow:
    turns = row.get("turns") or []
    return ProbeRow(
        id=f"{source}:{row.get('id', '')}",
        source=source,
        category=str(row.get("category") or "multi_turn"),
        is_multiturn=True,
        messages=tuple({"role": t.get("role", "user"), "content": t.get("content", "")}
                       for t in turns),
        # multi-turn modules key the gold on the FINAL turn.
        expected_refs=tuple(row.get("expected_final_refs") or row.get("expected_refs") or ()),
        expected_keywords=tuple(
            row.get("expected_final_keywords") or row.get("expected_keywords") or ()
        ),
        gold_answer=str(row.get("gold_answer") or ""),
    )


# (module_path, source-tag, is_multiturn) — the PRIMARY consolidated corpus.
_PRIMARY_SOURCES: tuple[tuple[str, str, bool], ...] = (
    ("evals.regenold.scenarios_paper_singleturn_v4", "paper_st_v4", False),
    ("evals.regenold.scenarios_paper_tricky_v4", "paper_tricky_v4", False),
    ("evals.regenold.scenarios_paper_multiturn_v4", "paper_mt_v4", True),
    ("evals.regenold.scenarios_tricky_v2", "tricky_v2", False),
    ("evals.regenold.scenarios_multiturn_v2", "mt_v2", True),
)


def load_probe_set(
    *,
    sources: tuple[str, ...] | None = None,
    categories: tuple[str, ...] | None = None,
    multiturn: bool | None = None,
    limit: int | None = None,
) -> list[ProbeRow]:
    """Load the consolidated probe set, optionally filtered.

    :param sources: restrict to these source tags (e.g. ``("tricky_v2",)``).
    :param categories: restrict to these weakness categories.
    :param multiturn: ``True`` only multi-turn, ``False`` only single-turn.
    :param limit: cap the total rows (after filtering) — for cheap smoke runs.

    Never raises on a missing optional module; skips it with no row.
    """
    import importlib

    out: list[ProbeRow] = []
    for module_path, source, is_mt in _PRIMARY_SOURCES:
        if sources is not None and source not in sources:
            continue
        try:
            mod = importlib.import_module(module_path)
        except Exception:  # noqa: BLE001 — a missing probe module is non-fatal
            continue
        rows = getattr(mod, "SCENARIOS", None) or []
        normaliser = _norm_multi if is_mt else _norm_single
        for row in rows:
            pr = normaliser(row, source)
            if multiturn is not None and pr.is_multiturn != multiturn:
                continue
            if categories is not None and pr.category not in categories:
                continue
            out.append(pr)
    if limit is not None:
        out = out[:limit]
    return out


def category_counts(rows: list[ProbeRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.category] = counts.get(r.category, 0) + 1
    return counts


__all__ = ["ProbeRow", "load_probe_set", "category_counts"]
