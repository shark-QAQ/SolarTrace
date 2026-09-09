# app/core/errors.py
"""统一领域异常与错误码。

业务层只抛出领域异常，由 API 层异常处理器翻译为结构化响应，
保证各层解耦且对外响应格式稳定。
"""
from __future__ import annotations

from typing import Any


class AppError(Exception):
    """业务异常基类。"""

    code: str = "APP_ERROR"
    http_status: int = 400
    message: str = "请求处理失败"

    def __init__(self, message: str | None = None, *, detail: Any = None) -> None:
        self.message = message or self.message
        self.detail = detail
        super().__init__(self.message)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.detail is not None:
            payload["detail"] = self.detail
        return payload


class AuthError(AppError):
    code = "AUTH_UNAUTHORIZED"
    http_status = 401
    message = "未认证或登录已失效"


class PermissionDenied(AppError):
    code = "AUTH_FORBIDDEN"
    http_status = 403
    message = "当前账号无权执行该操作"


class NotFoundError(AppError):
    code = "RESOURCE_NOT_FOUND"
    http_status = 404
    message = "资源不存在"


class ConflictError(AppError):
    code = "RESOURCE_CONFLICT"
    http_status = 409
    message = "资源状态冲突"


class ValidationFailed(AppError):
    code = "VALIDATION_FAILED"
    http_status = 422
    message = "参数校验失败"


class ParseFailed(AppError):
    code = "DOC_PARSE_FAILED"
    http_status = 422
    message = "文档解析失败，请检查文件格式与内容"


class ChunkingFailed(AppError):
    code = "DOC_CHUNK_FAILED"
    http_status = 422
    message = "文档分块失败"


class ProviderUnavailable(AppError):
    """依赖的外部服务（Ollama/向量库）不可用。"""

    code = "PROVIDER_UNAVAILABLE"
    http_status = 503
    message = "底层模型/向量服务暂不可用"


class EmbeddingUnavailable(ProviderUnavailable):
    code = "EMBEDDING_UNAVAILABLE"
    message = "嵌入模型服务不可用，请检查 Ollama/嵌入服务"


class LLMUnavailable(ProviderUnavailable):
    code = "LLM_UNAVAILABLE"
    message = "大模型生成服务不可用，请检查 Ollama/生成服务"


class VectorStoreUnavailable(ProviderUnavailable):
    code = "VECTOR_UNAVAILABLE"
    message = "向量库服务不可用"


class RetriableBaseError(ProviderUnavailable):
    """供上层决定是否重试。"""


class RateLimited(AppError):
    code = "RATE_LIMITED"
    http_status = 429
    message = "请求过于频繁，请稍后再试"
