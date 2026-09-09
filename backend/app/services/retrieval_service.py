# app/services/retrieval_service.py
"""混合检索服务：查询改写 → 稠密向量 + BM25 双路召回 → RRF 融合 →
两阶段精排截断 Top-K → 回表校验文档有效性（防引用失效政策）。"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import Document
from app.providers.registry import RagRuntime
from app.retrieval.rewrite import QueryRewriter, RewriteResult
from app.retrieval.types import RetrievedItem
from app.services.rag.keys import doc_key_for

logger = logging.getLogger(__name__)


@dataclass
class SearchContext:
    question: str
    rewrite: RewriteResult = field(default_factory=lambda: None)
    items: list[RetrievedItem] = field(default_factory=list)
    latency_ms: int = 0
    store_count: int = 0

    def citations(self) -> list[dict]:
        return [it.to_citation(i) for i, it in enumerate(self.items, start=1)]


class SearchService:
    def __init__(self, runtime: RagRuntime) -> None:
        self.rt = runtime
        self.rewriter = QueryRewriter()

    def _published_index(self, db: Session) -> dict[str, int]:
        """已发布文档当前版本映射：doc_key -> version_id（回表校验基准）。"""
        docs = db.query(Document).filter(Document.status == "published").all()
        return {
            doc_key_for(
                doc_type=doc.doc_type,
                doc_code=doc.doc_code,
                title=doc.title,
                issuing_body=doc.issuing_body,
            ): doc.current_version_id
            for doc in docs
            if doc.current_version_id
        }

    def search(self, db: Session, question: str, *, top_k: int | None = None) -> SearchContext:
        t0 = time.perf_counter()
        rt = self.rt
        cfg = rt.settings
        rewrite = self.rewriter.rewrite(question)
        top_k = top_k or cfg.rerank_top_k
        valid = self._published_index(db)

        # ---- 双路召回 ----
        vector = rt.embedder.embed([rewrite.expanded_query])[0]
        dense_hits = rt.store.query(vector, cfg.recall_dense_top_k, {"status": "published"})
        bm25_pairs = rt.bm25.search(rewrite.expanded_query, cfg.recall_bm25_top_k)
        bm25_order = [cid for cid, _ in bm25_pairs]
        bm25_scores = dict(bm25_pairs)

        dense_by_id = {h.vector_id: h for h in dense_hits}
        dense_order = [h.vector_id for h in dense_hits]

        pool: dict[str, RetrievedItem] = {}
        for cid in list(dense_order) + [c for c in bm25_order if c not in dense_by_id]:
            if cid in pool:
                continue
            hit = dense_by_id.get(cid)
            text = hit.text if hit else rt.bm25.doc_text(cid)
            meta_raw = hit.metadata if hit else rt.bm25.get(cid).meta if rt.bm25.get(cid) else {}
            if not text or not meta_raw:
                continue
            from app.retrieval.types import ChunkMeta

            meta = ChunkMeta.from_store(meta_raw)
            # 回表校验：当前仍为该文档已发布版本的块
            if valid.get(meta.doc_key) != meta.version_id:
                continue
            item = RetrievedItem(
                chunk_id=cid,
                text=text,
                meta=meta,
                dense_score=hit.score if hit else 0.0,
                bm25_score=bm25_scores.get(cid, 0.0),
            )
            pool[cid] = item

        # ---- RRF 融合 ----
        k = cfg.rrf_k
        for cid, item in pool.items():
            score = 0.0
            if cid in dense_by_id:
                rank = dense_order.index(cid) + 1
                score += 1.0 / (k + rank)
            if cid in bm25_scores:
                rank = bm25_order.index(cid) + 1
                score += 1.0 / (k + rank)
            item.fusion_score = round(score, 6)

        ranked = rt.reranker.rerank(
            rewrite.expanded_query,
            list(pool.values()),
            top_k=top_k,
            min_score=cfg.min_score_keep,
            doc_type_hint=rewrite.doc_type_hint,
        )
        ctx = SearchContext(
            question=question,
            rewrite=rewrite,
            items=ranked,
            store_count=rt.store.count({"status": "published"}),
        )
        ctx.latency_ms = int((time.perf_counter() - t0) * 1000)
        return ctx
