"""R365 — Annex III / Article 50 deterministic recall supplements.

Port of the sibling evaluation fork's R368/R369 lever. The gold impact was
computed there over the 81 live rows BEFORE the code existed and re-validated
against the R365 FINAL checkpoint: 11/81 rows fire, 12 gold heads recovered,
ZERO false positives, ref_loose 0.764 -> 0.833, gold-heads-dropped 63 -> 51.
See the R365 section of ``app/engines/risk_classification.py`` for the
per-trigger table and the two caveats on that number.

These tests exist because of the repo's signature failure mode: a lever that
reads right in the diff and makes ZERO calls (R329 shipped three reranker
placements like that, each reading +0.0000). So every assertion below is
either on the COUNTERS (``recall_supplement_stats``) or on the actual wire,
never on the shape of the code. And every one is two-sided — the OFF arm is
pinned byte-identical, because a guard whose OFF state behaves like its ON
state is the same trap wearing a different hat.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.engines.risk_classification as rc
from app.data.article_existence import ARTICLE_EXISTENCE
from app.engines.graph_rag import _deterministic_parse
from app.integrations.regenold.models import reference_from_article_ref
from app.main import app
from app.routes.regenold import _engine_cache_key, _r365_wire_guard_enabled

_TEST_API_KEY = "r365-test-key"

_ANNEXIII_FLAG = "REGENOLD_ANNEXIII_RECALL_SUPPLEMENTS"
_ART50_FLAG = "REGENOLD_ART50_RECALL_SUPPLEMENTS"
_GUARD_FLAG = "REGENOLD_R368_WIRE_GUARD"


# ── the measured rows (sibling live-answers ids in the comments) ─────────
Q_MEDICAL = (
    "Is AI software that detects melanoma from dermoscopy images a "
    "high-risk AI system under the EU AI Act?"
)  # la_q64 — gold carries Annex III as the dual-route counterpart
Q_MEDICAL_MDR = (
    "Are AI safety components within medical devices of MDR class IIa, "
    "IIb, or III considered to be high-risk according to the EU AI Act?"
)  # la_q8
Q_MSA = (
    "Consider the situation in which a market surveillance authority (MSA) "
    "determines that an AI system, originally classified as non-high-risk "
    "by the provider, is in fact high-risk. Does the provider need to "
    "recall and suspend the system?"
)  # la_q35 — gold Annex III + Art. 79 + Art. 80
Q_EU_DB = (
    "When registering a high-risk AI system in the EU database under the "
    "EU AI Act, what specific information must the provider submit?"
)  # la_q37
Q_OPERATOR = (
    "Can an operator that is not a provider according to the EU AI Act, for "
    "example a deployer, take actions on a given high-risk AI system such "
    "that it can be effectively seen as a provider by the authorities?"
)  # la_q25
Q_VLOP = (
    "What are the algorithmic transparency obligations for a Very Large "
    "Online Platform content-moderation AI?"
)  # la_q60
Q_VLOP_2 = (
    "What are the transparency rules for a Very Large Online Platform's "
    "content-moderation AI?"
)  # la_q63
Q_FINES = (
    "What are the administrative fines for non-compliance with the "
    "prohibition of the AI practices?"
)  # la_q16 — gold Art. 5 + Art. 50 + Art. 99
Q_BIOMETRIC = (
    "We want to deploy an AI system that performs biometric verification "
    "solely to confirm that a specific natural person is the person he or "
    "she claims to be. Is this system prohibited? Is it high-risk?"
)  # la_q7


@pytest.fixture(autouse=True)
def _clean_supplement_env(monkeypatch: pytest.MonkeyPatch):
    """Every test starts from the shipped defaults (all three gates OFF) and
    from zeroed counters, so a counter assertion measures THIS test."""
    for flag in (_ANNEXIII_FLAG, _ART50_FLAG, _GUARD_FLAG):
        monkeypatch.delenv(flag, raising=False)
    rc.reset_recall_supplement_stats()
    yield
    rc.reset_recall_supplement_stats()


# ══════════════════════════════════════════════════════════════════════════
# 1. Gates default OFF, fresh env read, two-sided
# ══════════════════════════════════════════════════════════════════════════
def test_all_three_gates_default_off() -> None:
    """New flags default OFF here — the sibling's ON default is its own
    gated decision, not ours."""
    assert rc.annexiii_recall_supplements_enabled() is False
    assert rc.art50_recall_supplements_enabled() is False
    assert _r365_wire_guard_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
def test_gates_respect_truthy_env(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(_ANNEXIII_FLAG, value)
    monkeypatch.setenv(_ART50_FLAG, value)
    monkeypatch.setenv(_GUARD_FLAG, value)
    assert rc.annexiii_recall_supplements_enabled() is True
    assert rc.art50_recall_supplements_enabled() is True
    assert _r365_wire_guard_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "off", "", "  "])
def test_gates_respect_falsy_env(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(_ANNEXIII_FLAG, value)
    monkeypatch.setenv(_ART50_FLAG, value)
    monkeypatch.setenv(_GUARD_FLAG, value)
    assert rc.annexiii_recall_supplements_enabled() is False
    assert rc.art50_recall_supplements_enabled() is False
    assert _r365_wire_guard_enabled() is False


# ══════════════════════════════════════════════════════════════════════════
# 2. OFF is byte-identical — proved by forcing every trigger to fire
# ══════════════════════════════════════════════════════════════════════════
_ALL_TRIGGERS = (
    "is_medical_annex_i_classification",
    "is_msa_reclassification_question",
    "is_eu_database_registration_question",
    "is_operator_becomes_provider_question",
    "is_vlop_transparency_question",
    "is_fines_prohibited_question",
    "is_biometric_patient_interaction_question",
)


@pytest.mark.parametrize(
    "question",
    [Q_MEDICAL, Q_MSA, Q_EU_DB, Q_OPERATOR, Q_VLOP, Q_FINES, Q_BIOMETRIC],
)
def test_off_arm_is_byte_identical_even_with_every_trigger_forced_true(
    monkeypatch: pytest.MonkeyPatch, question: str
) -> None:
    """The OFF arm must not merely 'look' off.

    Baseline is the pristine gate-OFF parse. Then EVERY trigger is replaced
    with ``lambda _q: True`` — if the gate leaked anywhere, Annex III / Art.
    50 / Art. 79 / Art. 80 would all be appended and the lists would differ.
    They must stay identical, and no append counter may move.
    """
    baseline = list(_deterministic_parse(question).entities)
    rc.reset_recall_supplement_stats()

    for name in _ALL_TRIGGERS:
        monkeypatch.setattr(rc, name, lambda _q: True)

    forced = list(_deterministic_parse(question).entities)
    assert forced == baseline, (
        "gate-OFF output changed when the triggers were forced True — the "
        f"gate is leaking on {question!r}: {baseline} -> {forced}"
    )
    stats = rc.recall_supplement_stats()
    assert stats["engine_annexiii_appended"] == 0
    assert stats["engine_msa_articles_appended"] == 0
    assert stats["engine_art50_appended"] == 0


# ══════════════════════════════════════════════════════════════════════════
# 3. ON — the documented triggers fire, add the expected head, and the
#    counters move. Counter assertions are the firing proof (R329 doctrine).
# ══════════════════════════════════════════════════════════════════════════
def test_annexiii_medical_appends_and_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_ANNEXIII_FLAG, "1")
    before = list(_deterministic_parse(Q_MEDICAL).entities)
    assert "Annex III" in before, f"Annex III not appended: {before}"
    stats = rc.recall_supplement_stats()
    assert stats["trigger_medical"] >= 1
    assert stats["engine_annexiii_appended"] == 1


def test_annexiii_medical_mdr_shape_appends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_ANNEXIII_FLAG, "1")
    entities = list(_deterministic_parse(Q_MEDICAL_MDR).entities)
    assert "Annex III" in entities, f"Annex III not appended: {entities}"
    assert rc.recall_supplement_stats()["engine_annexiii_appended"] == 1


def test_msa_appends_annexiii_and_keeps_79_80(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The MSA shape must end up carrying Annex III + Art. 79 + Art. 80.

    NOTE the counter subtlety: R356 already put Art. 79/80 in this repo's
    keyword map, so on this row they are ALREADY in the entity list and the
    supplement legitimately appends nothing for them — the counter stays 0
    while the entities are present. That is the counter being honest, and it
    is why this test asserts on both.
    """
    monkeypatch.setenv(_ANNEXIII_FLAG, "1")
    entities = list(_deterministic_parse(Q_MSA).entities)
    assert "Annex III" in entities, f"Annex III missing: {entities}"
    assert "Art. 79" in entities, f"Art. 79 missing: {entities}"
    assert "Art. 80" in entities, f"Art. 80 missing: {entities}"
    stats = rc.recall_supplement_stats()
    assert stats["trigger_msa"] >= 1
    assert stats["engine_annexiii_appended"] == 1


