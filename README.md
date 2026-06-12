# GustoBot 🍲

菜谱领域智能助手，基于 **LangGraph** 构建 Multi-Agent 工作流，支持多源数据融合检索（Neo4j 知识图谱 + Milvus 向量库 + MySQL 关系型数据库），提供自然语言菜谱问答、统计查询、图片识别与文件分析能力。

---

## 技术栈

### 核心框架

| 技术 | 版本 | 用途 |
|------|------|------|
| **FastAPI** | 0.109.0 | HTTP 后端服务 |
| **LangGraph** | 0.2.60 | 多智能体状态图编排 |
| **LangChain** | 0.3.6 | LLM 工具链 |
| **Pydantic** | 2.10.4 | 数据校验与序列化 |
| **Python** | ≥ 3.12 | 运行时 |

### 数据库

| 数据库 | 用途 | 本地端口 |
|--------|------|---------|
| **Neo4j** | 菜谱知识图谱（概念、食材关系、烹饪步骤） | 17687 |
| **Milvus** | 向量语义检索（1024 维 Embedding） | 19530 |
| **MySQL** | 结构化数据（菜谱元数据、评分、统计） | 13306 |
| **Redis Stack** | LangGraph Checkpoint + 会话管理 | 6379 |

### AI 模型（阿里云百炼 DashScope）

| 模型 | 用途 |
|------|------|
| `qwen-plus` | 主 LLM（意图识别、对话生成、SQL 生成） |
| `text-embedding-v3` | 文本向量化（维度 1024） |
| `gte-rerank` | 检索结果精排 |
| `qwen-vl-max` | 图片识别（可选） |

### 工具链

| 工具 | 用途 |
|------|------|
| **uv** | Python 包管理 |
| **Docker Compose** | 基础设施编排 |
| **Uvicorn** | ASGI 服务器 |
| **loguru** | 结构化日志 |

---

## 架构设计

采用 **DDD（领域驱动设计）** 分层架构：

```
gustobot/
├── config/                     # 配置层 — 环境变量管理
│   └── settings.py             # Pydantic-Settings 单例，从 .env 加载
│
├── domain/models/              # 领域层 — 纯数据模型
│   └── schemas.py              # API 请求/响应 Pydantic 模型
│
├── application/                # 应用层 — 业务逻辑编排
│   ├── agents/                 # LangGraph 多智能体工作流
│   │   ├── lg_builder.py       # 主图构建（节点注册 + 条件路由）
│   │   ├── lg_states.py        # 全局状态定义（AgentState, Router）
│   │   ├── rag_sub_graph/      # GraphRAG 子图（Neo4j 知识图谱检索）
│   │   └── text2sql_sub_graph/ # Text2SQL 子图（MySQL 统计查询）
│   ├── prompts/                # Prompt 集中管理
│   └── services/               # 业务服务（chat、knowledge、session）
│
├── infrastructure/             # 基础设施层 — 数据库驱动与工具
│   ├── core/                   # 日志、上下文管理、重排序器
│   ├── knowledge/              # Neo4j 图数据库客户端
│   └── persistence/            # Milvus 索引工具
│
└── interfaces/http/            # 接口层 — RESTful API
    ├── router.py               # 路由注册器（/api/v1 前缀）
    ├── chat.py                 # 对话接口（流式/非流式）
    ├── knowledge.py            # 知识库 CRUD + 语义搜索
    ├── sessions.py             # 会话管理
    ├── upload.py               # 文件/图片上传
    └── exceptions.py           # 统一异常处理
```

---

## LangGraph 工作流

### 主图流程

```
用户消息
    ↓
┌─────────────────────────────────┐
│  analyze_and_route_query        │  LLM 意图识别 → 7 种路由
└──────────┬──────────────────────┘
           ↓ 条件路由
    ┌──────┼──────┬─────────┬──────┬──────┐
    ↓      ↓      ↓         ↓      ↓      ↓
  闲聊   GraphRAG Text2SQL  追问   图片   文件
    │      │      │         │      │      │
    └──────┴──────┴─────────┴──────┴──────┘
                        ↓
              process_response（统一回复处理）
                        ↓
              check_hallucinations（有文档时）
                        ↓
                       END
```

