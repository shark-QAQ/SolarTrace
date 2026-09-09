# SolarTrace（光溯）· 光伏政策智能问答平台

> 面向光伏电站建设场景的**工业级 RAG 智能问答平台**：混合检索、两阶段精排、查询改写、
> 引用溯源防幻觉、文档版本化建索引、RAG 评测闭环 —— 前后端分离、工程分层、可独立交付。

- 技术栈：`FastAPI` / `SQLAlchemy` / `ChromaDB`(默认, 可切 `Qdrant`) / `bge-m3`(Ollama) /
  `BM25(RRF)` / `qwen2.5`(Ollama 生成) / `Vue 3 + Vite + Element Plus`
- 运行形态：**前后端物理分离**（`backend/` 与 `frontend/` 各自独立清单与环境，仅经 HTTP/SSE 通信）；
  **模块分层**（core / repositories / services / providers / api）；**工程隔离**（独立 git/venv/data/容器）。

---

## 1. 功能一览

| 能力 | 说明 |
| --- | --- |
| 光伏政策智能问答 | SSE 流式；回答强制绑定 `[n]` 原文引用（文号·标题·章节路径），防编造条款 |
| 混合检索 | 稠密向量（bge-m3）+ BM25 词法双路召回 → RRF 融合 |
| 两阶段精排 | 召回 Top-K 后第二阶段精排并截断（确定性精排默认，可配 bge-reranker 交叉编码器） |
| 查询理解与改写 | 术语归一/同义替换/术语扩展/文档类型软提示（例：「并网申请」→「并网验收要求」） |
| 引用溯源与回表校验 | 检索命中后回表校验文档状态与当前版本，归档/失效政策即时不再返回 |
| 文档版本管理 | 上传自动建索引；**发布即重建索引、退稿即清理向量**，索引与文档库一致；对账修复 |
| 标题感知父子分块 | 按标题层级切父块，约 300 字 + overlap 子块入检索，保留章节路径 |
| RAG 评测闭环 | 标注评测集回归：命中率(召回@K)/上下文召回率/引用忠实度，可一键跑分对比 |
| 权限与审计 | JWT + 管理员/编辑/访客三角色；登录与写操作审计留痕 |
| 工程化 | JSON/文本日志、健康检查、OpenAPI 文档、pytest 自动化测试、Docker 一键部署 |

## 2. 目录结构（项目隔离）

```
SolarTrace/
├─ backend/                # FastAPI 服务（独立 venv / .env / data）
│  ├─ app/
│  │  ├─ core/             # 配置、日志、异常、DB、安全（横切层）
│  │  ├─ models/           # SQLAlchemy ORM 实体 + 领域枚举
│  │  ├─ repositories/     # 数据访问（doc/user/eval/qa/audit）
│  │  ├─ services/         # 业务编排：文档、索引、检索、问答、评测
│  │  │  └─ rag/           # 解析/分块/存储路径（领域算法）
│  │  ├─ retrieval/        # 检索算法：BM25 / 重排 / 查询改写 / DTO
│  │  ├─ providers/        # 外部适配器：向量库 / 嵌入 / LLM / 运行时装配
│  │  └─ api/              # 接口层（路由 / 依赖 / 错误转译）
│  ├─ samples/             # 演示语料库 + 演示评测集（整理摘编·演示样本）
│  ├─ scripts/             # 种子 / CLI
│  └─ tests/               # pytest（19 项，离线可复现）
├─ frontend/               # Vue3 SPA（独立 node_modules / vite 代理）
├─ deploy/                 # Dockerfile / nginx / docker-compose
├─ docs/                   # 设计/接口/数据库/RAG方案/部署文档
└─ README.md
```

分层原则：`api → services(用例) → repositories(数据) / providers(外部适配器)`；
检索算法沉淀在 `retrieval/` 与 `services/rag/`，上层仅依赖协议，便于替换与测试。

## 3. 快速开始（本机开发）

