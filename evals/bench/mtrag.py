"""mtRAG multi-turn benchmark loader + scorer (R39 / B10).

mtRAG (TACL 2025): 110 conversations x multiple turns. We adopt the
benchmark for in-house evaluation only; loader supports both the
upstream JSONL format AND a small offline fixture for unit tests. The
scorer returns coherence_rate (turn-pairs that maintain consistent
reference grounding across context shifts).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterable


def load_mtrag_subset(
    fixture_path: str | None = None,
) -> Iterable[dict]:
    """Yield conversation dicts.

    When `fixture_path` is provided, load from local JSONL (for unit
    tests). When None, lazily try to load the upstream dataset via
    huggingface_hub.snapshot_download -- see the docstring there for
    auth setup.
    """
    if fixture_path:
        p = Path(fixture_path)
        if not p.exists():
            raise FileNotFoundError(f"mtRAG fixture not found: {p}")
        with p.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)
        return
    # TODO: hf_hub fetch path -- for R39 ship without it.
    raise NotImplementedError(
        "mtRAG live load via huggingface_hub not wired yet; use fixture_path"
    )


def score_multi_turn(
    conversations: Iterable[dict],
    agent: Callable[[dict, list[dict]], dict],
) -> dict:
    """Run each conversation through `agent` turn-by-turn.

    `agent(turn, history)` must return `{"answer": str, "references": list[str]}`.

    Returns:
        {"n_conversations": int, "coherence_rate": float, "details": [...]}

    coherence_rate = fraction of conversations where every turn's
    predicted refs intersect the turn's gold refs.
    """
    details: list[dict] = []
    n_coherent = 0
    n_total = 0
    for conv in conversations:
        n_total += 1
        history: list[dict] = []
        ok = True
        for turn in conv.get("turns", []):
            resp = agent(turn, history)
            history.append({"role": "user", "content": turn["question"]})
            history.append({"role": "assistant", "content": resp.get("answer", "")})
            pred = set(resp.get("references") or [])
            gold = set(turn.get("gold_refs") or [])
            # Loose match: at least one base ref overlaps (strip
            # sub-points + normalise "Art."/"Article"/"Annex" prefix
            # for comparison). The base key is the first Arabic or
            # Roman identifier after the prefix word.
            def _base(r: str) -> str:
                # Normalise: drop "Art." / "Article" / "Annex" prefix,
                # split on common sub-point separators, take the head
                # token as the comparison key.
                cleaned = (
                    r.replace("Art.", " ")
                     .replace("art.", " ")
                     .replace("Article", " ")
                     .replace("article", " ")
                     .replace("Annex", " ")
                     .replace("annex", " ")
                     .replace("(", " ")
                     .replace(")", " ")
                )
                # First whitespace-delimited token is the base id
                # (e.g. "13" from "Art. 13.1" -> " 13.1" -> "13.1");
                # then strip sub-point dot suffix.
                tokens = cleaned.split()
                if not tokens:
                    return r.upper()
                head = tokens[0]
                # Drop sub-point suffix: "13.1" -> "13", "IV.2" -> "IV".
                head = head.split(".", 1)[0]
                return head.upper()
            pred_bases = {_base(r) for r in pred}
            gold_bases = {_base(r) for r in gold}
            if pred_bases & gold_bases:
                continue
            ok = False
        if ok:
            n_coherent += 1
        details.append({"id": conv.get("id"), "ok": ok})
    return {
        "n_conversations": n_total,
        "coherence_rate": n_coherent / n_total if n_total else 0.0,
        "details": details,
    }
