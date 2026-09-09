# app/core/config.py
"""SolarTrace（光溯）全局配置。

所有配置项均可通过环境变量（前缀 SOLARTRACE_ 或同名小写）覆盖。
集中管理：安全、存储、向量库、嵌入/生成模型、检索超参、语料与上传。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# backend/ 目录（app/core/config.py -> parents[2]）
BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
SAMPLES_DIR = BASE_DIR / "samples"


class Settings(BaseSettings):
    """应用级配置。"""

    model_config = SettingsConfigDict(
        env_prefix="SOLARTRACE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- 应用 ----
    app_name: str = "SolarTrace（光溯）"
    app_version: str = "1.0.0"
    environment: str = "development"  # development | test | production
    debug: bool = False
    secret_key: str = "change-me-in-production-solar-trace"
    access_token_expire_minutes: int = 60 * 24
    data_dir: Path = DATA_DIR
    samples_dir: Path = SAMPLES_DIR
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
    ]

    # ---- 日志 ----
    log_level: str = "INFO"
    log_format: str = "text"  # text | json

    # ---- 数据库 ----
    database_url: str = ""  # 留空则使用 SQLite

    # ---- 向量库 ----
    vector_backend: str = "chroma"  # chroma | qdrant
    chroma_data_dir: Path | None = None
    chroma_collection: str = "solartrace_policy"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "solartrace_policy"
    vector_dimension: int = 1024

    # ---- 嵌入（Embedding）----
    embedding_provider: str = "ollama"  # ollama
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "bge-m3"
    embedding_batch_size: int = 32
    embedding_timeout_s: float = 60.0

    # ---- 生成（LLM）----
    llm_provider: str = "ollama"
    llm_model: str = "qwen2.5:7b"
    llm_temperature: float = 0.2
    llm_timeout_s: float = 180.0
    llm_num_ctx: int = 8192
    llm_use_rewrite: bool = False  # 是否启用 LLM 查询改写（默认规则改写，零成本）

    # ---- 重排（两阶段精排）----
    rerank_backend: str = "auto"  # auto | deterministic | cross_encoder
    rerank_model_name: str = "BAAI/bge-reranker-v2-m3"
    rerank_top_k: int = 5

    # ---- 检索超参 ----
    recall_dense_top_k: int = 30
    recall_bm25_top_k: int = 30
    rrf_k: float = 60.0
    min_score_keep: float = 0.30  # 重排后低于阈值的召回片段将被丢弃（防凑数）

    # ---- 分块 ----
    chunk_size: int = 300          # 子块约 300 字
    chunk_overlap: int = 60        # 子块 overlap
    parent_max_chars: int = 1800   # 父块（章节）上限，超过按边界继续拆

    # ---- 上传 ----
    upload_dir: Path | None = None
    max_upload_mb: int = 20
    allowed_upload_exts: Annotated[list[str], NoDecode] = [".pdf", ".docx", ".md", ".txt"]

    # ---- 演示语料种子 ----
    seed_on_startup: bool = False  # 空库时是否自动灌入演示语料（建议用脚本/页面触发）
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "admin123"
    bootstrap_admin_display: str = "系统管理员"

    @field_validator("cors_origins", "allowed_upload_exts", mode="before")
    @classmethod
    def _split_list(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @field_validator("data_dir", "samples_dir", mode="after")
    @classmethod
    def _abs_dir(cls, v: Path) -> Path:
        return v if v.is_absolute() else (Path.cwd() / v).resolve()

    # ---- 派生路径 ----
    @property
    def sqlite_url(self) -> str:
        return f"sqlite:///{(self.data_dir / 'solartrace.db').as_posix()}"

    @property
    def resolved_database_url(self) -> str:
        return self.database_url or self.sqlite_url

    @property
    def chroma_dir(self) -> Path:
        return self.chroma_data_dir or (self.data_dir / "chroma")

    @property
    def uploads_dir(self) -> Path:
        return self.upload_dir or (self.data_dir / "uploads")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.chroma_dir, self.uploads_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
