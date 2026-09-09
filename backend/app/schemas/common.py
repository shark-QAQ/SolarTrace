# app/schemas/common.py
"""通用响应结构。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Message(BaseModel):
    message: str


class KV(BaseModel):
    key: str
    value: Any
