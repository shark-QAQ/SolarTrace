# tests/test_retrieval.py
"""检索链路集成测试：发布建索引 → 混合检索 → 重排 → 版本更替/归档一致性。"""
from __future__ import annotations

from app.providers.registry import RagRuntime
from app.repositories import doc_repo
from app.services import index_service
from app.services.rag import storage
from app.services.retrieval_service import SearchService
from sqlalchemy.orm import Session

MD_V1 = """# 并网管理

分布式光伏发电项目并网前应完成接入系统方案确认，并网验收合格后方可并网运行。电网企业应公开并网受理条件与办理时限，不得无正当理由拒绝户用光伏项目并网。项目并网后应确保防孤岛保护与计量装置正常工作。

# 安全要求

项目业主应加强巡检，组件与逆变器及防雷接地设施状态良好，发现重大故障及时上报整改。
"""


def _publish(db: Session, runtime: RagRuntime, *, code: str, title: str, content: str, doc_type: str = "grid_connection") -> tuple[int, int]:
    doc = doc_repo.create_document(
        db,
        title=title,
        doc_code=code,
        doc_type=doc_type,
        issuing_body="测试机构",
        issue_year=2025,
        source_file_name="d.md",
        checksum="x",
        description="",
        created_by=1,
    )
    version = doc_repo.create_version(
        db, document_id=doc.id, version_no=1, source_file_name="d.md", file_checksum="x", notes=""
    )
    db.flush()
    path = storage.version_file_path(doc.id, version.id, "d.md")
    path.write_text(content, encoding="utf-8")
    db.commit()
    index_service.publish_version(db, runtime, doc.id, version.id, 1)
    return doc.id, version.id


def test_publish_then_search_returns_hit(db: Session, runtime: RagRuntime):
    doc_id, version_id = _publish(db, runtime, code="文号-A", title="分布式并网验收", content=MD_V1)
    ctx = SearchService(runtime).search(db, "分布式光伏并网前需要完成什么手续", top_k=3)
    assert len(ctx.items) > 0
    assert ctx.store_count > 0
    assert all(it.meta.version_id == version_id for it in ctx.items)
    codes = {it.meta.doc_code for it in ctx.items}
    assert "文号-A" in codes


def test_republish_new_version_replaces_old(db: Session, runtime: RagRuntime):
    doc_id, v1 = _publish(db, runtime, code="文号-B", title="屋顶光伏并网", content=MD_V1)
    # 新增 v2 并发布
    doc = doc_repo.get_document(db, doc_id)
    v2 = doc_repo.create_version(
        db, document_id=doc_id, version_no=2, source_file_name="d.md", file_checksum="y", notes="改版"
    )
    db.flush()
    p = storage.version_file_path(doc_id, v2.id, "d.md")
    p.write_text(MD_V1 + "# 新增条款\n\n工商业项目应取得产权人同意。", encoding="utf-8")
    db.commit()
    index_service.publish_version(db, runtime, doc_id, v2.id, 1)
    ctx = SearchService(runtime).search(db, "工商业屋顶光伏要产权人同意吗", top_k=5)
    # 旧版本向量已被清理，命中块仅来自新版本
    assert ctx.items, "新版发布后应能检索到新增条款"
    assert all(it.meta.version_id == v2.id for it in ctx.items)
    db.refresh(doc)
    assert doc.current_version_id == v2.id


def test_archive_cleans_index(db: Session, runtime: RagRuntime):
    doc_id, _ = _publish(db, runtime, code="文号-C", title="防孤岛保护", content=MD_V1)
    ctx = SearchService(runtime).search(db, "防孤岛保护", top_k=3)
    assert ctx.items
    index_service.archive_version(db, runtime, doc_id, None, 1)
    ctx2 = SearchService(runtime).search(db, "防孤岛保护", top_k=3)
    assert not ctx2.items, "归档后检索不应再返回该文档"