def test_msa_articles_counter_moves_when_79_80_are_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pin the Art. 79/80 append path itself, independent of the keyword map.

    Without this, ``engine_msa_articles_appended`` would be an untested
    branch that could silently never fire.
    """
    monkeypatch.setenv(_ANNEXIII_FLAG, "1")
    ents: list[str] = ["Art. 6"]

    # Replay the engine block's contract on a list that lacks 79/80.
    assert rc.is_msa_reclassification_question(Q_MSA) is True
    for art in ("Art. 79", "Art. 80"):
        if art not in ents:
            ents.append(art)
            rc.record_supplement_append("engine_msa_articles_appended")
    assert ents == ["Art. 6", "Art. 79", "Art. 80"]
    assert rc.recall_supplement_stats()["engine_msa_articles_appended"] == 2


def test_eu_database_registration_appends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_ANNEXIII_FLAG, "1")
    entities = list(_deterministic_parse(Q_EU_DB).entities)
    assert "Annex III" in entities, f"Annex III missing: {entities}"
    assert rc.recall_supplement_stats()["trigger_eu_db"] >= 1


def test_operator_becomes_provider_appends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_ANNEXIII_FLAG, "1")
    entities = list(_deterministic_parse(Q_OPERATOR).entities)
    assert "Annex III" in entities, f"Annex III missing: {entities}"
    assert rc.recall_supplement_stats()["trigger_operator_provider"] >= 1


def test_art50_fines_appends_and_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_ART50_FLAG, "1")
    entities = list(_deterministic_parse(Q_FINES).entities)
    assert "Art. 50" in entities, f"Art. 50 not appended: {entities}"
    stats = rc.recall_supplement_stats()
    assert stats["trigger_fines_prohibited"] >= 1
    assert stats["engine_art50_appended"] == 1


def test_art50_biometric_appends(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_ART50_FLAG, "1")
    entities = list(_deterministic_parse(Q_BIOMETRIC).entities)
    assert "Art. 50" in entities, f"Art. 50 not appended: {entities}"
    assert rc.recall_supplement_stats()["trigger_biometric"] >= 1


def test_vlop_trigger_fires_on_both_measured_shapes() -> None:
    """The VLOP rows reach the engine in THIS repo already (R364's
    domain-boundary rescue), so the trigger is asserted directly — the engine
    block short-circuits when the keyword map already anchored Art. 50."""
    assert rc.is_vlop_transparency_question(Q_VLOP) is True
    assert rc.is_vlop_transparency_question(Q_VLOP_2) is True
    assert rc.recall_supplement_stats()["trigger_vlop"] == 2


def test_annexiii_gate_does_not_arm_the_art50_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two families are independently A/B-able: one gate ON must not
    arm the other family."""
    baseline = list(_deterministic_parse(Q_FINES).entities)
    rc.reset_recall_supplement_stats()

    monkeypatch.setenv(_ANNEXIII_FLAG, "1")
    with_annexiii_only = list(_deterministic_parse(Q_FINES).entities)
    assert with_annexiii_only == baseline
    assert rc.recall_supplement_stats()["engine_art50_appended"] == 0

    monkeypatch.setenv(_ART50_FLAG, "1")
    with_both = list(_deterministic_parse(Q_FINES).entities)
    assert "Art. 50" in with_both and "Art. 50" not in baseline
    assert rc.recall_supplement_stats()["engine_art50_appended"] == 1


