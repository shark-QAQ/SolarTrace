# SolarTrace（光溯）· 光伏政策智能问答平台

[![CI](https://github.com/shark-QAQ/SolarTrace/actions/workflows/ci.yml/badge.svg)](https://github.com/shark-QAQ/SolarTrace/actions/workflows/ci.yml)

**一个"答错了能被发现"的 RAG 系统。**

政策问答里最贵的错误不是答不出，是**引用了一个不存在的条款**——用户会照着它去办事。

所以这个项目的重点不在"检索更聪明"，而在**每一条答案都必须能被追到原文的某一行，并且追得到的时候，那行还在有效期**。

`FastAPI` · `SQLAlchemy` · `ChromaDB`(可切 Qdrant) · `bge-m3` · `BM25 + RRF` · `qwen2.5` · `Vue 3 + Vite`

> 📹 演示 GIF / 截图：待补
>
> 状态：可独立交付的前后端分离系统，19 项 pytest 全离线可复现。

---

## 30 秒：为什么 RAG 在政策场景特别危险

通用的 RAG demo 长这样：问一句，检索 top-k，拼进 prompt，模型答一段。

在政策场景，这套会死在三件事上：

| 死法 | 后果 |
| --- | --- |
| 模型把两条不同文件的条款缝在一起 | 用户拿着一个不存在的条款去办事 |
| 检索到的是**旧版**政策 | 已经废止的规定被当成现行有效 |
| 文档更新了，向量库没更新 | 答的是三个月前的答案，而且没人发现 |

这三件事的共同点是：**从输出上看不出来**。答案流畅、引用格式漂亮、语气笃定。

SolarTrace 的设计全部围绕一件事：**让"错"这件事变成可见的。**

---

## 三个设计，都是为了"错了能被发现"

### 1. 引用不是装饰，是强制绑定

答案里的每个 `[n]` 绑定到**文号 · 标题 · 章节路径**，不是"第 3 段"这种模糊位置。

检索命中后还要**回表校验**：文档状态是不是已归档、当前版本是不是最新。

> 已归档/已失效的政策，**即时不再返回**——哪怕向量还在库里。

### 2. 索引与文档库强一致

这是绝大多数 RAG 项目不做、但在真实业务里最先出事的环节：

| 动作 | 索引行为 |
| --- | --- |
| 上传 | 自动建索引 |
| **发布** | **重建索引** |
| **退稿 / 归档** | **清理对应向量** |
| 定期 | 对账修复（发现库与索引不一致时自动补） |

**发布即重建、退稿即清理**——保证"能检索到的，就是当前有效的"。

### 3. 评测是闭环，不是感觉

内置标注评测集，可一键跑分对比：**命中率（召回@K）/ 上下文召回率 / 引用准确率**。

改一次检索参数，就能回答"是变好了还是变差了"，而不是"我感觉好像好一点"。

---

## 检索链路

```
问题
 ↓ 查询理解与改写      术语归一 / 同义替换 / 术语扩展 / 文档类型软提示
 │                    例：「并网申请」→「并网验收要求」
 ↓ 双路召回            稠密 bge-m3 (top 30)  ‖  BM25 词法 (top 30)
 ↓ RRF 融合            k=60，两路排名倒数求和
 ↓ 两阶段精排          确定性精排默认（可配 bge-reranker 交叉编码器）
 │                    门限 0.30，首条恒保留
 ↓ 父子分块回填        子块（300 字 / overlap 60）用于检索，父块（按标题层级）喂给模型
 ↓ 回表校验            文档状态 + 当前版本
 ↓ 生成 (SSE)          qwen2.5:7b，答案强制带 [n] 引用
```

**为什么必须混合检索**：政策文本里「GB 50797」「逆变器」「并网」这类词，稠密向量经常分不清近义与专有名词；BM25 恰好补上。RRF 不需要调权重，两路都在前 30 的才会被推到最前。

**为什么用父子分块**：小块检索准，但上下文不全；大块上下文全，但检索糊。按标题层级切父块、用子块检索、命中后回填父块——两个都要。

---

## 评测基线

演示语料，Top-5，确定性精排，**不启用生成**（纯检索质量）：

| 指标 | 结果 |
| --- | --- |
| 命中率 @5 | **100%** |
| Top-1 命中 | **72%** |
| 上下文召回率 | **89.3%** |

勾选"生成"后可得到**引用准确率**。

> 语料规模：8 篇政策/规范 → 38 个片段；评测集 25 题。
> 这是一套**小规模但可复现**的基线，用来验证链路与回归，不代表真实语料规模下的表现。

---

## 工程

| 项 | 说明 |
| --- | --- |
| 分层 | `api → services(用例) → repositories(数据) / providers(外部适配器)` |
| 检索算法 | 独立在 `retrieval/` 与 `services/rag/`，上层只依赖协议，可替换、可测试 |
| 前后端 | **物理分离**，各自独立清单与环境，仅经 HTTP/SSE 通信 |
| 权限 | JWT + 管理员 / 编辑 / 访客三角色，登录与写操作审计留痕 |
| 测试 | **19 项 pytest，全部离线可复现**（临时库 + Hash 嵌入 + FakeLLM，不需要模型） |
| 部署 | Docker Compose 一键起（后端 + nginx 前端，Qdrant 可选） |
| 日志 | JSON / 文本双格式、健康检查、OpenAPI |

**测试里最关键的一组**：`发布 → 检索 → 改版 → 归档` 的一致性用例——这是"索引与文档库一致"这条设计的回归测试，也是最容易在重构中悄悄坏掉的地方。

---

## 快速开始

前置：Python 3.14 + [uv](https://github.com/astral-sh/uv) + Node 18+，本地 Ollama 有 `bge-m3` 和 `qwen2.5:7b`。

```bash
# 后端
cd backend
cp .env.example .env
uv sync --extra test
uv run python -m app.scripts.seed_demo        # 8 篇语料 → 38 片段 + 25 题评测集（幂等）
uv run uvicorn app.main:app --reload --port 8000
```

```bash
# 前端（另开终端）
cd frontend
npm install
npm run dev                                    # http://localhost:5173
```

登录：`admin / admin123`。

**没有 GPU / 没有模型**也能跑通链路：

```bash
SOLARTRACE_EMBEDDING_PROVIDER=hash
SOLARTRACE_LLM_PROVIDER=fake
```

### Docker

```bash
cp .env.example .env
docker compose -f deploy/docker-compose.yml up -d --build
# 前端 http://localhost:8080 ，接口经 nginx 反代到 /api
```

Ollama 在宿主机时，容器内用 `host.docker.internal:11434`。

---

## 语料说明（务必读）

仓库内置的 `backend/samples/corpus/*.md` 是**整理摘编的演示样本**，不是标准原文全文。

它的作用是**零门槛演示与评测**；真实部署请通过「文档库 → 上传发布」灌入单位正式文本，平台会按正式文本重建索引。

`desc` / `docs` 中均已标注这一口径——**不把演示语料说成真实语料，是这个项目的基本诚实**。

---

## 关键配置

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `SOLARTRACE_VECTOR_BACKEND` | `chroma` | `chroma`(本地持久) / `qdrant`(docker) |
| `SOLARTRACE_EMBEDDING_PROVIDER` | `ollama` | `ollama` / `hash`(离线退避) |
| `SOLARTRACE_LLM_PROVIDER` | `ollama` | `ollama` / `fake`(离线/测试) |
| `SOLARTRACE_RERANK_BACKEND` | `deterministic` | `deterministic` / `cross_encoder`(配 bge-reranker) |
| `SOLARTRACE_RECALL_DENSE_TOP_K` / `RECALL_BM25_TOP_K` / `RRF_K` | `30 / 30 / 60` | 召回与融合 |
| `SOLARTRACE_CHUNK_SIZE` / `CHUNK_OVERLAP` | `300 / 60` | 子块与重叠 |
| `SOLARTRACE_MIN_SCORE_KEEP` | `0.30` | 精排门限（首条恒保留） |

---

## 结构

```
SolarTrace/
├─ backend/            FastAPI（独立 venv / .env / data）
│  ├─ app/
│  │  ├─ core/         配置、日志、异常、DB、安全
│  │  ├─ models/       ORM 实体 + 领域枚举
│  │  ├─ repositories/ 数据访问（doc/user/eval/qa/audit）
│  │  ├─ services/     业务编排：文档、索引、检索、问答、评测
│  │  │  └─ rag/       解析 / 分块 / 存储路径
│  │  ├─ retrieval/    BM25 / 重排 / 查询改写 / DTO
│  │  ├─ providers/    向量库 / 嵌入 / LLM / 运行时装配
│  │  └─ api/          路由 / 依赖 / 错误转译
│  ├─ samples/         演示语料 + 演示评测集
│  └─ tests/           19 项 pytest（离线）
├─ frontend/           Vue3 SPA
├─ deploy/             Dockerfile / nginx / compose
└─ docs/               设计 / 接口 / 数据库 / RAG 方案 / 部署
```

---

## 文档

| 文档 | 内容 |
| --- | --- |
| [`docs/RAG方案与评测.md`](docs/RAG方案与评测.md) | 检索链路细节与评测方法 |
| [`docs/系统设计.md`](docs/系统设计.md) | 总体架构、分层、RAG 流程、一致性策略 |
| [`docs/接口设计.md`](docs/接口设计.md) | REST + SSE 帧格式 |
| [`docs/数据库设计.md`](docs/数据库设计.md) | 表结构与 ER |
| [`docs/部署运维.md`](docs/部署运维.md) | 配置、部署、日志、安全清单 |
| [`docs/需求设计书.md`](docs/需求设计书.md) | 背景、范围、验收口径 |

---

## 一句话

> **RAG 的难点从来不是"检索得准不准"，而是"文档变了之后，你还能不能保证答的是现在这一版"。**
