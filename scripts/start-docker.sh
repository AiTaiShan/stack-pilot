#!/bin/bash

# StackPilot Docker 启动脚本

set -e

echo "使用 Docker Compose 启动 StackPilot..."

# 检查 .env 文件
if [ ! -f .env ]; then
    echo "警告: .env 文件不存在，使用默认配置"
fi

# 启动服务
docker-compose -f docker-compose.rust.yml up -d

echo "StackPilot 已启动"
echo "  - Rust 主服务: http://localhost:9099"
echo "  - Agent 服务: http://localhost:9091"
echo "  - PostgreSQL: localhost:15432"
echo "  - Redis: localhost:16379"
echo ""
echo "查看日志: docker-compose -f docker-compose.rust.yml logs -f"
echo "停止服务: docker-compose -f docker-compose.rust.yml down"