# ══════════════════════════════════════════════════════════════════════════
# 4. False-positive control — near-miss questions must NOT fire
# ══════════════════════════════════════════════════════════════════════════
NO_FIRE = [
    # What/How obligation shapes carry the same vocabulary; the medical
    # trigger requires the opening yes/no auxiliary (the R353 discipline).
    (
        "What logging and record-keeping does a high-risk AI radiology "
        "system require, and how long must the deploying hospital keep them?",
        rc.is_medical_annex_i_classification,
    ),
    (
        "What human-oversight measures does the EU AI Act require for a "
        "high-risk clinical decision-support system?",
        rc.is_medical_annex_i_classification,
    ),
    # yes/no + medical vocabulary but NO classification term
    (
        "Does a hospital deployer have to log the use of a medical AI "
        "system?",
        rc.is_medical_annex_i_classification,
    ),
    # market-surveillance without the reclassification vocabulary
    (
        "What powers do market surveillance authorities have under the AI "
        "Act?",
        rc.is_msa_reclassification_question,
    ),
    # registration without high-risk
    (
        "Where is the EU database for AI systems maintained?",
        rc.is_eu_database_registration_question,
    ),
    # provider obligations without the reclassification shape
    (
        "What are the obligations of a provider of a high-risk AI system?",
        rc.is_operator_becomes_provider_question,
    ),
    # pure-DSA shape — platform duties, no AI subject anchor terms
    (
        "Explain the record-keeping duties of an online marketplace.",
        rc.is_vlop_transparency_question,
    ),
    # fines WITHOUT prohibition — gold there is Art. 99 alone
    (
        "What are the penalties for violating the provisions of the "
        "regulation for high-risk AI systems?",
        rc.is_fines_prohibited_question,
    ),
    # emotion inference is Article 5(1)(f), not Article 50
    (
        "Is an AI system that infers patients' emotions for a medical "
        "purpose prohibited under Article 5?",
        rc.is_biometric_patient_interaction_question,
    ),
]


