"""R39 mtRAG loader/scorer (Issue B10)."""
from evals.bench.mtrag import (
    load_mtrag_subset,
    score_multi_turn,
)


def test_load_returns_iterable_of_conversations():
    # Loader uses a small in-repo fixture (placed by step 8.3) so the
    # test works offline.
    convs = list(load_mtrag_subset(fixture_path="tests/fixtures/mtrag_sample.jsonl"))
    assert len(convs) >= 1
    assert "turns" in convs[0]


def test_score_multi_turn_returns_coherence_rate():
    # 2-turn dummy: agent answers each turn with the SAME articles in
    # the expected sequence.
    convs = [
        {"turns": [
            {"question": "What is Art. 13?", "gold_refs": ["Art. 13"]},
            {"question": "And Art. 13(1)?", "gold_refs": ["Art. 13.1"]},
        ]}
    ]
    def agent(turn, history):
        if "13(1)" in turn["question"]:
            return {"answer": "transparency obligations", "references": ["Article 13.1"]}
        return {"answer": "transparency", "references": ["Article 13"]}
    out = score_multi_turn(convs, agent=agent)
    assert out["coherence_rate"] == 1.0
    assert out["n_conversations"] == 1
