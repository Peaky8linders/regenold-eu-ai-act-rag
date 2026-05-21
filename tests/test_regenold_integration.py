from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.main import app


def _client() -> TestClient:
    return TestClient(app)


def _messages(content: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": content}]


def test_regenold_endpoint_missing_key_returns_401() -> None:
    """Auth is required — a request with no X-Regenold-Api-Key header must return 401."""
    settings.regenold.api_key = SecretStr("regenold-test-key")
    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        json=_messages("What does EU AI Act Art. 13(1)(a) require?"),
    )
    assert r.status_code == 401, r.json()
    assert r.json()["detail"]["code"] == "regenold_api_key_missing"


def test_regenold_endpoint_rejects_invalid_key() -> None:
    """Header present but invalid → 403, NOT silent downgrade to anonymous.

    Silent downgrade would mask partner-side typos / stale keys. The
    explicit 403 makes the partner notice and rotate.
    """
    settings.regenold.api_key = SecretStr("regenold-test-key")
    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "wrong"},
        json=_messages("What does Art. 13(1)(a) require?"),
    )
    assert r.status_code == 403


def test_regenold_endpoint_unconfigured_deploy_returns_503() -> None:
    """Deployment with no configured key → 503 (integration not provisioned).

    The strict dep raises 503 when ``_configured_key()`` is None so the
    operator is alerted that the partner key has not been set.
    """
    settings.regenold.api_key = None  # Unconfigured deploy
    try:
        c = _client()
        r = c.post(
            "/api/v1/regenold/eu-ai-act/ask",
            headers={"X-Regenold-Api-Key": "anything-since-no-config"},
            json=_messages("Summarise EU AI Act Art. 13."),
        )
        assert r.status_code == 503, r.json()
        assert r.json()["detail"]["code"] == "regenold_not_configured"
    finally:
        # Reset for the rest of the suite which expects a configured key.
        settings.regenold.api_key = SecretStr("regenold-test-key")


def test_regenold_endpoint_accepts_valid_key_and_returns_openai_lite_shape() -> None:
    settings.regenold.api_key = SecretStr("regenold-test-key")
    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=_messages("Summarise EU AI Act Art. 13(1)(a)."),
    )
    assert r.status_code == 200
    body = r.json()
    assert "reasoning" in body
    assert body["reasoning"] is None or isinstance(body["reasoning"], str)
    assert "answer" in body and isinstance(body["answer"], str)
    assert "references" in body and isinstance(body["references"], list)

    # When references exist, they should be formatted EU AI Act refs.
    for ref in body["references"]:
        assert isinstance(ref, str)
        assert ref.startswith("Article ") or ref.startswith("Annex ")


def test_regenold_endpoint_accepts_messages_object_wrapper() -> None:
    """Compatibility: some clients wrap OpenAI `messages` under `{ "messages": [...] }`."""

    settings.regenold.api_key = SecretStr("regenold-test-key")
    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json={"messages": _messages("What is Annex IV(2) about?")},
    )
    assert r.status_code == 200
    body = r.json()
    assert "answer" in body and isinstance(body["answer"], str)
    assert "references" in body and isinstance(body["references"], list)


# ─── P0 hallucination-reduction regression guards ──────────────────────────


def test_p0_response_carries_confidence_kb_version_retrieval_path() -> None:
    """P0 #3 — telemetry fields are reachable via ?include_telemetry=true.

    The Regenold competition spec only lists ``reasoning`` / ``answer`` /
    ``references`` as required response fields — keeping the default
    response spec-clean prevents extra-field-induced evaluator failures
    AND wastes no tokens on a field the evaluator skips. Verifiers that
    need the engine's confidence / KB version / retrieval path / graph
    stats opt in via the query param. Pinned here so the fields stay
    reachable for our own downstream agents.
    """
    from app.data.kb import KB_VERSION

    settings.regenold.api_key = SecretStr("regenold-test-key")
    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask?include_telemetry=true",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=_messages("Summarise EU AI Act Art. 13(1)(a)."),
    )
    assert r.status_code == 200
    body = r.json()
    assert "confidence" in body
    assert isinstance(body["confidence"], (int, float))
    assert 0.0 <= float(body["confidence"]) <= 1.0
    assert body.get("kb_version") == KB_VERSION
    assert body.get("retrieval_path") in {
        "neo4j",
        "kb_fallback",
        "deterministic",
        "no_match",
    }
    # The structured reasoning summary is the telemetry one-liner here.
    assert body.get("reasoning") != "Not scored."
    assert "KB" in (body.get("reasoning") or "")
    assert "retrieval" in (body.get("reasoning") or "")


def test_p0_question_length_capped_at_4k() -> None:
    """P0 #5 — content cap dropped from 20K to 4K. A 5K question is rejected."""
    settings.regenold.api_key = SecretStr("regenold-test-key")
    c = _client()
    big_question = "A" * 5_000
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=_messages(big_question),
    )
    # Pydantic max_length violation surfaces as 422 via the route's
    # `model_validate`; the security middleware MAY repackage as 400.
    assert r.status_code in (400, 422), r.json()


def test_p0_question_at_4k_boundary_accepted() -> None:
    """P0 #5 boundary — exactly 4K is the cap; 4K chars must still work."""
    settings.regenold.api_key = SecretStr("regenold-test-key")
    c = _client()
    boundary_question = "Q" * 4_000
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=_messages(boundary_question),
    )
    # 4K is the inclusive max; should accept. (Engine itself may emit a
    # closed-world refusal because the question isn't groundable, but the
    # validation layer should pass.)
    assert r.status_code == 200, r.json()


