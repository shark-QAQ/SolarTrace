# app/retrieval/rewrite.py
"""查询理解与改写（Query Understanding & Rewriting）。

对口语化/长尾提问做：术语归一（同义替换）→ 术语扩展（追加规范表述）→
软元数据提示（年份/文档类型），降低表达差异对召回的损失（对应简历中
「并网申请」改写为「并网验收要求」一类能力）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models.enums import DocType

# 术语替换表：口语/别名 → 规范表述（按长度降序匹配）
_ALIAS_REPLACE: list[tuple[str, str]] = [
    ("光伏板", "光伏组件"),
    ("光伏电站板", "光伏组件"),
    ("光伏方阵", "光伏阵列"),
    ("并网申请", "并网验收要求"),
    ("申请并网", "并网验收要求"),
    ("能不能并网", "并网条件"),
    ("并网手续", "并网验收要求"),
    ("能卖电", "余电上网"),
    ("自己用不完卖电", "自发自用、余电上网"),
    ("屋顶光伏", "分布式光伏"),
    ("屋顶电站", "分布式光伏"),
    ("村集体光伏", "分布式光伏"),
    ("户用光伏电站", "户用分布式光伏"),
    ("工商业光伏", "工商业分布式光伏"),
    ("政策补贴", "电价补贴"),
    ("国家补贴", "电价补贴"),
    ("国补", "电价补贴"),
    ("备案流程", "项目备案"),
    ("要办什么手续", "项目备案"),
]

# 术语扩展表：命中即向查询追加规范术语，扩大召回
_TERM_EXPAND: list[tuple[str, tuple[str, ...]]] = [
    ("分布式光伏", ("分布式光伏发电",)),
    ("自发自用", ("余电上网",)),
    ("余电上网", ("自发自用",)),
    ("全额上网", ("上网电价",)),
    ("户用光伏", ("自然人", "户用分布式光伏")),
    ("并网", ("并网验收", "接入电网")),
    ("验收", ("并网验收",)),
    ("备案", ("项目备案", "备案管理")),
    ("电价", ("上网电价",)),
    ("补贴", ("电价补贴",)),
    ("建设", ("建设标准",)),
    ("设计", ("设计规范",)),
    ("安全", ("安全防护",)),
    ("消防", ("消防",)),
    ("发电量", ("发电量",)),
]

_YEAR = re.compile(r"(20\d{2})")

# 问题中出现的术语 → 文档类型软提示
_TYPE_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("并网", "接入电网", "验收", "电网公司", "电力公司", "消纳", "接入方案"), DocType.GRID_CONNECTION.value),
    (("备案", "核准", "立项", "用地", "审批", "手续", "审批流程", "文件清单"), DocType.EARLY_PROCEDURE.value),
    (("电价", "补贴", "结算", "上网电价", "度电", "竞价", "平价"), DocType.TARIFF_SUBSIDY.value),
    (("设计规范", "建设标准", "安装", "施工", "支架", "组件", "逆变器", "接地", "防雷", "安全"), DocType.BUILDING_STANDARD.value),
]


@dataclass
class RewriteResult:
    original: str
    normalized: str                    # 清洗后的原始问题
    expanded_query: str                # 术语归一+扩展后的检索串（用于向量/BM25）
    appended_terms: list[str] = field(default_factory=list)
    doc_type_hint: str | None = None   # 软提示，不强制过滤
    year_hint: int | None = None
    original_terms: list[str] = field(default_factory=list)  # 归一后查询词（BM25）

    def summary(self) -> dict:
        return {
            "original": self.original,
            "normalized": self.normalized,
            "expanded": self.expanded_query,
            "appended_terms": self.appended_terms,
            "doc_type_hint": self.doc_type_hint,
            "year_hint": self.year_hint,
        }


class QueryRewriter:
    def rewrite(self, query: str) -> RewriteResult:
        raw = (query or "").strip()
        norm = re.sub(r"\s+", " ", raw).strip()
        text = norm

        # 1) 术语归一（同义替换）
        for alias, std in sorted(_ALIAS_REPLACE, key=lambda kv: -len(kv[0])):
            if alias in text and std not in text:
                text = text.replace(alias, std)

        # 2) 术语扩展（追加规范表述，避免重复）
        appended: list[str] = []
        for term, cands in _TERM_EXPAND:
            if term in text:
                for c in cands:
                    if c not in text and c not in appended:
                        appended.append(c)
        expanded = text if not appended else f"{text} {' '.join(appended)}".strip()

        # 3) 类型/年份软提示
        doc_type_hint = None
        for terms, dtype in _TYPE_HINTS:
            if any(t in text for t in terms):
                doc_type_hint = dtype
                break
        year_hint = None
        m = _YEAR.search(text)
        if m:
            year_hint = int(m.group(1))

        from app.retrieval.text_utils import tokenize

        return RewriteResult(
            original=raw,
            normalized=norm,
            expanded_query=expanded,
            appended_terms=appended,
            doc_type_hint=doc_type_hint,
            year_hint=year_hint,
            original_terms=tokenize(expanded),
        )
