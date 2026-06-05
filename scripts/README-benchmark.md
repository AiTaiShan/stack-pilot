# StackPilot 性能基准测试

## 测试内容

1. **健康检查性能** - 测试 API 响应延迟和吞吐量
2. **并发性能** - 测试多并发请求处理能力
3. **内存使用** - 对比 Rust 和 Python 的内存占用

## 运行测试

```bash
# 确保服务已启动
./scripts/start.sh

# 运行基准测试
./scripts/benchmark.sh
```

## 预期结果

| 指标 | Rust | Python | 提升 |
|------|------|--------|------|
| 健康检查延迟 | <1ms | ~5ms | 5x |
| 吞吐量 | >10000 req/s | ~2000 req/s | 5x |
| 内存占用 | ~10MB | ~50MB | 5x |

## 依赖工具

- `curl` - HTTP 请求
- `bc` - 计算
- `ab` 或 `wrk` - 并发测试（可选）

安装并发测试工具：
```bash
# Apache Bench
sudo apt-get install apache2-utils

# wrk
sudo apt-get install wrk
```
