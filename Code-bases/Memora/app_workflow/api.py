import sys
import os
import signal
import uuid
import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional
from services.phoenix_tracing import setup_phoenix_tracing
from services.langfuse_tracing import get_langfuse_handler


# Both app_workflow/ and the project root must be on sys.path so that node
# imports work correctly regardless of how uvicorn is invoked.
_WORKFLOW_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _WORKFLOW_DIR.parent
if str(_WORKFLOW_DIR) not in sys.path:
    sys.path.insert(0, str(_WORKFLOW_DIR))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(1, str(_PROJECT_ROOT))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from services.logger_config import setup_logging, set_request_id
from services.llm_caller import LLMRateLimitAbortError
from state import GraphState
from app_workflow.config import (
    ENABLE_AUTO_DISTILLATION,
    ENABLE_LANGFUSE_TRACING,
    LEARN_EVERY_N,
    MIN_FEEDBACK_LEN,
    ENABLE_PHOENIX_TRACING,
)
from app_workflow.nodes.check_answer_quality import QUALITY_PASS_VERDICT
from app_workflow.services.switches import resolve_switches


if ENABLE_PHOENIX_TRACING:
    setup_phoenix_tracing()
langfuse_handler = get_langfuse_handler() if ENABLE_LANGFUSE_TRACING else None
setup_logging(log_dir=_WORKFLOW_DIR / "run_logs", app_name="langgraph_api")
logger = logging.getLogger(__name__)

_ctx: dict = {}

_COMMAND_INPUTS = {"bad", "stats", "learn", "exit", "quit"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Imported here so that a SystemExit from services.py (empty vector store)
    # surfaces as a startup failure rather than a module-level crash.
    from graph import build_graph
    from app_workflow.services import services
    from app_workflow.services.services import (
        feedback_store,
        learned_collection,
        self_learner,
    )

    rag_app = build_graph()
    _ctx.update(
        {
            "rag_app": rag_app,
            "services": services,
            "feedback_store": feedback_store,
            "learned_collection": learned_collection,
            "self_learner": self_learner,
        }
    )
    logger.info("LangGraph RAG API ready.")
    yield
    _ctx.clear()


app = FastAPI(title="LangGraph RAG API", lifespan=lifespan)


class WorkflowSwitches(BaseModel):
    """Per-request overrides for the ENABLE_* toggles in config.py.

    Any field left as None keeps the config.py default for that switch.
    """

    ENABLE_SUB_QUERY_GENERATION: Optional[bool] = None
    ENABLE_QUERY_VARIANTS_OUTPUT_FIX: Optional[bool] = None
    ENABLE_RETRIEVAL_DEDUP_MERGE: Optional[bool] = None
    ENABLE_RETRIEVAL_DEDUP_MERGE_OUTPUT_FIX: Optional[bool] = None
    ENABLE_RETRIEVAL_DEDUP_MERGE_VALIDATION: Optional[bool] = None
    ENABLE_RETRIEVAL_DEDUP_MERGE_VALIDATION_OUTPUT_FIX: Optional[bool] = None
    ENABLE_RETRIEVAL_VALIDATION: Optional[bool] = None
    ENABLE_RETRIEVAL_VALIDATION_OUTPUT_FIX: Optional[bool] = None
    ENABLE_NAC_COMPRESSION: Optional[bool] = None
    ENABLE_DC_COMPRESSION: Optional[bool] = None
    ENABLE_LBC_COMPRESSION: Optional[bool] = None
    ENABLE_COMPRESSION_VALIDATION: Optional[bool] = None
    ENABLE_COMPRESSION_OUTPUT_FIX: Optional[bool] = None
    ENABLE_ANSWER_DRAFT_CREATION: Optional[bool] = None
    ENABLE_ANSWER_QUALITY_CHECK: Optional[bool] = None
    ENABLE_ANSWER_QUALITY_OUTPUT_FIX: Optional[bool] = None
    ENABLE_AUTO_DISTILLATION: Optional[bool] = None
    ENABLE_QA_PAIR_GENERATION: Optional[bool] = None
    ENABLE_QA_PAIR_OUTPUT_FIX: Optional[bool] = None
    ENABLE_GLOBAL_LLM_OUTPUT_FIX: Optional[bool] = None


class QueryRequest(BaseModel):
    query: str
    switches: Optional[WorkflowSwitches] = None


class IngestRequest(BaseModel):
    """Optional per-request overrides for the ingestion-flow toggles.

    A field left as None keeps the config.py default for that switch.
    """

    ENABLE_MARKER_LOADER: Optional[bool] = None
    ENABLE_CUSTOM_SPLITTER: Optional[bool] = None


class FeedbackRequest(BaseModel):
    feedback: str = ""


def _build_initial_state(
    query: str, request_id: str = "", switches: Optional[WorkflowSwitches] = None
) -> GraphState:
    overrides = switches.model_dump(exclude_none=True) if switches else None
    return GraphState(
        user_input=query,
        query=query,
        request_id=request_id,
        switches=resolve_switches(overrides),
        user_feedback="",
        query_variants=[],
        answer="",
        retrieved_document_chunks=[],
        retrieved_learned_qa_chunks=[],
        validated_document_chunks=[],
        validated_learned_qa_chunks=[],
        dedup_merged_document_chunks=[],
        dedup_merged_learned_qa_chunks=[],
        dedup_merged_chunks=[],
        compressed_docs=[],
        retry_count=0,
        variants_with_chunks=[],
        newly_failed_variants=[],
    )


@app.post("/query")
async def query(req: QueryRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty.")
    if req.query.strip().lower() in _COMMAND_INPUTS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{req.query}' is a reserved command, not a query. "
                "Use /feedback/bad, /stats, or /learn endpoints instead."
            ),
        )

    request_id = str(uuid.uuid4())
    set_request_id(request_id)
    logger.info("Request received: request_id=%s", request_id)

    state = _build_initial_state(req.query, request_id=request_id, switches=req.switches)

    try:
        final_state = await asyncio.to_thread(
            _ctx["rag_app"].invoke,
            state,
            {"callbacks": [langfuse_handler] if langfuse_handler else []},
        )
    except LLMRateLimitAbortError as e:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit hit. Required backoff: {e.delay:.0f}s. "
                f"Please retry after {e.delay:.0f} seconds."
            ),
            headers={"Retry-After": str(int(e.delay))},
        )

    answer = final_state.get("answer", "")
    quality_verdict = (final_state.get("quality_verdict") or "").strip().upper()
    quality = "OK" if (not quality_verdict or quality_verdict == QUALITY_PASS_VERDICT) else quality_verdict
    compressed_docs = final_state.get("compressed_docs") or []
    sources = [{"source": d.get("source", "?")} for d in compressed_docs]

    return {
        "answer": answer,
        "quality": quality,
        "sources": sources,
    }


