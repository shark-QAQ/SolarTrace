# app/models/entities.py
"""SQLAlchemy ORM 实体。

分层原则：实体只承载持久化字段与轻量关系，不含业务逻辑；
业务规则集中在 services/ 层，检索 DTO 见 retrieval/types.py。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _now() -> datetime:
    return datetime.utcnow()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now, nullable=False
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="viewer", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Document(Base, TimestampMixin):
    """知识库文档（逻辑文档，一个文档可含多个版本）。"""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    doc_code: Mapped[str] = mapped_column(String(128), nullable=False, default="", index=True)
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False, default="other", index=True)
    issuing_body: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    issue_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", index=True)
    current_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_file_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    versions: Mapped[list[DocVersion]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocVersion.id"
    )


class DocVersion(Base, TimestampMixin):
    """文档版本。

    发布版本即建索引：所有块的向量 id 均带 ``version_id`` 命名空间，
    实现『退稿即清理向量、重发即原子重建』，保证索引与文档库一致。
    """

    __tablename__ = "doc_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_no", name="uq_doc_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", index=True)
    source_file_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    file_checksum: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    document: Mapped[Document] = relationship(back_populates="versions")


class QaLog(Base):
    """问答日志：用于审计、评测样本回填与效果复盘。"""

    __tablename__ = "qa_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    rewritten_query: Mapped[str] = mapped_column(Text, nullable=False, default="")
    answer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sources: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    grounded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    feedback: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1 有帮助 / -1 无帮助
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False, index=True)


class EvalSet(Base):
    """评测集（问题 → 期望命中的文号/条款/关键词）。"""

    __tablename__ = "eval_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    cases: Mapped[list[EvalCase]] = relationship(
        back_populates="eval_set", cascade="all, delete-orphan"
    )


class EvalCase(Base):
    __tablename__ = "eval_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    eval_set_id: Mapped[int] = mapped_column(
        ForeignKey("eval_sets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    golden_doc_codes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    golden_keywords: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    eval_set: Mapped[EvalSet] = relationship(back_populates="cases")


class EvalRun(Base):
    """一次评测执行的结果快照（含逐条明细，便于回归对比）。"""

    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    eval_set_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    case_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hit_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    hit_rate_top1: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    context_recall: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # 引用准确率：生成答案的 [n] 所指向文号中，属于黄金文号的占比。
    # 注意：这是「引用查准」，不校验论断是否被上下文支撑（非 RAGAS 的 faithfulness）。
    citation_precision: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    details: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False, index=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class IndexOp(Base):
    """索引操作流水（发布/重建/归档/对账），支撑一致性审计与断点修复。"""

    __tablename__ = "index_ops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    document_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok", index=True)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False, index=True)


class AuditLog(Base):
    """审计留痕：关键写操作与登录，资源与动作可追溯。"""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    resource_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    ip: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False, index=True)
