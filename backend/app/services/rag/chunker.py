# app/services/rag/chunker.py
"""标题感知 · 父子分块（约 300 字 + overlap）。

- 父块 = 标题链下的一段章节正文（分组单元，不入库）。
- 子块 = 对父块正文做带 overlap 的滑动切分，作为检索单元入库；
  子块文本前置标题路径提升语义命中，metadata 保留父级分组（parent_seq）与层级路径。
检索命中后可用同一 parent_seq 就近扩展同章节上下文（父子协同取上下文）。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import DocStatus
from app.retrieval.types import Chunk, ChunkMeta
from app.services.rag.parser import Section


@dataclass
class ChunkResult:
    children: list[Chunk]
    parent_count: int
    section_stats: dict


def _split_overlap(text: str, chunk_size: int, overlap: int) -> list[str]:
    """按字符窗口滑动切分，相邻块保留 overlap 字重叠，避免边界信息截断。"""
    if len(text) <= chunk_size:
        return [text] if text else []
    step = chunk_size - overlap
    if step < 1:
        step = 1
    out: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        out.append(text[start:end].strip())
        if end >= len(text):
            break
        nxt = start + step
        if nxt <= start or nxt >= end:
            nxt = end  # 防死循环；短尾直接前进
        start = nxt
    return [p for p in out if p]


def _path_label(path: list[str]) -> str:
    return "/".join([p for p in path if p.strip()])


def build_chunks(
    sections: list[Section],
    *,
    doc_id: int,
    version_id: int,
    doc_key: str,
    title: str,
    doc_code: str,
    doc_type: str,
    issuing_body: str,
    issue_year: int | None,
    chunk_size: int,
    chunk_overlap: int,
    parent_max_chars: int,
) -> ChunkResult:
    """由解析出的 Sections 生成父子分块结果。

    :param doc_key: 文档稳定主键（doc_type/文号/标题 派生），用于引用回表校验。
    """
    children: list[Chunk] = []
    parent_count = 0
    global_seq = 0

    def base_meta(parent_seq: int, seq: int, section_path: str, text: str) -> ChunkMeta:
        return ChunkMeta(
            vector_id=f"v{version_id}:{seq}",
            document_id=doc_id,
            version_id=version_id,
            doc_key=doc_key,
            title=title,
            doc_code=doc_code,
            doc_type=doc_type,
            issuing_body=issuing_body,
            issue_year=issue_year,
            status=DocStatus.PUBLISHED.value,
            relation="child",
            parent_seq=parent_seq,
            seq=seq,
            section_path=section_path,
            char_len=len(text),
        )

    # 将每个 Section 内容按段落切分为若干“父块”（每块 ≤ parent_max_chars）
    for section in sections:
        path_label = _path_label(section.path)
        text = section.full_text
        if not text:
            continue
        paras = [p.strip() for p in text.split("\n") if p.strip()]
        parent_buf: list[str] = []
        buf_len = 0
        for para in paras:
            if buf_len + len(para) > parent_max_chars and parent_buf:
                parent_count += 1
                body = "\n".join(parent_buf)
                for piece in _split_overlap(body, chunk_size, chunk_overlap):
                    prefix = f"{path_label}。" if path_label else ""
                    global_seq += 1
                    children.append(
                        Chunk(
                            text=f"{prefix}{piece}",
                            meta=base_meta(parent_count, global_seq, path_label, f"{prefix}{piece}"),
                            relation="child",
                        )
                    )
                parent_buf = [para]
                buf_len = len(para)
            else:
                parent_buf.append(para)
                buf_len += len(para) + 1
        if parent_buf:
            parent_count += 1
            body = "\n".join(parent_buf)
            for piece in _split_overlap(body, chunk_size, chunk_overlap):
                prefix = f"{path_label}。" if path_label else ""
                global_seq += 1
                children.append(
                    Chunk(
                        text=f"{prefix}{piece}",
                        meta=base_meta(parent_count, global_seq, path_label, f"{prefix}{piece}"),
                        relation="child",
                    )
                )

    return ChunkResult(
        children=children,
        parent_count=parent_count,
        section_stats={"sections": len(sections), "blocks": parent_count},
    )