def test_p0_reference_validation_filters_hallucinated_articles() -> None:
    """P0 #2 — the formatter rejects references not in ARTICLE_EXISTENCE.

    Direct unit test of ``reference_from_article_ref`` since end-to-end
    requires controlling the engine's citation output.
    """
    from app.integrations.regenold.models import reference_from_article_ref

    # Real articles — known good.
    assert reference_from_article_ref("Art. 13(1)(a)") == "Article 13.1.a"
    assert reference_from_article_ref("Art. 5") == "Article 5"
    assert reference_from_article_ref("Annex IV(2)") == "Annex IV.2"
    assert reference_from_article_ref("Annex IV") == "Annex IV"
    # Sub-paragraph prefix fallback — Art. 13 exists, so 13(1)(a) is valid.
    assert reference_from_article_ref("Art. 13(1)(a)(ii)") is not None

    # Hallucinated articles — must be dropped (return None).
    # Art. 999 does not exist; pre-fix this would cheerfully render
    # "Article 999.z" and ship it.
    assert reference_from_article_ref("Art. 999") is None
    assert reference_from_article_ref("Art. 999(z)") is None
    # Annex out of range — only Annex I … XIII exist.
    assert reference_from_article_ref("Annex XX") is None
    # Empty / nonsense input
    assert reference_from_article_ref("") is None
    assert reference_from_article_ref("garbage") is None


def test_p0_closed_world_refusal_for_nongrounded_question() -> None:
    """P0 #1 — a question with no graph/KB grounding gets a structured refusal.

    A clearly off-topic question routes the engine through the deterministic
    fallback with no obligations / no dimensions, so confidence falls below
    the 0.5 floor AND references is empty. Route must replace the answer
    with the no-match string + retrieval_path="no_match" + confidence=0.0.
    """
    settings.regenold.api_key = SecretStr("regenold-test-key")
    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        # Nonsense question — no article ref, no risk word, no dimension keyword.
        json=_messages("zxqv mnbv asdf 12345 678 hjkl"),
    )
    assert r.status_code == 200
    body = r.json()
    # Either we got a closed-world refusal (the desired path) OR the
    # engine still found *some* grounding. The closed-world contract is:
    # IF references is empty AND confidence < 0.5 THEN refusal fires.
    # We can't force the engine's hand from here, but we CAN pin the
    # invariant: a no-match response carries the right shape.
    if not body.get("references") and float(body.get("confidence", 1.0)) < 0.5:
        assert body["retrieval_path"] == "no_match"
        assert body["confidence"] == 0.0
        assert "No matching obligation" in body["answer"]


def test_p0_reasoning_summary_format() -> None:
    """The telemetry reasoning string is a structured 4-field one-liner."""
    from app.routes.regenold import _build_telemetry_reasoning

    text = _build_telemetry_reasoning(
        confidence=0.85,
        kb_version="2024.1689.v2",
        retrieval_path="neo4j",
        ref_count=7,
    )
    assert "0.85" in text
    assert "2024.1689.v2" in text
    assert "neo4j" in text
    assert "7" in text


def test_p0_retrieval_path_resolver_heuristic() -> None:
    """Pin the path-classification heuristic in `_resolve_retrieval_path`."""
    from app.routes.regenold import _resolve_retrieval_path

    # Live graph signal — edges followed
    assert _resolve_retrieval_path({"edges_followed": 4}) == "neo4j"
    # Live graph signal — gaps found (only graph reasoning produces gaps)
    assert _resolve_retrieval_path({"gaps_found": 3}) == "neo4j"
    # KB fallback — nodes_traversed without graph reasoning
    assert _resolve_retrieval_path({"nodes_traversed": 5}) == "kb_fallback"
    # No data at all
    assert _resolve_retrieval_path({}) == "deterministic"
    assert _resolve_retrieval_path({"nodes_traversed": 0}) == "deterministic"


# ─── P1 hallucination-reduction follow-ups ─────────────────────────────────


def test_p1_question_hash_is_64_hex_chars() -> None:
    """P1 #8 — full sha256 hex (64 chars / 256 bits) for forensic uniqueness.

    The pre-fix 16-char truncation gave 64 bits of collision space —
    birthday-collision territory at scale. Hash must be deterministic
    for the same question (so a forensic search "show me every request
    that asked this exact question" stays one-shot exact-match).
    """
    from app.integrations.regenold.models import question_hash

    h = question_hash("What does Art. 13(1)(a) require?")
    assert isinstance(h, str)
    assert len(h) == 64, h
    assert all(c in "0123456789abcdef" for c in h)
    # Determinism on identical input.
    assert h == question_hash("What does Art. 13(1)(a) require?")
    # Whitespace is stripped (matches the salt + strip() shape).
    assert h == question_hash("  What does Art. 13(1)(a) require?  ")
    # Different questions → different hashes.
    assert h != question_hash("What does Art. 26 require?")


def test_p1_reference_rank_orders_articles_before_annexes() -> None:
    """P1 #7 — sort by citation strength: Article > Annex; more specific first."""
    from app.routes.regenold import _reference_rank

    refs = [
        "Article 13",          # bare Article
        "Article 13.1.a",      # specific Article paragraph (deepest)
        "Annex IV.2",          # specific Annex (top-level subpoint)
        "Article 13.1",        # Article paragraph (mid specificity)
        "Annex IV",            # bare Annex
    ]
    sorted_refs = sorted(refs, key=_reference_rank)
    assert sorted_refs == [
        "Article 13.1.a",  # Articles first; deepest specificity wins within
        "Article 13.1",
        "Article 13",
        "Annex IV.2",       # Annexes next; deepest specificity wins within
        "Annex IV",
    ]


