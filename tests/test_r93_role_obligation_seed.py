"""R93 — role-obligation NOUN seed (gated, default OFF).

The R87-D role-duty seed fired only on action-verb shapes; the live
fresh-200 probe found the canonical noun shape ("What obligations does a
provider have?") missing the role's Article. The noun trigger is gated
behind REGENOLD_ROLE_DUTY_NOUN_SEED (default OFF) so davidath stays
byte-identical; railway.toml flips it ON for the live deploy.
"""
from __future__ import annotations

import pytest

from app.routes.regenold import _detect_role_duty_seed


def test_noun_seed_off_by_default(monkeypatch):
    monkeypatch.delenv("REGENOLD_ROLE_DUTY_NOUN_SEED", raising=False)
    # Noun shape does NOT fire when the gate is off (davidath parity).
    assert _detect_role_duty_seed("What obligations do we have as the provider?") is None


def test_verb_seed_still_fires_default(monkeypatch):
    # The R87-D verb path is unchanged (default ON, no gate).
    monkeypatch.delenv("REGENOLD_ROLE_DUTY_NOUN_SEED", raising=False)
    assert _detect_role_duty_seed(
        "When must a deployer report a serious incident?"
    ) == "Article 26"


@pytest.mark.parametrize(
    "q,expected",
    [
        ("What obligations do we have as the provider?", "Article 16"),
        ("What are the obligations of deployers of high-risk AI systems?", "Article 26"),
        ("What duties does an importer have?", "Article 23"),
        ("What responsibilities does a distributor have?", "Article 24"),
    ],
)
def test_noun_seed_fires_when_enabled(monkeypatch, q, expected):
    monkeypatch.setenv("REGENOLD_ROLE_DUTY_NOUN_SEED", "1")
    assert _detect_role_duty_seed(q) == expected


@pytest.mark.parametrize(
    "q",
    [
        "What is the difference between a provider and a deployer?",
        "What is a provider?",
        "What requirements must high-risk AI systems meet?",  # no role noun
    ],
)
def test_noun_seed_does_not_fire_on_definitional_or_roleless(monkeypatch, q):
    monkeypatch.setenv("REGENOLD_ROLE_DUTY_NOUN_SEED", "1")
    assert _detect_role_duty_seed(q) is None
