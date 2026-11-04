"""Reproduce two pipeline findings without network or model calls.

This is a diagnostic on new paraphrases, not a statistical measurement or a
claim about deployed settings. Run from the repository root:
    python docs/measurements/paper_2611_04546/pipeline_probe.py
"""
from __future__ import annotations

import functools
import inspect
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def main() -> None:
    # These flags configure the SERVICE, not pytest. No .env is read.
    offline = {
        "REGENOLD_SKIP_DOTENV": "1",
        "OPENAI_API_BASE": "http://127.0.0.1:1/v1",
        "P2P_GRAPH_RAG_PROVIDER": "cli",
        "REGENOLD_EXTERNAL_EMBEDDINGS": "0",
        "NEO4J_URI": "",
        "NEO4J_AUTO_SEED": "0",
    }
    os.environ.update(offline)
    for key in (
        "REGENOLD_MAX_ANSWER_SENTENCES",
        "REGENOLD_QA_LENGTH_CAP",
        "REGENOLD_COMPLEX_SENTENCE_CAP",
    ):
        os.environ.pop(key, None)

    network_attempts: list[str] = []

    def deny_network(*args, **kwargs):
        network_attempts.append("network connection attempted")
        raise RuntimeError("This offline probe prohibits network connections")

    original_connect = socket.socket.connect

    def guarded_connect(connection, address):
        # Windows implements asyncio's internal socketpair through loopback TCP.
        # Allow that standard-library plumbing only; reject application dials.
        caller = inspect.currentframe().f_back
        if caller and caller.f_code.co_name == "_fallback_socketpair":
            return original_connect(connection, address)
        return deny_network(connection, address)

    socket.create_connection = deny_network
    socket.socket.connect = guarded_connect

    from fastapi.testclient import TestClient

    import app.routes.regenold as route
    from app.engines import _graph_rag_impl as engine
    from app.integrations.regenold import models
    from app.main import app
    from evals.regenold.hard_preamble import preamble_messages

    changes: list[dict] = []
    for name, function in list(vars(route).items()):
        if not inspect.isfunction(function) or function.__module__ != route.__name__:
            continue
        parameters = list(inspect.signature(function).parameters)
        if not parameters or parameters[0] not in {"references", "refs", "candidates"}:
            continue

        def wrap(original, original_name):
            @functools.wraps(original)
            def observed(*args, **kwargs):
                before = list(args[0]) if args and isinstance(args[0], list) else None
                value = original(*args, **kwargs)
                if before is not None and isinstance(value, list) and before != value:
                    changes.append({"function": original_name, "before": before, "after": value})
                return value
            return observed

        setattr(route, name, wrap(function, name))

    client = TestClient(app)
    cases = []
    questions = [
        "What obligations must a hospital meet when it deploys a high-risk AI system?",
        "A hospital deploys a high-risk AI system. What are the hospital's obligations?",
    ]
    for question in questions:
        context = engine.GraphContext()
        draft = engine._deterministic_answer(question, context)
        changes.clear()
        response = client.post(
            "/api/v1/regenold/eu-ai-act/ask?include_reasoning=true",
            json={"messages": [{"role": "user", "content": question}]},
        )
        payload = response.json()
        sentences = models._split_sentences(models._strip_markdown(draft))
        cases.append({
            "question": question,
            "http_status": response.status_code,
            "draft": draft,
            "draft_sentences": len(sentences),
            "wire_answer_sentences": len(models._split_sentences(payload.get("answer", ""))),
            "draft_sentences_absent_from_wire": [s for s in sentences if s not in payload.get("answer", "")],
            "wire": payload,
            "reference_pass_changes": list(changes),
        })

    # A short Appendix B quotation is sufficient to demonstrate the functional
    # distinction. The complete official fixture belongs in a versioned import.
    appendix_user = "Is every Annex III AI system automatically high-risk?"
    fixture = {
        "source": "https://arxiv.org/html/2611.04546v1#A2",
        "scope": "one published user turn only; not the complete official fixture",
        "current_fixture_anchors": route._extract_conversation_anchors(
            [SimpleNamespace(**m) for m in preamble_messages()]
        ),
        "published_turn": appendix_user,
        "published_turn_anchors": route._extract_conversation_anchors(
            [SimpleNamespace(role="user", content=appendix_user)]
        ),
    }
    result = {
        "kind": "offline diagnostic; not a performance A/B evaluation",
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "service_environment": offline,
        "budget_environment": "unset; module defaults",
        "cases": cases,
        "fixture_probe": fixture,
        "network_attempts": network_attempts,
    }
    output = Path(__file__).with_suffix(".json")
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {output}; {len(cases)} cases; {len(network_attempts)} network attempts")


if __name__ == "__main__":
    main()
