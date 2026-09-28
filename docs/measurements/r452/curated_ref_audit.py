"""R452b — curated answers whose text states a provision their seeded refs omit.

A curated intercept skips Stage-2, and every prose->refs pass is
``_stage2_landed``-gated, so a provision the curated answer names reaches the
wire only if the intercept seeds it (the minimal-risk Articles 4 and 95 miss).
This walks every dict literal carrying ``"answer"`` and ``"refs"`` keys in the
engine and the route and prints each head the answer names that the refs lack,
with the sentence it sits in, so each can be judged operative or contrastive.
Heads are read with ``answer_completeness.named_heads`` (the route's own parser),
so plural and range forms ("Articles 13 and 50", "Articles 9 to 15") count.
Dicts whose answer or refs are not literals are listed rather than skipped
silently.

    py -3.12 docs/measurements/r452/curated_ref_audit.py
"""
from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")

from app.engines.answer_completeness import named_heads  # noqa: E402

FILES = [REPO / "app" / "engines" / "_graph_rag_impl.py", REPO / "app" / "routes" / "regenold.py"]


def _heads(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for sent in re.split(r"(?<=[.;])\s+", text):
        for head in named_heads(sent):
            out.setdefault(head, []).append(sent.strip())
    return out


def _ref_head(ref: str) -> str:
    return ref.strip().replace("Art. ", "Article ").split(".")[0]


def main() -> int:
    findings = 0
    skipped: list[str] = []
    for path in FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = [k.value if isinstance(k, ast.Constant) else None for k in node.keys]
            if "answer" not in keys or "refs" not in keys:
                continue
            answer = node.values[keys.index("answer")]
            refs = node.values[keys.index("refs")]
            if not (isinstance(answer, ast.Constant) and isinstance(answer.value, str)) or not (
                isinstance(refs, ast.List) and all(isinstance(e, ast.Constant) for e in refs.elts)
            ):
                skipped.append(f"{path.name}:{node.lineno}")
                continue
            name = node.values[keys.index("name")].value if "name" in keys and isinstance(
                node.values[keys.index("name")], ast.Constant) else "?"
            ref_heads = {_ref_head(e.value) for e in refs.elts}
            named = _heads(answer.value)
            missing = {h: s for h, s in named.items() if h not in ref_heads}
            if missing:
                findings += 1
                print(f"{path.name}:{node.lineno} [{name}] refs={[e.value for e in refs.elts]}")
                for head, sents in missing.items():
                    print(f"    missing {head}: {sents[0][:160]}")
    print(f"\ncurated dicts with answer-named heads missing from refs: {findings}")
    print(f"dicts not audited (non-literal answer or refs): {len(skipped)} {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