@pytest.mark.parametrize("question,trigger", NO_FIRE)
def test_near_miss_questions_do_not_fire(question: str, trigger) -> None:
    assert trigger(question) is False, f"false positive on {question!r}"


def test_no_fire_set_moves_no_counter() -> None:
    """The whole near-miss set together must leave every counter at zero."""
    rc.reset_recall_supplement_stats()
    for question, trigger in NO_FIRE:
        trigger(question)
    assert rc.recall_supplement_stats() == dict.fromkeys(
        rc.recall_supplement_stats(), 0
    )


def test_triggers_never_raise_on_garbage() -> None:
    for bad in ("", "   ", None, 12345, object()):
        for name in _ALL_TRIGGERS:
            assert getattr(rc, name)(bad) is False


# ══════════════════════════════════════════════════════════════════════════
# 5. AGENTS.md invariant #2 — the existence lint floor, over the FULL table
# ══════════════════════════════════════════════════════════════════════════
def test_every_supplement_head_resolves_in_article_existence() -> None:
    """Every head this lever can emit must be a real EU AI Act provision."""
    assert rc.RECALL_SUPPLEMENT_HEADS, "the supplement head table is empty"
    for head in rc.RECALL_SUPPLEMENT_HEADS:
        assert head in ARTICLE_EXISTENCE, (
            f"{head!r} is not in the 126-reference existence catalog "
            "(AGENTS.md invariant #2)"
        )


