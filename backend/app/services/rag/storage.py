# app/services/rag/storage.py
"""上传文件落盘路径（版本级）。"""
from __future__ import annotations

from pathlib import Path


def version_file_path(document_id: int, version_id: int, source_file_name: str) -> Path:
    from app.core.config import get_settings

    suffix = Path(source_file_name).suffix.lower()
    return get_settings().uploads_dir / f"doc{document_id}_v{version_id}{suffix}"
