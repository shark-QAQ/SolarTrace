# app/retrieval/types.py
"""检索域内部 DTO。

分块(Chunk)与检索命中(RetrievedItem)贯通 ingest → index → retrieval → qa，
用纯数据模型表达，避免下层与 SQLAlchemy / 具体向量库耦合。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Chunk:
    """一次分块的结果（父块或子块）。"""

    text: str
    meta: ChunkMeta
    relation: str  # ChunkRelation


@dataclass
class ChunkMeta:
    """块级元数据（进向量库的 metadata，同时用于过滤与引用溯源）。"""

    vector_id: str           # 全局唯一 id = f"v{version_id}:{seq}"
    document_id: int
    version_id: int
    doc_key: str             # 由 doc_type/文号/标题 派生的稳定主键（用于回表校验）
    title: str
    doc_code: str
    doc_type: str
    issuing_body: str
    issue_year: int | None
    status: str              # published/archived，检索命中后需回表复核
    relation: str            # parent|child
    parent_seq: int | None
    seq: int
    section_path: str = ""   # 标题感知路径，如 "第3章 电气/3.2 直流系统"
    char_len: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_store(self) -> dict[str, Any]:
        """转换为向量库可存的 metadata（仅标量字段）。"""
        return {
            "vector_id": self.vector_id,
            "document_id": self.document_id,
            "version_id": self.version_id,
            "doc_key": self.doc_key,
            "title": self.title,
            "doc_code": self.doc_code,
            "doc_type": self.doc_type,
            "issuing_body": self.issuing_body,
            "issue_year": self.issue_year if self.issue_year else 0,
            "status": self.status,
            "relation": self.relation,
            "parent_seq": self.parent_seq if self.parent_seq is not None else -1,
            "seq": self.seq,
            "section_path": self.section_path,
            "char_len": self.char_len,
        }

    @classmethod
    def from_store(cls, m: dict[str, Any]) -> ChunkMeta:
        return cls(
            vector_id=str(m.get("vector_id", "")),
            document_id=int(m.get("document_id", -1)),
            version_id=int(m.get("version_id", -1)),
            doc_key=str(m.get("doc_key", "")),
            title=str(m.get("title", "")),
            doc_code=str(m.get("doc_code", "")),
            doc_type=str(m.get("doc_type", "other")),
            issuing_body=str(m.get("issuing_body", "")),
            issue_year=int(m["issue_year"]) if m.get("issue_year") else None,
            status=str(m.get("status", "published")),
            relation=str(m.get("relation", "child")),
            parent_seq=int(m["parent_seq"]) if int(m.get("parent_seq", -1)) >= 0 else None,
            seq=int(m.get("seq", 0)),
            section_path=str(m.get("section_path", "")),
            char_len=int(m.get("char_len", 0)),
        )

    def citation(self) -> str:
        """可读引用串：文号·标题·章节路径。"""
        code = self.doc_code or self.title
        if self.section_path:
            return f"{code}·{self.section_path}"
        return f"{code}·{self.title}"


@dataclass
class RetrievedItem:
    """一次命中的条目：向量/BM25 两路分数 + 融合分 + 重排后排名。"""

    chunk_id: str
    text: str
    meta: ChunkMeta
    dense_score: float = 0.0
    bm25_score: float = 0.0
    fusion_score: float = 0.0
    rerank_score: float = 0.0
    rank: int = 0

    def to_citation(self, index: int) -> dict[str, Any]:
        """生成前端/答案可用的引用对象。"""
        m = self.meta
        return {
            "index": index,
            "chunk_id": self.chunk_id,
            "title": m.title,
            "doc_code": m.doc_code,
            "doc_type": m.doc_type,
            "section_path": m.section_path,
            "text": self.text[:220] + ("…" if len(self.text) > 220 else ""),
            "score": round(self.rerank_score, 4),
        }
