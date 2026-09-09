# app/core/database.py
"""SQLAlchemy 引擎与会话管理（同步，简化部署；默认 SQLite，可切 PostgreSQL）。"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import get_settings

Base = declarative_base()

_settings = get_settings()
_connect_args: dict = {}
if _settings.resolved_database_url.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine: Engine = create_engine(
    _settings.resolved_database_url,
    echo=False,
    future=True,
    pool_pre_ping=True,
    connect_args=_connect_args or None,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def get_db() -> Generator[Session]:
    """FastAPI 依赖：请求级会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all() -> None:
    """开发期建表；生产建议用 Alembic 迁移。"""
    # 延迟导入模型以注册所有表
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
