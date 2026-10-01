"""Ruff UP031: the R460 usage note used %-formatting; the module is otherwise
free of UP031. Idempotent.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ENGINE = ROOT / "app" / "engines" / "_graph_rag_impl.py"
src = ENGINE.read_text(encoding="utf-8")

OLD = '''            record_note(
                "stage2_usage in=%d out=%d system_chars=%d user_chars=%d turns=%s"
                % (
                    int(getattr(response, "prompt_tokens", 0) or 0),
                    int(getattr(response, "completion_tokens", 0) or 0),
                    len(wrapper_system or ""),
                    len(user or ""),
                    history_turn_count,
                )
            )
'''
NEW = '''            _usage_in = int(getattr(response, "prompt_tokens", 0) or 0)
            _usage_out = int(getattr(response, "completion_tokens", 0) or 0)
            record_note(
                f"stage2_usage in={_usage_in} out={_usage_out} "
                f"system_chars={len(wrapper_system or '')} "
                f"user_chars={len(user or '')} turns={history_turn_count}"
            )
'''

if NEW in src:
    print("already f-string")
else:
    assert src.count(OLD) == 1, src.count(OLD)
    ENGINE.write_text(src.replace(OLD, NEW), encoding="utf-8")
    print("switched to f-string")