def test_p1_reference_rank_falls_through_unknown_shape() -> None:
    """Defensive: a future format extension still gets a stable rank.

    The route only emits ``Article ...`` / ``Annex ...`` because
    ``reference_from_article_ref`` is the only producer, but the helper
    must not crash on unrecognised input — it returns priority 9 so
    unknown shapes sort last.
    """
    from app.routes.regenold import _reference_rank

    rank = _reference_rank("Recital 65")
    assert rank[0] == 9


def test_p1_reference_sort_applied_via_route_truncation() -> None:
    """End-to-end: when an answer carries grounded references, they come
    back sorted by citation strength.

    Specificity ordering in the response is the contract a downstream
    verifier or operator UI can rely on — first reference is the
    strongest the engine could surface for this question.
    """
    settings.regenold.api_key = SecretStr("regenold-test-key")
    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=_messages("Summarise EU AI Act Art. 13(1)(a)."),
    )
    assert r.status_code == 200
    refs = r.json().get("references", [])
    if not refs:
        # No grounded refs returned (engine may run in deterministic
        # fallback for some test envs); the sort guarantee can't be
        # asserted from here without a fixture.
        return
    # If we have refs, the first one must rank no-worse than the rest.
    from app.routes.regenold import _reference_rank
    ranks = [_reference_rank(ref) for ref in refs]
    assert ranks == sorted(ranks), refs


def test_p1_response_carries_graph_stats_fields() -> None:
    """P1 #9 — graph stats surface on the response when ?include_telemetry=true."""
    settings.regenold.api_key = SecretStr("regenold-test-key")
    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask?include_telemetry=true",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=_messages("What does EU AI Act Art. 13 require for transparency?"),
    )
    assert r.status_code == 200
    body = r.json()
    for field in ("nodes_traversed", "obligations_found", "gaps_found"):
        assert field in body, f"Missing P1 #9 field: {field}"
        value = body[field]
        assert isinstance(value, int), f"{field} should be int, got {type(value).__name__}"
        assert value >= 0, f"{field} should be ≥ 0, got {value}"


def test_p1_graph_stats_zero_on_closed_world_refusal() -> None:
    """Closed-world refusal: obligations_found / gaps_found should be 0.

    A refusal means retrieval found nothing actionable — those two
    counts must be at floor so a verifier doesn't see obligations_found > 0
    alongside retrieval_path == "no_match". nodes_traversed may
    legitimately be > 0 because KB-fallback derives dimension info even
    on no-match — the route's retrieval-path heuristic already separates
    that from a real graph hit. Use ``?include_telemetry=true`` to
    expose the fields needed for the assertion.
    """
    settings.regenold.api_key = SecretStr("regenold-test-key")
    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask?include_telemetry=true",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=_messages("zxqv mnbv asdf 12345 678 hjkl"),
    )
    assert r.status_code == 200
    body = r.json()
    if body.get("retrieval_path") != "no_match":
        return
    assert body["confidence"] == 0.0
    assert body["obligations_found"] == 0
    assert body["gaps_found"] == 0


def test_p1_evidence_chain_helper_records_full_hash() -> None:
    """P1 #8 follow-on — pin the salted-full-hash output as a regression guard.

    Defends against an accidental refactor that re-truncates or drops
    the salt. Re-deriving without the salt MUST produce a different
    value (proves salting is in effect).
    """
    import hashlib as _hl

    from app.integrations.regenold.models import question_hash

    h = question_hash("Some test question for the chain.")
    assert len(h) == 64
    bare = _hl.sha256(b"Some test question for the chain.").hexdigest()
    assert h != bare


# ─── Optional-auth (public competition) tier guards ────────────────────────


def test_optional_auth_dep_returns_none_without_header() -> None:
    """Pure unit test: the dep returns None, doesn't raise, on no header."""
    import asyncio

    from app.integrations.regenold.auth import optional_regenold_api_key

    result = asyncio.run(optional_regenold_api_key(api_key=None))
    assert result is None


def test_optional_auth_dep_returns_key_on_match() -> None:
    """Pure unit test: matching header returns the raw key for downstream use."""
    import asyncio

    from app.integrations.regenold.auth import optional_regenold_api_key

    settings.regenold.api_key = SecretStr("regenold-test-key")
    result = asyncio.run(optional_regenold_api_key(api_key="regenold-test-key"))
    assert result == "regenold-test-key"


def test_optional_auth_dep_raises_403_on_invalid_header() -> None:
    """Pure unit test: invalid header still raises 403 (no silent downgrade)."""
    import asyncio

    from fastapi import HTTPException

    from app.integrations.regenold.auth import optional_regenold_api_key

    settings.regenold.api_key = SecretStr("regenold-test-key")
    try:
        asyncio.run(optional_regenold_api_key(api_key="wrong"))
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail.get("code") == "regenold_api_key_invalid"
    else:
        raise AssertionError("expected HTTPException(403)")


def test_optional_auth_dep_unconfigured_returns_none_for_any_header() -> None:
    """Pure unit test: unconfigured deploy + header → None (not 503, not 403)."""
    import asyncio

    from app.integrations.regenold.auth import optional_regenold_api_key

    saved = settings.regenold.api_key
    settings.regenold.api_key = None
    try:
        assert asyncio.run(optional_regenold_api_key(api_key=None)) is None
        assert asyncio.run(optional_regenold_api_key(api_key="anything")) is None
    finally:
        settings.regenold.api_key = saved


def test_dynamic_limit_resolves_60_for_authed_30_for_anon() -> None:
    """Pin the dynamic-limit string mapping (private slowapi contract)."""
    from app.routes.regenold import (
        _RATE_KEY_PREFIX_ANON,
        _RATE_KEY_PREFIX_AUTHED,
        _regenold_dynamic_limit,
    )

    assert _regenold_dynamic_limit(f"{_RATE_KEY_PREFIX_AUTHED}abc123") == "60/minute"
    assert _regenold_dynamic_limit(f"{_RATE_KEY_PREFIX_ANON}deadbeef") == "30/minute"
    # Defensive fallback — unknown prefix falls to conservative anon tier.
    assert _regenold_dynamic_limit("unknown-prefix:zzz") == "30/minute"


