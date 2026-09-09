# tests/test_text.py
"""分词 / 查询改写 单元测试。"""
from __future__ import annotations

from app.retrieval.rewrite import QueryRewriter
from app.retrieval.text_utils import ascii_letters, tokenize


def test_tokenize_removes_stopwords():
    tokens = tokenize("光伏发电站的并网与验收要求")
    joined = "".join(tokens)
    assert tokens
    assert "光伏" in tokens
    assert "并网" in joined  # 词语可能被拆字，但整体语义保留
    assert "的" not in tokens
    assert "与" not in tokens


def test_ascii_letters():
    assert ascii_letters("国能发新能规〔2025〕7号") == "20257"
    assert ascii_letters("GB/T 19964-2012") == "GBT199642012"


def test_rewrite_synonym_normalization():
    rw = QueryRewriter().rewrite("光伏板的并网申请怎么办理")
    assert "并网验收要求" in rw.expanded_query  # 术语归一
    assert "光伏组件" in rw.expanded_query      # 同义替换


def test_rewrite_expansion_and_hints():
    rw = QueryRewriter().rewrite("工商业屋顶光伏要做什么手续备案")
    assert rw.doc_type_hint == "early_procedure"
    assert "项目备案" in rw.expanded_query or "备案管理" in rw.expanded_query


def test_rewrite_year_hint():
    rw = QueryRewriter().rewrite("2025年的分布式光伏政策还允许并网吗")
    assert rw.year_hint == 2025
