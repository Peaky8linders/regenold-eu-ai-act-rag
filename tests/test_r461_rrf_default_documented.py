"""R461 (V22) — the ``REGENOLD_RRF_FUSION`` docstring must state the default the code ships.

The R450 transplant left the gate's docstring opening its decision paragraph with
"Default ON (R450 candidate flip)" while the code default is ``"0"`` and the flip
was reverted 25 lines further down. A reader deciding whether a recorded ranking
was fused believed the header. This pins the documented default to the
behavioural one, in both directions, so a future real flip that forgets the
docstring fails here too.
"""
from __future__ import annotations

import inspect
import re

import pytest

from app.data import kb_search


def test_documented_rrf_default_matches_the_code_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REGENOLD_RRF_FUSION", raising=False)
    shipped_on = kb_search._rrf_fusion_enabled()  # noqa: SLF001

    doc = inspect.getdoc(kb_search._rrf_fusion_enabled) or ""  # noqa: SLF001
    claims = re.findall(r"\*\*Default (ON|OFF)\b", doc)
    assert claims, "the gate's docstring must state its default"
    assert set(claims) == {"ON" if shipped_on else "OFF"}, (claims, shipped_on)
