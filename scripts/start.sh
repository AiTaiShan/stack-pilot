#!/bin/bash

# StackPilot 启动脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# ── 端口检查 ──────────────────────────────────────
check_port() {
    local port=$1
    local name=$2
    if command -v lsof &>/dev/null; then
        if lsof -i :"$port" -sTCP:LISTEN &>/dev/null; then
            echo "错误: 端口 $port 已被占用 ($name)"
            echo "请先停止占用该端口的进程，或手动释放端口:"
            echo "  lsof -i :$port"
            exit 1
        fi
    elif command -v ss &>/dev/null; then
        if ss -tlnp "sport = :$port" 2>/dev/null | grep -q ":$port"; then
            echo "错误: 端口 $port 已被占用 ($name)"
            echo "请先停止占用该端口的进程，或手动释放端口:"
            echo "  ss -tlnp sport = :$port"
            exit 1
        fi
    fi
}

check_port 8066 "Agent 服务"
check_port 9099 "Rust 主服务"

echo "启动 StackPilot..."

# 检查 .env 文件
if [ ! -f .env ]; then
    echo "警告: .env 文件不存在，使用默认配置"
fi

# 加载 Rust 环境（如果已安装）
export PATH="$HOME/.rustup/toolchains/stable-x86_64-unknown-linux-gnu/bin:$PATH"

# ── Agent 服务 ──────────────────────────────────────
echo "启动 Agent 服务..."
if ! command -v uv &>/dev/null; then
    echo "错误: 未找到 uv（Python 包管理器）"
    echo "请安装 uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

cd "$PROJECT_ROOT/services/agent"
uv sync --quiet

AGENT_LOG="/tmp/stackpilot-agent.log"
uv run uvicorn src.main:app --reload --reload-dir src \
    --host 0.0.0.0 --port 8066 > "$AGENT_LOG" 2>&1 &
AGENT_PID=$!
cd "$PROJECT_ROOT"

# 等待 Agent 服务启动并检查存活
sleep 3
if ! kill -0 "$AGENT_PID" 2>/dev/null; then
    echo "错误: Agent 服务启动失败，详见 $AGENT_LOG"
    cat "$AGENT_LOG"
    exit 1
fi

# ── Rust 主服务 ─────────────────────────────────────
if ! command -v cargo &> /dev/null; then
    echo "错误: 未找到 cargo（Rust 工具链）"
    echo "请安装 Rust: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"
    echo "安装后执行: source ~/.cargo/env"
    kill $AGENT_PID 2>/dev/null
    exit 1
fi

echo "启动 Rust 主服务（首次编译可能需要 1-2 分钟）..."
cd "$PROJECT_ROOT/services/api"
if command -v cargo-watch &>/dev/null; then
    cargo watch -x run &
else
    cargo run &
fi
BACKEND_PID=$!
cd "$PROJECT_ROOT"

# 等待 Rust 服务编译完成并就绪
echo -n "等待 Rust 主服务就绪"
for i in $(seq 1 120); do
    if ss -tlnp 2>/dev/null | grep -q ":9099 " || \
       lsof -i :9099 -sTCP:LISTEN &>/dev/null 2>&1; then
        echo ""
        break
    fi
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo ""
        echo "错误: Rust 主服务启动失败"
        exit 1
    fi
    echo -n "."
    sleep 2
done

if ! ss -tlnp 2>/dev/null | grep -q ":9099 " && \
   ! lsof -i :9099 -sTCP:LISTEN &>/dev/null 2>&1; then
    echo ""
    echo "错误: Rust 主服务在 240 秒内未就绪"
    exit 1
fi

echo "StackPilot 已启动"
echo "  - Rust 主服务: http://localhost:9099"
echo "  - Agent 服务: http://localhost:8066"
echo ""
echo "按 Ctrl+C 停止服务"

# 等待信号
cleanup() {
    echo ""
    echo "正在停止服务..."
    kill $AGENT_PID $BACKEND_PID 2>/dev/null
    wait $AGENT_PID $BACKEND_PID 2>/dev/null
    echo "StackPilot 已停止"
    exit 0
}
trap cleanup INT TERM
wait
