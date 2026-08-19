"""Direct Stage-2 synthesis test on live AWS Bedrock with Qwen 3 32B and Qwen 3 235B."""
import os
import sys
import time
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()
os.environ["P2P_GRAPH_RAG_PROVIDER"] = "bedrock"

from app.engines._graph_rag_impl import _bedrock_complete_for_graph_rag

def test_direct_bedrock_stage2():
    print("=" * 70)
    print(" Live Bedrock Stage-2 Synthesis Test (Qwen 3 32B & Qwen 3 235B)")
    print("=" * 70)

    system_prompt = (
        "You are an expert EU AI Act regulatory compliance specialist. "
        "Lead with a direct verdict (BLUF). Cite exact statutory provisions."
    )

    # 1. Simple Question -> Qwen 3 32B
    user_simple = (
        "ORIGINAL QUESTION: Is a standard customer support chatbot high-risk under the EU AI Act?\n\n"
        "EU AI ACT REFERENCES:\n- Article 50 (Transparency obligations)\n- Article 6 (Classification rules)\n\n"
        "ANSWER COVERAGE: State whether it is high-risk and what transparency duties apply."
    )
    print("\n[1/2] Invoking Stage-2 Simple Question -> Qwen 3 32B...")
    t0 = time.time()
    out1 = _bedrock_complete_for_graph_rag(
        system=system_prompt,
        user=user_simple,
        max_tokens=600,
        temperature=0.0,
        complex_question=False,
        stage_name="Stage 2 (Polishing)",
    )
    elapsed1 = time.time() - t0
    print(f"Elapsed: {elapsed1:.2f}s")
    print(f"Response:\n{out1}\n")

    # 2. Complex Question -> Qwen 3 235B
    user_complex = (
        "ORIGINAL QUESTION: When does a fine-tuned GPAI model trigger provider obligations under Article 25 and cumulative systemic risk duties under Article 51 and 55?\n\n"
        "EU AI ACT REFERENCES:\n- Article 25 (Responsibilities along the AI value chain)\n- Article 51 (Classification of GPAI models with systemic risk)\n- Article 55 (Obligations for providers of GPAI models with systemic risk)\n\n"
        "ANSWER COVERAGE: Explain the compute thresholds, substantial modification rule under Article 25, and systemic risk obligations."
    )
    print("\n[2/2] Invoking Stage-2 Complex Question -> Qwen 3 235B...")
    t0 = time.time()
    out2 = _bedrock_complete_for_graph_rag(
        system=system_prompt,
        user=user_complex,
        max_tokens=800,
        temperature=0.0,
        complex_question=True,
        stage_name="Stage 2 (Polishing)",
    )
    elapsed2 = time.time() - t0
    print(f"Elapsed: {elapsed2:.2f}s")
    print(f"Response:\n{out2}\n")

if __name__ == "__main__":
    test_direct_bedrock_stage2()
