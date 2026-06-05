#!/bin/bash

# StackPilot 启动脚本

set -e

echo "启动 StackPilot..."

# 检查 .env 文件
if [ ! -f .env ]; then
    echo "警告: .env 文件不存在，使用默认配置"
fi

# 启动 Agent 服务
echo "启动 Agent 服务..."
cd services/agent
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
uvicorn src.main:app --host 0.0.0.0 --port 9091 &
AGENT_PID=$!
cd ../..

# 等待 Agent 服务启动
sleep 3

# 启动 Rust 主服务
echo "启动 Rust 主服务..."
cd services/api
cargo run &
BACKEND_PID=$!
cd ../..

echo "StackPilot 已启动"
echo "  - Rust 主服务: http://localhost:9099"
echo "  - Agent 服务: http://localhost:9091"
echo ""
echo "按 Ctrl+C 停止服务"

# 等待信号
trap "kill $AGENT_PID $BACKEND_PID 2>/dev/null; exit" INT TERM
wait