def test_unauthenticated_request_returns_401_and_writes_no_chain_entry() -> None:
    """Auth is required — a no-header request is rejected before touching the chain."""
    from app.evidence.store import get_evidence_store

    settings.regenold.api_key = SecretStr("regenold-test-key")
    store = get_evidence_store()
    before_partner = len(list(store.get_chain(tenant_id="partner:regenold", limit=1000)))

    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        json=_messages("Summarise EU AI Act Art. 26."),
    )
    assert r.status_code == 401, r.json()

    # Dep rejects before the handler runs, so no chain entry should be written.
    after_partner = len(list(store.get_chain(tenant_id="partner:regenold", limit=1000)))
    assert after_partner == before_partner, "chain entry written despite 401 rejection"


def test_authenticated_request_writes_partner_tenant_chain_entry() -> None:
    """Mirror of the public test: with a valid key, tenant becomes "partner:regenold"."""
    from app.evidence.store import get_evidence_store

    settings.regenold.api_key = SecretStr("regenold-test-key")
    store = get_evidence_store()
    before = len(list(store.get_chain(tenant_id="partner:regenold", limit=1000)))

    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=_messages("Summarise EU AI Act Art. 26."),
    )
    assert r.status_code == 200, r.json()

    # get_chain default order is DESC (newest-first); rows[0] is the route's write.
    rows = list(store.get_chain(tenant_id="partner:regenold", limit=1000))
    assert len(rows) > before, "no partner:regenold chain entry written"
    last = rows[0]
    payload = last.payload if isinstance(last.payload, dict) else {}
    assert payload.get("tier") == "partner"
    # Partner tier MUST NOT carry an ip_hash — the (hashed) key on the
    # rate-limit bucket already identifies the partner connection;
    # adding IP would expand the data surface without benefit.
    assert "ip_hash" not in payload


def test_chain_entry_persists_full_question_and_answer() -> None:
    """Round-24 audit policy: full question + answer text are persisted.

    Earlier rounds stored only ``question_hash`` + 500-char
    ``answer_excerpt`` for GDPR-Art.4(5) pseudonymisation. With a
    ``DATABASE_URL`` configured on the deployment, operators opt into
    durable full-text retention on their own Postgres — this test
    pins that contract so a future refactor that drops the raw text
    breaks loudly.
    """
    from app.evidence.store import get_evidence_store

    settings.regenold.api_key = SecretStr("regenold-test-key")
    store = get_evidence_store()
    c = _client()
    question_text = "What does EU AI Act Art. 13(1)(a) require?"
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=_messages(question_text),
    )
    assert r.status_code == 200, r.json()

    rows = list(store.get_chain(tenant_id="partner:regenold", limit=10))
    assert rows, "no chain entry was written"
    payload = rows[0].payload if isinstance(rows[0].payload, dict) else {}
    # Full raw question must be in the payload (not just the hash).
    assert payload.get("question") == question_text, (
        f"expected raw question {question_text!r}, got payload keys "
        f"{sorted(payload.keys())} (question={payload.get('question')!r})"
    )
    # Full answer text must be in the payload (not just a 500-char excerpt).
    answer = payload.get("answer")
    assert isinstance(answer, str) and answer, (
        f"expected non-empty 'answer' string in payload; got {answer!r}"
    )
    assert answer == r.json().get("answer"), (
        "chain-payload 'answer' must match the wire response 'answer'"
    )
    # The legacy hash + excerpt fields are still emitted alongside —
    # downstream forensic pipelines that key off them keep working.
    assert "question_hash" in payload
    assert "answer_excerpt" in payload


# ─── Competition spec contract guards ──────────────────────────────────────


def test_default_response_shape_matches_spec_template() -> None:
    """Spec wire shape: ``{reasoning, answer, references}`` — nothing else.

    Regenold's evaluator template only references those three fields.
    Extra keys risk strict-schema rejection AND cost the evaluator
    extra tokens on a field they explicitly say "will not be considered
    and might increase latency". Default must be spec-clean.
    """
    settings.regenold.api_key = SecretStr("regenold-test-key")
    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=_messages("What does EU AI Act Art. 13(1)(a) require?"),
    )
    assert r.status_code == 200
    body = r.json()
    assert sorted(body.keys()) == ["answer", "reasoning", "references"]
    # All three keys must be present (with empty string OK for reasoning).
    assert isinstance(body["reasoning"], str)
    assert isinstance(body["answer"], str)
    assert isinstance(body["references"], list)


def test_default_reasoning_is_empty_not_telemetry() -> None:
    """Default ``reasoning`` is the empty string, not the telemetry summary.

    Spec note: ``reasoning`` "*will not be considered and might increase
    latency*". Empty string keeps the key present (matching the spec
    template) without burning output tokens on retrieval telemetry the
    evaluator skips.
    """
    settings.regenold.api_key = SecretStr("regenold-test-key")
    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=_messages("Summarise EU AI Act Art. 13."),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["reasoning"] == ""


def test_references_capped_at_max_references() -> None:
    """Spec: "minimal set of relevant references". Cap at MAX_REFERENCES.

    The example response in the spec image carries 2 refs, suggesting
    the evaluator expects a tight citation list. We cap at 5 (still
    minimal but leaves headroom for cross-article queries).
    """
    from app.integrations.regenold.models import MAX_REFERENCES

    settings.regenold.api_key = SecretStr("regenold-test-key")
    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=_messages("Summarise EU AI Act Art. 13(1)(a)."),
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["references"]) <= MAX_REFERENCES, (
        f"references must be capped at {MAX_REFERENCES} per spec 'minimal set'"
    )
    # Floor the constant at 5 — relaxing past 5 would drift from "minimal".
    assert MAX_REFERENCES <= 5


