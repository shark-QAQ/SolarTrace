# app/providers/embedder.py
"""嵌入模型适配层。

- OllamaEmbedder：通过 Ollama ``/api/embed`` 调用 bge-m3（生产默认）。
- HashEmbedder：字符级确定性哈希嵌入，供离线/测试环境退避，支持无 GPU 演示。
端口设计：业务层只依赖 ``Embedder`` 协议，便于替换/测试。
"""
from __future__ import annotations

import hashlib
import logging
import math
from typing import Protocol

import httpx

from app.core.config import Settings
from app.core.errors import EmbeddingUnavailable

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OllamaEmbedder:
    """基于 Ollama 的 bge-m3 / bge-large-zh 嵌入。"""

    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.embedding_model
        self.dimension: int = settings.vector_dimension
        self.timeout = settings.embedding_timeout_s
        self.batch_size = settings.embedding_batch_size

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            with httpx.Client(timeout=self.timeout) as client:
                batches: list[list[float]] = []
                for i in range(0, len(texts), self.batch_size):
                    batch = texts[i : i + self.batch_size]
                    resp = client.post(
                        f"{self.base_url}/api/embed",
                        json={"model": self.model, "input": batch},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    embeds: list[list[float]] = data.get("embeddings")
                    if not embeds or len(embeds) != len(batch):
                        raise EmbeddingUnavailable("嵌入服务返回结果数量不符")
                    batches.extend(embeds)
                return batches
        except EmbeddingUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ollama 嵌入调用失败: %s", exc)
            raise EmbeddingUnavailable(f"嵌入服务不可用: {exc}") from exc

    def health(self) -> dict:
        try:
            with httpx.Client(timeout=3) as client:
                r = client.get(f"{self.base_url}/api/tags")
                r.raise_for_status()
                models = [m["name"] for m in r.json().get("models", [])]
            return {"ok": True, "model": self.model, "available": models}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "model": self.model, "error": str(exc)}


class HashEmbedder:
    """字符级局部敏感哈希嵌入（离线退避/测试）。

    相同字符共现越多向量越接近，可支撑无语义模型下的检索逻辑演示与确定性测试。
    """

    def __init__(self, dimension: int = 512) -> None:
        self.dimension = dimension

    def _char_dir(self, ch: str) -> list[float]:
        digest = hashlib.sha256(ch.encode("utf-8")).digest()
        v = [0.0] * self.dimension
        # 用 SHA-256 字节流填充若干维度的正弦分量，形成可复现的伪随机方向
        for i in range(min(64, self.dimension)):
            idx = i % self.dimension
            byte = digest[i % len(digest)]
            v[idx] += math.sin(byte + i * 0.618) * 0.5
        return v

    def _embed_one(self, text: str) -> list[float]:
        counts: dict[str, int] = {}
        for ch in text:
            if not ch.strip():
                continue
            counts[ch] = counts.get(ch, 0) + 1
        v = [0.0] * self.dimension
        for ch, cnt in counts.items():
            d = self._char_dir(ch)
            w = 1.0 + math.log(cnt)
            for i in range(self.dimension):
                v[i] += d[i] * w
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def health(self) -> dict:
        return {"ok": True, "model": "hash-offline", "available": ["hash-offline"]}
