# SolarTrace backend —— 单阶段 uv 构建
# 构建上下文为仓库根目录： docker build -f deploy/backend.Dockerfile .
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=300 \
    UV_CONCURRENT_DOWNLOADS=8 \
    UV_DEFAULT_INDEX=https://repo.huaweicloud.com/repository/pypi/simple \
    PIP_DEFAULT_TIMEOUT=120

WORKDIR /app

# 先装依赖（利用缓存；readme 为 pyproject 声明文件，一并拷入避免元数据校验失败）
COPY backend/pyproject.toml ./
COPY backend/README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --no-install-project

# 拷贝源码、演示语料与脚本
COPY backend/app ./app
COPY backend/samples ./samples

EXPOSE 8000
VOLUME ["/app/data"]

# 启动：灌入演示语料（幂等）后启动 API
CMD sh -c "uv run python -m app.scripts.seed_demo && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"
