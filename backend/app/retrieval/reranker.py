# app/retrieval/reranker.py
"""两阶段精排（Reranker）。

召回（RRF 融合选候选）后进入第二阶段精排：
- DeterministicReranker：零成本、可离线复现的启发式精排。以“绝对相关信号”
  （稠密余弦相似度 × 查询词覆盖/文号命中 × BM25 归一得分）计算 relevance 分
  （0–1 量纲），再按 top-k 截断；仅当片段确实与问题无关时才被丢弃。
- CrossEncoderReranker：可选 bge-reranker（配置了 sentence-transformers 与模型时）。
"""
from __future__ import annotations

import logging

from app.core.config import Settings
from app.retrieval.text_utils import ascii_letters, tokenize
from app.retrieval.types import RetrievedItem

logger = logging.getLogger(__name__)

# relevance 权重：语义 / 词法覆盖 / 词法命中（BM25 归一）
_W_DENSE = 0.45
_W_LEX = 0.35
_W_BM25 = 0.20


class DeterministicReranker:
    """启发式第二阶段精排（可解释、可测试）。"""

    def _lexical(self, query_tokens: list[str], item: RetrievedItem) -> float:
        if not query_tokens:
            return 0.0
        text_tokens = tokenize(item.text)
        title_tokens = tokenize(item.meta.title + " " + item.meta.section_path)
        n = len(query_tokens)
        hit = sum(1 for t in query_tokens if t in text_tokens)
        title_hit = sum(1 for t in query_tokens if t in title_tokens)
        cover = hit / n
        # 查询含文号/条款号（如 GB50797 / 19964）时，串匹配加成
        q_ascii = ascii_letters(item.text)
        code_ascii = ascii_letters(item.meta.doc_code)
        code_hit = 1.0 if code_ascii and code_ascii in q_ascii else 0.0
        return min(1.0, cover * 0.7 + title_hit / n * 0.2 + code_hit * 0.1)

    def rerank(
        self,
        query: str,
        items: list[RetrievedItem],
        *,
        top_k: int,
        min_score: float,
        doc_type_hint: str | None = None,
    ) -> list[RetrievedItem]:
        if not items:
            return []
        q_tokens = tokenize(query)
        bm25_max = max((it.bm25_score for it in items), default=0.0) or 1.0
        for it in items:
            lex = self._lexical(q_tokens, it)
            dense = max(0.0, min(1.0, it.dense_score))
            bm = max(0.0, min(1.0, it.bm25_score / bm25_max))
            score = _W_DENSE * dense + _W_LEX * lex + _W_BM25 * bm
            if doc_type_hint and it.meta.doc_type == doc_type_hint:
                score = min(1.0, score + 0.05)  # 软类型提示小加成
            it.rerank_score = round(score, 5)
        ordered = sorted(items, key=lambda x: (x.rerank_score, x.fusion_score), reverse=True)
        out: list[RetrievedItem] = []
        for i, it in enumerate(ordered, start=1):
            # 首条候选无论如何保留，避免“有相关材料却空回复”
            if out and it.rerank_score < min_score:
                continue
            it.rank = i
            out.append(it)
            if len(out) >= top_k:
                break
        return out


class CrossEncoderReranker:
    """可选 bge-reranker（sentence-transformers）两阶段精排。

    环境缺少库/模型时自动回退确定性精排并记录日志，保证链路可用。
    """

    def __init__(self, settings: Settings, fallback: DeterministicReranker | None = None) -> None:
        self.fallback = fallback or DeterministicReranker()
        self._model = None
        self._load_error: str | None = None
        self.model_name = settings.rerank_model_name
        try:
            from sentence_transformers import CrossEncoder  # type: ignore[import-not-found]

            self._model = CrossEncoder(self.model_name)
        except Exception as exc:  # noqa: BLE001
            self._load_error = str(exc)
            logger.warning("CrossEncoder 加载失败，回退确定性精排: %s", exc)

    @property
    def available(self) -> bool:
        return self._model is not None

    def rerank(
        self,
        query: str,
        items: list[RetrievedItem],
        *,
        top_k: int,
        min_score: float,
        doc_type_hint: str | None = None,
    ) -> list[RetrievedItem]:
        if not self.available:
            return self.fallback.rerank(
                query, items, top_k=top_k, min_score=min_score, doc_type_hint=doc_type_hint
            )
        scores = self._model.predict([(query, it.text) for it in items])  # type: ignore[union-attr]
        for it, s in zip(items, scores, strict=False):
            it.rerank_score = round(float(s), 5)
        ordered = sorted(items, key=lambda x: x.rerank_score, reverse=True)
        out: list[RetrievedItem] = []
        for i, it in enumerate(ordered, start=1):
            if out and it.rerank_score < min_score:
                continue
            it.rank = i
            out.append(it)
            if len(out) >= top_k:
                break
        return out


def build_reranker(settings: Settings) -> DeterministicReranker | CrossEncoderReranker:
    backend = (settings.rerank_backend or "auto").lower()
    if backend == "deterministic":
        return DeterministicReranker()
    if backend == "cross_encoder":
        return CrossEncoderReranker(settings)
    # auto：优先确定性，保持默认零外部依赖
    return DeterministicReranker()
