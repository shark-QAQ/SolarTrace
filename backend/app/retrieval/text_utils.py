# app/retrieval/text_utils.py
"""中文文本处理工具：分词、清洗、规范串。"""
from __future__ import annotations

import re

import jieba

# 关闭 jieba 冗长日志
jieba.setLogLevel(60)

_CJK_NUM = re.compile(r"[0-9A-Za-z一-鿿]+")
_SPACE_RE = re.compile(r"\s+")

_STOPWORDS = {
    "的", "了", "和", "与", "或", "及", "在", "对", "于", "由", "被", "把", "让", "等",
    "应", "须", "应当", "应该", "不得", "必须", "可以", "以及", "其", "之", "者",
    "我们", "你们", "他们", "这", "那", "该", "如", "按照", "根据", "依照", "规定", "情况", "进行", "如下", "其中", "是指", "所称", "本条", "条款",
    "the", "and", "or", "for", "with",
}


def normalize(text: str) -> str:
    """折叠空白并转小写，保留中英文/数字主体。"""
    text = _SPACE_RE.sub(" ", text or "").strip().lower()
    return text


def tokenize(text: str) -> list[str]:
    """中文分词：清洗标点后 jieba 切分并去除停用词。"""
    text = normalize(text)
    if not text:
        return []
    pieces = _CJK_NUM.findall(text)
    if not pieces:
        return []
    raw = jieba.lcut("".join(pieces))
    return [w for w in raw if w and w not in _STOPWORDS and len(w) <= 24]


def ascii_letters(text: str) -> str:
    """抽取中文之外便于做串匹配的字母数字（如 GB50797 / 文号）。"""
    return re.sub(r"[^0-9A-Za-z]", "", text.upper())
