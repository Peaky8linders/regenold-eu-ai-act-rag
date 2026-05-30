"""Offline validator for the paper-V4 eval modules.

Checks:
1. All three V4 modules import cleanly.
2. run_paper_v4 imports cleanly (schema/runner wiring).
3. Every expected_ref (singleturn + tricky) and expected_final_ref
   (multiturn) resolves in ARTICLE_EXISTENCE (using the internal
   "Art. N" / "Annex N" form that the catalog uses).
4. All IDs are unique within their module.
5. Multi-turn turns list is non-empty and the last turn is a "user" turn
   (required by runner_v2.run_multiturn — it sends the full history and
   scores the FINAL assistant response).
6. Each scenario has the required schema fields.

Exit code 0 = all checks pass.
Exit code 1 = one or more failures.
"""
from __future__ import annotations

import sys
from pathlib import Path

# ── Imports ────────────────────────────────────────────────────────────────
# These must resolve before any checks run.
from app.data.article_existence import ARTICLE_EXISTENCE

from evals.regenold.scenarios_paper_singleturn_v4 import SCENARIOS as SINGLETURN_V4
from evals.regenold.scenarios_paper_tricky_v4 import SCENARIOS as TRICKY_V4
from evals.regenold.scenarios_paper_multiturn_v4 import SCENARIOS as MULTITURN_V4

# Dry-import the runner to verify wiring (no HTTP calls)
import evals.regenold.run_paper_v4  # noqa: F401


# ── Reference form conversion ─────────────────────────────────────────────

def _user_facing_to_internal(ref: str) -> str:
    """Convert "Article 13" → "Art. 13" and "Annex III" → "Annex III".

    ARTICLE_EXISTENCE stores internal forms: "Art. N" and "Annex N".
    The wire (and our expected_refs) use user-facing form "Article N" / "Annex N".
    Annex names are the same in both forms.
    """
    s = ref.strip()
    if s.startswith("Article "):
        return "Art. " + s[len("Article "):]
    # "Annex N" is identical in both forms
    return s


# ── Validation helpers ────────────────────────────────────────────────────

def _check_ref(ref: str, scenario_id: str, errors: list[str]) -> None:
    internal = _user_facing_to_internal(ref)
    # Strip sub-point suffixes: "Art. 5(1)(a)" → "Art. 5"
    head = internal.split("(")[0].split(".")[0]
    # Re-attach the dot for "Art. N" format
    if head.startswith("Art "):
        # "Art 5" edge-case — shouldn't happen but guard anyway
        head = "Art. " + head[4:]
    # Check the plain article head
    if internal in ARTICLE_EXISTENCE:
        return  # exact match
    # Try head-only match (sub-point form)
    if head in ARTICLE_EXISTENCE:
        return
    # Try with trailing digit for "Annex III" style that may include a space
    # ARTICLE_EXISTENCE already has "Annex I".."Annex XIII" as full strings.
    if internal in ARTICLE_EXISTENCE:
        return
    errors.append(
        f"  [{scenario_id}] unresolved ref: {ref!r} "
        f"(internal={internal!r}, head={head!r})"
    )


def _check_tricky_schema(scn: dict, errors: list[str]) -> None:
    sid = scn.get("id", "<no-id>")
    for field in ("id", "question", "expected_refs", "expected_keywords", "category", "notes"):
        if field not in scn:
            errors.append(f"  [{sid}] missing field: {field!r}")
    refs = scn.get("expected_refs", [])
    if not isinstance(refs, list):
        errors.append(f"  [{sid}] expected_refs must be a list")
        return
    for ref in refs:
        _check_ref(ref, sid, errors)


def _check_multiturn_schema(scn: dict, errors: list[str]) -> None:
    sid = scn.get("id", "<no-id>")
    for field in ("id", "turns", "expected_final_refs", "expected_final_keywords", "notes"):
        if field not in scn:
            errors.append(f"  [{sid}] missing field: {field!r}")
    turns = scn.get("turns", [])
    if not isinstance(turns, list) or len(turns) < 2:
        errors.append(f"  [{sid}] turns must be a list with at least 2 entries")
        return
    last_role = turns[-1].get("role", "")
    if last_role != "user":
        errors.append(
            f"  [{sid}] last turn must be 'user' (got {last_role!r}) — "
            "runner_v2 sends full history and scores the engine's response "
            "to the final user message"
        )
    refs = scn.get("expected_final_refs", [])
    if not isinstance(refs, list):
        errors.append(f"  [{sid}] expected_final_refs must be a list")
        return
    for ref in refs:
        _check_ref(ref, sid, errors)


def _check_unique_ids(scenarios: list[dict], label: str, errors: list[str]) -> None:
    seen: dict[str, int] = {}
    for scn in scenarios:
        sid = scn.get("id", "<no-id>")
        seen[sid] = seen.get(sid, 0) + 1
    dupes = {k: v for k, v in seen.items() if v > 1}
    for sid, count in dupes.items():
        errors.append(f"  [{label}] duplicate ID {sid!r} appears {count} times")


# ── Main ─────────────────────────────────────────────────────────────────


def main() -> int:
    errors: list[str] = []
    total_refs = 0

    print("Validating evals/regenold/scenarios_paper_singleturn_v4.py ...")
    _check_unique_ids(SINGLETURN_V4, "singleturn_v4", errors)
    for scn in SINGLETURN_V4:
        _check_tricky_schema(scn, errors)
        total_refs += len(scn.get("expected_refs", []))
    print(f"  {len(SINGLETURN_V4)} scenarios, "
          f"{sum(len(s.get('expected_refs',[])) for s in SINGLETURN_V4)} refs checked")

    print("Validating evals/regenold/scenarios_paper_tricky_v4.py ...")
    _check_unique_ids(TRICKY_V4, "tricky_v4", errors)
    for scn in TRICKY_V4:
        _check_tricky_schema(scn, errors)
        total_refs += len(scn.get("expected_refs", []))
    print(f"  {len(TRICKY_V4)} scenarios, "
          f"{sum(len(s.get('expected_refs',[])) for s in TRICKY_V4)} refs checked")

    print("Validating evals/regenold/scenarios_paper_multiturn_v4.py ...")
    _check_unique_ids(MULTITURN_V4, "multiturn_v4", errors)
    for scn in MULTITURN_V4:
        _check_multiturn_schema(scn, errors)
        total_refs += len(scn.get("expected_final_refs", []))
    print(f"  {len(MULTITURN_V4)} scenarios, "
          f"{sum(len(s.get('expected_final_refs',[])) for s in MULTITURN_V4)} refs checked")

    print(f"\nTotal references checked: {total_refs}")

    if errors:
        print(f"\nFAIL — {len(errors)} error(s):")
        for e in errors:
            print(e)
        return 1

    # Category distribution summary
    all_single = SINGLETURN_V4 + TRICKY_V4
    cats: dict[str, int] = {}
    for s in all_single:
        cats[s.get("category", "?")] = cats.get(s.get("category", "?"), 0) + 1
    print("\nCategory distribution (singleturn + tricky combined):")
    for cat, n in sorted(cats.items()):
        print(f"  {cat:<28} {n}")

    turn_counts = [len(s.get("turns", [])) for s in MULTITURN_V4]
    print("\nMulti-turn turn-count distribution:")
    for n in sorted(set(turn_counts)):
        count = turn_counts.count(n)
        print(f"  {n} turns: {count} scenario(s)")

    print("\nPASS — all checks green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
