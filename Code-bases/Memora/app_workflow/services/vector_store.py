import json
import logging
import os
import uuid
from typing import Any, Dict, List

import numpy as np
import torch
import chromadb

try:
    from .embedding_manager import EmbeddingManager
except ImportError:
    from embedding_manager import EmbeddingManager

logger = logging.getLogger(__name__)


class VectorStore:
    def __init__(
        self,
        collection_name: str = "documents",
        persist_directory: str = "../data/vector_store",
    ):
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self.client = None
        self.collection = None
        self._initialize_store()

    def _initialize_store(self):
        try:
            os.makedirs(self.persist_directory, exist_ok=True)
            self.client = chromadb.PersistentClient(path=self.persist_directory)
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={
                    "Description": "Collection of document embeddings for RAG system.",
                    "hnsw:space": "cosine",
                },
            )
            logger.info(f"Vector store initialized: collection='{self.collection_name}', path='{self.persist_directory}'")
            logger.info(f"Existing documents in collection: {self.collection.count()}")
        except Exception:
            logger.exception(f"Error initializing vector store '{self.collection_name}'")
            raise

    def _sanitize_metadata_value(self, value):
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, list):
            return [
                item if isinstance(item, (str, int, float, bool)) or item is None
                else json.dumps(item, ensure_ascii=True)
                for item in value
            ]
        try:
            return json.dumps(value, ensure_ascii=True)
        except Exception:
            return str(value)

    def _sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        return {str(k): self._sanitize_metadata_value(v) for k, v in metadata.items()}

    def add_document(self, documents: List[Any], embeddings: np.ndarray):
        if len(documents) != len(embeddings):
            raise ValueError("Number of documents and embeddings must match.")
        logger.info(f"Adding {len(documents)} documents to the vector store...")

        ids, metadatas, documents_text, embeddings_list = [], [], [], []

        for i, (doc, embedding) in enumerate(zip(documents, embeddings)):
            ids.append(str(uuid.uuid4()) + f"_{i}")
            metadata = {**dict(doc.metadata), "doc_index": i, "content_length": len(doc.page_content)}
            metadatas.append(self._sanitize_metadata(metadata))
            documents_text.append(doc.page_content)
            embeddings_list.append(embedding.tolist())

        self.collection.add(
            ids=ids,
            embeddings=embeddings_list,
            metadatas=metadatas,
            documents=documents_text,
        )
        logger.info(f"{len(documents)} documents added to vector store.")

    def add_documents_in_batches(
        self,
        pdf_chunks,
        embedding_manager: EmbeddingManager,
        batch_size: int = 128,
    ):
        total = len(pdf_chunks)
        logger.info(f"Adding {total} chunks in batches of {batch_size}")

        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            batch_docs = pdf_chunks[start:end]
            batch_texts = [doc.page_content for doc in batch_docs]

            logger.debug(f"Processing batch {start} - {end - 1}")
            batch_embeddings = embedding_manager.generate_embedding(batch_texts, batch_size=batch_size)
            self.add_document(batch_docs, batch_embeddings)

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        logger.info("All batches inserted successfully.")


from .operation_tracing import instrument_namespace as _instrument_namespace
_instrument_namespace(globals(), "Vector Store")
