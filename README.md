# StackPilot

智能部署 Agent — 输入 Git 仓库地址，自动完成整个部署流程。

## 架构概览

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Frontend   │────▶│   services/api  │────▶│ services/agent  │
│  React+TS   │     │  (Rust/Axum)    │     │ (Python/LangG)  │
│  :5174      │     │    :9099        │     │    :9091        │
└─────────────┘     └─────────────────┘     └─────────────────┘
                           │
                     ┌─────┴─────┐
                     │ PostgreSQL │
                     │   :15432  │
                     └───────────┘
```

- **services/api** — Rust 主后端（Axum + SeaORM），负责 REST API、用户认证、项目管理、部署编排、代码扫描
- **services/agent** — Python AI 服务（FastAPI + LangGraph），负责 Dockerfile/Compose/环境变量的 AI 审核

## 功能特性

### 核心能力

- **智能代码扫描** — 自动识别 8 种语言（Node/Python/Java/Go/Rust/.NET/PHP/Ruby）和框架
- **多服务项目支持** — 单体应用、前后端分离、Spring Cloud 多模块、通用微服务架构
- **外部依赖检测** — 自动检测 39+ 外部服务（MySQL/Redis/Kafka/Elasticsearch/MongoDB 等）
- **AI 配置审核** — 集成大模型审核 Dockerfile、docker-compose.yml 和环境变量

### 部署能力

- **多平台部署** — 支持本地 Docker、Kubernetes、Coolify 平台
- **8 步自动化流程** — 克隆 → 审核 → 构建 → 环境变量审核 → 推送 → 部署 → 配置 → 验证
- **实时进度跟踪** — 可视化部署步骤，实时日志流
- **暂停/恢复/取消** — 部署过程中随时控制
- **检查点机制** — 步骤间持久化状态，支持断点续传
- **AI 错误诊断** — 部署失败时自动调用 AI 分析原因

### 安全能力

- **密码 bcrypt 哈希** — cost=12，不可逆加密
- **JWT 双 Token** — access_token (120min) + refresh_token (7天)
- **速率限制** — 300 次/分钟/IP
- **安全响应头** — X-Content-Type-Options, X-Frame-Options, CSP 等 5 个
- **统一错误格式** — 12 种错误码 + severity + retryable + timestamp

## 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| 主后端 | Rust / Axum / SeaORM | 1.96+ |
| AI 服务 | Python / FastAPI / LangGraph | 3.10+ |
| 前端 | React 18 / TypeScript / Ant Design / Zustand | — |
| 数据库 | PostgreSQL | 15 |
| 缓存 | Redis | 7-alpine |
| LLM | 阿里百炼 (qwen-plus) / OpenAI 兼容 | — |
| 部署 | Docker / Kubernetes / Coolify | — |

## 支持的语言和框架

| 语言 | 框架 | 默认端口 |
|------|------|----------|
| Python | FastAPI, Django, Flask | 8000 |
| JavaScript/TypeScript | Next.js, React, Vue, Express | 3000 |
| Java | Spring Boot, Spring Cloud, Quarkus | 8080 |
| Go | Gin, Echo, Fiber | 8080 |
| Rust | Actix, Axum, Rocket | 8080 |
| .NET | ASP.NET Core | 5000 |
| PHP | Laravel, Symfony | 8000 |
| Ruby | Rails, Sinatra | 3000 |

## 支持的外部服务

| 类型 | 服务 |
|------|------|
| 数据库 | MySQL, PostgreSQL, MongoDB, SQLite, Cassandra, CouchDB |
| 缓存 | Redis, Memcached |
| 消息队列 | Kafka, RabbitMQ, RocketMQ, NATS, Pulsar |
| 搜索引擎 | Elasticsearch, OpenSearch, Meilisearch, Solr |
| 对象存储 | MinIO, AWS S3, Azure Blob, GCS |
| 监控 | Prometheus, Grafana, Jaeger, Zipkin, Datadog |
| 注册中心 | Consul, Etcd, ZooKeeper, Nacos, Eureka |
| API 网关 | Kong, APISIX, Traefik |
| 其他 | Keycloak, Vault, XXL-Job, gRPC |

## 快速开始

### 前置条件

- Docker & Docker Compose
- Rust 1.96+
- Python 3.10+
- pnpm

### 一键初始化（推荐）

```bash
git clone https://github.com/your-org/stack-pilot.git
cd stack-pilot
./scripts/init.sh
```

初始化脚本会自动完成：
1. 检查依赖是否安装
2. 从 `.env.example` 创建 `.env`
3. 启动 PostgreSQL 和 Redis 容器
4. 执行数据库迁移（创建所有表和枚举类型）
5. 安装 Agent 和前端依赖

> 初始化完成后编辑 `.env`，填写 `LLM_API_KEY` 等配置。

### 启动服务

```bash
# 后端（API + Agent）
./scripts/start.sh

