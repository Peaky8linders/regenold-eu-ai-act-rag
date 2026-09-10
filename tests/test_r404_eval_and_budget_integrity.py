"""R404 integrity fixes for the live official evaluation path."""
from __future__ import annotations

import pytest


def test_bedrock_judge_uses_exact_requested_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from evals.official import judge as j

    monkeypatch.setattr(j, "MODEL", j.MODEL)
    seen = []

    class Provider:
        def complete(self, req):
            seen.append(req.model)
            return type("Response", (), {"text": '{"ok": true}', "error": None})()

    monkeypatch.setattr("app.llm.bedrock_client.get_bedrock_provider", lambda: Provider())
    j.configure_judge(provider="bedrock", model="eu.anthropic.claude-opus-5")

    assert j._call("probe", retries=1) == '{"ok": true}'
    assert seen == ["eu.anthropic.claude-opus-5"]


def test_bedrock_judge_retries_fail_soft_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    from evals.official import judge as j

    monkeypatch.setattr(j, "MODEL", j.MODEL)
    calls = 0

    class Provider:
        def complete(self, _req):
            nonlocal calls
            calls += 1
            return type("Response", (), {"text": "", "error": "api_throttled_429"})()

    monkeypatch.setattr("app.llm.bedrock_client.get_bedrock_provider", lambda: Provider())
    j.configure_judge(provider="bedrock", model="qwen.qwen3-235b-a22b-2507-v1:0")

    with pytest.raises(RuntimeError, match="api_throttled_429"):
        j._call("probe", retries=3)
    assert calls == 3


def test_judge_cache_key_is_model_scoped() -> None:
    from evals.official.score_arm import _key

    qwen = _key("q1", "same answer", "bedrock:qwen235:t=.1:r=3")
    opus = _key("q1", "same answer", "bedrock:opus5:t=.1:r=3")
    assert qwen != opus


def test_multiturn_depth_reaches_semantic_tier_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.data.graph_rag_prompts import tier_quota

    monkeypatch.setenv("REGENOLD_PROMPT_BUDGET_FLEX", "1")
    question = (
        "Conversation context:\nUser: Tell me about the AI Act.\n"
        "Latest question: What does Article 6 say?"
    )
    assert tier_quota(
        question,
        env_name="_R404_UNSET_QUOTA",
        default=16,
        lo=1,
        hi=60,
        scale={"S": 8, "M": 16, "L": 24},
    ) == 24


def test_cohere_required_run_detects_midrun_embedding_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import numpy as np

    from app.engines import cohere_rerank, external_embeddings, turboquant_index
    from evals.regenold.run_official_batch import _install_cohere_guard

    monkeypatch.setenv("COHERE_API_KEY", "test-key")
    calls = 0

    def embedding(_texts, *, is_query=False):
        del is_query
        nonlocal calls
        calls += 1
        return np.ones(3, dtype=np.float32) if calls == 1 else None

    monkeypatch.setattr(external_embeddings, "get_embedding", embedding)
    monkeypatch.setattr(
        turboquant_index,
        "index_diagnostics",
        lambda: {"loaded": True, "embedding_backend": "cohere"},
    )
    monkeypatch.setattr(
        cohere_rerank,
        "rerank_documents",
        lambda *_args, **_kwargs: (
            cohere_rerank._bump("attempts") or [(0, 0.9), (1, 0.1)]
        ),
    )

    assert_healthy = _install_cohere_guard()
    assert external_embeddings.get_embedding("later query", is_query=True) is None
    with pytest.raises(RuntimeError, match="embedding call fell back"):
        assert_healthy()


def test_cohere_required_run_rejects_noop_reranker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import numpy as np

    from app.engines import cohere_rerank, external_embeddings, turboquant_index
    from evals.regenold.run_official_batch import _install_cohere_guard

    monkeypatch.setenv("COHERE_API_KEY", "test-key")
    monkeypatch.setattr(
        external_embeddings,
        "get_embedding",
        lambda *_args, **_kwargs: np.ones(3, dtype=np.float32),
    )
    monkeypatch.setattr(
        turboquant_index,
        "index_diagnostics",
        lambda: {"loaded": True, "embedding_backend": "cohere"},
    )
    monkeypatch.setattr(cohere_rerank, "rerank_documents", lambda *_args, **_kwargs: None)

    with pytest.raises(RuntimeError, match="rerank preflight failed"):
        _install_cohere_guard()


def test_rerank_only_guard_allows_offline_embeddings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reranker experiment must not be forced to consume embedding quota."""
    from app.engines import cohere_rerank
    from evals.regenold.run_official_batch import _install_cohere_guard

    monkeypatch.setenv("COHERE_API_KEY", "test-key")
    monkeypatch.setenv("REGENOLD_EXTERNAL_EMBEDDINGS", "0")
    monkeypatch.setattr(
        cohere_rerank,
        "rerank_documents",
        lambda *_args, **_kwargs: (
            cohere_rerank._bump("attempts") or [(0, 0.9), (1, 0.1)]
        ),
    )

    assert_healthy = _install_cohere_guard(require_embeddings=False)
    assert_healthy()


def test_judge_remarks_are_persisted(monkeypatch: pytest.MonkeyPatch) -> None:
    """The judge asks for explanations, so the audit artifact must retain them."""
    from evals.official import judge

    replies = iter(
        [
            '{"verdicts":[{"n":1,"satisfied":true,"why":"States the rule."}]}',
            '{"appropriate":true,"clear":true,"why":"Professional and clear."}',
        ]
    )
    monkeypatch.setattr(judge, "_call", lambda *_args, **_kwargs: next(replies))

    out = judge.judge_row(
        {"question": "Q", "answer": "A", "criteria": ["rule"]},
        repeats=1,
    )

    assert out["criterion_remarks"] == ["States the rule."]
    assert out["tone_remark"] == "Professional and clear."
