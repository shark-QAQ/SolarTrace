# app/api/routes/documents.py
"""文档库与索引管理接口（editor/admin）。"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, Request, UploadFile
from pydantic import BaseModel

from app.api.deps import DbDep, EditorDep, RuntimeDep, UserDep, client_ip
from app.repositories import doc_repo, qa_repo
from app.schemas.doc import DocOut, UploadOut
from app.services import doc_service, index_service

router = APIRouter(tags=["文档库"])


class PublishBody(BaseModel):
    version_id: int | None = None


class ArchiveBody(BaseModel):
    version_id: int | None = None


class ReconcileOut(BaseModel):
    rebuilt: int
    cleaned: int


def _audit(db, user, action: str, doc_id: int | None, request: Request, **extra) -> None:
    qa_repo.add_audit(
        db,
        user_id=user.id,
        username=user.username,
        action=action,
        resource_type="document",
        resource_id=str(doc_id) if doc_id else "",
        detail=extra,
        ip=client_ip(request),
    )


@router.get("/documents")
def list_documents(
    db: DbDep,
    _: UserDep,
    status: str | None = None,
    doc_type: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    total, docs = doc_repo.list_documents(
        db, status=status, doc_type=doc_type, keyword=keyword, page=page, page_size=page_size
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [doc_repo.doc_to_dict(d) for d in docs],
    }


@router.get("/documents/{doc_id}", response_model=DocOut)
def get_document(doc_id: int, db: DbDep, _: UserDep) -> dict:
    data = doc_service.get_document_detail(db, doc_id)
    return {k: v for k, v in data.items() if k != "versions"}


@router.get("/documents/{doc_id}/versions")
def list_versions(doc_id: int, db: DbDep, _: UserDep) -> dict:
    doc = doc_repo.get_document_opt(db, doc_id)
    if not doc:
        from app.core.errors import NotFoundError

        raise NotFoundError("文档不存在")
    return {
        "document_id": doc_id,
        "versions": [doc_repo.version_to_dict(v) for v in doc_repo.versions_of(db, doc_id)],
    }


@router.get("/documents/{doc_id}/preview")
def preview_document(doc_id: int, db: DbDep, _: UserDep) -> dict:
    return {"document_id": doc_id, "text": doc_service.preview(db, doc_id)}


@router.post("/documents/upload", response_model=UploadOut)
def upload_document(
    db: DbDep,
    user: EditorDep,
    runtime: RuntimeDep,
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    doc_code: str = Form(""),
    doc_type: str = Form("other"),
    issuing_body: str = Form(""),
    issue_year: int | None = Form(None),
    description: str = Form(""),
    notes: str = Form(""),
    publish: bool = Form(True),
    document_id: int | None = Form(None),
) -> dict:
    meta = {
        "title": title,
        "doc_code": doc_code,
        "doc_type": doc_type,
        "issuing_body": issuing_body,
        "issue_year": issue_year,
        "description": description,
        "notes": notes,
        "document_id": document_id,
    }
    doc, version, path = doc_service.submit_upload(db, file=file, meta=meta, operator_id=user.id)
    indexed = False
    if publish:
        try:
            index_service.publish_version(db, runtime, doc.id, version.id, user.id)
            indexed = True
        except Exception:
            db.rollback()
            raise
    out = {
        "document": doc_repo.doc_to_dict(doc),
        "version": doc_repo.version_to_dict(version),
        "indexed": indexed,
    }
    _audit(db, user, "upload", doc.id, request, version_no=version.version_no, publish=publish)
    db.commit()
    return out


@router.post("/documents/{doc_id}/publish")
def publish_document(
    doc_id: int, body: PublishBody, db: DbDep, runtime: RuntimeDep, user: EditorDep, request: Request
) -> dict:
    if body.version_id is None:
        from app.repositories.doc_repo import versions_of

        versions = versions_of(db, doc_id)
        version = next((v for v in versions if v.status != "archived"), None)
        if version is None:
            from app.core.errors import NotFoundError

            raise NotFoundError("不存在可发布的版本，请先上传文档")
    else:
        from app.repositories.doc_repo import get_version_opt

        version = get_version_opt(db, body.version_id)
        if not version:
            from app.core.errors import NotFoundError

            raise NotFoundError("版本不存在")
    chunk_count, parent_count = index_service.publish_version(db, runtime, doc_id, version.id, user.id)
    doc = doc_repo.get_document_opt(db, doc_id)
    _audit(db, user, "publish", doc_id, request, version_no=version.version_no, chunks=chunk_count)
    db.commit()
    return {
        "document": doc_repo.doc_to_dict(doc),
        "version": doc_repo.version_to_dict(version),
        "chunk_count": chunk_count,
        "parent_count": parent_count,
    }


@router.post("/documents/{doc_id}/archive")
def archive_document(
    doc_id: int, body: ArchiveBody, db: DbDep, runtime: RuntimeDep, user: EditorDep, request: Request
) -> dict:
    index_service.archive_version(db, runtime, doc_id, body.version_id, user.id)
    doc = doc_repo.get_document_opt(db, doc_id)
    _audit(db, user, "archive", doc_id, request, version_id=body.version_id)
    db.commit()
    return {"message": "已归档并清理索引", "document": doc_repo.doc_to_dict(doc)}


@router.post("/system/reconcile", response_model=ReconcileOut)
def reconcile(db: DbDep, user: EditorDep, runtime: RuntimeDep, request: Request) -> dict:
    result = index_service.reconcile(db, runtime, operator_id=user.id)
    _audit(db, user, "reconcile", None, request, **result)
    db.commit()
    return result


@router.get("/system/index-ops")
def index_ops(db: DbDep, _: UserDep, limit: int = 50) -> dict:
    return {"items": [qa_repo.index_op_to_dict(op) for op in qa_repo.list_index_ops(db, limit)]}