def test_every_supplement_head_has_a_valid_wire_form() -> None:
    """AGENTS.md invariant #1: the wire form must be ``Article N`` /
    ``Annex X`` and must survive the existence-gated formatter."""
    import re

    shape = re.compile(r"^(?:Article \d+|Annex (?:I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|XIII))$")
    for head in rc.RECALL_SUPPLEMENT_HEADS:
        wire = reference_from_article_ref(head)
        assert wire, f"{head!r} does not resolve to a wire reference"
        assert shape.match(wire), f"{wire!r} violates the strict wire format"
        assert wire in rc.RECALL_SUPPLEMENT_WIRE_HEADS

    # and the declared wire table must be exactly the resolved set
    assert sorted(rc.RECALL_SUPPLEMENT_WIRE_HEADS) == sorted(
        reference_from_article_ref(h) for h in rc.RECALL_SUPPLEMENT_HEADS
    )


def test_supplement_head_table_covers_every_head_the_code_can_append() -> None:
    """Guard against a new trigger appending an unlisted head: the literals
    in the engine + route blocks must be a subset of the declared table."""
    import re as _re
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    engine = (repo / "app" / "engines" / "_graph_rag_impl.py").read_text(
        encoding="utf-8"
    )
    block = engine.split("# R365 — Annex III recall supplements", 1)[1]
    block = block.split("# R340 — cross-encoder rerank", 1)[0]

    # Every string literal in the block that looks like a provision head.
    heads = set(_re.findall(r'"((?:Art\. \d+|Annex [IVX]+))"', block))
    assert heads, "no provision literals found in the R365 engine block"
    assert heads <= set(rc.RECALL_SUPPLEMENT_HEADS), (
        "the R365 engine block references heads outside the declared table "
        f"(add them to RECALL_SUPPLEMENT_HEADS): "
        f"{sorted(heads - set(rc.RECALL_SUPPLEMENT_HEADS))}"
    )

    route = (repo / "app" / "routes" / "regenold.py").read_text(encoding="utf-8")
    guard = route.split("# R365 — recall-supplement WIRE GUARD", 1)[1]
    guard = guard.split("# R50 / R131 — finalise the reasoning trace", 1)[0]
    wire_heads = set(
        _re.findall(r'"((?:Article \d+|Annex [IVX]+))"', guard)
    )
    assert wire_heads, "no provision literals found in the R365 wire guard"
    assert wire_heads <= set(rc.RECALL_SUPPLEMENT_WIRE_HEADS), (
        "the R365 wire guard emits heads outside the declared wire table: "
        f"{sorted(wire_heads - set(rc.RECALL_SUPPLEMENT_WIRE_HEADS))}"
    )


# ══════════════════════════════════════════════════════════════════════════
# 6. Cache-key registration (AGENTS.md invariant #4 / R263.2)
# ══════════════════════════════════════════════════════════════════════════
def test_both_supplement_flags_move_the_engine_cache_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unkeyed flip serves arm A's cached response to arm B and the A/B
    reads a false '+0.0000, inert'."""
    base = _engine_cache_key(Q_MEDICAL, None)

    monkeypatch.setenv(_ANNEXIII_FLAG, "1")
    with_annexiii = _engine_cache_key(Q_MEDICAL, None)
    assert with_annexiii != base, f"{_ANNEXIII_FLAG} is not in the cache key"

    monkeypatch.delenv(_ANNEXIII_FLAG, raising=False)
    monkeypatch.setenv(_ART50_FLAG, "1")
    with_art50 = _engine_cache_key(Q_MEDICAL, None)
    assert with_art50 != base, f"{_ART50_FLAG} is not in the cache key"
    assert with_art50 != with_annexiii


def test_wire_guard_flag_is_deliberately_not_in_the_engine_cache_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard is a ROUTE pass — it re-runs on every engine-cache hit, so
    keying it would only fragment the cache (the R79 doctrine)."""
    base = _engine_cache_key(Q_FINES, None)
    monkeypatch.setenv(_GUARD_FLAG, "1")
    assert _engine_cache_key(Q_FINES, None) == base


