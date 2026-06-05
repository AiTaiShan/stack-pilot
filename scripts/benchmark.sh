#!/bin/bash

# StackPilot 性能基准测试脚本

set -e

echo "=========================================="
echo "StackPilot 性能基准测试"
echo "=========================================="
echo ""

# 检查服务是否运行
check_service() {
    local url=$1
    local name=$2
    if curl -s -f "$url" > /dev/null 2>&1; then
        echo "✓ $name 运行中"
        return 0
    else
        echo "✗ $name 未运行"
        return 1
    fi
}

echo "1. 检查服务状态"
echo "------------------------------------------"
RUST_RUNNING=false
PYTHON_RUNNING=false

if check_service "http://localhost:9099/api/v1/health" "Rust 主服务"; then
    RUST_RUNNING=true
fi

if check_service "http://localhost:9091/api/v1/health" "Python Agent 服务"; then
    PYTHON_RUNNING=true
fi

echo ""

# 健康检查性能测试
test_health_check() {
    local url=$1
    local name=$2
    local count=${3:-100}

    echo "测试 $name 健康检查 ($count 次请求)"
    echo "------------------------------------------"

    START_TIME=$(date +%s%N)
    for i in $(seq 1 $count); do
        curl -s "$url" > /dev/null
    done
    END_TIME=$(date +%s%N)

    DURATION=$(( (END_TIME - START_TIME) / 1000000 ))
    RPS=$(( count * 1000 / DURATION ))

    echo "  总耗时: ${DURATION}ms"
    echo "  平均延迟: $(echo "scale=2; $DURATION / $count" | bc)ms"
    echo "  吞吐量: ${RPS} req/s"
    echo ""
}

# 并发性能测试
test_concurrent() {
    local url=$1
    local name=$2
    local concurrency=${3:-10}
    local count=${4:-100}

    echo "测试 $name 并发性能 (${concurrency} 并发, ${count} 总请求)"
    echo "------------------------------------------"

    if command -v ab &> /dev/null; then
        ab -n $count -c $concurrency "$url" 2>/dev/null | grep -E "(Requests per second|Time per request|Transfer rate)"
    elif command -v wrk &> /dev/null; then
        wrk -t$concurrency -c$concurrency -d5s "$url" 2>/dev/null | grep -E "(Requests/sec|Avg|Transfer/sec)"
    else
        echo "  需要安装 ab 或 wrk 进行并发测试"
        echo "  安装: sudo apt-get install apache2-utils 或 sudo apt-get install wrk"
    fi
    echo ""
}

echo "2. 健康检查性能测试"
echo "=========================================="

if [ "$RUST_RUNNING" = true ]; then
    test_health_check "http://localhost:9099/api/v1/health" "Rust 主服务" 100
fi

if [ "$PYTHON_RUNNING" = true ]; then
    test_health_check "http://localhost:9091/api/v1/health" "Python Agent 服务" 100
fi

echo "3. 并发性能测试"
echo "=========================================="

if [ "$RUST_RUNNING" = true ]; then
    test_concurrent "http://localhost:9099/api/v1/health" "Rust 主服务" 10 1000
fi

if [ "$PYTHON_RUNNING" = true ]; then
    test_concurrent "http://localhost:9091/api/v1/health" "Python Agent 服务" 10 1000
fi

echo "4. 内存使用对比"
echo "=========================================="

if [ "$RUST_RUNNING" = true ]; then
    RUST_PID=$(pgrep -f "stackpilot-backend" | head -1)
    if [ -n "$RUST_PID" ]; then
        RUST_MEM=$(ps -o rss= -p $RUST_PID 2>/dev/null | awk '{print $1/1024}')
        echo "  Rust 主服务内存: ${RUST_MEM}MB"
    fi
fi

if [ "$PYTHON_RUNNING" = true ]; then
    PYTHON_PID=$(pgrep -f "uvicorn src.main:app" | head -1)
    if [ -n "$PYTHON_PID" ]; then
        PYTHON_MEM=$(ps -o rss= -p $PYTHON_PID 2>/dev/null | awk '{print $1/1024}')
        echo "  Python Agent 服务内存: ${PYTHON_MEM}MB"
    fi
fi

echo ""
echo "=========================================="
echo "测试完成"
echo "=========================================="
