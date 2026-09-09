# app/models/enums.py
"""领域枚举（以字符串存储，跨数据库可移植）。"""
from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"      # 系统管理：用户/审计/参数
    EDITOR = "editor"    # 知识库管理：上传/发布/归档/评测
    VIEWER = "viewer"    # 只读：问答/检索/查看

    @property
    def level(self) -> int:
        return {"admin": 3, "editor": 2, "viewer": 1}.get(self.value, 0)


class DocType(StrEnum):
    """知识库文档分类（对应查询元数据过滤维度）。"""

    BUILDING_STANDARD = "building_standard"  # 建设规范/设计标准
    GRID_CONNECTION = "grid_connection"      # 并网政策/技术规定
    EARLY_PROCEDURE = "early_procedure"      # 备案/用地/前期手续
    TARIFF_SUBSIDY = "tariff_subsidy"        # 电价/补贴/结算
    OTHER = "other"

    @classmethod
    def label(cls, v: str) -> str:
        return {
            cls.BUILDING_STANDARD.value: "建设规范",
            cls.GRID_CONNECTION.value: "并网政策",
            cls.EARLY_PROCEDURE.value: "前期手续",
            cls.TARIFF_SUBSIDY.value: "电价补贴",
            cls.OTHER.value: "其他",
        }.get(v, v)


class DocStatus(StrEnum):
    DRAFT = "draft"          # 草稿：尚未建索引
    PUBLISHED = "published"  # 已发布：对应版本已建索引、可被检索
    ARCHIVED = "archived"    # 已归档：索引已清理，不再返回（防引用失效政策）


class ChunkRelation(StrEnum):
    """父子分块：节点同时作为自身块被索引。"""

    PARENT = "parent"
    CHILD = "child"


class IndexOpKind(StrEnum):
    SEED = "seed"
    PUBLISH = "publish"
    REBUILD = "rebuild"
    ARCHIVE = "archive"
    RECONCILE = "reconcile"
    CLEANUP = "cleanup"


class EvalKind(StrEnum):
    TOPK = "topk"
    LLM_JUDGE = "llm_judge"
