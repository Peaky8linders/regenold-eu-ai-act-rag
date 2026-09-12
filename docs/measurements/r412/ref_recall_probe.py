"""R412 — gold-anchored reference RECALL probe (offline, deterministic).

QUESTION
--------
The architecture note says the wire reference set is recomputed FROM the final
prose (``_reconcile_references_to_prose`` + ``_add_prose_named_refs``). A single
live observation contradicted the useful half of that: the hospital-chatbot
answer discussed Article 50(1)-(4) in prose and shipped ``["Article 50.4"]``.

A "prose names it but the wire omits it" reading is NOT by itself a defect: the
engine over-cites (F6), so an omission can be correct pruning. The unambiguous
loss is narrower and gold-anchored:

    an EXPECTED (gold) reference head that the ANSWER PROSE names,
    but that the WIRE reference list omits.

Gold says it must be cited. The prose demonstrates the answer discusses it. The
wire drops it. That is a `ref_loose` / `ref_strict` loss with no compensating
conciseness gain, and it is the only form this probe reports as a defect.

Run it when nothing else is competing for CPU or the network — it is a
throughput probe, not a latency probe, but it must not be run alongside a
latency A/B.

    REGENOLD_SKIP_DOTENV=1 .venv/Scripts/python.exe \
        docs/measurements/r412/ref_recall_probe.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

os.environ["REGENOLD_SKIP_DOTENV"] = "1"
os.environ["P2P_GRAPH_RAG_PROVIDER"] = "cli"
os.environ["OPENAI_API_BASE"] = "http://127.0.0.1:1/v1"
os.environ["REGENOLD_QUERY_DENOISER"] = "0"
os.environ["REGENOLD_EXTERNAL_EMBEDDINGS"] = "0"

_ART = re.compile(r"\bArticle\s+(\d+)", re.IGNORECASE)
_ANNEX = re.compile(r"\bAnnex\s+([IVXL]+)\b", re.IGNORECASE)


def _head(token: str) -> str:
    """Canonical head grain: ``Article 50.4`` / ``Article 50(4)`` -> ``article50``."""
    text = str(token)
    m = _ART.search(text)
    if m:
        return f"article{m.group(1)}"
    m = _ANNEX.search(text)
    if m:
        return f"annex{m.group(1).lower()}"
    return ""


def _heads(tokens) -> set[str]:
    return {h for h in (_head(t) for t in tokens or []) if h}


def _names_coordinate(answer: str, head: str) -> bool:
    """Does ``answer`` name ``head`` (``article50`` / ``annexiii``)?"""
    m = re.fullmatch(r"article(\d+)", head)
    if m:
        return bool(re.search(rf"\bArticle\s+{m.group(1)}\b", answer, re.IGNORECASE))
    m = re.fullmatch(r"annex([ivxl]+)", head)
    if m:
        return bool(re.search(rf"\bAnnex\s+{m.group(1)}\b", answer, re.IGNORECASE))
    return False


def _load_gold() -> list[dict]:
    return [
        json.loads(line)
        for line in GOLD.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


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

    scored = 0
    losses: list[dict] = []
    for row in _load_gold():
        expected = _heads(row.get("expected_refs") or [])
        if not expected:
            continue  # the rubric excludes these rows from the reference metrics
        resp = client.post(
            "/api/v1/regenold/eu-ai-act/ask",
            json=[{"role": "user", "content": row["question"]}],
        )
        if resp.status_code != 200:
            continue
        data = resp.json()
        answer = data.get("answer", "") or ""
        refs = [str(x).strip() for x in (data.get("references") or [])]
        wire = _heads(refs)
        named = {h for h in expected if _names_coordinate(answer, h)}
        lost = sorted(named - wire)
        scored += 1
        if lost:
            losses.append(
                {
                    "id": row.get("id"),
                    "expected": sorted(expected),
                    "wire": refs,
                    "lost_but_named": lost,
                }
            )

    print(f"scored rows: {scored}")
    print(f"rows with a NAMED-but-omitted expected head: {len(losses)}")
    for row in losses:
        print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
