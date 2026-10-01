"""R460 exploratory #4: dump one real Stage-2 payload (system + user) to disk."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
OUT = Path(__file__).resolve().parent

_PARSED = json.dumps(
    {
        "intent": "general_compliance",
        "entities": ["provider", "high-risk AI system"],
        "risk_context": "high_risk",
        "dimension_hint": "obligations",
        "keywords": ["transparency", "instructions for use"],
        "reasoning": "stub parse",
    }
)
_ANSWER = "Under Article 13(1) the provider must be transparent. References: Article 13."
BASE = {"REGENOLD_QUERY_DENOISER": "0", "REGENOLD_EXTERNAL_EMBEDDINGS": "0"}


def main() -> None:
    os.environ.update(BASE)
    from app.llm.openai_wrapper_provider import get_openai_wrapper_provider
    from evals.regenold.official_batch import build_hard_messages, load_official_batch
    from evals.regenold.runner_v2 import _post_local

    want = os.environ.get("R460_ID", "rg_003")
    rows = {r.id: r for r in load_official_batch()}
    row = rows[want]
    provider = get_openai_wrapper_provider()
    original = provider.complete
    seen: list[dict[str, Any]] = []

    def rec(request: Any, *_a: Any, **_k: Any) -> SimpleNamespace:
        user = str(getattr(request, "user", "") or "")
        system = str(getattr(request, "system", "") or "")
        stage2 = ("EU AI ACT REFERENCES:" in user) or ("ANSWER CONTRACT" in user)
        seen.append({"stage2": stage2, "system": system, "user": user})
        return SimpleNamespace(
            error=None, text=_ANSWER if stage2 else _PARSED, thinking="",
            finish_reason="stop", model="probe-stub", usage=None, latency_ms=1, headers=None,
        )

    provider.complete = rec  # type: ignore[method-assign]
    try:
        _post_local(
            "local://app.main:app/api/v1/regenold/eu-ai-act/ask",
            None,
            build_hard_messages(row, []),
            180.0,
        )
    finally:
        provider.complete = original  # type: ignore[method-assign]

    s2 = [p for p in seen if p["stage2"]]
    if not s2:
        raise SystemExit(f"no Stage-2 payload for {want}")
    p = s2[-1]
    (OUT / "_dump_user.txt").write_text(p["user"], encoding="utf-8")
    (OUT / "_dump_system.txt").write_text(p["system"], encoding="utf-8")
    print(f"row={want} system={len(p['system'])} user={len(p['user'])}")
    print("--- user top-level markers ---")
    for marker in (
        "ORIGINAL QUESTION:", "REWRITTEN / SEARCH QUESTION:", "LEGAL VERSION:",
        "SYSTEM DESCRIPTION:", "EU AI ACT REFERENCES:", "ANSWER CONTRACT",
        "LENGTH LIMIT", "REFERENCE MINIMALITY", "SUB-PARAGRAPH DISCIPLINE",
        "VALID COORDINATES", "CHALLENGE TURN", "GOVERNING PROVISION",
        "ACT TERMS", "PROVISIONS TO NAME", "COMPLETENESS OF THE FINAL SENTENCE",
        "APPLICABLE OBLIGATIONS", "ARTICLE-SPECIFIC OBLIGATIONS", "BACKGROUND OBLIGATIONS",
    ):
        idx = p["user"].find(marker)
        print(f"  {marker!r:50s} at {idx}")
    print("--- system first lines ---")
    print("\n".join(p["system"].splitlines()[:6]))


if __name__ == "__main__":
    main()
