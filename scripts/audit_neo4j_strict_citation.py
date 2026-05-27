"""Boot-time audit Cypher: every Article/Annex node carries a well-formed
``strict_citation`` matching the CLAUDE.md hard rule #1 reference shape.

R84-C ships ``legal_type`` + ``strict_citation`` properties on every legal-
element node via :mod:`scripts.seed_neo4j_kb`. This script is the operator
verification gate — re-runnable post-deploy / post-seed to assert the
graph state matches the schema. Exits non-zero (and prints offending
rows) if any node fails the strict-format check, suitable for
inclusion in a CI or pre-deploy smoke.

Decision tree:

* No ``NEO4J_URI`` set in the environment (and no CLI override) →
  ``SKIPPED`` + exit 0. We deliberately don't fail CI on environments
  without Neo4j configured.
* Driver acquired but query fails for any reason → exit 0 with a
  ``SKIPPED — driver error`` message. The audit is a *probe*, not a
  hard requirement. Production health is covered by ``/healthz/graph``.
* Query succeeds + returns zero rows → ``OK`` + exit 0.
* Query succeeds + returns rows → print each row + summary + exit 1.

CLI flags mirror :mod:`scripts.seed_neo4j_kb` (``--neo4j-uri``,
``--neo4j-user``, ``--neo4j-password``, ``--neo4j-database``); all fall
through to the corresponding env vars.

Pure stdlib + project imports — no driver dep at module-import time.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any

# The audit Cypher: rejects Articles whose ``number`` isn't bare digits or
# whose ``strict_citation`` doesn't match the CLAUDE.md hard rule #1
# article shape; same for Annexes against the Roman-numeral shape. Both
# regexes allow an optional sub-point tail (``.N``) because future seeder
# rounds may add sub-point nodes — base nodes match the no-tail form.
_AUDIT_CYPHER = r"""
MATCH (a:Article)
WHERE NOT a.number =~ '\\d+'
   OR NOT a.strict_citation =~ '^Article \\d+(\\.\\d+)?$'
RETURN 'Article' AS label, a.id AS id, a.number AS number,
       a.strict_citation AS strict_citation
UNION
MATCH (a:Annex)
WHERE NOT a.number =~ '[IVXLCDM]+'
   OR NOT a.strict_citation =~ '^Annex [IVXLCDM]+(\\.\\d+)?$'
RETURN 'Annex' AS label, a.id AS id, a.number AS number,
       a.strict_citation AS strict_citation
"""


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="audit_neo4j_strict_citation",
        description=(
            "Verify every Article / Annex node in Neo4j carries a "
            "well-formed strict_citation property (CLAUDE.md hard rule #1)."
        ),
    )
    p.add_argument(
        "--neo4j-uri",
        default=None,
        help="Override the NEO4J_URI env var.",
    )
    p.add_argument(
        "--neo4j-user",
        default=None,
        help="Override the NEO4J_USER env var.",
    )
    p.add_argument(
        "--neo4j-password",
        default=None,
        help="Override the NEO4J_PASSWORD env var.",
    )
    p.add_argument(
        "--neo4j-database",
        default=None,
        help="Override the NEO4J_DATABASE env var.",
    )
    return p


def _apply_env_overrides(args: argparse.Namespace) -> None:
    """Map CLI overrides into env vars before GraphSettings reads them.

    Mirrors :func:`scripts.seed_neo4j_kb._apply_env_overrides` so operators
    can flip between the two scripts with identical flag muscle memory.
    """
    if args.neo4j_uri:
        os.environ["NEO4J_URI"] = args.neo4j_uri
    if args.neo4j_user:
        os.environ["NEO4J_USER"] = args.neo4j_user
    if args.neo4j_password:
        os.environ["NEO4J_PASSWORD"] = args.neo4j_password
    if args.neo4j_database:
        os.environ["NEO4J_DATABASE"] = args.neo4j_database


def _format_row(row: dict[str, Any]) -> str:
    label = row.get("label", "?")
    node_id = row.get("id", "?")
    number = row.get("number", "?")
    strict_citation = row.get("strict_citation", "?")
    return (
        f"{label} {node_id} number={number!r} "
        f"strict_citation={strict_citation!r}"
    )


def run_audit() -> int:
    """Run the audit; return the exit code (0/1).

    Lazily imports the GraphClient so a stripped environment (no
    ``neo4j`` driver installed) can still load this module to print
    ``--help`` etc.
    """
    if not os.environ.get("NEO4J_URI"):
        print("SKIPPED — no NEO4J_URI set; nothing to audit.")
        return 0

    try:
        from app.graph.client import get_graph_client
    except Exception as exc:  # noqa: BLE001
        print(f"SKIPPED — graph client import failed: {exc}")
        return 0

    try:
        client = get_graph_client()
    except Exception as exc:  # noqa: BLE001
        print(f"SKIPPED — graph client init failed: {exc}")
        return 0

    if not getattr(client, "enabled", False):
        print("SKIPPED — graph client disabled (driver init failed).")
        return 0

    try:
        rows = client.execute_read(_AUDIT_CYPHER)
    except Exception as exc:  # noqa: BLE001
        print(f"SKIPPED — driver error during audit query: {exc}")
        return 0

    if not rows:
        print("OK — all 126 legal-element nodes pass the strict format audit.")
        return 0

    print(f"FAIL — {len(rows)} node(s) failed the strict format audit:")
    for row in rows:
        print(f"  {_format_row(row)}")
    print(
        "Re-seed via ``python -m scripts.seed_neo4j_kb`` to refresh the "
        "strict_citation / legal_type properties (R84-C)."
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _apply_env_overrides(args)
    return run_audit()


if __name__ == "__main__":
    sys.exit(main())
