# StackPilot

智能部署 Agent — 输入 Git 仓库地址，自动完成整个部署流程。

## 功能特性

### 核心能力

- **智能代码扫描** — 自动识别技术栈（Node.js/Python/Java/Go/Rust/.NET/PHP/Ruby）和框架
- **多服务项目支持** — 支持单体应用、前后端分离、Spring Cloud 多模块、通用微服务架构
- **外部依赖检测** — 自动检测 40+ 外部服务（MySQL/Redis/Kafka/Elasticsearch/MongoDB 等）
- **数据库初始化** — 自动检测迁移工具（Alembic/Flyway/Prisma/TypeORM 等）和种子数据
- **AI 配置审核** — 集成大模型审核 Dockerfile 和 docker-compose.yml，提供优化建议

### 部署能力

- **多平台部署** — 支持本地 Docker、Kubernetes、Coolify 平台
- **6 步自动化流程** — 克隆 → 构建 → 推送 → 部署 → 配置 → 验证
- **实时进度跟踪** — 可视化部署步骤，实时日志流，抽屉式详情面板
- **中断恢复** — 检查点机制，支持暂停/恢复/回滚部署
- **容器清理** — 自动清理旧镜像和悬空资源，防止磁盘膨胀
- **重复部署防护** — 同项目同分支禁止并发部署，避免资源冲突

### 管理能力

- **项目管理** — 项目 CRUD，动态分支选择，自动检测默认分支
- **部署记录** — 完整部署历史，支持重试和终止操作
- **配置管理** — 系统配置 CRUD，敏感值自动遮蔽，验证规则
- **监控日志** — 结构化 JSON 日志，部署指标统计，系统状态监控
- **安全加固** — 速率限制、安全响应头、请求日志
- **错误处理** — 统一错误码、指数退避重试、AI 错误诊断

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.10+ / FastAPI / SQLAlchemy / Alembic |
| 前端 | React 18 / TypeScript / Ant Design / Zustand / ESLint(含 import 校验) |
| 数据库 | PostgreSQL 15 |
| 缓存 | Redis 7 |
| LLM | 阿里百炼 (qwen-plus) / OpenAI 兼容接口 |
| 部署 | Docker / Kubernetes / Coolify |

## 支持的语言和框架

| 语言 | 框架 | 特点 |
|------|------|------|
| Python | FastAPI, Django, Flask | 自动检测 requirements.txt/pyproject.toml |
| JavaScript/TypeScript | Next.js, React, Vue, Express | 自动检测 package.json |
| Java | Spring Boot, Spring Cloud | 支持多模块 Maven/Gradle 项目 |
| Go | Gin, Echo, Fiber | 自动检测 go.mod/go.sum |
| Rust | Actix, Axum | 自动检测 Cargo.toml |
| .NET | ASP.NET Core | 自动检测 .csproj |
| PHP | Laravel, Symfony | 自动检测 composer.json |
| Ruby | Rails, Sinatra | 自动检测 Gemfile |

## 支持的外部服务

| 类型 | 服务 |
|------|------|
| 数据库 | MySQL, PostgreSQL, MongoDB, SQLite, SQL Server, Oracle |
| 缓存 | Redis, Memcached |
| 消息队列 | Kafka, RabbitMQ, RocketMQ, ActiveMQ |
| 搜索引擎 | Elasticsearch, OpenSearch |
| 对象存储 | MinIO, AWS S3 |
| 注册中心 | Nacos, Consul, ZooKeeper, Eureka |
| 配置中心 | Nacos, Apollo, Consul |
| 其他 | Etcd, InfluxDB, Neo4j, ClickHouse |

## 快速开始

### Docker Compose（推荐）

```bash
# 克隆项目
git clone <repo-url>
cd stack-pilot

# 配置环境变量
cp .env.example .env
# 编辑 .env，配置 LLM_API_KEY、JWT_SECRET_KEY 等

# 一键启动
docker-compose up -d

# 访问
# 前端: http://localhost:5173
# 后端 API: http://localhost:9000
# API 文档: http://localhost:9000/docs
```

### 本地开发

#### 1. 启动数据库和 Redis

```bash
docker-compose up -d db redis
```

#### 2. 后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 初始化数据库
cp ../.env.example ../.env  # 首次需要
.venv/bin/alembic upgrade head

# 启动
.venv/bin/uvicorn app.main:app --reload --port 9099
```

#### 3. 前端（请使用 pnpm）

```bash
cd frontend
pnpm install
pnpm run dev

# 代码检查
pnpm run lint

