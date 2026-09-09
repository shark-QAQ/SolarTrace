# app/services/rag/keys.py
"""文档稳定主键（doc_key）生成。

doc_key 由文档元数据确定性派生，落库时写入每个块，
检索命中后用它回表校验当前文档/版本状态，杜绝引用失效政策。
"""
from __future__ import annotations


def doc_key_for(
    *, doc_type: str, doc_code: str, title: str, issuing_body: str = ""
) -> str:
    code = (doc_code or "").strip()
    t = (title or "").strip()
    body = (issuing_body or "").strip()
    if code:
        return f"{doc_type}:{code}"
    return f"{doc_type}:{body}:{t}"
