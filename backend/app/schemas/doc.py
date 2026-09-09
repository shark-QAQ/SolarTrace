# app/schemas/doc.py
"""文档库相关输入/输出。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import DocType


class DocCreateMeta(BaseModel):
    """上传同时补充的文档元数据。"""

    title: str | None = None
    doc_code: str = Field(default="")
    doc_type: str = Field(default=DocType.OTHER.value)
    issuing_body: str = Field(default="")
    issue_year: int | None = Field(default=None, ge=1990, le=2100)
    description: str = Field(default="")
    notes: str = Field(default="")
    publish: bool = Field(default=True)  # 是否上传后直接发布建索引


class DocOut(BaseModel):
    id: int
    title: str
    doc_code: str
    doc_type: str
    issuing_body: str
    issue_year: int | None
    status: str
    current_version_id: int | None
    source_file_name: str
    description: str
    created_at: str
    updated_at: str


class VersionOut(BaseModel):
    id: int
    document_id: int
    version_no: int
    status: str
    source_file_name: str
    chunk_count: int
    parent_count: int
    notes: str
    published_at: str | None
    archived_at: str | None


class DocListOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[DocOut]


class UploadOut(BaseModel):
    document: DocOut
    version: VersionOut
    indexed: bool = False


class PublishOut(BaseModel):
    document: DocOut
    version: VersionOut
    chunk_count: int
    parent_count: int
    op_id: int | None = None


class SearchHitOut(BaseModel):
    chunk_id: str
    rank: int
    score: float
    title: str
    doc_code: str
    doc_type: str
    section_path: str
    snippet: str
    text: str
    document_id: int
    version_id: int


class SearchResponse(BaseModel):
    question: str
    rewritten: dict[str, Any]
    hits: list[SearchHitOut]
    latency_ms: int
    store_count: int



