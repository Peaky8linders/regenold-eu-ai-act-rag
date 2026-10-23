"""R467b — after the fixes deploy: is Stage-2 live, and does the short Q74 ask ship whole?

Asks, on production, the two questions ``tunnel_smoke_postdeploy.json`` recorded
before the fixes: a question no statutory answer covers (it must go through
Stage-2 over the tunnel) and the short Q74 rephrasing whose Article 50(5) and
application-date sentences the three-sentence cap used to cut. Then reads
``/healthz/llm`` for the transport counters. The API key is read from ``.env``
and never printed.

Usage (repo root):
    .venv/Scripts/python.exe docs/measurements/r467/postfix_smoke.py [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import dotenv_values

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from expert_review_rerun import REPO, _get, ask  # noqa: E402

QUESTIONS = {
    "stage2_smoke": "What does Article 4 of the EU AI Act require regarding AI literacy?",
    "q74_short_paraphrase": "Must I label AI-generated audio in my artistic work?",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "tunnel_smoke_postfix.json"))
    target = Path(ap.parse_args().out)
    key = dotenv_values(REPO / ".env").get("P2P_REGENOLD_API_KEY") or ""
    if not key:
        raise SystemExit("P2P_REGENOLD_API_KEY missing from .env")
    out: dict = {"commit": _get("/healthz", 30).get("commit")}
    for name, question in QUESTIONS.items():
        data, latency = ask(question, key)
        out[name] = {"question": question, "latency_s": latency,
                     **{k: data.get(k) for k in ("answer", "references", "warning",
                                                 "retrieval_path")}}
        print(f"{name}: {latency}s refs={data.get('references')} "
              f"path={data.get('retrieval_path')}", flush=True)
    llm = _get("/healthz/llm")
    out["healthz_llm"] = {k: llm.get(k) for k in ("llm_ok", "provider", "model", "detail",
                                                  "stage2_transport")}
    target.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {target}; transport={out['healthz_llm']['stage2_transport']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
