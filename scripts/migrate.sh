#!/bin/bash
set -e

DB_URL="${DATABASE_URL:-postgresql://user:password@localhost:15432/stackpilot}"

echo "执行数据库迁移..."
echo "DATABASE_URL: $DB_URL"
echo ""

cd migration
DATABASE_URL="$DB_URL" cargo run -- up

echo ""
echo "迁移完成"
