# app/api/routes/search.py
"""检索接口：结构化返回重写信息与命中片段（供检索调试页/评测/调用方）。"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import DbDep, RuntimeDep, UserDep
from app.schemas.doc import SearchResponse
from app.services.retrieval_service import SearchService

router = APIRouter(tags=["检索"])


@router.get("/search", response_model=SearchResponse)
def search(
    db: DbDep,
    runtime: RuntimeDep,
    _: UserDep,
    q: str = Query(..., min_length=1, max_length=500, description="问题/关键词"),
    top_k: int = Query(5, ge=1, le=20),
) -> dict:
    ctx = SearchService(runtime).search(db, q, top_k=top_k)
    hits = [
        {
            "chunk_id": it.chunk_id,
            "rank": it.rank,
            "score": it.rerank_score,
            "title": it.meta.title,
            "doc_code": it.meta.doc_code,
            "doc_type": it.meta.doc_type,
            "section_path": it.meta.section_path,
            "snippet": it.text[:200],
            "text": it.text,
            "document_id": it.meta.document_id,
            "version_id": it.meta.version_id,
        }
        for it in ctx.items
    ]
    return {
        "question": ctx.question,
        "rewritten": ctx.rewrite.summary() if ctx.rewrite else {},
        "hits": hits,
        "latency_ms": ctx.latency_ms,
        "store_count": ctx.store_count,
    }
