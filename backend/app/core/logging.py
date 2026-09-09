# app/core/logging.py
"""结构化日志：text / json 两种格式，统一 request-id 串联。"""
from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

from app.core.config import get_settings


class JsonFormatter(logging.Formatter):
    """输出单行 JSON 日志，便于采集与检索。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # 附带业务字段（如 request_id）
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """简洁可读的文本日志。"""

    _FMT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"

    def __init__(self) -> None:
        super().__init__(self._FMT, "%H:%M:%S")


def setup_logging() -> None:
    """幂等初始化根日志。"""
    root = logging.getLogger()
    if root.handlers:
        return
    settings = get_settings()
    handler = logging.StreamHandler(sys.stdout)
    if settings.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(TextFormatter())
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
    # 降低三方库噪音
    logging.getLogger("uvicorn.access").setLevel(settings.log_level.upper())
    for noisy in ("httpx", "httpcore", "chromadb", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
