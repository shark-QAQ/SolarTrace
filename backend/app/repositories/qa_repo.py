# app/repositories/qa_repo.py
"""问答日志 / 索引操作流水 / 审计日志 仓储。"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, IndexOp, QaLog


# ---------- Q&A 日志 ----------
def add_qa_log(
    db: Session,
    *,
    user_id: int | None,
    question: str,
    rewritten_query: str,
    answer: str,
    sources: list[dict],
    model: str,
    latency_ms: int,
    grounded: bool,
) -> QaLog:
    log = QaLog(
        user_id=user_id,
        question=question,
        rewritten_query=rewritten_query,
        answer=answer,
        sources=sources,
        model=model,
        latency_ms=latency_ms,
        grounded=grounded,
    )
    db.add(log)
    db.flush()
    return log


def list_qa_logs(
    db: Session, *, user_id: int | None = None, page: int = 1, page_size: int = 20
) -> tuple[int, list[QaLog]]:
    stmt = select(QaLog)
    count_stmt = select(func.count(QaLog.id))
    if user_id:
        stmt = stmt.where(QaLog.user_id == user_id)
        count_stmt = count_stmt.where(QaLog.user_id == user_id)
    total = int(db.execute(count_stmt).scalar_one())
    rows = db.execute(stmt.order_by(QaLog.id.desc()).offset((page - 1) * page_size).limit(page_size)).scalars()
    return total, list(rows)


def set_feedback(db: Session, log_id: int, feedback: int) -> bool:
    row = db.execute(select(QaLog).where(QaLog.id == log_id)).scalar_one_or_none()
    if not row:
        return False
    row.feedback = feedback
    db.flush()
    return True


def qa_log_to_dict(q: QaLog) -> dict[str, Any]:
    return {
        "id": q.id,
        "user_id": q.user_id,
        "question": q.question,
        "rewritten_query": q.rewritten_query,
        "answer": q.answer,
        "sources": q.sources,
        "model": q.model,
        "latency_ms": q.latency_ms,
        "grounded": q.grounded,
        "feedback": q.feedback,
        "created_at": q.created_at.isoformat(),
    }


# ---------- 索引操作流水 ----------
def add_index_op(
    db: Session,
    *,
    kind: str,
    document_id: int | None,
    version_id: int | None,
    status: str,
    detail: dict,
    created_by: int | None,
) -> IndexOp:
    op = IndexOp(
        kind=kind,
        document_id=document_id,
        version_id=version_id,
        status=status,
        detail=detail,
        created_by=created_by,
    )
    db.add(op)
    db.flush()
    return op


def list_index_ops(db: Session, limit: int = 50) -> list[IndexOp]:
    return list(db.execute(select(IndexOp).order_by(IndexOp.id.desc()).limit(limit)).scalars())


def index_op_to_dict(op: IndexOp) -> dict[str, Any]:
    return {
        "id": op.id,
        "kind": op.kind,
        "document_id": op.document_id,
        "version_id": op.version_id,
        "status": op.status,
        "detail": op.detail,
        "created_at": op.created_at.isoformat(),
    }


# ---------- 审计日志 ----------
def add_audit(
    db: Session,
    *,
    user_id: int | None,
    username: str,
    action: str,
    resource_type: str,
    resource_id: str,
    detail: dict,
    ip: str,
) -> AuditLog:
    a = AuditLog(
        user_id=user_id,
        username=username,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
        ip=ip,
    )
    db.add(a)
    db.flush()
    return a


def list_audit(db: Session, limit: int = 100) -> list[AuditLog]:
    return list(db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)).scalars())


def audit_to_dict(a: AuditLog) -> dict[str, Any]:
    return {
        "id": a.id,
        "user_id": a.user_id,
        "username": a.username,
        "action": a.action,
        "resource_type": a.resource_type,
        "resource_id": a.resource_id,
        "detail": a.detail,
        "ip": a.ip,
        "created_at": a.created_at.isoformat(),
    }
