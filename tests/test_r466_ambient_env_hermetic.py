"""R466 — the suite must not inherit the documented OFFLINE RECIPE from the shell.

``AGENTS.md`` and ``CLAUDE.md`` hand the operator

    OPENAI_API_BASE=http://127.0.0.1:1/v1
    P2P_GRAPH_RAG_PROVIDER=cli
    REGENOLD_EXTERNAL_EMBEDDINGS=0

as the deterministic local-testing environment. Exporting that in a shell and
then running ``pytest tests/`` used to fail 57 tests — and ONLY then, which is
why the failures read as test-order dependence for three rounds:

    P2P_GRAPH_RAG_PROVIDER=cli      51 failures
    REGENOLD_EXTERNAL_EMBEDDINGS=0   6 failures
    union                           57  (disjoint — measured, not estimated)

The union of those two sets is exactly the observed 57, and each flag
reproduces alone in a single file on a clean tree::

    P2P_GRAPH_RAG_PROVIDER=cli pytest tests/test_bridging_taxonomy.py
    REGENOLD_EXTERNAL_EMBEDDINGS=0 pytest tests/test_external_embeddings.py

So there was never a poisoning test to isolate. Both flags are read live by
first-class gates — ``is_openai_wrapper_enabled()`` returns False for ``cli``
(Stage-0 intent, Stage-2 polish and the CLARA gate then short-circuit before
their own mocks) and ``external_embeddings`` force-disables both providers on
``=0`` (a test that sets a Cohere key and expects ``is_available()`` to follow
it gets False). ``tests/conftest.py`` neutralises the credentials but must also
drop these two, or the suite silently grades a different configuration than a
clean CI clone does.

The behavioural half runs a REAL child pytest with the poisoned environment,
because conftest is already imported by the time any test executes — the
neutralisation cannot be re-run in-process, so asserting on module state alone
would not notice its removal. The child collects only these two files, so there
is no recursion.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]

#: The two files that fail on the ambient flags and pass without them. Chosen
#: because each is fast (< 1 s) and each is the FIRST failure of its flag.
_CHILD_TARGETS = (
    "tests/test_bridging_taxonomy.py",  # P2P_GRAPH_RAG_PROVIDER=cli
    "tests/test_external_embeddings.py",  # REGENOLD_EXTERNAL_EMBEDDINGS=0
)


def test_the_neutralised_flags_are_the_documented_recipe() -> None:
    """The list is a contract, asserted by name.

    A future edit that drops ``REGENOLD_EXTERNAL_EMBEDDINGS`` from the list is
    inaudible while nobody exports it — the behavioural test below still passes
    on a clean shell. This test is the half that fails immediately.
    """
    import tests.conftest as conftest

    assert set(conftest._AMBIENT_OFFLINE_FLAGS) == {
        "P2P_GRAPH_RAG_PROVIDER",
        "REGENOLD_EXTERNAL_EMBEDDINGS",
    }, (
        "R466 — both flags of the documented offline recipe must be "
        "neutralised at conftest import; see AGENTS.md"
    )


def test_this_process_did_not_keep_the_poisoning_values() -> None:
    """End state in the running session — not just the intent to drop them."""
    assert os.environ.get("P2P_GRAPH_RAG_PROVIDER", "").strip().lower() != "cli", (
        "R466 — P2P_GRAPH_RAG_PROVIDER=cli survived conftest import, so this "
        "session is running the cli configuration instead of the defaults"
    )
    assert os.environ.get("REGENOLD_EXTERNAL_EMBEDDINGS", "").strip() != "0", (
        "R466 — REGENOLD_EXTERNAL_EMBEDDINGS=0 survived conftest import"
    )


def test_a_child_pytest_with_the_recipe_exported_passes() -> None:
    """The real gate: a fresh interpreter, the recipe in the environment.

    Without the conftest neutralisation this child reports the same failures
    the operator saw — 1 in ``test_bridging_taxonomy.py`` and 1 in
    ``test_external_embeddings.py`` — so the assertion is not tautological.
    """
    env = dict(os.environ)
    env["P2P_GRAPH_RAG_PROVIDER"] = "cli"
    env["REGENOLD_EXTERNAL_EMBEDDINGS"] = "0"
    # The child must import ``app`` from this checkout, exactly like the parent.
    env["PYTHONPATH"] = os.pathsep.join(
        [_REPO_ROOT.as_posix(), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    env.setdefault("PYTHONIOENCODING", "utf-8")

    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                *_CHILD_TARGETS,
                "-q",
                "-p",
                "no:cacheprovider",
            ],
            cwd=_REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        pytest.skip(f"cannot spawn a child pytest here ({exc}) — nothing measured")

    tail = (proc.stdout or "")[-2500:] + (proc.stderr or "")[-1500:]
    assert proc.returncode == 0, (
        "R466 — exporting the documented offline recipe still fails tests: the "
        "conftest must drop P2P_GRAPH_RAG_PROVIDER / "
        f"REGENOLD_EXTERNAL_EMBEDDINGS at import.\n\n{tail}"
    )
    assert " passed" in tail, f"child ran but its summary is missing:\n{tail}"
