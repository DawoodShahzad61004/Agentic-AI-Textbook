import concurrent.futures
import logging
import time
from typing import Any, Dict, List, Optional

import chromadb
import numpy as np


from .embedding_manager import EmbeddingManager
from .prompts import _THIN as _SEP
from .vector_store import VectorStore
from app_workflow.config import (
    RETRIEVAL_TOP_K,
    RETRIEVAL_TOP_L,
    MIN_SIMILARITY,
    DOCUMENTS_MIN_SIMILARITY,
    LEARNED_QA_MIN_SIMILARITY,
    RETRIEVAL_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


class RetrievalTimeoutError(Exception):
    """Raised when a ChromaDB collection query does not complete within RETRIEVAL_TIMEOUT_SECONDS."""
    def __init__(self, collection_name: str, timeout: float) -> None:
        self.collection_name = collection_name
        self.timeout = timeout
        super().__init__(f"Collection '{collection_name}' did not respond within {timeout:.0f}s.")


def _log(header: str, *lines):
    logger.debug(f"\n{_SEP}")
    logger.debug(f"  {header}")
    logger.debug(_SEP)
    for line in lines:
        logger.debug(f"  {line}")
    logger.debug(_SEP)


class RAGRetriever:
    def __init__(
        self,
        vector_store: VectorStore,
        embedding_manager: EmbeddingManager,
        learned_collection: Optional[chromadb.Collection] = None,
    ):
        self.vector_store = vector_store
        self.embedding_manager = embedding_manager
        self.learned_collection = learned_collection
        self._last_document_chunks: list[dict] = []
        self._last_learned_qa_chunks: list[dict] = []

    def retrieve(
        self,
        query: str,
        top_k: int = RETRIEVAL_TOP_K,
        score_threshold: float = MIN_SIMILARITY,
    ) -> List[Dict[str, Any]]:
        """Retrieve from the documents collection only."""
        query_embedding = self._embed_and_log(query)
        logger.debug(
            f"\n  Querying documents collection - "
            f"top_k={top_k}, score_threshold={score_threshold}"
        )

        results = self._query_collection(
            self.vector_store.collection, query_embedding, top_k
        )
        documents = self._rank_collection_results(
            results, limit=top_k, score_threshold=score_threshold
        )

        self._log_ranked_results("documents", documents)
        self._last_document_chunks = documents
        self._last_learned_qa_chunks = []
        return documents

    def retrieve_separate(
        self,
        query: str,
        top_k: int = RETRIEVAL_TOP_K,
        top_l: int = RETRIEVAL_TOP_L,
        doc_score_threshold: float = DOCUMENTS_MIN_SIMILARITY,
        learned_score_threshold: float = LEARNED_QA_MIN_SIMILARITY,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Retrieve documents and learned QA as two independent ranked lists."""
        query_embedding = self._embed_and_log(query)
        logger.debug(
            f"\n  Querying collections separately - "
            f"documents top_k={top_k}, learned_qa top_l={top_l}, "
            f"doc_score_threshold={doc_score_threshold}, "
            f"learned_score_threshold={learned_score_threshold}"
        )

        document_results = self._query_collection(
            self.vector_store.collection, query_embedding, top_k
        )
        documents = self._rank_collection_results(
            document_results, limit=top_k, score_threshold=doc_score_threshold
        )

        learned_qa: list[dict] = []
        if self.learned_collection and self.learned_collection.count() > 0:
            learned_results = self._query_collection(
                self.learned_collection, query_embedding, top_l
            )
            learned_qa = self._rank_collection_results(
                learned_results, limit=top_l, score_threshold=learned_score_threshold
            )

        self._log_ranked_results("documents", documents)
        self._log_ranked_results("learned_qa", learned_qa)
        self._last_document_chunks = documents
        self._last_learned_qa_chunks = learned_qa
        return {"documents": documents, "learned_qa": learned_qa}

    def get_last_document_chunks(self) -> list[dict]:
        return self._last_document_chunks

    def get_last_learned_qa_chunks(self) -> list[dict]:
        return self._last_learned_qa_chunks

    def _embed_and_log(self, query: str):
        query_embedding = self.embedding_manager.generate_embedding(query)
        _log(
            "STEP: QUERY -> EMBEDDING",
            f'Query        : "{query}"',
            f"Model        : {self.embedding_manager.model_name}",
            f"Shape        : {query_embedding.shape}",
            f"First 8 vals : {[round(float(v), 6) for v in query_embedding[:8]]}",
            f"L2 norm      : {float(np.linalg.norm(query_embedding)):.6f}  "
            f"(1.0 = fully normalised)",
        )
        return query_embedding

    @staticmethod
    def _rank_collection_results(
        results: list[dict],
        limit: int,
        score_threshold: float,
    ) -> list[dict]:
        seen_ids: set = set()
        ranked: list[dict] = []
        for doc in sorted(results, key=lambda d: d["similarity_score"], reverse=True):
            if doc["id"] in seen_ids:
                continue
            seen_ids.add(doc["id"])
            if doc["similarity_score"] < score_threshold:
                continue
            ranked.append({**doc, "rank": len(ranked) + 1})
            if len(ranked) >= limit:
                break
        return ranked

    @staticmethod
    def _log_ranked_results(collection_name: str, chunks: list[dict]) -> None:
        logger.debug(
            f"\n  Ranked {len(chunks)} result(s) from {collection_name} "
            f"after within-collection dedup/threshold filter:"
        )
        for i, doc in enumerate(chunks):
            src = doc["metadata"].get("source", "?")
            logger.debug(
                f"    {collection_name}[{i}] - "
                f"score: {doc['similarity_score']:.4f}  [{src}]"
            )
            preview = doc["content"].replace("\n", " ")[:120]
            logger.debug(f"            preview: {preview}...")

    def _query_collection(
        self,
        collection: chromadb.Collection,
        query_embedding,
        top_k: int,
    ) -> list[dict]:
        collection_name = collection.name
        logger.debug(f"  [retriever] querying collection '{collection_name}'")
        try:
            t0 = time.perf_counter()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _executor:
                _future = _executor.submit(
                    collection.query,
                    query_embeddings=[query_embedding.tolist()],
                    n_results=min(top_k, collection.count()),
                    include=["documents", "metadatas", "distances"],
                )
                try:
                    results = _future.result(timeout=RETRIEVAL_TIMEOUT_SECONDS)
                except concurrent.futures.TimeoutError:
                    raise RetrievalTimeoutError(collection_name, RETRIEVAL_TIMEOUT_SECONDS)
            logger.debug(
                f"  [retriever] collection '{collection_name}' retrieval took "
                f"{time.perf_counter() - t0:.3f}s"
            )
        except RetrievalTimeoutError as e:
            logger.error(
                f"  [retriever] collection '{e.collection_name}' did not respond within "
                f"{e.timeout:.0f}s (RETRIEVAL_TIMEOUT_SECONDS={RETRIEVAL_TIMEOUT_SECONDS})"
                f" — skipping retrieval."
            )
            return []
        except Exception:
            logger.warning("[retriever] collection query failed", exc_info=True)
            return []

        docs = []
        if results and results.get("documents") and results["documents"][0]:
            for doc, meta, dist, uid in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
                results["ids"][0],
            ):
                docs.append(
                    {
                        "id": uid,
                        "content": doc,
                        "metadata": meta,
                        "similarity_score": 1 - dist,
                        "distance": dist,
                    }
                )
        return docs