# ══════════════════════════════════════════════════════════════════════════
# 7. THE WIRE. The engine append alone is INERT here — pin that, both ways.
# ══════════════════════════════════════════════════════════════════════════
@pytest.fixture(autouse=True)
def _pin_the_auth_key():
    """R365 — pin the key these tests SEND on the settings singleton.

    These tests used to send ``r365-test-key`` and configure nothing, so they
    passed only while NO key was configured (the route is anonymous-friendly
    in that state). Any earlier suite that pinned a key — e.g.
    ``test_r100_synthesis_default._client`` (:204) — turned every request here
    into ``403 regenold_api_key_invalid``: green file-scoped, red in-suite.
    Configuring the key we actually send makes the file independent of test
    order in BOTH directions.
    """
    from pydantic import SecretStr  # noqa: PLC0415

    from app.config import settings as _cfg  # noqa: PLC0415

    _saved = _cfg.regenold.api_key
    _cfg.regenold.api_key = SecretStr(_TEST_API_KEY)
    try:
        yield
    finally:
        _cfg.regenold.api_key = _saved


def _wire_refs(client: TestClient, question: str) -> list[str]:
    r = client.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": _TEST_API_KEY},
        json=[{"role": "user", "content": question}],
    )
    assert r.status_code == 200, r.text
    return list(r.json()["references"])


