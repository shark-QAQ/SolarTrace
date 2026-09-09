# app/services/doc_service.py
"""文档库业务：上传入库（按文号/标题智能挂版本）、元数据、预览、发布/归档入口。"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationFailed
from app.models import Document
from app.repositories import doc_repo
from app.services.rag import storage
from app.services.rag.parser import parse_file

logger = logging.getLogger(__name__)


def _norm_code(code: str) -> str:
    return "".join((code or "").split()).upper()


def find_target_document(db: Session, *, doc_code: str, title: str) -> Document | None:
    """同一文号/同名文档视为同一知识文档，上传即新增版本。"""
    code = _norm_code(doc_code)
    if code:
        docs = db.execute(
            select(Document).where(Document.status != "archived")
        ).scalars()
        for d in docs:
            if _norm_code(d.doc_code) == code:
                return d
    if title:
        docs = db.execute(
            select(Document).where(Document.status != "archived", Document.title == title.strip())
        ).scalars()
        for d in docs:
            return d
    return None


def submit_upload(
    db: Session,
    *,
    file: UploadFile,
    meta: dict,
    operator_id: int | None,
) -> tuple[Document, object, str]:
    """落盘并创建 文档/版本（草稿），返回 (doc, version, saved_path)。"""
    name = file.filename or ""
    ext = Path(name).suffix.lower()
    settings = get_settings()
    if ext not in settings.allowed_upload_exts:
        raise ValidationFailed(f"不支持的文件类型：{ext}，允许：{settings.allowed_upload_exts}")
    content = file.file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise ValidationFailed(f"文件超过 {settings.max_upload_mb}MB 限制")
    if not content.strip():
        raise ValidationFailed("文件内容为空")
    checksum = hashlib.sha256(content).hexdigest()

    doc_code = (meta.get("doc_code") or "").strip()
    title = (meta.get("title") or "").strip()
    if not title:
        title = Path(name).stem.strip() or "未命名文档"

    target = meta.get("document_id")
    doc: Document | None = None
    if target:
        doc = doc_repo.get_document_opt(db, int(target))
        if not doc:
            raise NotFoundError("目标文档不存在")
    else:
        doc = find_target_document(db, doc_code=doc_code, title=title)

    if doc is None:
        doc = doc_repo.create_document(
            db,
            title=title,
            doc_code=doc_code,
            doc_type=meta.get("doc_type") or "other",
            issuing_body=(meta.get("issuing_body") or "").strip(),
            issue_year=meta.get("issue_year"),
            source_file_name=name,
            checksum=checksum,
            description=(meta.get("description") or "").strip(),
            created_by=operator_id,
        )
    version_no = doc_repo.next_version_no(db, doc.id)
    version = doc_repo.create_version(
        db,
        document_id=doc.id,
        version_no=version_no,
        source_file_name=name,
        file_checksum=checksum,
        notes=(meta.get("notes") or "").strip(),
    )
    db.flush()
    path = storage.version_file_path(doc.id, version.id, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    db.commit()
    return doc, version, str(path)


def get_document_detail(db: Session, document_id: int) -> dict:
    doc = doc_repo.get_document_opt(db, document_id)
    if not doc:
        raise NotFoundError("文档不存在")
    versions = [doc_repo.version_to_dict(v) for v in doc_repo.versions_of(db, doc.id)]
    out = doc_repo.doc_to_dict(doc)
    out["versions"] = versions
    return out


def preview(db: Session, document_id: int, limit: int = 6000) -> str:
    doc = doc_repo.get_document_opt(db, document_id)
    if not doc:
        raise NotFoundError("文档不存在")
    version = doc_repo.current_version_of(db, doc.id) or doc_repo.versions_of(db, doc.id)[0]
    if not version:
        return ""
    path = storage.version_file_path(doc.id, version.id, version.source_file_name)
    if not path.exists():
        return ""
    sections = parse_file(str(path), version.source_file_name)
    buf: list[str] = []
    for s in sections:
        head = " / ".join(s.path) if s.path else ""
        if head:
            buf.append(f"### {head}")
        buf.append(s.full_text)
        if sum(len(x) for x in buf) > limit:
            break
    return "\n\n".join(buf)[:limit]