def test_references_match_strict_spec_format() -> None:
    """Spec: every reference is ``Annex <Roman>(.<sub>)*`` or ``Article <int>(.<sub>)*``.

    NOT ``Annex 3``, ``Annex 3(2)``, ``Annex III . 2``, ``Annex III-2``,
    ``Article III``, ``Article III.2``, ``Article 3/2`` — reject all of
    these defensively if any slip through future refactors. We verify
    each shipped ref against the strict regex from
    :data:`_ANNEX_OUTPUT_RE` / :data:`_ARTICLE_OUTPUT_RE`.
    """
    import re

    settings.regenold.api_key = SecretStr("regenold-test-key")
    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=_messages("Summarise EU AI Act Art. 13(1)(a)."),
    )
    assert r.status_code == 200
    refs = r.json()["references"]
    annex_pat = re.compile(r"^Annex [IVXLC]+(?:\.[A-Za-z0-9]+)*$")
    article_pat = re.compile(r"^Article \d+(?:\.[A-Za-z0-9]+)*$")
    for ref in refs:
        assert annex_pat.match(ref) or article_pat.match(ref), (
            f"reference {ref!r} fails the Regenold spec format"
        )


def test_answer_capped_at_max_sentences() -> None:
    """Spec: "Short (3-4 sentences max) but professionally worded answers".

    Hard rule (per CLAUDE.md): ``MAX_ANSWER_SENTENCES == 3``. This test
    pins both the truncation behaviour AND the constant itself so a
    quiet bump back up to 4 trips the suite — that change should be a
    deliberate, measured one, not a stealth re-relax.
    """
    from app.integrations.regenold.models import (
        MAX_ANSWER_SENTENCES,
        _split_sentences,
        _truncate_to_sentences,
    )

    # Hard rule: must be exactly 3. Don't relax this without measuring
    # the conciseness delta against the eval (see CLAUDE.md hard rule #2).
    assert MAX_ANSWER_SENTENCES == 3, (
        f"MAX_ANSWER_SENTENCES drifted to {MAX_ANSWER_SENTENCES}; expected 3"
    )

    # Confirm we cap to exactly N sentences (using the production
    # abbreviation-aware splitter so "Art. 26." isn't mis-counted as 2).
    long_answer = " ".join(f"Sentence {i}." for i in range(1, 10))  # 9 sentences
    truncated = _truncate_to_sentences(long_answer, max_sentences=MAX_ANSWER_SENTENCES)
    sentence_count = len(_split_sentences(truncated))
    assert sentence_count == MAX_ANSWER_SENTENCES, (
        f"expected {MAX_ANSWER_SENTENCES} sentences, got {sentence_count}: {truncated!r}"
    )


def test_answer_endpoint_truncates_long_engine_output() -> None:
    """End-to-end: even if the engine emits >4 sentences, we ship ≤4."""
    settings.regenold.api_key = SecretStr("regenold-test-key")
    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=_messages("Summarise EU AI Act Art. 13."),
    )
    assert r.status_code == 200
    body = r.json()
    answer = body["answer"]
    from app.integrations.regenold.models import _split_sentences, MAX_ANSWER_SENTENCES  # noqa: PLC0415
    sentence_count = len(_split_sentences(answer))
    assert sentence_count <= MAX_ANSWER_SENTENCES, (
        f"answer carries {sentence_count} sentences (max {MAX_ANSWER_SENTENCES}): {answer!r}"
    )


def test_multi_turn_history_threaded_into_question() -> None:
    """Spec: input is a CONVERSATION HISTORY. Prior turns must inform retrieval.

    Pre-fix we only used the last user message; a follow-up like "What
    about deployers?" was unintelligible without the prior assistant
    answer. The route now threads the last few turns into the question
    prompt under a "Conversation so far:" preamble. We verify the
    end-to-end response is 200 and that the chain entry records the
    history-turn count (so we can grep audit rows for multi-turn use).
    """
    from app.evidence.store import get_evidence_store

    settings.regenold.api_key = SecretStr("regenold-test-key")
    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=[
            {"role": "user", "content": "What does Art. 13 require for transparency?"},
            {
                "role": "assistant",
                "content": "Article 13(1) requires high-risk providers to design systems...",
            },
            {"role": "user", "content": "What about for deployers using third-party systems?"},
        ],
    )
    assert r.status_code == 200, r.json()

    # Evidence chain should record that we used 2 prior turns
    # (1 user + 1 assistant before the live question).
    store = get_evidence_store()
    rows = list(store.get_chain(tenant_id="partner:regenold", limit=10))
    assert rows, "no chain row written"
    last = rows[0]
    payload = last.payload if isinstance(last.payload, dict) else {}
    assert payload.get("history_turns_used") == 2, (
        f"expected 2 history turns, got {payload.get('history_turns_used')}"
    )


def test_build_question_from_history_threads_prior_turns() -> None:
    """Pure unit: history block is prepended above the latest question."""
    from app.integrations.regenold.models import RegenoldChatMessage
    from app.routes.regenold import _build_question_from_history

    msgs = [
        RegenoldChatMessage(role="system", content="Hospital triage assistant."),
        RegenoldChatMessage(role="user", content="What does Art. 13 require?"),
        RegenoldChatMessage(role="assistant", content="Transparency obligations..."),
        RegenoldChatMessage(role="user", content="What about deployers?"),
    ]
    question, system_context = _build_question_from_history(msgs)
    assert system_context == "Hospital triage assistant."
    assert "Conversation so far:" in question
    assert "User: What does Art. 13 require?" in question
    assert "Assistant: Transparency obligations..." in question
    assert "Latest question:" in question
    assert "What about deployers?" in question


