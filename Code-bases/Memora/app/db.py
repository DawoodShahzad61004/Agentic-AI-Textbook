import logging
import os

from pymongo import MongoClient, ASCENDING

logger = logging.getLogger(__name__)

_client: MongoClient | None = None
_indexes_ensured = False


def get_client() -> MongoClient:
    global _client
    if _client is None:
        uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        _client = MongoClient(uri)
        # Log without exposing credentials in the URI
        display = uri.split("@")[-1] if "@" in uri else uri
        logger.info("MongoDB client initialized (host=%s)", display)
    return _client


def get_db():
    db_name = os.getenv("MONGODB_DB_NAME", "rag_db")
    return get_client()[db_name]


def _ensure_indexes() -> None:
    global _indexes_ensured
    if _indexes_ensured:
        return
    db = get_db()
    db["feedback_interactions"].create_index([("ts", ASCENDING)])
    db["feedback_interactions"].create_index([("request_id", ASCENDING)], unique=True)
    db["user_thumbdowns"].create_index([("normalized_query", ASCENDING)])
    db["failed_variants"].create_index([("normalized_query", ASCENDING)], unique=True)
    _indexes_ensured = True
    logger.info("MongoDB indexes ensured.")


def interactions_col():
    _ensure_indexes()
    return get_db()["feedback_interactions"]


def thumbdowns_col():
    _ensure_indexes()
    return get_db()["user_thumbdowns"]


def failed_variants_col():
    _ensure_indexes()
    return get_db()["failed_variants"]
