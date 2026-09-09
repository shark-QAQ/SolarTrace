# app/services/seed_service.py
"""演示语料库与演示评测集种子。

- 语料：读取 samples/corpus/*.md（文档元数据在 front-matter），
  通过标准『上传 → 版本 → 发布建索引』链路入库，可复用版本管理与一致性校验。
- 评测：读取 samples/eval_demo.json 灌入评测集。
全流程幂等：已发布且未变化文档跳过。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document
from app.providers.registry import RagRuntime
from app.repositories import doc_repo, eval_repo
from app.services import index_service
from app.services.rag import storage

logger = logging.getLogger(__name__)

_FM_RE = re.compile(r"^---\s*$(.*?)^---\s*$", re.M | re.S)
_KEY_RE = re.compile(r"^(\w[\w\-_]*):\s*(.*)$")


@dataclass
class CorpusDoc:
    filename: str
    title: str
    code: str = ""
    doc_type: str = "other"
    issuer: str = ""
    year: int | None = None
    desc: str = ""
    body: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return (self.code or self.title).strip()


def load_corpus_dir(directory: Path) -> list[CorpusDoc]:
    docs: list[CorpusDoc] = []
    for f in sorted(directory.glob("*.md")):
        raw = f.read_text(encoding="utf-8")
        docs.append(parse_corpus_file(f.name, raw))
    return docs


def parse_corpus_file(filename: str, raw: str) -> CorpusDoc:
    meta: dict = {}
    body = raw
    m = _FM_RE.search(raw)
    if m:
        for line in m.group(1).splitlines():
            km = _KEY_RE.match(line.strip())
            if km:
                meta[km.group(1)] = km.group(2).strip()
        body = raw[m.end():].strip()
    year_s = str(meta.get("year") or "").strip()
    return CorpusDoc(
        filename=filename,
        title=meta.get("title") or filename.removesuffix(".md"),
        code=meta.get("code", ""),
        doc_type=meta.get("type", "other"),
        issuer=meta.get("issuer", ""),
        year=int(year_s) if year_s.isdigit() else None,
        desc=meta.get("desc", ""),
        body=body,
        meta=meta,
    )


def _same_doc(doc: Document, cd: CorpusDoc) -> bool:
    return (doc.doc_code and doc.doc_code == cd.code) or (not cd.code and doc.title == cd.title)


def seed_demo(db: Session, runtime: RagRuntime, directory: Path, operator_id: int = 1) -> dict:
    docs = load_corpus_dir(directory)
    created, skipped, indexed_chunks = 0, 0, 0
    for cd in docs:
        body_bytes = cd.body.encode("utf-8")
        checksum = __import__("hashlib").sha256(body_bytes).hexdigest()
        existing = db.execute(select(Document)).scalars().all()
        doc = next((d for d in existing if _same_doc(d, cd)), None)
        if doc is None:
            doc = doc_repo.create_document(
                db,
                title=cd.title,
                doc_code=cd.code,
                doc_type=cd.doc_type,
                issuing_body=cd.issuer,
                issue_year=cd.year,
                source_file_name=cd.filename,
                checksum=checksum,
                description=cd.desc,
                created_by=operator_id,
            )
            created += 1
        # 已存在且当前发布版本即该文件且内容一致 → 跳过
        cur = doc_repo.current_version_of(db, doc.id)
        if cur and cur.file_checksum == checksum and doc.status == "published":
            skipped += 1
            continue
        version = doc_repo.create_version(
            db,
            document_id=doc.id,
            version_no=doc_repo.next_version_no(db, doc.id),
            source_file_name=cd.filename,
            file_checksum=checksum,
            notes="演示语料种子",
        )
        db.flush()
        path = storage.version_file_path(doc.id, version.id, cd.filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body_bytes)
        db.commit()
        chunks, _ = index_service.publish_version(db, runtime, doc.id, version.id, operator_id)
        indexed_chunks += chunks
    logger.info("语料种子完成：新建 %s，跳过 %s，累计片段 %s", created, skipped, indexed_chunks)
    return {"created": created, "skipped": skipped, "indexed_chunks": indexed_chunks}


def seed_eval_demo(db: Session, json_path: Path, operator_id: int = 1) -> dict:
    if not json_path.exists():
        return {"loaded": 0, "message": "评测样本文件不存在"}
    sets = eval_repo.list_sets(db)
    if sets and any(s.cases for s in sets):
        return {"loaded": 0, "message": "已存在评测集，跳过"}
    cases = json.loads(json_path.read_text(encoding="utf-8"))
    name = json_path.stem.replace("eval_demo", "光溯演示评测集").replace("_", " ")
    s = eval_repo.create_set(db, name=name, description="光伏政策问答 RAG 评测集（演示样本）", created_by=operator_id)
    added = eval_repo.add_cases(db, s.id, cases)
    db.commit()
    return {"loaded": added, "eval_set_id": s.id}