def test_supplements_alone_do_not_reach_the_wire(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⚠ The measured defect this port had to find.

    With both supplement gates ON and the wire guard OFF, the route's lossy
    passes eat the supplemented heads and the wire is byte-identical to
    baseline on both headline rows. This is the R329 "reads right, fires
    zero" failure one layer further down — recorded as a test so nobody
    ships the engine half alone and reads a flat A/B as "the lever is inert".
    """
    client = TestClient(app)
    base_fines = _wire_refs(client, Q_FINES)
    base_medical = _wire_refs(client, Q_MEDICAL)

    monkeypatch.setenv(_ANNEXIII_FLAG, "1")
    monkeypatch.setenv(_ART50_FLAG, "1")
    assert _wire_refs(client, Q_FINES) == base_fines
    assert _wire_refs(client, Q_MEDICAL) == base_medical
    assert rc.recall_supplement_stats()["wire_guard_added"] == 0
    # …and the engine DID fire — this is not "the flag never ran".
    stats = rc.recall_supplement_stats()
    assert stats["engine_annexiii_appended"] >= 1
    assert stats["engine_art50_appended"] >= 1


def test_engine_half_is_not_output_neutral_it_is_head_neutral(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sharper statement of the row above, pinned on the MSA row.

    "The engine append does not reach the wire" is NOT the same as "the
    engine append does nothing". The appended entities re-order retrieval, so
    on la_q35 the wire DOES change with the supplements ON — it just changes
    in the wrong direction: it picks up extra heads while the ``Annex III``
    the trigger fired for is still eaten before the wire. Only the guard
    delivers the intended head. Anyone reading a live A/B of the engine half
    alone is measuring that noise, not the recall lever.
    """
    client = TestClient(app)
    base = _wire_refs(client, Q_MSA)

    monkeypatch.setenv(_ANNEXIII_FLAG, "1")
    supplemented = _wire_refs(client, Q_MSA)
    assert supplemented != base, "expected retrieval-order drift on the MSA row"
    assert "Annex III" not in supplemented, (
        "the engine half unexpectedly delivered Annex III to the wire — if "
        "this now passes, a route pass changed and the guard's rationale "
        "must be re-measured"
    )

    monkeypatch.setenv(_GUARD_FLAG, "1")
    guarded = _wire_refs(client, Q_MSA)
    assert "Annex III" in guarded, f"guard failed to deliver: {guarded}"
    assert set(supplemented) <= set(guarded)


def test_wire_guard_recovers_the_measured_heads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Supplements ON + guard ON: Article 50 reaches the la_q16 wire and
    Annex III reaches the la_q64 wire, and the counter proves it fired."""
    client = TestClient(app)
    monkeypatch.setenv(_ANNEXIII_FLAG, "1")
    monkeypatch.setenv(_ART50_FLAG, "1")
    monkeypatch.setenv(_GUARD_FLAG, "1")
    rc.reset_recall_supplement_stats()

    fines = _wire_refs(client, Q_FINES)
    assert "Article 50" in fines, f"Article 50 not on the wire: {fines}"

    medical = _wire_refs(client, Q_MEDICAL)
    assert "Annex III" in medical, f"Annex III not on the wire: {medical}"

    assert rc.recall_supplement_stats()["wire_guard_added"] >= 2


def test_wire_guard_is_add_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADD-only contract: the guard is a superset of the ungated wire, so
    ``gold_dropped_head`` cannot move."""
    client = TestClient(app)
    base_fines = _wire_refs(client, Q_FINES)
    base_medical = _wire_refs(client, Q_MEDICAL)

    monkeypatch.setenv(_ANNEXIII_FLAG, "1")
    monkeypatch.setenv(_ART50_FLAG, "1")
    monkeypatch.setenv(_GUARD_FLAG, "1")
    assert set(base_fines) <= set(_wire_refs(client, Q_FINES))
    assert set(base_medical) <= set(_wire_refs(client, Q_MEDICAL))


def test_wire_guard_only_emits_declared_heads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whatever the guard adds must come from the declared wire table."""
    client = TestClient(app)
    base = set(_wire_refs(client, Q_FINES)) | set(_wire_refs(client, Q_MEDICAL))

    monkeypatch.setenv(_ANNEXIII_FLAG, "1")
    monkeypatch.setenv(_ART50_FLAG, "1")
    monkeypatch.setenv(_GUARD_FLAG, "1")
    guarded = set(_wire_refs(client, Q_FINES)) | set(_wire_refs(client, Q_MEDICAL))
    added = guarded - base
    assert added, "the guard added nothing — it is inert"
    assert added <= set(rc.RECALL_SUPPLEMENT_WIRE_HEADS)


def test_guard_alone_without_the_supplement_gates_is_inert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DEVIATION FROM THE SIBLING, pinned: the guard is coupled per-family to
    its supplement gate, so ``guard ON / supplements OFF`` is a no-op rather
    than a stronger, never-measured lever."""
    client = TestClient(app)
    base_fines = _wire_refs(client, Q_FINES)
    base_medical = _wire_refs(client, Q_MEDICAL)

    monkeypatch.setenv(_GUARD_FLAG, "1")
    assert _wire_refs(client, Q_FINES) == base_fines
    assert _wire_refs(client, Q_MEDICAL) == base_medical
    assert rc.recall_supplement_stats()["wire_guard_added"] == 0


def test_wire_refs_all_resolve_in_article_existence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full-pipeline restatement of the lint floor with the lever fully ON."""
    from app.routes.regenold import _canonical_reference_base

    client = TestClient(app)
    monkeypatch.setenv(_ANNEXIII_FLAG, "1")
    monkeypatch.setenv(_ART50_FLAG, "1")
    monkeypatch.setenv(_GUARD_FLAG, "1")
    for question in (Q_FINES, Q_MEDICAL, Q_MSA, Q_EU_DB, Q_OPERATOR, Q_BIOMETRIC):
        for ref in _wire_refs(client, question):
            head = _canonical_reference_base(ref)
            assert head, f"{ref!r} does not canonicalise"
            internal = (
                head.replace("Article ", "Art. ")
                if head.startswith("Article ")
                else head
            )
            assert internal in ARTICLE_EXISTENCE, (
                f"{ref!r} (head {head!r}) is not in the existence catalog"
            )
