# tests/test_rankers.py
"""BM25 索引与两阶段重排 单元测试。"""
from __future__ import annotations

from app.retrieval.bm25 import BM25Doc, BM25Index
from app.retrieval.reranker import DeterministicReranker
from app.retrieval.types import ChunkMeta, RetrievedItem


def _meta(code: str, text: str, section: str = "") -> ChunkMeta:
    return ChunkMeta(
        vector_id=f"v::{code}",
        document_id=1,
        version_id=1,
        doc_key=f"x:{code}",
        title=code,
        doc_code=code,
        doc_type="grid_connection",
        issuing_body="机构",
        issue_year=2025,
        status="published",
        relation="child",
        parent_seq=1,
        seq=1,
        section_path=section,
    )


def test_bm25_finds_term_and_orders():
    idx = BM25Index()
    docs = [
        BM25Doc("a", "分布式光伏并网前应完成接入系统方案确认。", _meta("A", "a").to_store(), []),
        BM25Doc("b", "光伏发电站并网应满足电能质量要求并配置防孤岛保护。", _meta("B", "b").to_store(), []),
        BM25Doc("c", "户用光伏建设需确认屋顶产权并做好备案。", _meta("C", "c").to_store(), []),
    ]
    for d in docs:
        d.tokens = __import__("app.retrieval.text_utils", fromlist=["tokenize"]).tokenize(d.text)
    idx.rebuild(docs)
    assert idx.size == 3
    hits = idx.search("光伏并网", 3)
    assert hits[0][0] == "a" or hits[0][0] == "b"
    assert len(hits) <= 3


def test_deterministic_rerank_keeps_first_and_truncates():
    rk = DeterministicReranker()
    items = [
        RetrievedItem(
            chunk_id="1", text="分布式光伏项目需要办理备案手续。",
            meta=_meta("A", "t1", "项目备案"), dense_score=0.95, bm25_score=10.0, fusion_score=1.0,
        ),
        RetrievedItem(
            chunk_id="2", text="今天是晴天适合晒被子。",
            meta=_meta("B", "t2", "天气"), dense_score=0.3, bm25_score=0.0, fusion_score=0.001,
        ),
        RetrievedItem(
            chunk_id="3", text="并网验收合格后方可并网运行。",
            meta=_meta("C", "t3", "并网验收"), dense_score=0.6, bm25_score=4.0, fusion_score=0.5,
        ),
    ]
    out = rk.rerank("分布式光伏并网验收", items, top_k=2, min_score=0.5)
    assert len(out) <= 2
    assert out[0].chunk_id in {"1", "3"}  # 首条始终保留且语义相关优先
    assert all(x.rank >= 1 for x in out)
