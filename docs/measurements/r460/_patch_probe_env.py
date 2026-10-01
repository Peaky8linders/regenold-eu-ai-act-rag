"""One-shot fix: collapse the doubled env-loading import block in the probe.

History: the first patch inserted
``import app.config`` + comment before the provider import. A second run of the
patch script found the import block already present but still matched the
ORIGINAL two-line anchor, so it inserted the comment+import again. This
collapses the duplicate. Idempotent.

The probe needs ``app.config`` because ``_load_dotenv_once`` attaches the
Cloudflare Access service token to the provider; without it every wrapper call
returns ``api_status_401`` in ~40 ms (measured 2026-09-30 12:33).
"""
from __future__ import annotations

from pathlib import Path

P = Path(__file__).resolve().parent / "token_leg_probe.py"
src = P.read_text(encoding="utf-8")

BLOCK = (
    "    # Load .env at import (app.config::_load_dotenv_once). Without this the\n"
    "    # provider has no CF Access service token and every call 401s.\n"
    "    import app.config  # noqa: F401, PLC0415\n"
)
DOUBLED = BLOCK + "\n" + BLOCK
FIXED = BLOCK

if FIXED in src and DOUBLED not in src:
    print("already fixed")
else:
    assert src.count(DOUBLED) == 1, f"doubled block count={src.count(DOUBLED)}"
    src = src.replace(DOUBLED, FIXED)
    P.write_text(src, encoding="utf-8")
    print("collapsed doubled block")
