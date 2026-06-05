#!/bin/bash

# StackPilot Docker 停止脚本

set -e

echo "停止 StackPilot..."

docker-compose -f docker-compose.rust.yml down

echo "StackPilot 已停止"
