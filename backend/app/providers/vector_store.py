# app/providers/vector_store.py
"""向量库适配层（Vector Store）。

- ChromaStore：本地持久（默认，零外部依赖，适合演示与单机交付）。
- QdrantStore：REST 直连（生产/分布式，经 docker-compose 起服务）。
端口协议只暴露 add/delete/query/count，metadata 过滤统一为单层 eq，
屏蔽各库差异；版本清理以 ``version_id`` 等值过滤实现。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.core.errors import VectorStoreUnavailable

logger = logging.getLogger(__name__)


@dataclass
class VectorEntry:
    vector_id: str
    vector: list[float]
    text: str
    metadata: dict[str, Any]


@dataclass
class VectorHit:
    vector_id: str
    text: str
    metadata: dict[str, Any]
    score: float  # 余弦相似度 [0,1]


class VectorStore(Protocol):
    dimension: int

    def add(self, entries: list[VectorEntry]) -> None: ...

    def delete(self, vector_ids: list[str]) -> None: ...

    def delete_by(self, filter_eq: dict[str, Any]) -> None: ...

    def query(
        self, vector: list[float], top_k: int, filter_eq: dict[str, Any] | None = None
    ) -> list[VectorHit]: ...

    def all(self, filter_eq: dict[str, Any] | None = None) -> list[VectorHit]: ...

    def count(self, filter_eq: dict[str, Any] | None = None) -> int: ...


def _cos(score: float) -> float:
    """各库 distance 统一为 cosine 相似度 [0,1]（客户端自行保证归一）。"""
    return max(0.0, min(1.0, score))


class ChromaStore:
    """基于 ChromaDB 的持久向量库（支持余弦距离与等值过滤）。"""

    def __init__(self, settings: Settings) -> None:
        import chromadb

        self._client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        self._col = self._client.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )
        self.dimension = settings.vector_dimension

    def add(self, entries: list[VectorEntry]) -> None:
        if not entries:
            return
        self._col.add(
            ids=[e.vector_id for e in entries],
            embeddings=[e.vector for e in entries],
            documents=[e.text for e in entries],
            metadatas=[e.metadata for e in entries],
        )

    def delete(self, vector_ids: list[str]) -> None:
        if not vector_ids:
            return
        self._col.delete(ids=vector_ids)

    def delete_by(self, filter_eq: dict[str, Any]) -> None:
        try:
            self._col.delete(where=filter_eq)
        except Exception as exc:  # noqa: BLE001
            logger.warning("按元数据清理失败: %s", exc)

    def query(
        self, vector: list[float], top_k: int, filter_eq: dict[str, Any] | None = None
    ) -> list[VectorHit]:
        res = self._col.query(
            query_embeddings=[vector],
            n_results=top_k,
            where=filter_eq or None,
            include=["documents", "metadatas", "distances"],
        )
        hits: list[VectorHit] = []
        if not res or not res["ids"] or not res["ids"][0]:
            return hits
        for i, vid in enumerate(res["ids"][0]):
            hits.append(
                VectorHit(
                    vector_id=str(vid),
                    text=str(res["documents"][0][i]),
                    metadata=dict(res["metadatas"][0][i]),
                    score=float(_cos(1 - res["distances"][0][i])),
                )
            )
        return hits

    def all(self, filter_eq: dict[str, Any] | None = None) -> list[VectorHit]:
        res = self._col.get(where=filter_eq or None, include=["documents", "metadatas"])
        hits: list[VectorHit] = []
        if not res or not res["ids"]:
            return hits
        metas = res.get("metadatas") or [{} for _ in res["ids"]]
        docs = res.get("documents") or ["" for _ in res["ids"]]
        for i, vid in enumerate(res["ids"]):
            hits.append(
                VectorHit(
                    vector_id=str(vid),
                    text=str(docs[i]),
                    metadata=dict(metas[i] or {}),
                    score=1.0,
                )
            )
        return hits

    def count(self, filter_eq: dict[str, Any] | None = None) -> int:
        try:
            return int(self._col.count(where=filter_eq or None))
        except Exception:  # noqa: BLE001
            return int(self._col.count())


def _numeric_id(vector_id: str) -> int:
    """把任意字符串向量 id 稳定映射到 Qdrant int64 数值 id。"""
    digest = __import__("hashlib").sha256(vector_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF


class QdrantStore:
    """通过 REST API 直连 Qdrant（生产模式；由 docker-compose 提供服务）。"""

    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.qdrant_url.rstrip("/")
        self.collection = settings.qdrant_collection
        self.dimension = settings.vector_dimension
        self.headers = (
            {"api-key": settings.qdrant_api_key} if settings.qdrant_api_key else {}
        )
        self._client = httpx.Client(timeout=20.0)
        self._ensure_collection()

    def _req(self, method: str, path: str, **kw: Any) -> Any:
        try:
            resp = self._client.request(method, f"{self.base_url}{path}", headers=self.headers, **kw)
            resp.raise_for_status()
            return resp.json()
        except VectorStoreUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreUnavailable(f"Qdrant 不可用: {exc}") from exc

    def _ensure_collection(self) -> None:
        info = self._req("GET", f"/collections/{self.collection}")
        if info.get("status") != "green" and info.get("result"):
            return
        # 不存在则创建
        try:
            self._req(
                "PUT",
                f"/collections/{self.collection}",
                json={
                    "vectors": {"size": self.dimension, "distance": "Cosine"},
                    "optimizers_config": {"indexing_threshold": 200},
                },
            )
        except VectorStoreUnavailable:
            raise

    def _to_points(self, entries: list[VectorEntry]) -> list[dict[str, Any]]:
        return [
            {
                "id": _numeric_id(e.vector_id),
                "vector": e.vector,
                "payload": {"vector_id": e.vector_id, "text": e.text, **e.metadata},
            }
            for e in entries
        ]

    def add(self, entries: list[VectorEntry]) -> None:
        if not entries:
            return
        self._req(
            "PUT",
            f"/collections/{self.collection}/points",
            json={"points": self._to_points(entries)},
        )

    def delete(self, vector_ids: list[str]) -> None:
        if not vector_ids:
            return
        ids = [_numeric_id(v) for v in vector_ids]
        self._req(
            "POST",
            f"/collections/{self.collection}/points/delete",
            json={"points": ids},
        )

    def delete_by(self, filter_eq: dict[str, Any]) -> None:
        must = [
            {"key": k, "match": {"value": v}}
            for k, v in filter_eq.items()
        ]
        self._req(
            "POST",
            f"/collections/{self.collection}/points/delete",
            json={"filter": {"must": must}},
        )

    def query(
        self, vector: list[float], top_k: int, filter_eq: dict[str, Any] | None = None
    ) -> list[VectorHit]:
        body: dict[str, Any] = {"vector": vector, "limit": top_k, "with_payload": True}
        if filter_eq:
            body["filter"] = {
                "must": [{"key": k, "match": {"value": v}} for k, v in filter_eq.items()]
            }
        data = self._req("POST", f"/collections/{self.collection}/points/search", json=body)
        hits: list[VectorHit] = []
        for pt in data.get("result", []):
            payload = pt.get("payload", {})
            hits.append(
                VectorHit(
                    vector_id=str(payload.get("vector_id", "")),
                    text=str(payload.get("text", "")),
                    metadata=dict(payload),
                    score=float(_cos(pt.get("score", 0.0))),
                )
            )
        return hits

    def all(self, filter_eq: dict[str, Any] | None = None) -> list[VectorHit]:
        scroll: list[VectorHit] = []
        offset: Any = None
        for _ in range(200):
            body: dict[str, Any] = {"limit": 1000, "with_payload": True}
            if offset is not None:
                body["offset"] = offset
            if filter_eq:
                body["filter"] = {
                    "must": [{"key": k, "match": {"value": v}} for k, v in filter_eq.items()]
                }
            data = self._req("POST", f"/collections/{self.collection}/points/scroll", json=body)
            points = data.get("result", {}).get("points", [])
            for pt in points:
                p = pt.get("payload", {})
                scroll.append(
                    VectorHit(
                        vector_id=str(p.get("vector_id", "")),
                        text=str(p.get("text", "")),
                        metadata=dict(p),
                        score=1.0,
                    )
                )
            nxt = data.get("result", {}).get("next_page_offset")
            if not nxt:
                break
            offset = nxt
        return scroll

    def count(self, filter_eq: dict[str, Any] | None = None) -> int:
        data = self._req("POST", f"/collections/{self.collection}/points/count", json={})
        return int(data.get("result", {}).get("count", 0))


def _normalize_filter(filter_eq: dict[str, Any] | None) -> dict[str, Any] | None:
    """把形如 {"version_id": "5"} 的值还原为 int，便于入库比较。"""
    if not filter_eq:
        return None
    out: dict[str, Any] = {}
    for k, v in filter_eq.items():
        if re.fullmatch(r"-?\d+", str(v)):
            out[k] = int(v)
        else:
            out[k] = v
    return out
