import logging
import uuid

import chromadb
from chromadb.errors import NotFoundError

try:
    from ..config import LEARNED_COLLECTION
except ImportError:
    from app_workflow.config import LEARNED_COLLECTION

logger = logging.getLogger(__name__)


LEARNED_QA_METADATA = {
    "description": "Distilled QA pairs from verified interactions.",
    "hnsw:space": "cosine",
}


def _collection_space(collection) -> str:
    configuration = getattr(collection, "configuration", {}) or {}
    hnsw = configuration.get("hnsw") or {}
    return hnsw.get("space", "")


def _snapshot_collection(collection, batch_size: int) -> list[dict]:
    records: list[dict] = []
    total = collection.count()
    for offset in range(0, total, batch_size):
        batch = collection.get(
            limit=batch_size,
            offset=offset,
            include=["embeddings", "metadatas", "documents"],
        )
        ids = batch.get("ids") or []
        embeddings = batch.get("embeddings")
        metadatas = batch.get("metadatas")
        documents = batch.get("documents")
        for index, uid in enumerate(ids):
            records.append({
                "id": uid,
                "embedding": embeddings[index] if embeddings is not None else None,
                "metadata": metadatas[index] if metadatas is not None else None,
                "document": documents[index] if documents is not None else None,
            })
    return records


def _restore_collection(collection, records: list[dict], batch_size: int) -> None:
    for start in range(0, len(records), batch_size):
        batch = records[start:start + batch_size]
        add_kwargs = {
            "ids": [record["id"] for record in batch],
            "embeddings": [record["embedding"] for record in batch],
        }
        if all(record["metadata"] is not None for record in batch):
            add_kwargs["metadatas"] = [record["metadata"] for record in batch]
        if all(record["document"] is not None for record in batch):
            add_kwargs["documents"] = [record["document"] for record in batch]
        collection.add(**add_kwargs)


def get_or_create_learned_qa_collection(
    client: chromadb.ClientAPI,
    collection_name: str = LEARNED_COLLECTION,
    batch_size: int = 512,
):
    """Return a cosine learned-QA collection, migrating an older L2 index safely."""
    try:
        collection = client.get_collection(name=collection_name)
    except NotFoundError:
        return client.create_collection(
            name=collection_name,
            metadata=LEARNED_QA_METADATA,
        )

    if _collection_space(collection) == "cosine":
        return collection

    records = _snapshot_collection(collection, batch_size)
    backup_name = f"{collection_name}__distance_backup_{uuid.uuid4().hex[:8]}"
    original_metadata = dict(getattr(collection, "metadata", {}) or {})
    target_metadata = {**original_metadata, **LEARNED_QA_METADATA}

    logger.info(
        f"[LearnedQAStore] migrating '{collection_name}' from "
        f"{_collection_space(collection) or 'unknown'} to cosine "
        f"({len(records)} entries)."
    )

    collection.modify(name=backup_name)
    replacement = None
    try:
        replacement = client.create_collection(
            name=collection_name,
            metadata=target_metadata,
        )
        _restore_collection(replacement, records, batch_size)
        if replacement.count() != len(records):
            raise RuntimeError(
                f"learned-QA migration count mismatch: "
                f"expected {len(records)}, restored {replacement.count()}"
            )
        client.delete_collection(name=backup_name)
    except Exception:
        if replacement is not None:
            try:
                client.delete_collection(name=collection_name)
            except NotFoundError:
                pass
        collection.modify(name=collection_name)
        raise

    logger.info(
        f"[LearnedQAStore] learned_qa migration complete: "
        f"{replacement.count()} entries, cosine distance."
    )
    return replacement


from .operation_tracing import instrument_namespace as _instrument_namespace
_instrument_namespace(globals(), "Learned QA Store")
