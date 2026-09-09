# app/services/index_service.py
"""知识库索引编排：解析 → 分块 → 嵌入 → 入库，发布/退稿/对账。

一致性策略（文档版本管理）：
- 发布新版本：先物理清理该文档在向量库的全部旧块（按 document_id），再原子写入新块，
  随后刷新 BM25；DB 提交成功后记录 IndexOp，失败可对账修复。
- 归档/退稿：删除该文档向量并置状态，检索层回表校验双重兜底。
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ChunkingFailed, NotFoundError
from app.models import Document, DocVersion
from app.models.enums import DocStatus, IndexOpKind
from app.providers.registry import RagRuntime
from app.providers.vector_store import VectorEntry
from app.repositories import doc_repo, qa_repo
from app.services.rag import storage
from app.services.rag.chunker import build_chunks
from app.services.rag.keys import doc_key_for
from app.services.rag.parser import Section, parse_file

logger = logging.getLogger(__name__)


def doc_key(doc: Document) -> str:
    return doc_key_for(
        doc_type=doc.doc_type,
        doc_code=doc.doc_code,
        title=doc.title,
        issuing_body=doc.issuing_body,
    )


def _index_children(
    db: Session,
    runtime: RagRuntime,
    doc: Document,
    version: DocVersion,
    sections: list[Section],
    operator_id: int | None,
) -> tuple[int, int]:
    """对单个版本建索引（调用方负责 DB 事务与向量清理）。"""
    cfg: Settings = runtime.settings
    result = build_chunks(
        sections,
        doc_id=doc.id,
        version_id=version.id,
        doc_key=doc_key(doc),
        title=doc.title,
        doc_code=doc.doc_code,
        doc_type=doc.doc_type,
        issuing_body=doc.issuing_body,
        issue_year=doc.issue_year,
        chunk_size=cfg.chunk_size,
        chunk_overlap=cfg.chunk_overlap,
        parent_max_chars=cfg.parent_max_chars,
    )
    children = result.children
    if not children:
        raise ChunkingFailed("未从该文档解析出可索引文本（请检查内容是否为空）")
    embeddings = runtime.embedder.embed([c.text for c in children])
    if len(embeddings) != len(children):
        raise ChunkingFailed("嵌入数量与分块数量不一致，已终止发布")
    # 物理清理同文档旧版本的全部向量，保证“索引与文档库一致”
    runtime.store.delete_by({"document_id": doc.id})
    batch: list[VectorEntry] = []
    for c, vec in zip(children, embeddings, strict=True):
        batch.append(
            VectorEntry(vector_id=c.meta.vector_id, vector=vec, text=c.text, metadata=c.meta.to_store())
        )
        if len(batch) >= 200:
            runtime.store.add(batch)
            batch = []
    if batch:
        runtime.store.add(batch)
    runtime.refresh_bm25()
    qa_repo.add_index_op(
        db,
        kind=IndexOpKind.PUBLISH.value,
        document_id=doc.id,
        version_id=version.id,
        status="ok",
        detail={
            "title": doc.title,
            "chunk_count": len(children),
            "parent_count": result.parent_count,
            "sections": result.section_stats,
        },
        created_by=operator_id,
    )
    return len(children), result.parent_count


def publish_version(
    db: Session,
    runtime: RagRuntime,
    document_id: int,
    version_id: int,
    operator_id: int | None,
) -> tuple[int, int]:
    doc = doc_repo.get_document_opt(db, document_id)
    if not doc:
        raise NotFoundError("文档不存在")
    version = doc_repo.get_version_opt(db, version_id)
    if not version or version.document_id != doc.id:
        raise NotFoundError("版本不存在")
    if version.status == DocStatus.PUBLISHED.value:
        # 重复发布视为重建
        pass
    path = storage.version_file_path(doc.id, version.id, version.source_file_name)
    if not path.exists():
        raise NotFoundError("版本源文件缺失，无法发布")
    sections = parse_file(str(path), version.source_file_name)
    chunk_count, parent_count = _index_children(db, runtime, doc, version, sections, operator_id)
    doc_repo.publish_document(db, doc, version, chunk_count, parent_count)
    db.commit()
    return chunk_count, parent_count


def archive_version(
    db: Session,
    runtime: RagRuntime,
    document_id: int,
    version_id: int | None,
    operator_id: int | None,
) -> None:
    """归档文档：删除向量、状态置 archived，索引随之一致。"""
    doc = doc_repo.get_document_opt(db, document_id)
    if not doc:
        raise NotFoundError("文档不存在")
    version = doc_repo.get_version_opt(db, version_id) if version_id else None
    if version is not None and version.document_id != doc.id:
        raise NotFoundError("版本不存在")
    runtime.store.delete_by({"document_id": doc.id})
    runtime.refresh_bm25()
    if version is not None:
        doc_repo.archive_document(db, doc, version)
    else:
        doc.status = DocStatus.ARCHIVED.value
        doc.current_version_id = None
        db.flush()
    qa_repo.add_index_op(
        db,
        kind=IndexOpKind.ARCHIVE.value,
        document_id=doc.id,
        version_id=version.id if version else None,
        status="ok",
        detail={"title": doc.title},
        created_by=operator_id,
    )
    db.commit()


def remove_version(db: Session, runtime: RagRuntime, version_id: int) -> None:
    """直接清理某版本的向量（退稿未发布版本）。"""
    version = doc_repo.get_version_opt(db, version_id)
    if version:
        runtime.store.delete_by({"version_id": version.id})
        runtime.refresh_bm25()


def reconcile(
    db: Session, runtime: RagRuntime, operator_id: int | None = None
) -> dict:
    """对账：让向量库/BM25 与数据库中的“已发布文档”一致。

    对每个 published 文档，比对 DB current_version 与向量库中该文档的
    version 标记，不一致则重建；同时清理孤儿向量。
    """
    from sqlalchemy import select

    from app.models import Document

    docs = db.execute(select(Document)).scalars().all()
    rebuilt, cleaned = 0, 0
    for doc in docs:
        if doc.status != DocStatus.PUBLISHED.value:
            # 非发布态仍存在向量则清理
            if runtime.store.count({"document_id": doc.id}) > 0:
                runtime.store.delete_by({"document_id": doc.id})
                cleaned += 1
            continue
        version = doc_repo.current_version_of(db, doc.id)
        if not version:
            continue
        present_versions = _present_versions(runtime, doc.id)
        if set(present_versions) != {version.id}:
            try:
                publish_version(db, runtime, doc.id, version.id, operator_id)
                rebuilt += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("对账重建失败 doc=%s: %s", doc.id, exc)
    runtime.refresh_bm25()
    qa_repo.add_index_op(
        db,
        kind=IndexOpKind.RECONCILE.value,
        document_id=None,
        version_id=None,
        status="ok",
        detail={"rebuilt": rebuilt, "cleaned": cleaned},
        created_by=operator_id,
    )
    db.commit()
    return {"rebuilt": rebuilt, "cleaned": cleaned}


def _present_versions(runtime: RagRuntime, document_id: int) -> list[int]:
    hits = runtime.store.all({"document_id": document_id})
    return sorted({int(h.metadata.get("version_id", -1)) for h in hits})