# 生产构建
pnpm run build
```

#### 4. 运行测试

```bash
cd backend
.venv/bin/pytest tests/ -v
```

## 项目结构

```
stack-pilot/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # API 路由（auth/projects/deployments/configs/monitoring）
│   │   ├── core/            # 核心模块（config/database/security/error_handler/middleware）
│   │   ├── models/          # SQLAlchemy 模型（user/project/deployment/config）
│   │   ├── schemas/         # Pydantic 数据模式
│   │   ├── services/        # 业务逻辑
│   │   │   ├── auth/        # 认证服务
│   │   │   ├── scanner/     # 代码扫描（检测规则 + Dockerfile 模板）
│   │   │   │   ├── rules/     # 语言检测规则（8 种语言）
│   │   │   │   └── templates/ # Dockerfile 模板（8 种语言）
│   │   │   ├── ai/          # AI 服务（配置审核 + 错误诊断）
│   │   │   ├── deployer/    # Docker/K8s/部署管理器 + 容器清理
│   │   │   ├── config/      # 配置管理
│   │   │   └── monitoring/  # 监控服务
│   │   └── utils/           # 工具（日志）
│   ├── alembic/             # 数据库迁移
│   ├── tests/               # 测试（232 个）
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api/             # Axios 客户端
│   │   ├── components/      # 布局和通用组件（含 DeploymentProgress）
│   │   ├── pages/           # 页面（Login/Dashboard/Projects/Deployments）
│   │   └── stores/          # Zustand 状态管理
│   ├── Dockerfile
│   └── nginx.conf
├── k8s/                     # Kubernetes 部署配置
├── docs/                    # 文档
│   ├── api.md               # API 文档
│   └── deployment.md        # 部署指南
├── docker-compose.yml
└── .env.example
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | PostgreSQL 连接地址 | `postgresql://user:password@localhost:5432/stackpilot` |
| `REDIS_URL` | Redis 连接地址 | `redis://localhost:6379` |
| `JWT_SECRET_KEY` | JWT 签名密钥 | `your-secret-key-here`（生产环境必须修改） |
| `LLM_PROVIDER` | LLM 服务商 | `dashscope` |
| `LLM_API_KEY` | LLM API Key | — |
| `LLM_MODEL` | LLM 模型名 | `qwen-plus` |
| `LLM_BASE_URL` | LLM 接口地址 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `DEBUG` | 调试模式 | `true` |

## 部署流程

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   克隆代码   │ →  │   构建镜像   │ →  │   推送镜像   │ →  │   部署应用   │ →  │   配置服务   │ →  │   验证部署   │
│    Clone    │    │    Build    │    │    Push     │    │   Deploy    │    │  Configure  │    │   Verify    │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
     10%                40%                60%                80%                90%               100%
```

### 特性亮点

- **智能检测**：自动识别项目类型、技术栈、外部依赖
- **AI 审核**：生成的 Dockerfile 和 docker-compose.yml 经过 AI 审核优化
- **实时进度**：可视化步骤进度，实时日志流
- **自动清理**：部署后自动清理旧镜像和悬空资源
- **错误诊断**：部署失败时 AI 自动分析错误原因并提供修复建议

## API 接口

### 认证
- `POST /api/v1/auth/register` — 用户注册
- `POST /api/v1/auth/login` — 用户登录
- `POST /api/v1/auth/refresh` — 刷新 Token

### 项目管理
- `GET /api/v1/projects/` — 项目列表
- `POST /api/v1/projects/` — 创建项目
- `GET /api/v1/projects/{id}` — 项目详情
- `PUT /api/v1/projects/{id}` — 更新项目
- `GET /api/v1/projects/{id}/branches` — 获取远程分支

### 部署管理
- `GET /api/v1/deployments/` — 部署列表
- `POST /api/v1/deployments/` — 创建部署
- `GET /api/v1/deployments/{id}/status` — 部署状态
- `GET /api/v1/deployments/{id}/logs` — 部署日志
- `POST /api/v1/deployments/{id}/cancel` — 终止部署
- `POST /api/v1/deployments/{id}/pause` — 暂停部署
- `POST /api/v1/deployments/{id}/resume` — 恢复部署
- `POST /api/v1/deployments/{id}/rollback` — 回滚部署
- `DELETE /api/v1/deployments/all` — 清空部署记录

### 监控
- `GET /api/v1/monitoring/status` — 系统状态
- `GET /api/v1/monitoring/deployments/stats` — 部署统计

## 文档

- [API 文档](docs/api.md) — 所有接口说明
- [部署指南](docs/deployment.md) — 详细部署步骤
- 交互式 API 文档：启动后端后访问 http://localhost:9000/docs

## 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 许可证

MIT License
