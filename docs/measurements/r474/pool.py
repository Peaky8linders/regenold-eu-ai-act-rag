"""R474 - the non-official question pool for the R473 route A/B.

Mirrors the R469 pool (``docs/measurements/r469/ab_statutory.py::labels``): every
single-turn question in the probe corpus, the R465 corpus (if present on disk),
the blind held-out rephrasing sets, and question-shaped strings in the test files,
MINUS the official 110 and minus the tests' own R473/R474 fixtures. The official
110 is excluded on purpose: AGENTS.md (operator directive 2026-10-25) forbids
measuring a change on it.
"""
from __future__ import annotations

import ast
import glob
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OWN_TESTS = ("test_r473", "test_r474", "test_paper_2611")
R465_CORPUS_CANDIDATES = (
    REPO / "scratch" / "r465_ab_corpus.json",
    Path("D:/Claude Projects/regenold-eu-ai-act-rag/scratch/r465_ab_corpus.json"),
)
HELDOUT_FILES = (
    "docs/measurements/r467/heldout_rephrasings.json",
    "docs/measurements/r469/heldout_rephrasings.json",
    "docs/measurements/r469/heldout_rephrasings_2.json",
)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _official() -> set[str]:
    path = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"
    return {
        norm(json.loads(line)["question"])
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def build() -> tuple[list[str], dict[str, str]]:
    """Return ``(questions, source_by_question)``, deduplicated, official excluded."""
    from evals.harness.probe_set import load_probe_set

    src: dict[str, str] = {}

    def add(q: str, where: str) -> None:
        q = q.strip()
        if q and q not in src:
            src[q] = where

    for r in load_probe_set(multiturn=False):
        add(r.messages[-1]["content"], "probe")
    for cand in R465_CORPUS_CANDIDATES:
        if cand.exists():
            for r in json.loads(cand.read_text(encoding="utf-8")):
                add(r["question"], "r465")
            break
    for rel in HELDOUT_FILES:
        p = REPO / rel
        if p.exists():
            for r in json.loads(p.read_text(encoding="utf-8"))["rows"]:
                add(r["question"], "heldout")
    for f in sorted(glob.glob(str(REPO / "tests" / "*.py"))):
        if Path(f).name.startswith(OWN_TESTS):
            continue
        try:
            tree = ast.parse(Path(f).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                s = node.value.strip()
                if (20 <= len(s) <= 300 and s.endswith("?") and "\n" not in s
                        and not re.match(r"[A-Z][A-Z ]{3,}:", s)):
                    add(s, "tests")
    off = _official()
    questions = sorted(q for q in src if norm(q) not in off)
    return questions, {q: src[q] for q in questions}