# 前端（另一个终端）
cd frontend && pnpm dev
```

### 手动步骤

如果不想用一键脚本，按以下顺序操作：

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env，配置 LLM_API_KEY、JWT_SECRET 等

# 2. 启动数据库和 Redis
docker-compose up -d db redis

# 3. 数据库迁移
./scripts/migrate.sh
# 或手动执行：
# cd migration && DATABASE_URL=postgresql://user:password@localhost:15432/stackpilot cargo run -- up

# 4. 启动 Agent 服务
cd services/agent
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
uvicorn src.main:app --host 0.0.0.0 --port 9091

# 5. 启动 Rust 主服务（自动执行迁移）
cd services/api
cargo run

# 6. 启动前端
cd frontend
pnpm install && pnpm dev
```

### 运行测试

```bash
cd services/api
cargo test
```

### 新增迁移

当表结构变更时，创建新的迁移文件：

```bash
# 在 migration/src/ 下新建迁移文件，例如 m20240201_000002_add_xxx.rs
# 在 migration/src/lib.rs 的 migrations() 中注册
# 执行迁移
./scripts/migrate.sh
```

## 项目结构

```
stack-pilot/
├── services/
│   ├── api/                    # Rust 主后端 (Axum + SeaORM)
│   │   ├── src/
│   │   │   ├── api/v1/         # REST API 路由（auth/projects/deployments/configs/monitoring/members/users）
│   │   │   ├── services/       # 业务逻辑
│   │   │   │   ├── auth/       # 认证服务（bcrypt + JWT）
│   │   │   │   ├── scanner/    # 代码扫描（8 种语言规则 + 依赖检测 + 结构检测）
│   │   │   │   │   ├── rules/      # 语言检测规则
│   │   │   │   │   ├── templates/  # Dockerfile 模板
│   │   │   │   │   └── dependency/ # 外部依赖检测
│   │   │   │   ├── deployer/   # 部署编排（8 步流程 + 暂停恢复 + 检查点）
│   │   │   │   │   ├── manager/    # 状态管理 + 执行器
│   │   │   │   │   ├── steps/      # 8 个部署步骤
│   │   │   │   │   ├── docker/     # Docker 操作（超时重试）
│   │   │   │   │   ├── k8s/        # Kubernetes 操作
│   │   │   │   │   └── compose/    # Compose 生成
│   │   │   │   ├── agent/      # Agent 服务客户端
│   │   │   │   ├── config/     # 配置管理（数据库 CRUD）
│   │   │   │   ├── project/    # 项目 + 成员管理
│   │   │   │   ├── user/       # 用户服务
│   │   │   │   └── monitoring/ # 监控服务（系统指标 + 部署统计）
│   │   │   ├── models/         # SeaORM 数据模型（7 个）
│   │   │   ├── middleware/     # 中间件（CORS/限流/安全头/日志/认证）
│   │   │   ├── utils/          # 工具（JWT/重试）
│   │   │   ├── db/             # 数据库连接
│   │   │   ├── config.rs       # 配置（读取根目录 .env）
│   │   │   └── error.rs        # 统一错误处理（12 种错误码）
│   │   ├── tests/              # 测试（52 个）
│   │   └── Cargo.toml
│   └── agent/                  # Python AI 服务 (FastAPI + LangGraph)
│       ├── src/
│       │   ├── agent/          # LangGraph 工作流（审核者→调度者→修复者）
│       │   ├── api/            # API 路由（health/review）
│       │   ├── llm/            # LLM 提供商（OpenAI/DashScope）
│       │   └── review/         # 审核逻辑（Dockerfile/Compose/环境变量）
│       └── requirements.txt
├── frontend/                   # React + TypeScript 前端
│   ├── src/
│   │   ├── api/                # Axios 客户端
│   │   ├── components/         # 组件（Layout/DeploymentProgress/EnvVarReviewModal）
│   │   ├── pages/              # 页面（Login/Dashboard/Projects/Deployments）
│   │   └── stores/             # Zustand 状态管理
│   └── package.json
├── k8s/                        # Kubernetes 部署配置
├── docs/                       # 文档
├── scripts/                    # 脚本
│   └── start.sh                # 一键启动脚本
├── docker-compose.yml          # 本地开发编排
├── docker-compose.rust.yml     # Rust 版编排
└── .env                        # 统一环境变量配置
```

## 环境变量

