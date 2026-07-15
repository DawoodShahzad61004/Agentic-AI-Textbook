import sys
import os
import signal
import json
import uuid
import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

# Ensure app/ is on sys.path and is CWD so config.py relative paths resolve correctly.
_APP_DIR = Path(__file__).resolve().parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))
os.chdir(_APP_DIR)

from dotenv import load_dotenv

load_dotenv()

from phoenix_tracing import setup_phoenix_tracing

# Set up tracing/logging before any pipeline imports to win the "configure once" guard.
from logger_config import setup_logging, set_request_id

setup_phoenix_tracing()
setup_logging(log_dir=_APP_DIR / "run_logs", app_name="langchain_api")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import chromadb

from embedding_manager import EmbeddingManager
from vector_store import VectorStore
from retriever import RAGRetriever
from tools import make_tools, make_check_answer_quality
from feedback_store import FeedbackStore
from learned_qa_store import get_or_create_learned_qa_collection
from self_learner import SelfLearner
from llm_caller import LLMRateLimitAbortError
from llm_setup import llm, merge_llm, judge_llm
from agent_query import run_agent
from db import failed_variants_col
from config import (
    VECTOR_STORE_PATH,
    COLLECTION_NAME,
    LEARN_EVERY_N,
    ENABLE_AUTO_DISTILLATION,
    MIN_FEEDBACK_LEN,
)
logger = logging.getLogger(__name__)

_ctx: dict = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    embedding_manager = EmbeddingManager()
    vector_store = VectorStore(
        collection_name=COLLECTION_NAME, persist_directory=VECTOR_STORE_PATH
    )

    if vector_store.collection.count() == 0:
        raise RuntimeError("Vector store is empty. Run ingest.py first.")

    chroma_client = chromadb.PersistentClient(path=VECTOR_STORE_PATH)
    learned_collection = get_or_create_learned_qa_collection(chroma_client)
    retriever = RAGRetriever(
        vector_store, embedding_manager, learned_collection=learned_collection
    )

    agent_state: dict = {}
    tool_schemas, callables = make_tools(
        retriever, judge_llm=judge_llm, merge_llm=merge_llm, agent_state=agent_state
    )
    check_answer_quality = make_check_answer_quality(judge_llm)
    feedback_store = FeedbackStore()
    self_learner = SelfLearner(
        embedding_manager=embedding_manager,
        llm=llm,
        feedback_store=feedback_store,
        vector_store_path=VECTOR_STORE_PATH,
        learn_every_n=LEARN_EVERY_N,
    )

    _ctx.update(
        {
            "llm": llm,
            "merge_llm": merge_llm,
            "judge_llm": judge_llm,
            "retriever": retriever,
            "agent_state": agent_state,
            "tool_schemas": tool_schemas,
            "callables": callables,
            "check_answer_quality": check_answer_quality,
            "feedback_store": feedback_store,
            "self_learner": self_learner,
            "learned_collection": learned_collection,
        }
    )
    logger.info("LangChain RAG API ready.")
    yield
    _ctx.clear()


app = FastAPI(title="LangChain RAG API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    query: str


class FeedbackRequest(BaseModel):
    request_id: str
    feedback: str = ""


@app.post("/query")
async def query(req: QueryRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    request_id = str(uuid.uuid4())
    set_request_id(request_id)
    logger.info("Request received: request_id=%s", request_id)

    norm = req.query.lower().strip()
    fv_col = failed_variants_col()
    fv_doc = fv_col.find_one({"normalized_query": norm})
    blocked: list[str] = list(fv_doc["variants"]) if fv_doc else []
    if blocked:
        logger.debug("[BLOCKED VARIANTS] %d known-failing variant(s) loaded from DB.", len(blocked))

    feedback_store: FeedbackStore = _ctx["feedback_store"]
    prior_thumbdowns = feedback_store.find_thumbdowns_for_query(req.query)

    existing_blocked: set[str] = set(blocked)
    for td in prior_thumbdowns:
        for v in (td.get("variants") or []):
            vq = (v.get("query") or "").strip()
            if vq and vq not in existing_blocked:
                blocked.append(vq)
                existing_blocked.add(vq)

    try:
        result, newly_failed = await asyncio.to_thread(
            run_agent,
            req.query,
            _ctx["llm"],
            _ctx["merge_llm"],
            _ctx["judge_llm"],
            _ctx["tool_schemas"],
            _ctx["callables"],
            _ctx["check_answer_quality"],
            _ctx["retriever"],
            _ctx["agent_state"],
            blocked,
            prior_thumbdowns,
            request_id,
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

    if newly_failed:
        fv_doc = fv_col.find_one({"normalized_query": norm})
        existing = set(fv_doc["variants"]) if fv_doc else set()
        fresh = [v for v in newly_failed if v not in existing]
        if fresh:
            fv_col.update_one(
                {"normalized_query": norm},
                {"$addToSet": {"variants": {"$each": fresh}}},
                upsert=True,
            )
            logger.info(
                "[FAILED VARIANTS] saved %d new failing variant(s) to MongoDB for norm=%r",
                len(fresh), norm,
            )

    feedback_store.log(
        query=req.query,
        answer=result["answer"],
        sources=result["sources"],
        quality=result["quality"],
        document_retrieved_chunks=result.get("document_chunks", []),
        learned_qa_retrieved_chunks=result.get("learned_qa_chunks", []),
        request_id=request_id,
        variants=result.get("variants", []),
    )

    if (
        ENABLE_AUTO_DISTILLATION
        and result["quality"] == "OK"
        and _ctx["self_learner"].should_learn()
    ):
        added = await asyncio.to_thread(_ctx["self_learner"].run_distillation)
        logger.info("[Self-Learning] %d new QA pair(s) added to knowledge base", added)

    result["request_id"] = request_id
    return result


@app.post("/feedback/bad")
async def feedback_bad(req: FeedbackRequest):
    feedback_store: FeedbackStore = _ctx["feedback_store"]
    ok = feedback_store.mark_bad(request_id=req.request_id, feedback=req.feedback)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Interaction not found: request_id={req.request_id}")
    persisted = bool(req.feedback and len(req.feedback) >= MIN_FEEDBACK_LEN)
    logger.info("Feedback received: request_id=%s persisted=%s", req.request_id, persisted)
    return {"status": "flagged", "request_id": req.request_id, "persisted": persisted}


@app.get("/stats")
async def stats():
    feedback_store: FeedbackStore = _ctx["feedback_store"]
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
    added = await asyncio.to_thread(_ctx["self_learner"].run_distillation)
    return {"added_qa_pairs": added}


@app.post("/quit")
async def quit_server():
    logger.info("Shutdown requested via /quit endpoint.")
    os.kill(os.getpid(), signal.SIGTERM)
    return {"status": "shutting down"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)
