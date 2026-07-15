import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from state import GraphState

from services.phoenix_tracing import setup_phoenix_tracing
from services.langfuse_tracing import get_langfuse_handler
from services.logger_config import setup_logging
from services.llm_caller import LLMRateLimitAbortError
from config import MIN_FEEDBACK_LEN, ENABLE_PHOENIX_TRACING, ENABLE_LANGFUSE_TRACING
from graph import build_graph

_log_dir = Path(__file__).resolve().parent / "run_logs"
if ENABLE_PHOENIX_TRACING:
    setup_phoenix_tracing()
langfuse_handler = get_langfuse_handler() if ENABLE_LANGFUSE_TRACING else None
setup_logging(log_dir=_log_dir, app_name="rag_langgraph")
logger = logging.getLogger(__name__)

rag_app = build_graph()

try:
    graph_image_path = Path(__file__).with_name("rag_graph.png")
    graph_image_path.write_bytes(rag_app.get_graph().draw_mermaid_png())
    logger.info("Graph saved to %s", graph_image_path)
except ImportError:
    logger.info("Graph structure:\n%s", rag_app.get_graph().draw_ascii())

logger.info('RAG Assistant ready.')
print('Commands: "stats" | "learn" | "bad" (flag last answer) | "exit" / "quit"\n')

while True:
    question = input("You: ").strip()
    if not question:
        continue

    user_feedback = ""
    if question.lower() == "bad":
        print(
            f"\nWhy was this answer bad? (optional — press Enter to skip)."
            f"\nIf you provide at least {MIN_FEEDBACK_LEN} characters, it will be persisted.\n"
        )
        try:
            user_feedback = input("Your feedback: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()

    state = GraphState(
        user_input=question,
        query=question,
        user_feedback=user_feedback,
        query_variants=[],
        answer="",
        # Per-track retrieval accumulators (Annotated lists start empty)
        retrieved_document_chunks=[],
        retrieved_learned_qa_chunks=[],
        # Per-track validated
        validated_document_chunks=[],
        validated_learned_qa_chunks=[],
        # Per-track dedup-merged
        dedup_merged_document_chunks=[],
        dedup_merged_learned_qa_chunks=[],
        # Combined for compression
        dedup_merged_chunks=[],
        # Compression output
        compressed_docs=[],
        retry_count=0,
        # Feedback persistence accumulators (Annotated lists, accumulated across retrieve branches)
        variants_with_chunks=[],
        newly_failed_variants=[],
    )
    try:
        rag_app.invoke(
            state,
            config={"callbacks": [langfuse_handler] if langfuse_handler else []},
        )
    except LLMRateLimitAbortError as e:
        mins = int(e.delay // 60)
        secs = int(e.delay % 60)
        wait_str = f"{mins}m {secs}s" if mins else f"{secs}s"
        print(
            f"\n[Rate Limit] Execution stopped — the required backoff ({wait_str}) is too high.\n"
            f"Please do not send a query for at least {wait_str}.\n"
        )
