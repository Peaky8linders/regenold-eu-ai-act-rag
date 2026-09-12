"""R412 — does the wire reference list keep every provision the prose names?

OBSERVATION THAT MOTIVATED THIS
-------------------------------
The live production answer to the hospital-chatbot question discussed Article
50(1), 50(2), 50(3) and 50(4) in the prose, yet shipped exactly one wire
reference: ``["Article 50.4"]``. If the reference list loses provisions the
answer actually discusses, `ref_loose` / `ref_strict` are being scored against a
list that under-reports the answer's own coverage — a pure, silent loss on two
of the eight graded axes.

This probe isolates WHERE that happens by running the real route with the LLM
transport pointed at a dead port. The deterministic Stage-1 path is then the
only producer of the reference set, so any loss is in the ref pipeline and NOT
introduced by Stage-2 prose.

    REGENOLD_SKIP_DOTENV=1 .venv/Scripts/python.exe \
        docs/measurements/r412/ref_grain_probe.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Same deterministic offline environment the R409/R411 instruments use.
os.environ["REGENOLD_SKIP_DOTENV"] = "1"
os.environ["P2P_GRAPH_RAG_PROVIDER"] = "cli"
os.environ["OPENAI_API_BASE"] = "http://127.0.0.1:1/v1"
os.environ["REGENOLD_QUERY_DENOISER"] = "0"
os.environ["REGENOLD_EXTERNAL_EMBEDDINGS"] = "0"

QUESTIONS = [
    (
        "transparency-art50",
        "What transparency obligations apply to providers and deployers of AI "
        "systems under the EU AI Act?",
    ),
    (
        "chatbot-hospital",
        "We provide a patient-facing chatbot that a hospital deploys on its "
        "website to answer general patient queries. What EU AI Act transparency "
        "duties apply to us as provider?",
    ),
    (
        "gpai-enforcement",
        "What rights of defence do GPAI model providers have in enforcement "
        "proceedings under the EU AI Act?",
    ),
]

#: ``Article 50.1``, ``Article 50(1)``, ``Annex IV.2`` — the two surfaces the
#: prose may use for the same coordinate.
_ART = re.compile(r"\bArticle\s+(\d+)(?:[.\s]*\(?(\d+)\)?)?", re.IGNORECASE)
_ANNEX = re.compile(r"\bAnnex\s+([IVXL]+)(?:[.\s]*\(?(\d+)\)?)?", re.IGNORECASE)


def _norm(token: str) -> str:
    return re.sub(r"\s+", "", token).lower().replace("(", ".").replace(")", "")


def prose_heads(answer: str) -> set[str]:
    """Article / Annex numbers the PROSE names (head grain, e.g. ``article50``)."""
    heads: set[str] = set()
    for m in _ART.finditer(answer or ""):
        heads.add(f"article{m.group(1)}")
    for m in _ANNEX.finditer(answer or ""):
        heads.add(f"annex{m.group(1).lower()}")
    return heads


def wire_heads(refs: list[str]) -> set[str]:
    heads: set[str] = set()
    for r in refs:
        for m in _ART.finditer(r):
            heads.add(f"article{m.group(1)}")
        for m in _ANNEX.finditer(r):
            heads.add(f"annex{m.group(1).lower()}")
    return heads


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    from fastapi.testclient import TestClient

    from app.main import app
    from app.rate_limit import limiter

    limiter.enabled = False
    client = TestClient(app)

    for label, question in QUESTIONS:
        resp = client.post(
            "/api/v1/regenold/eu-ai-act/ask",
            json=[{"role": "user", "content": question}],
        )
        data = resp.json() if resp.status_code == 200 else {}
        answer = data.get("answer", "") or ""
        refs = [str(x).strip() for x in (data.get("references") or [])]
        p_heads, w_heads = prose_heads(answer), wire_heads(refs)
        missing = sorted(p_heads - w_heads)
        print(f"\n=== {label} (HTTP {resp.status_code}) ===")
        print(f"wire refs ({len(refs)}): {refs}")
        print(f"prose-named heads ({len(p_heads)}): {sorted(p_heads)}")
        print(f"MISSING from wire ({len(missing)}): {missing}")
        print(f"answer chars: {len(answer)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
