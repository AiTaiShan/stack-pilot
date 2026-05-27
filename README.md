# StackPilot

智能部署Agent - 输入Git仓库地址，自动完成整个部署流程

## 功能特性

- 自动识别技术栈和依赖
- 自动创建数据库和缓存
- 自动构建Docker镜像
- 自动部署到K8s/Coolify
- 自动配置域名和SSL

## 快速开始

### 使用Docker Compose

```bash
# 克隆项目
git clone https://github.com/your-org/stackpilot.git
cd stackpilot

# 复制环境变量
cp .env.example .env

# 启动服务
docker-compose up -d

# 访问应用
# 前端: http://localhost:3000
# 后端API: http://localhost:8000
# API文档: http://localhost:8000/docs
```

### 本地开发

#### 后端

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

#### 前端

```bash
cd frontend
npm install
npm run dev
```

## 技术栈

- **后端**: Python + FastAPI
- **前端**: React + TypeScript
- **数据库**: PostgreSQL
- **缓存**: Redis
- **容器化**: Docker

## 文档

- [API文档](http://localhost:8000/docs)
- [用户手册](docs/user-manual.md)
- [部署指南](docs/deployment-guide.md)