### 7 种路由类型

| 路由 | 触发条件 | 数据源 |
|------|---------|--------|
| `general-query` | 闲聊、常识 | 纯 LLM |
| `graphrag-query` | 做法、食材、步骤 | Neo4j 知识图谱 |
| `text2sql-query` | 统计、排名、数量 | MySQL |
| `additional-query` | 信息不足需追问 | LLM + Neo4j Schema |
| `image-query` | 图片识别/生成 | 视觉模型 |
| `file-query` | 用户上传文件分析 | LLM |

### GraphRAG 子图

处理知识图谱相关查询，内部流程：

```
问题输入
  ↓ Guardrails（范围检查）
  ↓ Planner（任务拆解）
  ↓ Tool Selection（工具选择）
  ├─ text2cypher（自然语言 → Cypher）
  ├─ predefined_cypher（预定义查询库）
  └─ graphrag（多跳关系遍历）
  ↓ Summarization（文档汇总）
  ↓ Final Answer
```

### Text2SQL 子图

处理统计与聚合查询，内部流程：

```
问题输入
  ↓ Guardrails（范围检查）
  ↓ Query Analysis（意图分析）
  ↓ SQL Generation（LLM 生成 SQL）
  ↓ SQL Validation（语法 + 安全检查）
  ↓ SQL Execution（SQLAlchemy 执行）
  ↓ Format Answer（结果格式化）
```

---

## API 接口

统一前缀 `/api/v1`

## 数据库可视化入口

启动全部基础设施和可视化服务：

```bash
docker compose up -d
```

- Neo4j Browser: `http://localhost:17474`
- MySQL Adminer: `http://localhost:18080`
  - System: `MySQL`
  - Server: `mysql`
  - Username: `recipe_user`
  - Password: `recipepass`
  - Database: `recipe_db`
- Redis Insight: `http://localhost:18081`
  - Host: `redis`
  - Port: `6379`
- Milvus Attu: `http://localhost:18000`
  - Address: `milvus:19530`

### 健康检查

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/health` | 检查 Redis/Milvus/Neo4j/MySQL 连通性 |

### 对话 `/chat`

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/` | 非流式对话 |
| POST | `/stream` | SSE 流式对话 |
| DELETE | `/session/{session_id}` | 删除会话及 Checkpoint |
| GET | `/routes` | 查看路由类型列表 |

### 知识库 `/knowledge`

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/recipes` | 添加菜谱到向量库 |
| POST | `/recipes/batch` | 批量添加 |
| POST | `/search` | 语义搜索 |
| DELETE | `/recipes/{recipe_id}` | 删除指定菜谱 |
| DELETE | `/clear?confirm=true` | 清空知识库 |
| GET | `/stats` | 知识库统计 |
| GET | `/graph` | 图谱快照 |
| POST | `/graph/qa` | 图谱问答 |

### 会话 `/sessions`

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/` | 创建会话 |
| GET | `/` | 列出所有会话（支持 `skip`/`limit` 分页、`user_id` 过滤） |
| GET | `/{session_id}` | 获取会话详情 |
| PATCH | `/{session_id}` | 更新会话（title, tags 等） |
| DELETE | `/{session_id}` | 删除会话 |
| GET | `/{session_id}/history` | 获取对话历史 |
| GET | `/user/{user_id}/count` | 用户会话数 |

### 文件上传 `/upload`

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/file` | 上传文件 |
| POST | `/image` | 上传图片 |
| GET | `/files/{filename}` | 获取已上传文件 |
| GET | `/images/{filename}` | 获取已上传图片 |
| DELETE | `/{file_id}` | 删除文件 |

---

## 数据流

```
客户端 → FastAPI 接口层 → 服务层 → LangGraph 主图
                                        ↓
                               意图识别 → 条件路由
                                        ↓
                         ┌──────────────┼──────────────┐
                         ↓              ↓              ↓
                    Neo4j 图谱     Milvus 向量      MySQL
                   (GraphRAG)    (语义检索)     (Text2SQL)
                         └──────────────┼──────────────┘
                                        ↓
                               统一回复处理 + 幻觉检查
                                        ↓
                                   会话持久化 (Redis)
                                        ↓
                                   返回客户端
