import logging
from datetime import datetime, timezone

from pymongo import DESCENDING
from pymongo.errors import DuplicateKeyError

from db import interactions_col, thumbdowns_col, get_client
from config import MIN_FEEDBACK_LEN

logger = logging.getLogger(__name__)

# Re-exported so callers can do: from feedback_store import MIN_FEEDBACK_LEN
__all__ = ["FeedbackStore", "MIN_FEEDBACK_LEN"]


class FeedbackStore:
    def __init__(self):
        self._interactions = interactions_col()
        self._thumbdowns = thumbdowns_col()

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
        quality: str,           # "OK" | "INSUFFICIENT" | "USER_THUMBSDOWN"
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

        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
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
            # Fetch last `limit` records in chronological order
            docs = list(
                self._interactions.find({"quality": "OK"}, {"_id": 0})
                .sort("ts", DESCENDING).limit(limit)
            )
            return list(reversed(docs))
        return list(self._interactions.find({"quality": "OK"}, {"_id": 0}))

    # ── User feedback ──────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_query(q: str) -> str:
        return q.lower().strip()

    def mark_last_bad(
        self,
        feedback: str = "",
        variants: list[dict] | None = None,
    ) -> bool:
        """
        Update the last interaction's quality to USER_THUMBSDOWN.

        If `feedback` meets the minimum-length threshold, also persist a
        structured thumbdown entry with the query variants and retrieved chunks.
        Both writes are wrapped in a single MongoDB transaction so they either
        both commit or both roll back.
        """
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

    def mark_bad(self, request_id: str, feedback: str = "") -> bool:
        """Mark a specific interaction as USER_THUMBSDOWN by request_id (MongoDB lookup)."""
        doc = self._interactions.find_one({"request_id": request_id})
        if not doc:
            logger.warning("mark_bad: request_id=%s not found in MongoDB.", request_id)
            return False

        feedback_clean = (feedback or "").strip()
        store_thumbdown = feedback_clean and len(feedback_clean) >= MIN_FEEDBACK_LEN

        with get_client().start_session() as session:
            with session.start_transaction():
                self._interactions.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"quality": "USER_THUMBSDOWN"}},
                    session=session,
                )
                logger.info("Interaction marked USER_THUMBSDOWN in MongoDB: request_id=%s", request_id)
                if store_thumbdown:
                    self._append_thumbdown(
                        original_query=doc.get("query", ""),
                        bad_answer=doc.get("answer", ""),
                        feedback=feedback_clean,
                        variants=doc.get("variants", []),
                        request_id=request_id,
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
        """Return all prior thumbdown entries whose normalized query matches `query`."""
        norm = self._normalize_query(query)
        return [
            {k: v for k, v in doc.items() if k != "_id"}
            for doc in self._thumbdowns.find({"normalized_query": norm})
        ]
