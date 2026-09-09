# app/providers/registry.py
"""运行时组装：按配置构建向量库/嵌入/LLM/重排，供服务层注入（依赖倒置）。

Services 不直接 new 具体适配器，而是接收 RagRuntime —— 便于测试注入
HashEmbedder / FakeLLM / 临时 Chroma。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.core.config import Settings
from app.models.enums import DocStatus
from app.providers.embedder import Embedder, HashEmbedder, OllamaEmbedder
from app.providers.llm import FakeLLM, LLMProvider, OllamaLLM
from app.providers.vector_store import ChromaStore, QdrantStore, VectorStore
from app.retrieval.bm25 import BM25Doc, BM25Index
from app.retrieval.reranker import build_reranker

logger = logging.getLogger(__name__)


@dataclass
class RagRuntime:
    settings: Settings
    store: VectorStore
    embedder: Embedder
    llm: LLMProvider
    bm25: BM25Index
    reranker: Any = field(init=False)

    def __post_init__(self) -> None:
        self.reranker = build_reranker(self.settings)

    # ---- 便捷方法 ----
    def refresh_bm25(self) -> int:
        """从向量库重建 BM25 词法索引（与持久库同源，避免内存态漂移）。"""
        entries = self.store.all({"status": DocStatus.PUBLISHED.value})
        docs: list[BM25Doc] = []
        for e in entries:
            docs.append(BM25Doc(chunk_id=e.vector_id, text=e.text, meta=e.metadata, tokens=[]))
        # 分词批量做，控制耗时
        from app.retrieval.text_utils import tokenize

        for d in docs:
            d.tokens = tokenize(d.text)
        self.bm25.rebuild(docs)
        return len(docs)

    def health(self) -> dict:
        embed = getattr(self.embedder, "health", lambda: {})()
        llm = getattr(self.llm, "health", lambda: {})()
        return {
            "embedder": embed,
            "llm": llm,
            "store_count": self.store.count({"status": DocStatus.PUBLISHED.value}),
            "bm25_size": self.bm25.size,
        }


def build_store(settings: Settings) -> VectorStore:
    backend = (settings.vector_backend or "chroma").lower()
    if backend == "qdrant":
        return QdrantStore(settings)
    return ChromaStore(settings)


def build_embedder(settings: Settings) -> Embedder:
    provider = (settings.embedding_provider or "ollama").lower()
    if provider == "hash":
        return HashEmbedder(settings.vector_dimension)
    return OllamaEmbedder(settings)


def build_llm(settings: Settings) -> LLMProvider:
    provider = (settings.llm_provider or "ollama").lower()
    if provider == "fake":
        return FakeLLM()
    return OllamaLLM(settings)


def build_runtime(settings: Settings | None = None) -> RagRuntime:
    settings = settings or get_runtime_settings()
    store = build_store(settings)
    embedder = build_embedder(settings)
    llm = build_llm(settings)
    runtime = RagRuntime(
        settings=settings,
        store=store,
        embedder=embedder,
        llm=llm,
        bm25=BM25Index(),
    )
    try:
        n = runtime.refresh_bm25()
        logger.info("BM25 索引已重建：%s 个词法片段", n)
    except Exception as exc:  # noqa: BLE001
        logger.warning("启动期 BM25 重建失败（可稍后对账）: %s", exc)
    return runtime


def get_runtime_settings() -> Settings:
    from app.core.config import get_settings

    return get_settings()


# ---------- 应用级运行时单例 ----------
_runtime: RagRuntime | None = None


def get_runtime() -> RagRuntime:
    """FastAPI 依赖：返回应用级运行时（进程内单例）。"""
    global _runtime
    if _runtime is None:
        _runtime = build_runtime()
    return _runtime


def set_runtime(runtime: RagRuntime) -> None:
    """测试注入用。"""
    global _runtime
    _runtime = runtime
