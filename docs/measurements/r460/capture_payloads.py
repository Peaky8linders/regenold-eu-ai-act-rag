"""R460 — capture the raw Stage-2 payloads to ``stage2-payloads.jsonl``.

The census says WHERE the characters sit; this capture is the RECORDED DRAW that
the evidence-bundle minifier is measured against afterwards, without another
route run and without an LLM. Real route, real retrieval, real builders, Stage-2
provider stubbed at the seam (R423 pattern).

Usage::

    R460_ROWS=8 R460_STRIDE=5 .venv\\\\Scripts\\\\python.exe docs/measurements/r460/capture_payloads.py
"""
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
        "reasoning": "stub parse for the R460 payload capture",
    }
)
_ANSWER = (
    "Under Article 13(1) the provider must ensure the system is designed so that "
    "its operation is sufficiently transparent. References: Article 13, Article 13.1."
)
PROBE_BASELINE = {
    "REGENOLD_QUERY_DENOISER": "0",
    "REGENOLD_EXTERNAL_EMBEDDINGS": "0",
}


class _Recorder:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def complete(self, request: Any, *_a: Any, **_k: Any) -> SimpleNamespace:
        user = str(getattr(request, "user", "") or "")
        system = str(getattr(request, "system", "") or "")
        stage2 = ("EU AI ACT REFERENCES:" in user) or ("ANSWER CONTRACT" in user)
        self.payloads.append({"stage2": stage2, "system": system, "user": user})
        return SimpleNamespace(
            error=None, text=_ANSWER if stage2 else _PARSED, thinking="",
            finish_reason="stop", model="probe-stub", usage=None,
            latency_ms=1, headers=None,
        )


def _history(depth: int) -> list[dict[str, str]]:
    from evals.regenold.official_batch import trim_history

    history: list[dict[str, str]] = []
    for i in range(depth):
        history = trim_history(
            [
                *history,
                {"role": "user", "content": f"Prior question {i + 1} about the EU AI Act."},
                {"role": "assistant", "content": _ANSWER},
            ]
        )
    return history


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    from app.llm.openai_wrapper_provider import get_openai_wrapper_provider
    from evals.regenold.official_batch import build_hard_messages, load_official_batch
    from evals.regenold.runner_v2 import _post_local

    os.environ.update(PROBE_BASELINE)
    n_rows = int(os.environ.get("R460_ROWS", "8"))
    stride = int(os.environ.get("R460_STRIDE", "5"))
    depth = int(os.environ.get("R460_DEPTH", "0"))
    difficulty = os.environ.get("R460_DIFFICULTY", "HARD").strip().upper()
    forced = [x.strip() for x in (os.environ.get("R460_IDS") or "").split(",") if x.strip()]

    rows = list(load_official_batch())
    if forced:
        wanted = set(forced)
        rows = [r for r in rows if r.id in wanted]
    else:
        if difficulty in ("HARD", "EASY"):
            rows = [r for r in rows if (r.difficulty or "").upper() == difficulty]
        rows = rows[::stride][:n_rows]

    provider = get_openai_wrapper_provider()
    original = provider.complete
    written = 0
    vacuous: list[str] = []
    with (OUT / "stage2-payloads.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            recorder = _Recorder()
            provider.complete = recorder.complete  # type: ignore[method-assign]
            try:
                _post_local(
                    "local://app.main:app/api/v1/regenold/eu-ai-act/ask",
                    None,
                    build_hard_messages(row, _history(depth)),
                    180.0,
                )
            finally:
                provider.complete = original  # type: ignore[method-assign]
            graded = [p for p in recorder.payloads if p["stage2"]]
            if not graded:
                vacuous.append(row.id)
                continue
            payload = graded[-1]
            fh.write(
                json.dumps(
                    {
                        "id": row.id,
                        "difficulty": row.difficulty,
                        "depth": depth,
                        "system": payload["system"],
                        "user": payload["user"],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            written += 1
            print(f"{row.id} system={len(payload['system'])} user={len(payload['user'])}")
    print(f"wrote {written} payloads to stage2-payloads.jsonl; vacuous={vacuous}")


if __name__ == "__main__":
    main()
