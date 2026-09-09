# tests/test_chunker.py
"""标题感知父子分块 单元测试。"""
from __future__ import annotations

from app.services.rag.chunker import build_chunks
from app.services.rag.parser import parse_markdown

_LONG = (
    "光伏发电站并网前应完成接入系统方案审查，并网验收合格后方可并网运行。"
    "电网企业应公开并网受理条件与办理时限，不得无正当理由拒绝分布式光伏项目并网。"
    "项目业主应加强设备巡检，确保组件、逆变器及防雷接地设施状态良好。"
    "发生重大设备故障时应按要求上报并及时整改。" * 3
)


def _chunks(**kw):
    text = kw.pop("text", _LONG)
    sections = parse_markdown(f"# 并网管理\n\n{text}\n\n# 运行维护\n\n{text[:200]}")
    base = {
        "doc_id": 1,
        "version_id": 5,
        "doc_key": "grid_connection:测试文号",
        "title": "测试文档",
        "doc_code": "测试文号",
        "doc_type": "grid_connection",
        "issuing_body": "测试机构",
        "issue_year": 2025,
        "chunk_size": 120,
        "chunk_overlap": 20,
        "parent_max_chars": 600,
    }
    base.update(kw)
    return build_chunks(sections, **base)


def test_chunk_split_respects_size():
    res = _chunks(text=_LONG * 2)
    assert len(res.children) > 1
    for c in res.children:
        assert len(c.text) <= 160  # 块文本上限（含前缀）


def test_children_have_metadata_and_parent_group():
    res = _chunks()
    parents = {c.meta.parent_seq for c in res.children}
    assert len(parents) >= 1
    for c in res.children:
        assert c.meta.doc_code == "测试文号"
        assert c.meta.version_id == 5
        assert c.meta.status == "published"
        assert c.meta.relation == "child"
        assert c.meta.section_path


def test_overlap_present_for_long_text():
    res = _chunks(text=_LONG * 3, chunk_size=120, chunk_overlap=30)
    # 存在相邻块共享字符（overlap 生效）
    texts = [c.text for c in res.children]
    overlapped = False
    for i in range(len(texts) - 1):
        if len(set(texts[i]).intersection(texts[i + 1])) > 0:
            overlapped = True
            break
    assert overlapped


def test_parent_chunk_boundaries():
    # 单段很长的文字会被拆成多个父块
    res = _chunks(text=_LONG * 4, chunk_size=120, chunk_overlap=20, parent_max_chars=400)
    assert res.parent_count > 1
    assert res.section_stats["sections"] >= 2