@app.post("/feedback/bad")
async def feedback_bad(req: FeedbackRequest):
    feedback_store = _ctx["feedback_store"]
    services = _ctx["services"]
    variants = list(services.last_variants_with_chunks)
    ok = feedback_store.mark_last_bad(feedback=req.feedback, variants=variants)
    if not ok:
        raise HTTPException(status_code=404, detail="No previous answer to flag.")
    persisted = bool(req.feedback and len(req.feedback) >= MIN_FEEDBACK_LEN)
    return {"status": "flagged", "persisted": persisted}


@app.get("/stats")
async def stats():
    feedback_store = _ctx["feedback_store"]
    learned_collection = _ctx["learned_collection"]
    total = feedback_store.count()
    good = feedback_store.count_good()
    learned = learned_collection.count()
    return {
        "total_interactions": total,
        "successful": good,
        "learned_qa_pairs": learned,
        "auto_distillation_enabled": ENABLE_AUTO_DISTILLATION,
        "learn_every_n": LEARN_EVERY_N if ENABLE_AUTO_DISTILLATION else None,
    }


@app.post("/learn")
async def learn():
    learn_config = {"callbacks": [langfuse_handler]} if langfuse_handler else None
    added = await asyncio.to_thread(_ctx["self_learner"].run_distillation, config=learn_config)
    return {"added_qa_pairs": added}


@app.post("/ingest")
async def ingest(req: Optional[IngestRequest] = None):
    """Run the document-ingestion pipeline.

    The optional body's ENABLE_MARKER_LOADER / ENABLE_CUSTOM_SPLITTER booleans,
    when provided, override the config.py defaults for this run and select the
    loader (Marker vs. Unstructured) and splitter (custom vs. recursive).
    """
    from app_workflow.ingestion.ingestion_requests import run_ingestion

    enable_marker = req.ENABLE_MARKER_LOADER if req else None
    enable_custom = req.ENABLE_CUSTOM_SPLITTER if req else None

    summary = await asyncio.to_thread(
        run_ingestion,
        enable_marker_loader=enable_marker,
        enable_custom_splitter=enable_custom,
    )
    return summary


@app.post("/quit")
async def quit_server():
    logger.info("Shutdown requested via /quit endpoint.")
    os.kill(os.getpid(), signal.SIGTERM)
    return {"status": "shutting down"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8001, reload=False)
