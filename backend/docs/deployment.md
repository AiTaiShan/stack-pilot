# StackPilot 部署指南

## 概述

本文档介绍如何部署和运行 StackPilot 智能部署 Agent 系统。

---

## 环境要求

### 基础环境
- **Python**: 3.10 或更高版本
- **Node.js**: 18 或更高版本（前端开发）
- **PostgreSQL**: 14 或更高版本
- **Redis**: 6 或更高版本

### 开发工具
- **包管理器**: pip 或 poetry（Python），npm 或 yarn（Node.js）
- **数据库迁移**: Alembic（已集成）

---

## 快速启动

### 1. 克隆项目

```bash
git clone <repository-url>
cd stack-pilot
```

### 2. 后端服务

#### 创建虚拟环境

```bash
cd backend
python -m venv venv

# Linux/macOS
source venv/bin/activate

# Windows
venv\Scripts\activate
```

#### 安装依赖

```bash
# 使用国内镜像源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

#### 配置环境变量

创建 `.env` 文件：

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置以下变量：

```env
# 数据库配置
DATABASE_URL=postgresql://username:password@localhost:5432/stackpilot

# Redis 配置
REDIS_URL=redis://localhost:6379/0

# JWT 配置
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# LLM API 配置（用于智能分析）
LLM_API_KEY=your-llm-api-key
LLM_API_URL=https://api.openai.com/v1

# 应用配置
DEBUG=true
APP_NAME=StackPilot
APP_VERSION=1.0.0
```

#### 启动数据库

确保 PostgreSQL 和 Redis 服务已启动。

```bash
# PostgreSQL（如果使用 Docker）
docker run -d \
  --name stackpilot-db \
  -e POSTGRES_USER=stackpilot \
  -e POSTGRES_PASSWORD=stackpilot \
  -e POSTGRES_DB=stackpilot \
  -p 5432:5432 \
  postgres:14

# Redis（如果使用 Docker）
docker run -d \
  --name stackpilot-redis \
  -p 6379:6379 \
  redis:6
```

#### 运行数据库迁移

```bash
# 应用迁移
alembic upgrade head

# 创建迁移（开发时使用）
alembic revision --autogenerate -m "描述信息"
```

#### 启动后端服务

```bash
# 开发模式
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 或者使用 Python 直接运行
python -m app.main
```

后端服务将在 `http://localhost:9000` 启动。

API 文档地址：`http://localhost:9000/docs`（Swagger UI）

---

### 3. 前端服务

```bash
cd frontend

# 安装依赖（使用国内镜像）
npm install --registry=https://registry.npmmirror.com

# 启动开发服务器
npm run dev
```

前端服务将在 `http://localhost:5173` 启动。

---

## Docker Compose 部署

使用 Docker Compose 可以一键启动所有服务。

### 1. 准备环境变量

创建 `.env` 文件（同上）。

### 2. 启动服务

```bash
# 构建并启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 3. Docker Compose 配置

项目根目录下的 `docker-compose.yml` 包含以下服务：

```yaml
version: '3.8'

services:
  # PostgreSQL 数据库
  db:
    image: postgres:14
    environment:
      POSTGRES_USER: stackpilot
      POSTGRES_PASSWORD: stackpilot
      POSTGRES_DB: stackpilot
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  # Redis 缓存
  redis:
    image: redis:6
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  # 后端 API 服务
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://stackpilot:stackpilot@db:5432/stackpilot
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis

  # 前端服务
  frontend:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      - backend

volumes:
  postgres_data:
  redis_data:
```

### 4. 数据库迁移

在 Docker 环境中运行迁移：

```bash
docker-compose exec backend alembic upgrade head
```

---

## 环境变量说明

| 变量名 | 说明 | 默认值 | 必需 |
|--------|------|--------|------|
| `DATABASE_URL` | PostgreSQL 连接字符串 | - | 是 |
| `REDIS_URL` | Redis 连接字符串 | `redis://localhost:6379/0` | 是 |
| `JWT_SECRET_KEY` | JWT 签名密钥 | - | 是 |
| `JWT_ALGORITHM` | JWT 算法 | `HS256` | 否 |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | 访问令牌过期时间（分钟） | `30` | 否 |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | 刷新令牌过期时间（天） | `7` | 否 |
| `LLM_API_KEY` | LLM API 密钥 | - | 是 |
| `LLM_API_URL` | LLM API 地址 | - | 是 |
| `DEBUG` | 调试模式 | `false` | 否 |
| `APP_NAME` | 应用名称 | `StackPilot` | 否 |
| `APP_VERSION` | 应用版本 | `1.0.0` | 否 |

---

## 生产环境注意事项

### 1. 安全配置

#### JWT 密钥
- **必须**使用强随机字符串作为 `JWT_SECRET_KEY`
- 建议使用 256 位或更长的密钥
- 不要将密钥提交到版本控制系统

生成密钥示例：
```bash
# Python
python -c "import secrets; print(secrets.token_hex(32))"

# OpenSSL
openssl rand -hex 32
```

#### 调试模式
- 生产环境**必须**设置 `DEBUG=false`
- 调试模式会暴露敏感信息

### 2. CORS 配置

在 `app/main.py` 中配置 CORS：

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://yourdomain.com",
        "https://www.yourdomain.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**注意**: 生产环境不要使用 `allow_origins=["*"]`，应该明确指定允许的域名。

### 3. 数据库配置

#### 连接池
建议配置连接池参数：

```env
DATABASE_URL=postgresql://user:pass@host:5432/db?pool_size=20&max_overflow=10
```

#### 备份
定期备份数据库：

```bash
pg_dump -U stackpilot stackpilot > backup_$(date +%Y%m%d).sql
```

### 4. Redis 配置

#### 持久化
确保 Redis 配置了持久化（RDB 或 AOF）。

#### 内存限制
配置 `maxmemory` 和 `maxmemory-policy`：

```conf
maxmemory 256mb
maxmemory-policy allkeys-lru
```

### 5. 日志配置

生产环境建议：
- 使用结构化日志（JSON 格式）
- 配置日志轮转
- 将日志发送到集中式日志系统（如 ELK）

### 6. 监控

建议配置：
- 应用性能监控（APM）
- 健康检查端点
- 告警机制

### 7. 反向代理

建议使用 Nginx 或 Traefik 作为反向代理：

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /etc/ssl/certs/yourdomain.com.crt;
    ssl_certificate_key /etc/ssl/private/yourdomain.com.key;

    location / {
        proxy_pass http://localhost:9000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 常见问题

### Q: 数据库连接失败

检查：
1. PostgreSQL 服务是否启动
2. 连接字符串是否正确
3. 用户权限是否足够
4. 防火墙是否放行端口

### Q: Redis 连接失败

检查：
1. Redis 服务是否启动
2. 连接字符串是否正确
3. 是否需要密码认证

### Q: 迁移失败

```bash
# 查看当前迁移状态
alembic current

# 回滚迁移
alembic downgrade -1

# 重新应用迁移
alembic upgrade head
```

### Q: 前端无法连接后端

检查：
1. 后端服务是否启动
2. API 地址配置是否正确
3. CORS 配置是否允许前端域名

---

## 开发指南

### 运行测试

```bash
# 后端测试
cd backend
pytest

# 前端测试
cd frontend
npm test
```

### 代码规范

```bash
# Python 代码格式化
black .
isort .

# Python 代码检查
flake8
mypy .

# 前端代码格式化
npm run lint
```

---

## 技术支持

如有问题，请通过以下方式联系：
- 提交 GitHub Issue
- 查看项目文档
- 联系开发团队