```

---

## 运维与工程特性

### 统一异常处理

全局注册 3 类异常处理器（`interfaces/http/exceptions.py`），所有错误响应格式统一：

```json
{
  "status": "error",
  "code": 422,
  "message": "请求参数校验失败",
  "detail": [{"field": "body → message", "message": "Field required"}]
}
```

| 异常类型 | 状态码 | 行为 |
|---------|--------|------|
| `HTTPException` | 原始码 | 结构化 JSON |
| `RequestValidationError` | 422 | 字段级错误详情 |
| 未捕获异常 | 500 | 记录堆栈 + 安全信息 |

### 健康检查

`GET /health` 检查四个基础服务连通性，返回 200（全部健康）或 503（降级）。

### 请求日志中间件

每个 HTTP 请求自动记录方法、路径、状态码和耗时（ms），由 `log_request_time` 中间件实现。

### 异步优化

- **Redis**：`session_service.py` 使用 `redis.asyncio`，全部异步操作
- **文件 I/O**：`upload.py` 使用 `aiofiles` 异步读写
- **Milvus/Neo4j**：`knowledge.py` 路由层通过 `asyncio.to_thread()` 包裹同步调用

### 幻觉检测重试

对有文档支撑的回答进行幻觉检查，不通过时自动重试（最多 3 次），超过阈值返回降级提示。

### 前端测试面板

访问 `http://localhost:8000/` 可打开内置 API 测试面板（`static/index.html`），覆盖全部接口，支持一键调试。

---

## 快速启动

详见 [docs/启动指南.md](docs/启动指南.md)

首次启动完整流程：

```bash
# 1. 启动基础设施和可视化服务
docker compose up -d

# 2. 安装依赖
uv sync

# 3. 配置 .env
# 参见 docs/启动指南.md

# 4. 导入 Neo4j 知识图谱数据
docker compose exec neo4j cypher-shell -f /import/neo4j_import.cypher

# 5. 重建 Milvus 向量索引
python -m gustobot.infrastructure.persistence.rebuild_milvus_index

# 6. 启动应用
python main.py

# 7. 打开测试面板
open http://localhost:8000

# 8. 或命令行测试
curl -X POST http://127.0.0.1:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "红烧肉怎么做", "session_id": "demo"}'
```

日常启动流程：

```bash
docker compose up -d
python main.py
```

重新导入 Neo4j 图谱数据：

```bash
docker compose exec neo4j cypher-shell "MATCH (n) DETACH DELETE n;"
docker compose exec neo4j cypher-shell -f /import/neo4j_import.cypher
python -m gustobot.infrastructure.persistence.rebuild_milvus_index
```

数据初始化说明：

- MySQL 容器首次创建时会自动执行 `gustobot/data/init_mysql.sql` 和 `gustobot/data/insert_sample_data.sql`。
- Neo4j 使用 `gustobot/data/kg_output/neo4j_import.cypher` 导入图谱数据。
- Milvus 索引依赖 Neo4j 数据和 Embedding 配置，重建前需确认 `.env` 中的 `EMBEDDING_API_KEY` 可用。

---

## 环境变量

在项目根目录创建 `.env` 文件，关键配置项：

| 变量 | 说明 | 默认值 |
|------|------|-------|
| `LLM_API_KEY` | 阿里云百炼 API Key | **必填** |
| `LLM_MODEL` | 主 LLM 模型名 | `qwen-plus` |
| `LLM_BASE_URL` | OpenAI 兼容端点 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `API_PREFIX` | API 路由前缀 | `/api/v1` |
| `NEO4J_URI` | Neo4j 连接地址 | `bolt://localhost:17687` |
| `MYSQL_HOST` / `MYSQL_PORT` | MySQL 地址 | `localhost` / `13306` |
| `REDIS_URL` | Redis 连接 | `redis://localhost:6379` |
| `MILVUS_HOST` / `MILVUS_PORT` | Milvus 地址 | `localhost` / `19530` |

> Docker 服务名作为默认 host，本地开发需在 `.env` 覆盖为 `localhost`。
