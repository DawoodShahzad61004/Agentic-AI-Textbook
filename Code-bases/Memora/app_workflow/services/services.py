import chromadb
from .embedding_manager import EmbeddingManager
from .vector_store import VectorStore
from .retriever import RAGRetriever
from .learned_qa_store import get_or_create_learned_qa_collection
from .feedback_store import FeedbackStore
from .self_learner import SelfLearner
from .llm_setup import llm as _workflow_llm
from app_workflow.config import (
    COLLECTION_NAME,
    LEARN_EVERY_N,
    VECTOR_STORE_PATH,
)


embedding_manager = EmbeddingManager()
vector_store = VectorStore(collection_name=COLLECTION_NAME, persist_directory=VECTOR_STORE_PATH)

if vector_store.collection.count() == 0:
    raise SystemExit("Vector store is empty. Run ingest.py first.")

chroma_client = chromadb.PersistentClient(path=VECTOR_STORE_PATH)
learned_collection = get_or_create_learned_qa_collection(chroma_client)
retriever = RAGRetriever(vector_store, embedding_manager, learned_collection=learned_collection)

feedback_store = FeedbackStore()

# Holds the variants_with_chunks list from the most recent answer run so that
# cmd_bad (a separate graph invocation) can pass them to mark_last_bad().
last_variants_with_chunks: list[dict] = []

self_learner = SelfLearner(
    embedding_manager=embedding_manager,
    llm=_workflow_llm,
    feedback_store=feedback_store,
    vector_store_path=VECTOR_STORE_PATH,
    learn_every_n=LEARN_EVERY_N,
)
