"""R449 — contextual (fielded) BM25 fields + engine cache-key registration.

Three properties are load-bearing and each has a specific way to look true while
being false, so each gets its own test:

1. **Default OFF and byte-identical.** A fielded index that silently changes the
   deterministic baseline would invalidate every recorded davidath number.
2. **ON actually changes scoring.** An env flag whose value the index never
   reads is the R329 "inert lever" trap: the A/B reads +0.0000 and looks like
   "no effect" instead of "never ran".
3. **Keyed in `_engine_cache_key`.** The flag changes candidate ranking, so it
   changes the cached `GraphRAGResponse`; unkeyed, an in-process A/B replays the
   other arm's answer.
"""
from __future__ import annotations

import math

import pytest

from app.data import kb_search
from app.data.provision_text import title_for_ref


@pytest.fixture(autouse=True)
def _clear_index_cache():
    """Every test here changes an index-affecting env var."""
    kb_search._build_index.cache_clear()  # noqa: SLF001 — module-level lru_cache
    yield
    kb_search._build_index.cache_clear()  # noqa: SLF001


def _legacy_score(index, doc_idx: int, query_tokens: list[str]) -> float:
    """The pre-R449 BM25 formula, re-implemented here as the OFF oracle."""
    doc = index.docs[doc_idx]
    freqs = index.doc_freqs[doc_idx]
    doc_len = len(doc)
    score = 0.0
    for term in query_tokens:
        if term not in freqs:
            continue
        tf = freqs[term]
        idf = index.idf.get(term, 0.0)
        numerator = tf * (index.k1 + 1)
        denominator = tf + index.k1 * (
            1 - index.b + index.b * doc_len / index.avg_doc_len
        )
        score += idf * (numerator / denominator)
    return score


def test_contextual_fields_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv(kb_search._CONTEXTUAL_FIELDS_ENV, raising=False)  # noqa: SLF001
    assert kb_search.contextual_fields_enabled() is False

    index = kb_search._build_index()  # noqa: SLF001
    assert index.field_freqs == ()
    assert index.field_lens == ()
    assert index.field_avg_len == {}


def test_off_path_reproduces_the_legacy_formula(monkeypatch) -> None:
    monkeypatch.setenv(kb_search._CONTEXTUAL_FIELDS_ENV, "0")  # noqa: SLF001
    index = kb_search._build_index()  # noqa: SLF001
    query_tokens = kb_search._tokenize(  # noqa: SLF001
        "What must the technical documentation contain for a high-risk AI system?"
    )
    checked = 0
    for doc_idx in range(len(index.docs)):
        got = kb_search._score(index, doc_idx, query_tokens)  # noqa: SLF001
        want = _legacy_score(index, doc_idx, query_tokens)
        assert got == pytest.approx(want, abs=1e-12)
        checked += 1
    assert checked > 0


def test_on_path_builds_fields_and_is_deterministic(monkeypatch) -> None:
    monkeypatch.setenv(kb_search._CONTEXTUAL_FIELDS_ENV, "1")  # noqa: SLF001
    index = kb_search._build_index()  # noqa: SLF001

    assert len(index.field_freqs) == len(index.docs)
    assert len(index.field_lens) == len(index.docs)
    assert set(index.field_avg_len) == {"title", "body"}
    assert index.field_avg_len["title"] > 0
    assert index.field_avg_len["body"] > 0
    # The title field is the short context prefix, never the body.
    assert index.field_avg_len["title"] < index.field_avg_len["body"]

    # Determinism: rebuild and compare the scored surface exactly.
    first = [
        kb_search._score(index, i, ["transparency"])  # noqa: SLF001
        for i in range(len(index.docs))
    ]
    kb_search._build_index.cache_clear()  # noqa: SLF001
    rebuilt = kb_search._build_index()  # noqa: SLF001
    second = [
        kb_search._score(rebuilt, i, ["transparency"])  # noqa: SLF001
        for i in range(len(rebuilt.docs))
    ]
    assert first == second


def test_fielded_idf_counts_title_only_terms_once_per_document(monkeypatch) -> None:
    """BM25F IDF must include title-only terms without double-counting fields."""
    token = "ctxonlyr449token"
    monkeypatch.setenv(kb_search._CONTEXTUAL_FIELDS_ENV, "1")  # noqa: SLF001
    monkeypatch.setattr(
        kb_search,
        "_context_prefix",
        lambda article_ref: token if article_ref == "Art. 13" else "",
    )

    index = kb_search._build_index()  # noqa: SLF001
    assert all(token not in freqs for freqs in index.doc_freqs)

    document_frequency = sum(
        any(token in field_freqs for field_freqs in fields.values())
        for fields in index.field_freqs
    )
    assert 0 < document_frequency < len(index.docs)
    expected_idf = math.log(
        (len(index.docs) - document_frequency + 0.5)
        / (document_frequency + 0.5)
        + 1.0
    )
    assert index.idf[token] == pytest.approx(expected_idf)

    for doc_idx, fields in enumerate(index.field_freqs):
        score = kb_search._score(index, doc_idx, [token])  # noqa: SLF001
        if token in fields["title"]:
            assert score > 0.0
        else:
            assert score == 0.0


def test_on_path_changes_scores_of_title_bearing_documents(monkeypatch) -> None:
    """The fielded score must differ *somewhere*, or the flag is a no-op."""
    query_tokens = ["transparency"]
    monkeypatch.setenv(kb_search._CONTEXTUAL_FIELDS_ENV, "0")  # noqa: SLF001
    plain = kb_search._build_index()  # noqa: SLF001
    off_scores = [
        kb_search._score(plain, i, query_tokens) for i in range(len(plain.docs))  # noqa: SLF001
    ]

    kb_search._build_index.cache_clear()  # noqa: SLF001
    monkeypatch.setenv(kb_search._CONTEXTUAL_FIELDS_ENV, "1")  # noqa: SLF001
    fielded = kb_search._build_index()  # noqa: SLF001
    on_scores = [
        kb_search._score(fielded, i, query_tokens)  # noqa: SLF001
        for i in range(len(fielded.docs))
    ]
    assert len(off_scores) == len(on_scores)
    assert any(a != b for a, b in zip(off_scores, on_scores, strict=True))


def test_engine_cache_key_includes_contextual_fields(monkeypatch) -> None:
    from app.routes.regenold import _engine_cache_key

    monkeypatch.setenv(kb_search._CONTEXTUAL_FIELDS_ENV, "0")  # noqa: SLF001
    off_key = _engine_cache_key("What about Article 13?", None)
    monkeypatch.setenv(kb_search._CONTEXTUAL_FIELDS_ENV, "1")  # noqa: SLF001
    on_key = _engine_cache_key("What about Article 13?", None)
    assert off_key != on_key


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("Art. 13", "Transparency and provision of information to deployers"),
        ("Article 13", "Transparency and provision of information to deployers"),
        ("Annex IV", "Technical documentation referred to in Article 11(1)"),
    ],
)
def test_title_for_ref(ref: str, expected: str) -> None:
    assert title_for_ref(ref) == expected


def test_title_for_ref_unknown_is_empty() -> None:
    assert title_for_ref("Art. 999") == ""
    assert title_for_ref("nonsense") == ""