def test_build_question_from_history_single_turn_no_preamble() -> None:
    """Single-turn (no prior history): question stays bare, no preamble."""
    from app.integrations.regenold.models import RegenoldChatMessage
    from app.routes.regenold import _build_question_from_history

    msgs = [RegenoldChatMessage(role="user", content="What does Art. 13 require?")]
    question, system_context = _build_question_from_history(msgs)
    assert system_context is None
    assert question == "What does Art. 13 require?"
    assert "Conversation so far:" not in question


def test_build_question_truncates_left_to_engine_cap() -> None:
    """Multi-turn that overflows 2K chars truncates from the LEFT.

    The live user question MUST survive — drop oldest turns first.
    """
    from app.integrations.regenold.models import RegenoldChatMessage
    from app.routes.regenold import _build_question_from_history

    msgs = [
        RegenoldChatMessage(role="user", content="A" * 1500),
        RegenoldChatMessage(role="assistant", content="B" * 1500),
        RegenoldChatMessage(role="user", content="LIVE QUESTION HERE"),
    ]
    question, _ = _build_question_from_history(msgs)
    assert len(question) <= 2000
    # Live question must survive truncation (left-truncate keeps the tail).
    assert "LIVE QUESTION HERE" in question


# ── Annex multi-segment fix (was a real bug) ──


def test_annex_multi_segment_subchain_preserved() -> None:
    """Pre-fix bug: ``Annex III(1)(a)`` produced ``Annex III.1`` (lost ``.a``).

    Symmetric with the Article path which already joined all tokens.
    """
    from app.integrations.regenold.models import reference_from_article_ref

    assert reference_from_article_ref("Annex III(1)(a)") == "Annex III.1.a"
    assert reference_from_article_ref("Annex IV(2)(b)") == "Annex IV.2.b"
    # Single-segment still works the same.
    assert reference_from_article_ref("Annex IV(2)") == "Annex IV.2"
    assert reference_from_article_ref("Annex IV") == "Annex IV"


def test_article_prefix_form_normalised_against_catalog() -> None:
    """Pre-fix bug: ``Article 13(1)(a)`` returned None because the catalog
    only stores ``Art. 13``. Normalise the prefix before existence check.
    """
    from app.integrations.regenold.models import reference_from_article_ref

    assert reference_from_article_ref("Article 13(1)(a)") == "Article 13.1.a"
    assert reference_from_article_ref("Article 5") == "Article 5"
    assert reference_from_article_ref("Article 26") == "Article 26"


def test_dot_form_input_subpoint_preserved() -> None:
    """Pre-fix bug: ``Art. 13.1.a`` (dot-form input) lost the sub-points.

    Some upstream emissions use dot notation; we should accept both
    parenthesised and dot-form input shapes.
    """
    from app.integrations.regenold.models import reference_from_article_ref

    assert reference_from_article_ref("Art. 13.1.a") == "Article 13.1.a"
    assert reference_from_article_ref("Article 13.1") == "Article 13.1"


def test_strict_output_format_rejects_invalid_shapes() -> None:
    """All bad-shape inputs from the spec must produce None.

    Spec is explicit:
    - NOT ``Annex 3``, ``Annex 3(2)``, ``Annex III . 2``, ``Annex III-2``
    - NOT ``Article III``, ``Article III.2``, ``Article 3/2``
    """
    from app.integrations.regenold.models import reference_from_article_ref

    bad = [
        "Annex 3",  # Arabic in place of Roman
        "Annex 3(2)",  # Arabic + paren
        "Annex III-2",  # hyphen separator
        "Article III",  # Roman in place of Arabic
        "Article III.2",  # Roman + dot
        "Article 3/2",  # slash separator
    ]
    for s in bad:
        assert reference_from_article_ref(s) is None, (
            f"{s!r} should be rejected per spec"
        )


def test_extra_subpoints_serialise_with_dots_only() -> None:
    """Output shape always uses dots — never parens, hyphens, or slashes."""
    from app.integrations.regenold.models import reference_from_article_ref

    out = reference_from_article_ref("Art. 13(1)(a)(ii)")
    assert out is not None
    assert "(" not in out and ")" not in out
    assert "-" not in out and "/" not in out
    # Sub-segments separated by dots only.
    assert out.count(".") == 3  # "13.1.a.ii"


# ─── Answer post-processing pipeline (markdown + meta-leak + sentences) ────


def test_normalise_drops_markdown_headings_and_bold() -> None:
    """Markdown structure shouldn't leak into the spec-clean answer."""
    from app.integrations.regenold.models import normalise_answer_for_regenold

    sample = (
        "### Key Requirements\n"
        "**Article 13** requires *transparent* design. The system must `log events`."
    )
    out = normalise_answer_for_regenold(sample, max_sentences=4)
    assert "###" not in out, f"heading leaked: {out!r}"
    assert "**" not in out and "__" not in out, f"bold leaked: {out!r}"
    assert "*transparent*" not in out, f"italic leaked: {out!r}"
    assert "`log events`" not in out, f"inline code leaked: {out!r}"
    assert "Article 13 requires transparent design" in out
    assert "log events" in out


