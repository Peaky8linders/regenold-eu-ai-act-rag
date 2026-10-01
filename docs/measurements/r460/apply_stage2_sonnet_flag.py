"""R460 — apply the two-string patch that makes a Sonnet Stage-2 id reachable.

WHY A SCRIPT AND NOT A DIFF. The worktree this runs in lives under an ignored
path, so the ordinary editor cannot open these files; a hand-written unified
diff also has to survive CRLF. This does an exact, asserted BYTE replacement
(count must be 1) and leaves every other byte untouched, so `git diff` shows
exactly the change. Idempotent: re-running it reports "already applied".

The change is inert by default: with REGENOLD_STAGE2_ALLOW_NON_OPUS unset the
routing rule is byte-identical to today, including the floor assertions in
tests/test_r442_opus55_model_option.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

IMPL = REPO / "app" / "engines" / "_graph_rag_impl.py"
ROUTES = REPO / "app" / "routes" / "regenold.py"

OLD_ROUTE = (
    '    if is_stage2:\r\n'
    '        model = complex_model or stage2_model or "claude-opus-4-8"\r\n'
    '        return model if "opus" in model.lower() else "claude-opus-4-8"\r\n'
    '    return base_model\r\n'
)

NEW_ROUTE = (
    '    if is_stage2:\r\n'
    '        model = complex_model or stage2_model or "claude-opus-4-8"\r\n'
    '        if "opus" in model.lower() or _stage2_allow_non_opus():\r\n'
    '            return model\r\n'
    '        return "claude-opus-4-8"\r\n'
    '    return base_model\r\n'
    '\r\n'
    '\r\n'
    'def _stage2_allow_non_opus() -> bool:\r\n'
    '    """R460 - opt-in escape from the R139 Opus floor. **Default OFF.**\r\n'
    '\r\n'
    '    The floor is why the DOCUMENTED override in ``GraphRAGSettings.stage2_model``\r\n'
    '    ("Restore the Sonnet-5 simple tier per-deploy with\r\n'
    '    ``P2P_GRAPH_RAG_STAGE2_MODEL=claude-sonnet-5``") has never worked: any\r\n'
    '    non-Opus Stage-2 id is rewritten to ``claude-opus-4-8``, and a set\r\n'
    '    ``complex_model`` wins the standard path as well. MEASURED 2026-09-30 at\r\n'
    '    the provider seam and pinned by\r\n'
    '    ``tests/test_r442_opus55_model_option.py``.\r\n'
    '\r\n'
    '    OFF is byte-identical to the shipped routing, including those floor\r\n'
    '    assertions. ON is how a Sonnet-as-Stage-2 candidate reaches the wire for\r\n'
    '    an A/B; flipping it in production needs the R448 gate order (answer\r\n'
    '    correctness, then gold references, then the other axes, then latency).\r\n'
    '    """\r\n'
    '    return os.environ.get("REGENOLD_STAGE2_ALLOW_NON_OPUS", "0").strip().lower() in {\r\n'
    '        "1",\r\n'
    '        "true",\r\n'
    '        "yes",\r\n'
    '        "on",\r\n'
    '    }\r\n'
)

OLD_KEY = '            "P2P_GRAPH_RAG_COMPLEX_MODEL",\r\n'

NEW_KEY = (
    '            "P2P_GRAPH_RAG_COMPLEX_MODEL",\r\n'
    '            # R460 - the allow-non-opus escape flips the Stage-2 answer MODEL\r\n'
    '            # (Sonnet 5 vs Opus 5.5) exactly as COMPLEX_MODEL does above, so\r\n'
    '            # it flips GraphRAGResponse.answer. Read fresh per call in\r\n'
    '            # ``_route_stage_model``, so it MUST be in the key (R263.2).\r\n'
    '            "REGENOLD_STAGE2_ALLOW_NON_OPUS",\r\n'
)


def _patch(path: Path, old: str, new: str) -> str:
    data = path.read_bytes()
    old_b = old.encode("utf-8")
    new_b = new.encode("utf-8")
    if new_b in data:
        return f"already applied: {path.name}"
    count = data.count(old_b)
    if count != 1:
        raise SystemExit(f"REFUSING: {path.name} matched {count} times (expected 1)")
    path.write_bytes(data.replace(old_b, new_b, 1))
    return f"patched: {path.name}"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print(_patch(IMPL, OLD_ROUTE, NEW_ROUTE))
    print(_patch(ROUTES, OLD_KEY, NEW_KEY))


if __name__ == "__main__":
    main()