前置：Python 3.14 + [uv](https://github.com/astral-sh/uv) + Node 18+；本地 Ollama 已装
`bge-m3` 与 `qwen2.5:7b`（或任一可用的嵌入/生成模型，见 §7 配置）。

```bash
# 1) 后端：安装依赖
cd backend
cp .env.example .env            # 按需修改（默认即可本地运行）
uv sync --extra test

# 2) 灌入演示语料（8 篇政策/规范 → 38 个片段 + 25 题评测集；幂等，可重复执行）
uv run python -m app.scripts.seed_demo

# 3) 启动后端（默认 http://localhost:8000，接口文档 /docs）
uv run uvicorn app.main:app --reload --port 8000
```

```bash
# 4) 前端（另开终端，开发态经 /api 代理到 8000）
cd ../frontend
npm install
npm run dev                    # http://localhost:5173
```

打开 http://localhost:5173 → 登录（默认 `admin / admin123`）。

### 3.1 一键脚本
在 `backend/` 下可直接：
```bash
uv run python -m app.scripts.seed_demo        # 灌数据
uv run python -m pytest -q                    # 跑测试（离线、免模型）
uv run ruff check app tests                   # 静态检查
```

## 4. Docker 一键部署

> 镜像把后端（uv 构建）、前端（nginx 托管静态资源并反代 `/api`）分别打包；Qdrant 可选用。
> Ollama 位于宿主机时，容器内以 `host.docker.internal:11434` 访问。

```bash
cd SolarTrace
cp .env.example .env
docker compose -f deploy/docker-compose.yml up -d --build
# 前端 http://localhost:8080  →  接口 http://localhost:8080/api/...（经 nginx）
```

详见 [`docs/部署运维.md`](docs/部署运维.md)。

## 5. 语料与模型说明（务必阅读）

- 仓库内置的 `backend/samples/corpus/*.md` 是**整理摘编·演示样本**（要点概述，非标准原文全文），
  用于零门槛演示与评测；真实部署请使用单位正式政策/规范原文，通过“文档库 → 上传发布”入库，
  平台会按正式文本重建索引。`desc`/`docs` 中均已标注该口径。
- 默认运行时：嵌入 `bge-m3`、生成 `qwen2.5:7b`（Ollama）。无 GPU / 无模型时可设
  `SOLARTRACE_EMBEDDING_PROVIDER=hash`、`SOLARTRACE_LLM_PROVIDER=fake` 做**离线链路演示**（检索仍可跑通）。
- 评测基线（演示语料，Top-5，确定性精排，无生成）：命中率 @5 = 100%，Top1 = 72%，上下文召回 = 89.3%；
  勾选“生成”可得到引用忠实度。

## 6. 里程碑 / 说明文档

| 文档 | 内容 |
| --- | --- |
| [docs/需求设计书.md](docs/需求设计书.md) | 背景、范围、用例、非功能需求、验收口径 |
| [docs/系统设计.md](docs/系统设计.md) | 总体架构、分层、RAG 流程、一致性策略 |
| [docs/RAG方案与评测.md](docs/RAG方案与评测.md) | 检索链路细节与评测方法/基线 |
| [docs/接口设计.md](docs/接口设计.md) | REST 概览 + SSE 帧格式 |
| [docs/数据库设计.md](docs/数据库设计.md) | 表结构 ER 说明 |
| [docs/部署运维.md](docs/部署运维.md) | 配置清单、部署、日志、安全清单 |

## 7. 关键配置（backend/.env）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `SOLARTRACE_VECTOR_BACKEND` | `chroma` | `chroma`(本地持久) / `qdrant`(docker) |
| `SOLARTRACE_EMBEDDING_PROVIDER` | `ollama` | `ollama` / `hash`(离线退避) |
| `SOLARTRACE_LLM_PROVIDER` | `ollama` | `ollama` / `fake`(离线/测试) |
| `SOLARTRACE_EMBEDDING_MODEL` | `bge-m3` | 嵌入模型 |
| `SOLARTRACE_LLM_MODEL` | `qwen2.5:7b` | 生成模型 |
| `SOLARTRACE_RERANK_BACKEND` | `deterministic` | `deterministic` / `cross_encoder`(配 bge-reranker) |
| `SOLARTRACE_RECALL_DENSE_TOP_K` / `RECALL_BM25_TOP_K` / `RRF_K` | `30/30/60` | 召回与融合 |
| `SOLARTRACE_CHUNK_SIZE` / `CHUNK_OVERLAP` | `300/60` | 子块与重叠 |
| `SOLARTRACE_MIN_SCORE_KEEP` | `0.30` | 精排门限（首条恒保留） |

## 8. 测试

`backend/tests/` 共 19 项：分词/改写、父子分块、BM25/重排、**发布→检索→改版→归档一致性**、
认证/RBAC/上传发布/评测/SSE 冒烟。全部使用临时库 + Hash 嵌入 + FakeLLM，**离线可复现**：

```bash
cd backend && uv run python -m pytest -q
```