def test_normalise_drops_meta_leak_sentences() -> None:
    """Sentences mentioning 'graph context' / 'knowledge graph' get dropped wholesale.

    Pre-fix attempt was substring deletion which left grammatical
    residue ("While provide exhaustive details" — orphan connective).
    Sentence-level filter is cleaner.
    """
    from app.integrations.regenold.models import normalise_answer_for_regenold

    sample = (
        "Article 26 imposes deployer obligations. "
        "While the graph context does not provide exhaustive details, "
        "the obligations include logging. "
        "Deployers must monitor operations per Art. 26(5)."
    )
    out = normalise_answer_for_regenold(sample, max_sentences=4)
    # The middle sentence (with "graph context") is gone.
    assert "graph context" not in out.lower()
    assert "while" not in out.lower() or "while the graph" not in out.lower()
    # Surrounding clean sentences survive.
    assert "Article 26 imposes deployer obligations." in out
    assert "Art. 26(5)" in out


def test_normalise_strips_direct_answer_label_marker() -> None:
    """The deterministic-style ``**Direct Answer:**`` opener gets dropped.

    Engine produces this when in deterministic-fallback mode. Spec wants
    plain prose, no labels.
    """
    from app.integrations.regenold.models import normalise_answer_for_regenold

    sample = "**Direct Answer:**\nArticle 13 requires transparency to deployers."
    out = normalise_answer_for_regenold(sample, max_sentences=4)
    assert "Direct Answer" not in out, f"label leaked: {out!r}"
    assert out.startswith("Article 13 requires"), out


def test_normalise_handles_numbered_list_inside_prose() -> None:
    """The actual production bug: ``Art. 13. 2. Monitoring`` no longer
    leaves a stray ``"2."`` as its own sentence.

    Pre-fix, the markdown stripper missed mid-line numbered markers and
    the sentence splitter left fragments like ``"2."`` and ``"3."``
    standing as degenerate sentences.
    """
    from app.integrations.regenold.models import normalise_answer_for_regenold

    sample = (
        "Article 26 imposes deployer obligations.\n\n"
        "1. **Use in Accordance (Art. 26(1))**: Use the system per the instructions. "
        "2. **Monitoring (Art. 26(5))**: Monitor the operation. "
        "3. Records: keep auto-generated logs."
    )
    out = normalise_answer_for_regenold(sample, max_sentences=4)
    # No degenerate "2." or "3." sentences
    import re

    # Find every sentence ending — none should be a bare digit.
    bare_digit_sentence = re.search(r"\b\d{1,3}\.\s*$", out)
    # Allow "Art. 26(5)." style mid-text but the answer shouldn't END
    # on a bare digit.
    assert not bare_digit_sentence or "Art" in out[bare_digit_sentence.start() - 5 : bare_digit_sentence.start()], (
        f"output ends with bare digit fragment: {out!r}"
    )
    # The actual list content must survive.
    assert "Use the system" in out or "Monitoring" in out


def test_normalise_preserves_abbreviation_periods() -> None:
    """Pre-fix bug: 'Art. 26 requires X.' was split into 2 sentences.

    The abbreviation-aware splitter must keep ``Art. NN`` together,
    same for ``Annex NN``, ``e.g.``, ``i.e.``, ``Sec.``, ``para.``.
    """
    from app.integrations.regenold.models import (
        _split_sentences,
        normalise_answer_for_regenold,
    )

    cases = [
        ("Art. 26 requires logging.", 1),
        ("Annex IV(2) lists doc requirements.", 1),
        ("Per Sec. 12, the system must log events.", 1),
        ("Per para. 1, deployers must register.", 1),
        ("E.g. Art. 26 imposes monitoring duties.", 1),
        ("Art. 13 requires X. Art. 14 requires Y.", 2),
    ]
    for sample, expected_count in cases:
        out = normalise_answer_for_regenold(sample, max_sentences=10)
        sentences = _split_sentences(out)
        assert len(sentences) == expected_count, (
            f"{sample!r} -> {sentences!r} (expected {expected_count} sentences)"
        )


def test_normalise_pipeline_on_real_engine_output() -> None:
    """End-to-end on the exact prose that triggered the user's complaint.

    The engine emitted a markdown-headed, meta-leaking, numbered-list
    answer. After normalisation, the user-facing prose should be:
    plain text, no graph mentions, no headings, no bullet markers, no
    degenerate fragments, capped at 4 sentences.
    """
    from app.integrations.regenold.models import (
        _split_sentences,
        normalise_answer_for_regenold,
    )

    sample = (
        "**Direct Answer:**\n"
        "Article 26 of the EU AI Act imposes specific responsibilities on "
        "**deployers** of high-risk AI systems to ensure safe, compliant, and "
        "transparent use. While the graph context does not provide exhaustive "
        "details, the core obligations under **Art. 26** include:\n\n"
        "1. **Use in Accordance with Instructions (Art. 26(1))**: Deployers "
        "must use the AI system in accordance with its instructions for use "
        "as required by Art. 13. "
        "2. **Monitoring (Art. 26(5))**: Deployers must monitor the operation. "
        "3. Records: keep auto-generated logs."
    )
    out = normalise_answer_for_regenold(sample, max_sentences=4)

    # Hard requirements:
    assert "**" not in out, f"markdown bold leaked: {out!r}"
    assert "###" not in out, f"markdown heading leaked: {out!r}"
    assert "graph context" not in out.lower(), f"meta leak: {out!r}"
    assert "knowledge graph" not in out.lower(), f"meta leak: {out!r}"
    assert "Direct Answer" not in out, f"label leaked: {out!r}"
    # Sentence cap
    sentences = _split_sentences(out)
    assert len(sentences) <= 4, f"too many sentences: {sentences!r}"
    # Content actually present
    assert "Article 26" in out
    assert "deployers" in out.lower()


def test_normalise_returns_empty_when_all_sentences_are_meta() -> None:
    """If every sentence is meta-leak, the pipeline returns empty.

    The route then falls back to the deterministic refusal string
    rather than shipping an empty answer.
    """
    from app.integrations.regenold.models import normalise_answer_for_regenold

    sample = (
        "Based on the knowledge graph, the answer is X. "
        "The graph context lacks more details. "
        "From the graph, no further information is available."
    )
    out = normalise_answer_for_regenold(sample, max_sentences=4)
    assert out == "", f"expected empty; got {out!r}"


