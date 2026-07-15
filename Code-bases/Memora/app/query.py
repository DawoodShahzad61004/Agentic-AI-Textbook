"""
    python query.py                  # interactive loop (default)
    python query.py --simple         # use basic answer mode
    python query.py --top-k 5        # retrieve top 5 chunks
"""

import argparse
from typing import Any, Dict, List

from langchain_openai import ChatOpenAI

from embedding_manager import EmbeddingManager
from llm_caller import llm_invoke
from llm_setup import llm as build_llm_result
from retriever import RAGRetriever
from vector_store import VectorStore

# ── Configuration ────────────────────────────────────────────────────────────
VECTOR_STORE_PATH = "../data/vector_store"
COLLECTION_NAME = "documents"
DEFAULT_TOP_K = 7
DEFAULT_MIN_SCORE = 0.2
# ─────────────────────────────────────────────────────────────────────────────


def build_llm() -> ChatOpenAI:
    return build_llm_result


def generate_answer(query: str, retriever: RAGRetriever, llm: ChatOpenAI, top_k: int) -> str:
    retrieved_docs = retriever.retrieve(query, top_k=top_k)
    if not retrieved_docs:
        return "No relevant documents found to answer the question."

    context = "\n\n".join(
        [f"Document {doc['rank']}:\n{doc['content']}" for doc in retrieved_docs]
    )
    prompt = f"""You are an expert assistant. Use the following retrieved documents to answer the question.

Question: {query}

Context:
{context}

Provide a concise and accurate answer based on the above information."""

    result = llm_invoke(
        llm,
        [{"role": "user", "content": prompt}],
        caller_tag="QUERY-SIMPLE",
    )
    if not result.ok:
        return f"LLM call failed: {result.error_message}"
    return result.content


def advanced_answer(
    query: str,
    retriever: RAGRetriever,
    llm: ChatOpenAI,
    top_k: int,
    min_score: float = DEFAULT_MIN_SCORE,
    return_context: bool = False,
) -> Dict[str, Any]:
    retrieved_docs = retriever.retrieve(query, top_k=top_k, score_threshold=min_score)
    if not retrieved_docs:
        return {"answer": "No relevant documents found.", "sources": [], "confidence": 0.0}

    context = "\n\n".join(
        [f"Document {doc['rank']}:\n{doc['content']}" for doc in retrieved_docs]
    )
    sources = [
        {
            "source": doc["metadata"].get("source", "Unknown"),
            "page": doc["metadata"].get("page", "unknown"),
            "similarity_score": doc["similarity_score"],
            "preview": doc["content"][:300] + ("..." if len(doc["content"]) > 300 else ""),
        }
        for doc in retrieved_docs
    ]
    confidence = max(doc["similarity_score"] for doc in retrieved_docs)

    prompt = f"""You are an expert assistant. Use the following retrieved documents to answer the question.

Question: {query}

Context:
{context}

Provide a concise and accurate answer based on the above information."""

    result = llm_invoke(
        llm,
        [{"role": "user", "content": prompt}],
        caller_tag="QUERY-ADVANCED",
    )
    response = result.content if result.ok else f"LLM call failed: {result.error_message}"
    output: Dict[str, Any] = {"answer": response, "sources": sources, "confidence": confidence}
    if return_context:
        output["context"] = context
    return output


def print_advanced_result(result: Dict[str, Any]):
    print("\n" + "=" * 60)
    print("ANSWER:")
    print(result["answer"])
    print(f"\nConfidence Score: {result['confidence']:.4f}")
    print("\nSources:")
    for s in result["sources"]:
        print(f"  • {s['source']}  (page {s['page']}, score {s['similarity_score']:.4f})")
        print(f"    Preview: {s['preview'][:120]}...")
    print("=" * 60)


def interactive_loop(retriever: RAGRetriever, llm: ChatOpenAI, top_k: int, simple: bool):
    print("\n" + "=" * 60)
    print("RAG Pipeline — Query Interface")
    print("Type your question and press Enter. Type 'quit' or 'exit' to stop.")
    print("=" * 60 + "\n")

    while True:
        try:
            query = input("Your question: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not query:
            continue
        if query.lower() in {"quit", "exit", "q"}:
            print("Goodbye!")
            break

        if simple:
            answer = generate_answer(query, retriever, llm, top_k)
            print(f"\nAnswer: {answer}\n")
        else:
            result = advanced_answer(query, retriever, llm, top_k, return_context=False)
            print_advanced_result(result)


def main():
    parser = argparse.ArgumentParser(description="RAG Pipeline Query Interface")
    parser.add_argument("--simple", action="store_true", help="Use simple answer mode (no sources/confidence)")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help=f"Number of chunks to retrieve (default: {DEFAULT_TOP_K})")
    parser.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE, help=f"Minimum similarity score threshold (default: {DEFAULT_MIN_SCORE})")
    args = parser.parse_args()

    embedding_manager = EmbeddingManager()
    vector_store = VectorStore(
        collection_name=COLLECTION_NAME,
        persist_directory=VECTOR_STORE_PATH,
    )

    doc_count = vector_store.collection.count()
    if doc_count == 0:
        print("⚠️  Vector store is empty. Run `python ingest.py` first to index your documents.")
        return

    print(f"Vector store loaded — {doc_count} document chunks available.")

    retriever = RAGRetriever(vector_store, embedding_manager)
    llm = build_llm()

    interactive_loop(retriever, llm, top_k=args.top_k, simple=args.simple)


if __name__ == "__main__":
    main()
