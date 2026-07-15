import logging
import uuid
from datetime import datetime, timezone

from pymongo import DESCENDING
from pymongo.errors import DuplicateKeyError

from app_workflow.services.db import interactions_col, thumbdowns_col, failed_variants_col, get_client
from app_workflow.config import MIN_FEEDBACK_LEN

logger = logging.getLogger(__name__)

__all__ = ["FeedbackStore", "MIN_FEEDBACK_LEN"]


class FeedbackStore:
    def __init__(self):
        self._interactions = interactions_col()
        self._thumbdowns = thumbdowns_col()
        self._failed_variants = failed_variants_col()

    @staticmethod
    def _stored_chunks(chunks: list[dict] | None) -> list[dict]:
        return [
            {
                "content": chunk.get("content", ""),
                "source": chunk.get(
                    "source",
                    (chunk.get("metadata") or {}).get("source", "?"),
                ),
            }
            for chunk in (chunks or [])[:3]
            if chunk.get("content")
        ]

    @staticmethod
    def _split_legacy_chunks(chunks: list[dict] | None) -> tuple[list[dict], list[dict]]:
        documents: list[dict] = []
        learned_qa: list[dict] = []
        for chunk in chunks or []:
            source = chunk.get(
                "source",
                (chunk.get("metadata") or {}).get("source", "?"),
            )
            target = learned_qa if source == "learned_qa" else documents
            target.append(chunk)
        return documents, learned_qa

    # ── Write ────────────────────────────────────────────────────────────────

    def log(
        self,
        query: str,
        answer: str,
        sources: list[dict],
        quality: str,           # "OK" | "USER_THUMBSDOWN" | a grounding-judge verdict
                                 # (e.g. "PARTIALLY_FABRICATED", "OVERCLAIMED", "OFF_TOPIC", "UNKNOWN")
        document_retrieved_chunks: list[dict] | None = None,
        learned_qa_retrieved_chunks: list[dict] | None = None,
        retrieved_chunks: list[dict] | None = None,
        request_id: str = "",
        variants: list[dict] | None = None,
    ) -> None:
        if (
            retrieved_chunks is not None
            and document_retrieved_chunks is None
            and learned_qa_retrieved_chunks is None
        ):
            document_retrieved_chunks, learned_qa_retrieved_chunks = (
                self._split_legacy_chunks(retrieved_chunks)
            )

        record: dict = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id or str(uuid.uuid4()),
            "query": query,
            "answer": answer,
            "quality": quality,
            "sources": sources,
            "document_chunks": self._stored_chunks(document_retrieved_chunks),
            "learned_qa_chunks": self._stored_chunks(learned_qa_retrieved_chunks),
            "variants": variants or [],
        }

        try:
            self._interactions.insert_one(record)
        except DuplicateKeyError:
            logger.warning(
                "Duplicate interaction log skipped (node retry): request_id=%s",
                request_id,
            )
            return
        logger.debug(
            "Interaction logged to MongoDB: request_id=%s quality=%s",
            request_id, quality,
        )

    # ── Read ─────────────────────────────────────────────────────────────────

    def load_all(self) -> list[dict]:
        return [
            {k: v for k, v in doc.items() if k != "_id"}
            for doc in self._interactions.find({})
        ]

    def count(self) -> int:
        return self._interactions.count_documents({})

    def count_good(self) -> int:
        return self._interactions.count_documents({"quality": "OK"})

    def load_good(self, limit: int | None = None) -> list[dict]:
        if limit:
            docs = list(
                self._interactions.find({"quality": "OK"}, {"_id": 0})
                .sort("ts", DESCENDING).limit(limit)
            )
            return list(reversed(docs))
        return list(self._interactions.find({"quality": "OK"}, {"_id": 0}))

    # ── User feedback ─────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_query(q: str) -> str:
        return q.lower().strip()

    def mark_last_bad(
        self,
        feedback: str = "",
        variants: list[dict] | None = None,
    ) -> bool:
        last = self._interactions.find_one(sort=[("ts", DESCENDING)])
        if not last:
            return False

        feedback_clean = (feedback or "").strip()
        store_thumbdown = feedback_clean and len(feedback_clean) >= MIN_FEEDBACK_LEN

        with get_client().start_session() as session:
            with session.start_transaction():
                self._interactions.update_one(
                    {"_id": last["_id"]},
                    {"$set": {"quality": "USER_THUMBSDOWN"}},
                    session=session,
                )
                logger.info(
                    "Interaction marked USER_THUMBSDOWN in MongoDB: request_id=%s",
                    last.get("request_id", ""),
                )
                if store_thumbdown:
                    self._append_thumbdown(
                        original_query=last.get("query", ""),
                        bad_answer=last.get("answer", ""),
                        feedback=feedback_clean,
                        variants=variants or [],
                        request_id=last.get("request_id", ""),
                        session=session,
                    )
        return True

    def _append_thumbdown(
        self,
        original_query: str,
        bad_answer: str,
        feedback: str,
        variants: list[dict],
        request_id: str = "",
        session=None,
    ) -> None:
        normalized = self._normalize_query(original_query)
        doc = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "original_query": original_query,
            "normalized_query": normalized,
            "bad_answer": bad_answer,
            "user_feedback": feedback,
            "variants": [
                {
                    "query": v.get("query", ""),
                    "document_chunks": [
                        {
                            "content": (c.get("content") or "")[:1000],
                            "source": c.get("source", "?"),
                        }
                        for c in (v.get("document_chunks") or v.get("chunks") or [])
                    ],
                    "learned_qa_chunks": [
                        {
                            "content": (c.get("content") or "")[:1000],
                            "source": c.get("source", "?"),
                        }
                        for c in (v.get("learned_qa_chunks") or [])
                    ],
                }
                for v in variants
            ],
        }
        self._thumbdowns.insert_one(doc, session=session)
        logger.info(
            "Thumbdown persisted to MongoDB: request_id=%s normalized_query=%r",
            request_id, normalized,
        )

    def find_thumbdowns_for_query(self, query: str) -> list[dict]:
        norm = self._normalize_query(query)
        return [
            {k: v for k, v in doc.items() if k != "_id"}
            for doc in self._thumbdowns.find({"normalized_query": norm})
        ]

    # ── Failed variants ───────────────────────────────────────────────────────

    def load_failed_variants(self, query: str) -> list[str]:
        norm = self._normalize_query(query)
        doc = self._failed_variants.find_one({"normalized_query": norm})
        return list(doc["variants"]) if doc else []

    def save_failed_variants(self, query: str, variants: list[str]) -> None:
        if not variants:
            return
        norm = self._normalize_query(query)
        self._failed_variants.update_one(
            {"normalized_query": norm},
            {"$addToSet": {"variants": {"$each": variants}}},
            upsert=True,
        )
        logger.info(
            "[FAILED VARIANTS] saved %d variant(s) to MongoDB for norm=%r",
            len(variants), norm,
        )
