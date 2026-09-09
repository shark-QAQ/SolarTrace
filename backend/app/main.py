# app/main.py
"""SolarTrace（光溯）FastAPI 应用工厂与全局异常处理。"""
from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import auth, chat, documents, search, system
from app.api.routes import eval as eval_router
from app.core.config import get_settings
from app.core.database import SessionLocal, create_all
from app.core.errors import AppError
from app.core.logging import setup_logging
from app.providers.registry import get_runtime as _rt
from app.services.bootstrap_service import ensure_admin

logger = logging.getLogger(__name__)


def _error_response(err: AppError) -> JSONResponse:
    return JSONResponse(status_code=err.http_status, content={"error": err.to_payload()})


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error_response(exc)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "HTTP_ERROR", "message": str(exc.detail)}},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "VALIDATION_FAILED", "message": "参数校验失败", "detail": exc.errors()}},
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    settings = get_settings()
    logger.info("启动 %s v%s（%s）", settings.app_name, settings.app_version, settings.environment)
    create_all()
    db = SessionLocal()
    try:
        ensure_admin(db)
    finally:
        db.close()
    # 提前构建运行时，校验向量库连通性
    try:
        runtime = _rt()
        logger.info("运行时就绪：向量=%s 条，BM25=%s 条", runtime.store.count(), runtime.bm25.size)
    except Exception as exc:  # noqa: BLE001
        logger.warning("运行时初始化告警（仍可启动，问答/检索将报 503）: %s", exc)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="光伏电站建设政策与规范智能问答平台 —— 工业级 RAG（SolarTrace / 光溯）",
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
    )

    # CORS：前端分离部署时跨源放行
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-request-id"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    register_exception_handlers(app)

    api = app
    for r in (auth.router, documents.router, search.router, chat.router, eval_router.router, system.router):
        api.include_router(r, prefix="/api/v1")

    @app.get("/")
    def root() -> dict:
        return {"app": settings.app_name, "version": settings.app_version, "docs": "/docs"}

    return app


app = create_app()
