import hashlib
import logging
import os
from pathlib import Path

import chromadb
from langchain_groq import ChatGroq

from .embedding_manager import EmbeddingManager
from .feedback_store import FeedbackStore
from .fix_llm_output import fix_llm_output, _parse_to_python
from .learned_qa_store import get_or_create_learned_qa_collection
from .llm_caller import llm_invoke

logger = logging.getLogger(__name__)

from app_workflow.config import (
    VECTOR_STORE_PATH, 
    LEARNED_COLLECTION,
    ENABLE_QA_PAIR_GENERATION,
    ENABLE_QA_PAIR_OUTPUT_FIX,
    ENABLE_GLOBAL_LLM_OUTPUT_FIX,
)

from .prompts import DISTILL_PROMPT, _THICK, _THIN

def _stable_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]

class SelfLearner:
    def __init__(
        self,
        embedding_manager: EmbeddingManager,
        llm: ChatGroq,
        feedback_store: FeedbackStore,
        vector_store_path: str = VECTOR_STORE_PATH,
        learn_every_n: int = 5,
    ):
        self.embedding_manager = embedding_manager
        self.llm = llm
        self.feedback_store = feedback_store
        self.learn_every_n = learn_every_n

        self.client = chromadb.PersistentClient(path=vector_store_path)
        self.collection = get_or_create_learned_qa_collection(self.client)
        logger.debug(f"[SelfLearner] learned_qa collection has {self.collection.count()} entries.")

    def should_learn(self) -> bool:
        good = self.feedback_store.count_good()
        return good > 0 and good % self.learn_every_n == 0

    def run_distillation(self, batch_size: int = 10, config=None) -> int:
        if not ENABLE_QA_PAIR_GENERATION:
            logger.warning("\n[SelfLearner] QA-pair generation is disabled; skipping distillation.")
            return 0

        logger.debug(f"\n{_THICK}")
        logger.info(f"  DISTILLATION STARTED")
        logger.debug(_THICK)
        logger.debug(f"  batch_size           : {batch_size}")
        logger.debug(f"  learned_qa (before)  : {self.collection.count()} entries")
        logger.debug(_THICK)

        interactions = self.feedback_store.load_good(limit=batch_size)

        logger.debug(f"\n{_THIN}")
        logger.debug(f"  STEP 1 — LOAD GOOD INTERACTIONS FROM FEEDBACK STORE")
        logger.debug(_THIN)
        if not interactions:
            logger.warning(f"  No good interactions found — nothing to distil.")
            logger.debug(_THIN)
            return 0

        logger.info(f"  Loaded {len(interactions)} interaction(s):")
        for idx, ia in enumerate(interactions):
            logger.debug(f"\n  [{idx}] ts={ia.get('ts', '?')}  quality={ia.get('quality', '?')}")
            logger.debug(f"       query   : \"{ia['query']}\"")
            logger.debug(f"       answer  : {ia['answer'][:200]}{'...' if len(ia['answer']) > 200 else ''}")
            document_chunks = ia.get("document_chunks", ia.get("chunks", []))
            learned_qa_chunks = ia.get("learned_qa_chunks", [])
            logger.debug(
                f"       chunks  : documents={len(document_chunks)}, "
                f"learned_qa={len(learned_qa_chunks)}"
            )
        logger.debug(_THIN)

        total_added = 0
        for idx, interaction in enumerate(interactions):
            logger.debug(f"\n{_THICK}")
            logger.info(f"  PROCESSING INTERACTION {idx + 1} / {len(interactions)}")
            logger.debug(_THICK)
            logger.debug(f"  query : \"{interaction['query']}\"")
            logger.debug(_THICK)

            pairs = self._generate_qa_pairs(interaction, config=config)
            added = self._upsert_pairs(pairs, interaction)
            total_added += added

            logger.info(f"\n  [INTERACTION {idx + 1} RESULT] {added} new pair(s) added to learned_qa")

        logger.debug(f"\n{_THICK}")
        logger.info(f"  DISTILLATION COMPLETE")
        logger.debug(_THICK)
        logger.debug(f"  Total new QA pairs added : {total_added}")
        logger.debug(f"  learned_qa (after)       : {self.collection.count()} entries")
        logger.debug(_THICK)

        return total_added

    def _generate_qa_pairs(self, interaction: dict, config=None) -> list[dict]:
        learned_qa_chunks = interaction.get("learned_qa_chunks", [])
        document_chunks = interaction.get("document_chunks", interaction.get("chunks", []))
        chunks_text = "\n---\n".join([
            *[
                f"[LEARNED QA - HIGH PRIORITY] [{c['source']}] {c['content'][:400]}"
                for c in learned_qa_chunks
            ],
            *[
                f"[DOCUMENT] [{c['source']}] {c['content'][:400]}"
                for c in document_chunks
            ],
        ])
        if not chunks_text:
            chunks_text = interaction["answer"]

        prompt = DISTILL_PROMPT.format(
            query=interaction["query"],
            answer=interaction["answer"],
            chunks=chunks_text,
        )

        logger.debug(f"\n{_THIN}")
        logger.debug(f"  STEP 2 — DISTILLATION PROMPT SENT TO LLM")
        logger.debug(_THIN)
        logger.debug(prompt)
        logger.debug(_THIN)

        try:
            result = llm_invoke(
                self.llm,
                [{"role": "user", "content": prompt}],
                caller_tag="DISTILL-QA",
                config=config,
            )
            if not result.ok:
                logger.error(
                    f"\n  [ERROR] LLM distillation failed "
                    f"({result.error_kind.name}): {result.error_message}"
                )
                logger.debug(_THIN)
                return []
            raw = result.content

            logger.debug(f"\n{_THIN}")
            logger.debug(f"  STEP 3 — RAW LLM RESPONSE")
            logger.debug(_THIN)
            logger.debug(raw)
            logger.debug(_THIN)

            if ENABLE_QA_PAIR_OUTPUT_FIX and ENABLE_GLOBAL_LLM_OUTPUT_FIX:
                llm_result, _ok = fix_llm_output("distill_qa", raw, llm=self.llm, config=config)

                if _ok and isinstance(llm_result, list):
                    logger.debug(f"\n  STEP 4 — PARSED QA Pairs ({len(llm_result)} pair(s))")
                    logger.debug(_THIN)
                else:
                    logger.error(f"\n  [ERROR] Failed to parse LLM response into valid QA pairs.")
                    logger.debug(f"  Response was: {raw}")
                    logger.debug(_THIN)
                    return []
            else:
                llm_result = _parse_to_python(raw)
            if not isinstance(llm_result, list):
                logger.warning(f"\n  [ERROR] Failed to parse LLM response into valid QA pairs.")
                logger.debug(f"  Response was: {raw}")
                logger.debug(_THIN)
                return []
            llm_result = [p for p in llm_result if isinstance(p, dict)]
            for i, p in enumerate(llm_result):
                logger.debug(f"  Pair {i}:")
                logger.debug(f"    question : \"{p.get('question', '')}\"")
                logger.debug(f"    answer   : {p.get('answer', '')[:300]}{'...' if len(p.get('answer','')) > 300 else ''}")
            logger.debug(_THIN)
            return llm_result

        except Exception:
            logger.exception("LLM distillation failed")
            logger.debug(_THIN)

        return []

    def _upsert_pairs(self, pairs: list[dict], interaction: dict) -> int:
        if not pairs:
            logger.warning(f"\n  [UPSERT] No pairs to upsert — skipping.")
            return 0

        texts, ids, metadatas = [], [], []
        for pair in pairs:
            q = pair.get("question", "").strip()
            a = pair.get("answer", "").strip()
            if not q or not a:
                continue
            combined = f"Q: {q}\nA: {a}"
            uid = _stable_id(combined)
            texts.append(combined)
            ids.append(uid)
            metadatas.append({
                "source": "learned_qa",
                "original_query": interaction["query"][:200],
                "question": q[:300],
                "answer": a[:500],
                "interaction_ts": interaction.get("ts", ""),
            })

        if not texts:
            logger.warning(f"\n  [UPSERT] All pairs were empty after validation — skipping.")
            return 0

        logger.debug(f"\n{_THIN}")
        logger.debug(f"  STEP 5 — GENERATING EMBEDDINGS FOR {len(texts)} QA TEXT(S)")
        logger.debug(_THIN)
        for i, t in enumerate(texts):
            logger.debug(f"  [{i}] \"{t[:120]}{'...' if len(t) > 120 else ''}\"")
        logger.debug(_THIN)

        embeddings = self.embedding_manager.generate_embedding(texts)

        logger.debug(f"\n  STEP 5 RESULT — Embeddings generated")
        logger.debug(_THIN)
        logger.debug(f"  Shape  : {embeddings.shape}")
        for i in range(len(texts)):
            import numpy as np
            norm = float(np.linalg.norm(embeddings[i]))
            logger.debug(f"  [{i}] first 8 vals : {[round(float(v), 6) for v in embeddings[i][:8]]}")
            logger.debug(f"       L2 norm      : {norm:.6f}")
        logger.debug(_THIN)

        existing_ids = set(self.collection.get(ids=ids)["ids"])
        new_mask = [i for i, uid in enumerate(ids) if uid not in existing_ids]

        logger.debug(f"\n{_THIN}")
        logger.debug(f"  STEP 6 — DEDUPLICATION CHECK")
        logger.debug(_THIN)
        logger.debug(f"  Candidate IDs  : {ids}")
        logger.debug(f"  Already stored : {list(existing_ids)}")
        logger.debug(f"  New (to insert): {[ids[i] for i in new_mask]}")
        logger.debug(_THIN)

        if new_mask:
            self.collection.add(
                ids=[ids[i] for i in new_mask],
                embeddings=[embeddings[i].tolist() for i in new_mask],
                documents=[texts[i] for i in new_mask],
                metadatas=[metadatas[i] for i in new_mask],
            )
            logger.info(f"\n  STEP 7 — UPSERT COMPLETE")
            logger.debug(_THIN)
            logger.info(f"  {len(new_mask)} new QA pair(s) added to '{LEARNED_COLLECTION}' collection.")
            for i in new_mask:
                logger.debug(f"    id={ids[i]}  doc=\"{texts[i][:100]}...\"")
            logger.debug(_THIN)
        else:
            logger.warning(f"\n  STEP 7 — UPSERT SKIPPED (all {len(ids)} pair(s) already exist in collection)")

        return len(new_mask)
