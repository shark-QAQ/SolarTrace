# app/retrieval/bm25.py
"""BM25 词法召回索引。

作为混合检索的词法一路（对应简历中 BM25 + RRF），
与稠密向量路互补：精准命中条款编号/文号/关键词。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rank_bm25 import BM25Okapi

from app.retrieval.text_utils import tokenize


@dataclass
class BM25Doc:
    chunk_id: str
    text: str
    meta: dict[str, Any]
    tokens: list[str]


class BM25Index:
    """内存 BM25 索引；发布/归档时整库重建保证一致。"""

    def __init__(self) -> None:
        self._docs: list[BM25Doc] = []
        self._bm25: BM25Okapi | None = None
        self._by_id: dict[str, BM25Doc] = {}

    @property
    def size(self) -> int:
        return len(self._docs)

    def rebuild(self, docs: list[BM25Doc]) -> None:
        """全量重建（与向量库同源，仅在事务成功提交后调用）。"""
        self._docs = docs
        self._by_id = {d.chunk_id: d for d in docs}
        self._bm25 = BM25Okapi([d.tokens for d in docs]) if docs else None

    def search(self, query: str, top_k: int) -> list[tuple[str, float]]:
        """返回 [(chunk_id, bm25_score), ...]，按分数降序。"""
        tokens = tokenize(query)
        if not tokens or self._bm25 is None or not self._docs:
            return []
        scores = self._bm25.get_scores(tokens)
        order = sorted(range(len(self._docs)), key=lambda i: scores[i], reverse=True)
        results: list[tuple[str, float]] = []
        for i in order:
            if scores[i] <= 0:
                break
            results.append((self._docs[i].chunk_id, float(scores[i])))
            if len(results) >= top_k:
                break
        return results

    def get(self, chunk_id: str) -> BM25Doc | None:
        return self._by_id.get(chunk_id)

    def doc_text(self, chunk_id: str) -> str:
        doc = self._by_id.get(chunk_id)
        return doc.text if doc else ""
