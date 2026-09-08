#!/usr/bin/env python3
"""Boot the service the way Railway does, and fail if the healthcheck never comes up.

R394.2/R394.3. PR #389 shipped an ``import`` of a module that was never
``git add``-ed. Everything local stayed green — the suite runs against the
working tree, which is exactly where the untracked file lived — while Railway,
which deploys from a **clone**, died at import, never bound ``/healthz``, and
silently kept serving the previous release for hours.

CI is a clean clone, so simply *starting the app here* is the check that was
missing. This script is that check.

It deliberately reads the start command, the healthcheck path and the timeout
**out of railway.toml** rather than restating them, so CI can never drift into
testing a command Railway does not run. Change railway.toml and this follows.

No secrets and no network: the app must boot with no environment at all (Neo4j,
Bedrock, Cohere and Postgres are all lazy), which is itself worth pinning — an
import-time dependency on a credential would be a deploy risk of its own.
"""

from __future__ import annotations

import os
import shlex
import shutil
import socket
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "railway.toml"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def main() -> int:
    deploy = tomllib.loads(CONFIG.read_text(encoding="utf-8")).get("deploy", {})
    start = deploy.get("startCommand")
    if not start:
        print(f"FAIL: no [deploy].startCommand in {CONFIG}", file=sys.stderr)
        return 1
    path = deploy.get("healthcheckPath", "/healthz")
    # Railway's own budget, plus room for a cold CI runner installing nothing.
    budget = int(deploy.get("healthcheckTimeout", 30)) + 60

    port = str(_free_port())
    # railway.toml binds 0.0.0.0:$PORT; keep the command verbatim and only swap
    # the loopback host so the runner does not expose a port it need not.
    argv = [
        (port if tok == "$PORT" else "127.0.0.1" if tok == "0.0.0.0" else tok)
        for tok in shlex.split(start.strip())
    ]
    # Prefer Railway's literal argv; fall back to `python -m` when the console
    # script is not on PATH (a venv-less local run), so this stays verifiable
    # off-CI without changing what CI actually executes.
    if shutil.which(argv[0]) is None:
        argv = [sys.executable, "-m", *argv]
    env = {**os.environ, "PORT": port}

    print(f"railway.toml startCommand : {start}")
    print(f"running                   : {' '.join(argv)}")
    print(f"healthcheck               : {path}  (budget {budget}s)")

    log = REPO / "boot.log"
    with log.open("w", encoding="utf-8") as fh:
        proc = subprocess.Popen(argv, cwd=str(REPO), env=env, stdout=fh, stderr=subprocess.STDOUT)
        url = f"http://127.0.0.1:{port}{path}"
        t0, ok, last = time.time(), False, "no attempt yet"
        while time.time() - t0 < budget:
            if proc.poll() is not None:
                print(f"\nFAIL: the server exited after {time.time()-t0:.1f}s "
                      f"(code {proc.returncode}) — it never bound {path}.", file=sys.stderr)
                break
            try:
                with urllib.request.urlopen(url, timeout=3) as r:
                    if r.status == 200:
                        print(f"\nOK: {path} returned 200 after {time.time()-t0:.2f}s")
                        print("body:", r.read().decode("utf-8", "replace")[:300])
                        ok = True
                        break
                    last = f"HTTP {r.status}"
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                last = f"{type(exc).__name__}: {exc}"
            time.sleep(0.5)
        else:
            print(f"\nFAIL: {path} never returned 200 within {budget}s. last: {last}",
                  file=sys.stderr)

        # Snapshot the log BEFORE shutting the server down. Terminating uvicorn
        # unwinds its workers through asyncio and writes a CancelledError
        # traceback, so reading afterwards makes a perfectly green run look like
        # a crash.
        captured = log.read_text(encoding="utf-8", errors="replace").splitlines()

        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()

    print("\n--- server log " + ("(startup)" if ok else "(FULL — this is the failure)") + " ---")
    print("\n".join(captured[-25:] if ok else captured))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