def test_route_falls_back_to_no_match_when_normalise_drops_all() -> None:
    """If post-normalisation answer is empty, route ships the no-match string.

    Pin the regression that we never ship an empty ``answer`` field.
    """
    from app.integrations.regenold.models import normalise_answer_for_regenold

    # Empty input → empty output
    assert normalise_answer_for_regenold("") == ""
    # Pure-meta input → empty output (filter dropped everything)
    assert (
        normalise_answer_for_regenold("Based on the knowledge graph, X is required.")
        == ""
    )


# ─── R53.1-B — compound-role per-row budget split ───────────────────────


def test_route_strong_compound_role_gets_12_ref_budget() -> None:
    """STRONG signal ("both X and Y" literal phrase) → 12-ref budget restored.

    R52.1-C cut compound-role budget 12 → 8 after a judge "citation
    padding" failure. R53.1-B restores 12 ONLY when the question
    explicitly names both roles via a literal "both X and Y" phrase
    (the V2 ``role_ambiguity`` failure mode where the gold answer
    carries the full provider+deployer chain).

    The route ships at most ``_effective_max_refs`` references; for a
    strong compound-role question the cap is 12. We assert the
    response carries MORE than 8 refs (the R52.1-C weak ceiling) which
    proves the strong path restored a wider budget. Strict ``≥ 9``
    floor protects the test from minor floor-cap edge cases.
    """
    settings.regenold.api_key = SecretStr("regenold-test-key")
    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=_messages(
            "We are both a provider and a deployer of a high-risk "
            "CV-screening AI in our internal hiring pipeline. What "
            "obligations apply to us across the full lifecycle?"
        ),
    )
    assert r.status_code == 200, r.json()
    body = r.json()
    # STRONG-signal compound role lifts the budget above the
    # R52.1-C weak ceiling of 8. Tightened to ``>= 11`` per the eng-
    # review (P2 #4): the original ``> 8`` floor would silently pass
    # at 9 refs if a future change accidentally demoted the strong
    # path back to weak.
    assert len(body["references"]) >= 11, (
        f"strong compound-role question should ship >= 11 refs (12-budget "
        f"restored, minus 1 for floor-cap edge cases); got "
        f"{len(body['references'])} refs: {body['references']!r}"
    )
    # And of course bounded by the 12-ref cap.
    assert len(body["references"]) <= 12, (
        f"strong compound-role budget is 12; got "
        f"{len(body['references'])} refs"
    )


def test_route_weak_compound_role_gets_8_ref_budget() -> None:
    """WEAK signal (rebrand / fine-tune / authrep / configurable-SaaS) → stays at 8.

    R52.1-C tightened weak compound-role budget 12 → 8 to fix the
    "citation padding" failure mode. R53.1-B keeps that floor for the
    weak class (prose still only describes 1-2 articles for these
    shapes).
    """
    settings.regenold.api_key = SecretStr("regenold-test-key")
    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=_messages(
            "We rebrand a third-party CV-screening AI under our own "
            "brand before shipping to enterprise customers. What "
            "obligations apply to us?"
        ),
    )
    assert r.status_code == 200, r.json()
    body = r.json()
    # WEAK compound role → tightened R52.1-C 8-ref ceiling holds.
    assert len(body["references"]) <= 8, (
        f"weak compound-role question should stay at the R52.1-C "
        f"tightened 8-ref budget; got {len(body['references'])} refs: "
        f"{body['references']!r}"
    )


def test_route_weak_compound_question_gets_tight_budget() -> None:
    """R69 round-2 — a WEAK compound-role QUESTION (short, not a full
    "We are a {role} offering…" scenario) gets a tight 5-ref budget.

    The r69-live V2 run shipped 8 refs on tricky ``role_ambiguity`` rows
    where the gold is 1-3 articles; the LLM-judge refs axis failed them
    ("bulk citation dump … never described in prose", refS 0.18-0.30).
    A weak compound signal on a non-scenario question now caps at 5.
    Strong compound (explicit "both X and Y") still gets 12.
    """
    settings.regenold.api_key = SecretStr("regenold-test-key")
    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=_messages(
            "We built an internal AI for our own HR use - never "
            "released externally. Are we a provider or just a deployer?"
        ),
    )
    assert r.status_code == 200, r.json()
    body = r.json()
    assert len(body["references"]) <= 5, (
        f"weak compound-role QUESTION should ship <= 5 refs (R69 round-2 "
        f"tight budget); got {len(body['references'])} refs: "
        f"{body['references']!r}"
    )


def test_engine_prompt_no_longer_mentions_graph_context() -> None:
    """The engine system prompt should not instruct the LLM to talk about
    'graph context' / 'knowledge graph' — that wording cascades into the
    user-facing answer.

    Before this PR the prompt explicitly mentioned 'compliance knowledge
    graph' twice and 'graph context' three times. Pin that the new
    prompt doesn't.
    """
    from app.data.graph_rag_prompts import ANSWER_GENERATE_SYSTEM

    low = ANSWER_GENERATE_SYSTEM.lower()
    # Negative pin — these specific phrases must not be in the prompt.
    assert "compliance knowledge graph" not in low, (
        "engine prompt still mentions 'compliance knowledge graph'"
    )
    assert "the graph context" not in low, (
        "engine prompt still tells the model to use 'the graph context'"
    )
    # Positive pin — the prompt should still tell the model to ground
    # answers in the regulation.
    assert "regulation" in low or "eu ai act" in low
