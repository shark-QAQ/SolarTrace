# tests/conftest.py
"""测试夹具：独立 SQLite + 独立 Chroma 目录 + Hash 嵌入 + FakeLLM。

所有测试彼此隔离、不依赖 Ollama/网络/默认 data 目录，可离线复现。
"""
from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from app.api.deps import get_runtime
from app.api.routes import auth, chat, documents, search, system
from app.api.routes import eval as eval_router
from app.core.config import Settings
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import register_exception_handlers
from app.models import User
from app.models.enums import Role
from app.providers.registry import RagRuntime, build_runtime
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def db(tmp_path: Path) -> Generator[Session]:
    engine = create_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def runtime(tmp_path: Path) -> RagRuntime:
    settings = Settings(
        data_dir=tmp_path / "data",
        chroma_data_dir=tmp_path / "chroma",
        embedding_provider="hash",
        llm_provider="fake",
        vector_backend="chroma",
        vector_dimension=96,
        rerank_backend="deterministic",
        min_score_keep=0.10,
        chunk_size=120,
        chunk_overlap=20,
        parent_max_chars=600,
        recall_dense_top_k=20,
        recall_bm25_top_k=20,
        rrf_k=60.0,
    )
    settings.ensure_dirs()
    return build_runtime(settings)


def _make_user(db: Session, username: str, role: str, password: str = "secret123") -> User:
    u = User(
        username=username,
        hashed_password=hash_password(password),
        display_name=username,
        role=role,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def api(runtime: RagRuntime, db: Session):
    """返回带依赖覆盖的测试用 FastAPI + TestClient。"""
    app = FastAPI(title="solartrace-test")
    for r in (auth.router, documents.router, search.router, chat.router, eval_router.router, system.router):
        app.include_router(r, prefix="/api/v1")
    register_exception_handlers(app)

    def _get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_runtime] = lambda: runtime
    client = TestClient(app)
    # 预置管理员/编辑用户
    _make_user(db, "admin", Role.ADMIN.value)
    _make_user(db, "editor", Role.EDITOR.value)
    _make_user(db, "viewer", Role.VIEWER.value)
    db.commit()
    return client, db, runtime


def login(client: TestClient, username: str, password: str = "secret123") -> dict:
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()
