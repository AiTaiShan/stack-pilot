#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rust Dockerfile 模板

提供 generate() 函数，根据输入的端口、构建命令、启动命令和框架
生成标准化的 Rust 多阶段构建 Dockerfile 内容。
"""


def generate(port: int, build_cmd: str, start_cmd: str, framework: str = "") -> str:
    """生成 Rust Dockerfile 内容（多阶段构建）。

    Args:
        port: 应用监听端口
        build_cmd: 构建命令（如 cargo build --release）
        start_cmd: 启动命令（如 ./target/release/app）
        framework: 框架名称（当前暂未使用）

    Returns:
        Dockerfile 内容字符串
    """
    return f"""FROM rust:1.75-slim AS builder
WORKDIR /app
COPY Cargo.toml Cargo.lock ./
RUN cargo fetch
COPY . .
RUN {build_cmd or 'cargo build --release'}

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /app/target/release/* ./
EXPOSE {port}
CMD ["sh", "-c", "{start_cmd or './main'}"]
"""
