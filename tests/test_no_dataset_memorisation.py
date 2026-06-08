"""R82-B.3 — Unit test to verify zero dataset memorisation.

Asserts that no gold answers from the benchmark dataset are verbatim substrings
or share >= 80% Jaccard overlap with the few-shot exemplars in ANSWER_GENERATE_SYSTEM.
"""

from __future__ import annotations

import re
from app.data.graph_rag_prompts import ANSWER_GENERATE_SYSTEM
from evals.bench.dataset import load_qa_pairs


def _tokenize(text: str) -> set[str]:
    # Simple alphanumeric tokenizer
    words = re.findall(r"\b\w+\b", text.lower())
    return set(words)


def _jaccard_similarity(s1: set[str], s2: set[str]) -> float:
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)


def test_no_dataset_memorisation() -> None:
    # Extract exemplar answers from ANSWER_GENERATE_SYSTEM
    # We find strings matching the exemplar answers
    exemplars = [
        "A remote biometric identification system is defined in Article 3(36) as an AI system used for identifying natural persons at a distance through the comparison of biometric data against reference data, excluding real-time systems in private spaces.",
        "A provider must first establish a quality management system under Article 17, draw up the required technical documentation specified in Article 11, and undergo the conformity assessment procedure in Article 43. Additionally, the provider must register the system in the EU database pursuant to Article 49.",
        "The use of AI systems to detect emotions of natural persons in educational institutions is prohibited under Article 5(1)(f). Deployers must not place or use such systems in classrooms, as emotion recognition in educational environments is classified as an unacceptable risk.",
        "AI systems used by law enforcement for profiling natural persons are classified as high-risk under Annex III(6)(a). Providers of such systems must establish a risk management system pursuant to Article 9, ensure high-quality training and data governance under Article 10, and enable human oversight in accordance with Article 14."
    ]

    # Verify that these exemplars are indeed inside ANSWER_GENERATE_SYSTEM
    for ex in exemplars:
        assert ex in ANSWER_GENERATE_SYSTEM, f"Exemplar '{ex[:30]}...' not found in ANSWER_GENERATE_SYSTEM"

    # Load gold QA pairs
    qa_pairs = load_qa_pairs()
    assert len(qa_pairs) > 0, "No QA pairs loaded"

    # Tokenize exemplars
    exemplar_tokens = [_tokenize(ex) for ex in exemplars]

    # Check each QA pair gold answer
    for row in qa_pairs:
        gold_ans = row.get("answer", "")
        if not gold_ans:
            continue
        
        gold_tokens = _tokenize(gold_ans)
        gold_lower = gold_ans.lower()

        for idx, (ex_text, ex_toks) in enumerate(zip(exemplars, exemplar_tokens)):
            # 1. Substring assertion (verbatim leakage)
            assert gold_lower not in ex_text.lower(), (
                f"Gold answer is a substring of exemplar {idx+1}!\n"
                f"Gold: {gold_ans}\nExemplar: {ex_text}"
            )
            assert ex_text.lower() not in gold_lower, (
                f"Exemplar {idx+1} is a substring of gold answer!\n"
                f"Gold: {gold_ans}\nExemplar: {ex_text}"
            )

            # 2. Jaccard similarity threshold (< 80%)
            similarity = _jaccard_similarity(gold_tokens, ex_toks)
            assert similarity < 0.8, (
                f"Exemplar {idx+1} has high overlap ({similarity:.2%}) with gold answer!\n"
                f"Gold: {gold_ans}\nExemplar: {ex_text}"
            )
