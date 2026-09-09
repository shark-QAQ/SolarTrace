# SolarTrace backend

FastAPI 工业级 RAG 服务（详见仓库根 [README](../README.md) 与 [docs](../docs)）。

```bash
cp .env.example .env
uv sync --extra test
uv run python -m app.scripts.seed_demo      # 灌演示语料（幂等）
uv run uvicorn app.main:app --reload --port 8000
```

- 接口文档：`http://localhost:8000/docs`
- 测试：`uv run pytest -q`（离线，不依赖模型）
- 代码分层：`api → services → repositories/providers/retrieval`；检索算法见 `app/retrieval/`。