所有服务共享根目录 `.env` 文件：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | PostgreSQL 连接地址 | `postgresql://user:password@localhost:15432/stackpilot` |
| `REDIS_URL` | Redis 连接地址 | `redis://localhost:16379` |
| `JWT_SECRET` | JWT 签名密钥 | `your-secret-key-here`（生产环境必须修改） |
| `JWT_ALGORITHM` | JWT 算法 | `HS256` |
| `JWT_EXPIRE_MINUTES` | access_token 过期时间 | `120` |
| `REFRESH_TOKEN_DAYS` | refresh_token 过期时间 | `7` |
| `CORS_ORIGINS` | CORS 允许源（逗号分隔） | `http://localhost:5173,http://localhost:5174` |
| `SERVER_PORT` | 主服务端口 | `9099` |
| `AGENT_SERVICE_URL` | Agent 服务地址 | `http://localhost:9091` |
| `LLM_PROVIDER` | LLM 服务商 | `dashscope` |
| `LLM_API_KEY` | LLM API Key | — |
| `LLM_MODEL` | LLM 模型名 | `qwen-plus` |
| `LLM_BASE_URL` | LLM 接口地址 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `DEBUG` | 调试模式 | `true` |

## 部署流程

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│  克隆代码 │ → │ AI 审核  │ → │ 构建镜像 │ → │ 环境变量 │ → │ 推送镜像 │ → │ 部署应用 │ → │ 配置服务 │ → │ 验证部署 │
│  Clone   │   │ Review   │   │  Build   │   │ EnvReview│   │   Push   │   │  Deploy  │   │Configure │   │  Verify  │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
    10%            35%            55%            65%            75%            85%            93%            100%
```

### 状态机

```
PENDING → RUNNING → SUCCESS
    │        ├── PAUSED → RUNNING（用户恢复）
    │        └── FAILED → ROLLED_BACK（用户回滚）
    └── CANCELLED（用户取消）
```

## API 接口

### 认证
- `POST /api/v1/auth/register` — 用户注册（返回 token + refresh_token）
- `POST /api/v1/auth/login` — 用户登录（返回 token + refresh_token）
- `POST /api/v1/auth/refresh` — 刷新 Token

### 用户
- `GET /api/v1/users/me` — 获取当前用户信息
- `PUT /api/v1/users/me` — 更新当前用户信息

### 项目管理
- `GET /api/v1/projects` — 项目列表
- `POST /api/v1/projects` — 创建项目（自动校验 Git URL）
- `GET /api/v1/projects/{id}` — 项目详情
- `PUT /api/v1/projects/{id}` — 更新项目
- `DELETE /api/v1/projects/{id}` — 删除项目
- `GET /api/v1/projects/{id}/branches` — 获取远程分支列表

### 成员管理
- `GET /api/v1/projects/{id}/members` — 成员列表
- `POST /api/v1/projects/{id}/members` — 添加成员
- `PUT /api/v1/projects/{id}/members/{uid}` — 更新成员角色
- `DELETE /api/v1/projects/{id}/members/{uid}` — 移除成员

### 部署管理
- `GET /api/v1/deployments` — 部署列表
- `POST /api/v1/deployments` — 创建部署
- `GET /api/v1/deployments/{id}` — 部署详情
- `GET /api/v1/deployments/{id}/status` — 部署状态（含进度和当前步骤）
- `GET /api/v1/deployments/{id}/logs` — 部署日志
- `POST /api/v1/deployments/{id}/cancel` — 取消部署
- `POST /api/v1/deployments/{id}/pause` — 暂停部署
- `POST /api/v1/deployments/{id}/resume` — 恢复部署
- `POST /api/v1/deployments/{id}/rollback` — 回滚部署
- `GET /api/v1/deployments/{id}/compose-file` — 获取 compose 文件
- `PUT /api/v1/deployments/{id}/compose-file` — 更新 compose 文件
- `POST /api/v1/deployments/{id}/confirm-env-vars` — 确认环境变量审核
- `DELETE /api/v1/deployments/all` — 清空部署记录

### 配置管理
- `GET /api/v1/configs` — 配置列表（敏感值自动遮蔽）
- `GET /api/v1/configs/{key}` — 获取配置
- `POST /api/v1/configs` — 创建配置
- `PUT /api/v1/configs/{key}` — 更新配置
- `DELETE /api/v1/configs/{key}` — 删除配置

### 监控
- `GET /api/v1/monitoring/status` — 系统状态（CPU/内存/磁盘）
- `GET /api/v1/monitoring/stats` — 部署统计
- `GET /api/v1/monitoring/metrics/{name}` — 指标查询

### 健康检查
- `GET /api/v1/health` — 健康检查

## 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 许可证

MIT License
