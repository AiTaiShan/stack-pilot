#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo -e "${GREEN}  StackPilot 初始化脚本${NC}"
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo ""

# ── 1. 检查依赖 ──────────────────────────────────────
echo -e "${YELLOW}[1/5] 检查依赖...${NC}"

check_cmd() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "${RED}✗ 未找到 $1，请先安装${NC}"
        exit 1
    fi
    echo -e "${GREEN}  ✓ $1 ($(command -v $1))${NC}"
}

check_cmd docker
check_cmd cargo
check_cmd python3
check_cmd pnpm

echo ""

# ── 2. 环境变量 ──────────────────────────────────────
echo -e "${YELLOW}[2/5] 配置环境变量...${NC}"

if [ ! -f .env ]; then
    cp .env.example .env
    echo -e "${GREEN}  ✓ 已从 .env.example 创建 .env${NC}"
    echo -e "${YELLOW}  ⚠ 请编辑 .env 填写 LLM_API_KEY 等配置${NC}"
else
    echo -e "${GREEN}  ✓ .env 已存在，跳过${NC}"
fi

echo ""

# ── 3. 启动数据库和 Redis ───────────────────────────
echo -e "${YELLOW}[3/5] 启动 PostgreSQL 和 Redis...${NC}"

docker-compose up -d db redis

echo -e "${YELLOW}  等待数据库就绪...${NC}"
for i in $(seq 1 30); do
    if docker-compose exec -T db pg_isready -U user -d stackpilot > /dev/null 2>&1; then
        echo -e "${GREEN}  ✓ PostgreSQL 就绪${NC}"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo -e "${RED}  ✗ PostgreSQL 启动超时${NC}"
        exit 1
    fi
    sleep 1
done

if docker-compose exec -T redis redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}  ✓ Redis 就绪${NC}"
else
    echo -e "${YELLOW}  ⚠ Redis 可能未就绪，继续...${NC}"
fi

echo ""

# ── 4. 数据库迁移 ───────────────────────────────────
echo -e "${YELLOW}[4/5] 执行数据库迁移...${NC}"

cd migration
DATABASE_URL=postgresql://user:password@localhost:15432/stackpilot cargo run -- up 2>&1 | while read line; do
    echo -e "  $line"
done
cd ..

echo -e "${GREEN}  ✓ 数据库迁移完成${NC}"
echo ""

# ── 5. 安装依赖 ─────────────────────────────────────
echo -e "${YELLOW}[5/5] 安装依赖...${NC}"

# Python Agent 依赖（使用虚拟环境）
echo -e "  创建 Agent Python 虚拟环境..."
python3 -m venv services/agent/.venv
echo -e "  安装 Agent 依赖..."
services/agent/.venv/bin/pip install -r services/agent/requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple -q 2>&1 | tail -1
echo -e "${GREEN}  ✓ Agent 依赖安装完成${NC}"

# 前端依赖
echo -e "  安装前端依赖..."
cd frontend
pnpm install --silent 2>&1 | tail -1
cd ..
echo -e "${GREEN}  ✓ 前端依赖安装完成${NC}"

echo ""
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo -e "${GREEN}  ✓ 初始化完成！${NC}"
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo ""
echo -e "启动服务："
echo -e "  ${YELLOW}./scripts/start.sh${NC}          # 启动后端（API + Agent）"
echo -e "  ${YELLOW}cd frontend && pnpm dev${NC}     # 启动前端"
echo ""
echo -e "服务地址："
echo -e "  前端:     http://localhost:5174"
echo -e "  API:      http://localhost:9099"
echo -e "  Agent:    http://localhost:8066"
echo -e "  数据库:   localhost:15432"
echo -e "  Redis:    localhost:16379"
echo ""
