# app/repositories/doc_repo.py
"""文档/版本仓储：SQL 访问与状态流转均收敛于此。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Document, DocVersion


def create_document(
    db: Session,
    *,
    title: str,
    doc_code: str,
    doc_type: str,
    issuing_body: str,
    issue_year: int | None,
    source_file_name: str,
    checksum: str,
    description: str,
    created_by: int | None,
) -> Document:
    doc = Document(
        title=title,
        doc_code=doc_code,
        doc_type=doc_type,
        issuing_body=issuing_body,
        issue_year=issue_year,
        status="draft",
        source_file_name=source_file_name,
        checksum=checksum,
        description=description,
        created_by=created_by,
    )
    db.add(doc)
    db.flush()
    return doc


def get_document(db: Session, doc_id: int) -> Document:
    return db.execute(select(Document).where(Document.id == doc_id)).scalar_one()


def get_document_opt(db: Session, doc_id: int) -> Document | None:
    return db.execute(select(Document).where(Document.id == doc_id)).scalar_one_or_none()


def list_documents(
    db: Session,
    *,
    status: str | None = None,
    doc_type: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[int, list[Document]]:
    stmt = select(Document)
    count_stmt = select(func.count(Document.id))
    if status:
        stmt = stmt.where(Document.status == status)
        count_stmt = count_stmt.where(Document.status == status)
    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)
        count_stmt = count_stmt.where(Document.doc_type == doc_type)
    if keyword:
        like = f"%{keyword}%"
        cond = Document.title.like(like) | Document.doc_code.like(like) | Document.issuing_body.like(like)
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    total = int(db.execute(count_stmt).scalar_one())
    rows = db.execute(
        stmt.order_by(Document.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars()
    return total, list(rows)


def next_version_no(db: Session, document_id: int) -> int:
    cur = db.execute(
        select(func.max(DocVersion.version_no)).where(DocVersion.document_id == document_id)
    ).scalar_one()
    return int(cur) + 1 if cur else 1


def create_version(
    db: Session,
    *,
    document_id: int,
    version_no: int,
    source_file_name: str,
    file_checksum: str,
    notes: str,
) -> DocVersion:
    v = DocVersion(
        document_id=document_id,
        version_no=version_no,
        status="draft",
        source_file_name=source_file_name,
        file_checksum=file_checksum,
        notes=notes,
    )
    db.add(v)
    db.flush()
    return v


def get_version(db: Session, version_id: int) -> DocVersion:
    return db.execute(select(DocVersion).where(DocVersion.id == version_id)).scalar_one()


def get_version_opt(db: Session, version_id: int) -> DocVersion | None:
    return db.execute(select(DocVersion).where(DocVersion.id == version_id)).scalar_one_or_none()


def versions_of(db: Session, document_id: int) -> list[DocVersion]:
    return list(
        db.execute(
            select(DocVersion).where(DocVersion.document_id == document_id).order_by(DocVersion.id.desc())
        ).scalars()
    )


def current_version_of(db: Session, document_id: int) -> DocVersion | None:
    doc = get_document_opt(db, document_id)
    if not doc or not doc.current_version_id:
        return None
    return get_version_opt(db, doc.current_version_id)


def publish_document(
    db: Session, doc: Document, version: DocVersion, chunk_count: int, parent_count: int
) -> None:
    doc.status = "published"
    doc.current_version_id = version.id
    version.status = "published"
    version.chunk_count = chunk_count
    version.parent_count = parent_count
    version.published_at = datetime.utcnow()
    db.flush()


def archive_document(db: Session, doc: Document, version: DocVersion) -> None:
    doc.status = "archived"
    version.status = "archived"
    version.archived_at = datetime.utcnow()
    db.flush()


def count_by_status(db: Session) -> dict[str, int]:
    rows = db.execute(
        select(Document.status, func.count(Document.id)).group_by(Document.status)
    ).all()
    return {k: int(v) for k, v in rows}


def count_versions(db: Session) -> int:
    return int(db.execute(select(func.count(DocVersion.id))).scalar_one())


def recent_docs(db: Session, limit: int = 5) -> list[Document]:
    return list(
        db.execute(select(Document).order_by(Document.updated_at.desc()).limit(limit)).scalars()
    )


def doc_to_dict(doc: Document) -> dict[str, Any]:
    return {
        "id": doc.id,
        "title": doc.title,
        "doc_code": doc.doc_code,
        "doc_type": doc.doc_type,
        "issuing_body": doc.issuing_body,
        "issue_year": doc.issue_year,
        "status": doc.status,
        "current_version_id": doc.current_version_id,
        "source_file_name": doc.source_file_name,
        "description": doc.description,
        "created_by": doc.created_by,
        "created_at": doc.created_at.isoformat(),
        "updated_at": doc.updated_at.isoformat(),
    }


def version_to_dict(v: DocVersion) -> dict[str, Any]:
    return {
        "id": v.id,
        "document_id": v.document_id,
        "version_no": v.version_no,
        "status": v.status,
        "source_file_name": v.source_file_name,
        "chunk_count": v.chunk_count,
        "parent_count": v.parent_count,
        "notes": v.notes,
        "published_at": v.published_at.isoformat() if v.published_at else None,
        "archived_at": v.archived_at.isoformat() if v.archived_at else None,
    }
