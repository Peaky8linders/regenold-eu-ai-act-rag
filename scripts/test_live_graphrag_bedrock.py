"""End-to-end Live GraphRAG compliance question test using AWS Bedrock (Qwen 3 235B/32B)."""
import os
import sys
import json
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

os.environ["P2P_GRAPH_RAG_PROVIDER"] = "bedrock"
os.environ["P2P_GRAPH_RAG_ENABLE_STAGE2"] = "1"

from app.engines._graph_rag_impl import ask_compliance_question, GraphRAGRequest

def test_live_bedrock_graphrag():
    print("=" * 70)
    print(" Live GraphRAG Pipeline Test with AWS Bedrock Qwen Routing")
    print("=" * 70)
    
    # 1. Simple Question (should route to Qwen 3 32B)
    q1 = "Is an AI system that translates text from French to English in an office setting high-risk under the EU AI Act?"
    print(f"\n[Test 1: Simple Question] -> Expected Qwen 3 32B")
    print(f"Question: {q1}")
    t0 = time.time()
    resp1 = ask_compliance_question(GraphRAGRequest(question=q1, history_turn_count=0))
    elapsed1 = time.time() - t0
    print(f"Confidence: {resp1.confidence}")
    cites1 = [c.article_ref or c.node_id for c in resp1.citations] if resp1.citations else []
    print(f"Citations: {cites1}")
    print(f"Elapsed: {elapsed1:.2f}s")
    print(f"Answer:\n{resp1.answer}\n")
    print(f"Reasoning Trace:\n{json.dumps(resp1.reasoning_trace, indent=2)}")

    # 2. Complex Question (should route to Qwen 3 235B)
    q2 = "What are the cumulative compute thresholds under Article 51(1)(a) and the exemption procedures under Article 51(2) for GPAI models with systemic risk, and what obligations apply under Article 55?"
    print(f"\n[Test 2: Complex Question] -> Expected Qwen 3 235B")
    print(f"Question: {q2}")
    t0 = time.time()
    resp2 = ask_compliance_question(GraphRAGRequest(question=q2, history_turn_count=0))
    elapsed2 = time.time() - t0
    print(f"Confidence: {resp2.confidence}")
    cites2 = [c.article_ref or c.node_id for c in resp2.citations] if resp2.citations else []
    print(f"Citations: {cites2}")
    print(f"Elapsed: {elapsed2:.2f}s")
    print(f"Answer:\n{resp2.answer}\n")
    print(f"Reasoning Trace:\n{json.dumps(resp2.reasoning_trace, indent=2)}")

if __name__ == "__main__":
    test_live_bedrock_graphrag()
