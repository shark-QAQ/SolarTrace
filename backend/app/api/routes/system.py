# app/api/routes/system.py
"""系统状态：健康检查/就绪/统计/审计。"""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select, text

from app.api.deps import AdminDep, DbDep, RuntimeDep, UserDep
from app.core.config import get_settings
from app.models import Document, QaLog, User
from app.repositories import doc_repo, qa_repo

router = APIRouter(tags=["系统"])


@router.get("/system/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": get_settings().app_name,
        "version": get_settings().app_version,
        "environment": get_settings().environment,
    }


@router.get("/system/ready")
def ready(db: DbDep, runtime: RuntimeDep) -> dict:
    checks = {"database": False, "vector_store": False, "bm25": False, "embedder": None, "llm": None}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as exc:  # noqa: BLE001
        checks["database_error"] = str(exc)
    try:
        checks["vector_store"] = True
        checks["vector_count"] = runtime.store.count()
    except Exception as exc:  # noqa: BLE001
        checks["vector_error"] = str(exc)
    checks["bm25"] = runtime.bm25.size > 0
    embed_health = getattr(runtime.embedder, "health", lambda: None)()
    llm_health = getattr(runtime.llm, "health", lambda: None)()
    checks["embedder"] = bool(embed_health and embed_health.get("ok"))
    checks["llm"] = bool(llm_health and llm_health.get("ok"))
    checks["ready"] = checks["database"] and checks["vector_store"]
    return checks


@router.get("/system/stats")
def stats(db: DbDep, runtime: RuntimeDep, _: UserDep) -> dict:
    user_total = int(db.execute(select(func.count(User.id))).scalar_one())
    qa_total = int(db.execute(select(func.count(QaLog.id))).scalar_one())
    doc_total = int(db.execute(select(func.count(Document.id))).scalar_one())
    store_count = 0
    try:
        store_count = runtime.store.count({"status": "published"})
    except Exception:  # noqa: BLE001
        pass
    return {
        "documents": doc_repo.count_by_status(db),
        "document_total": doc_total,
        "versions": doc_repo.count_versions(db),
        "vector_chunks": store_count,
        "bm25_size": runtime.bm25.size,
        "qa_logs": qa_total,
        "users": user_total,
        "recent_documents": [doc_repo.doc_to_dict(d) for d in doc_repo.recent_docs(db, 5)],
    }


@router.get("/system/audit")
def audit(db: DbDep, _: AdminDep, limit: int = 100) -> dict:
    rows = qa_repo.list_audit(db, limit)
    return {"items": [qa_repo.audit_to_dict(a) for a in rows]}


@router.get("/system/runtime")
def runtime_info(runtime: RuntimeDep, _: UserDep) -> dict:
    s = get_settings()
    return {
        "app": s.app_name,
        "embedding_provider": s.embedding_provider,
        "embedding_model": s.embedding_model,
        "llm_provider": s.llm_provider,
        "llm_model": s.llm_model,
        "vector_backend": s.vector_backend,
        "rerank_backend": s.rerank_backend,
        "chunk_size": s.chunk_size,
        "chunk_overlap": s.chunk_overlap,
        "rerank_top_k": s.rerank_top_k,
        "health": runtime.health(),
    }
