#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Go Dockerfile 模板

提供 generate() 函数，根据输入的端口、构建命令、启动命令和框架
生成标准化的 Go 多阶段构建 Dockerfile 内容。
"""


def generate(port: int, build_cmd: str, start_cmd: str, framework: str = "", version: str = "1.21") -> str:
    """生成 Go Dockerfile 内容（多阶段构建）。

    Args:
        port: 应用监听端口
        build_cmd: 构建命令（如 go build -o main .）
        start_cmd: 启动命令（如 ./main）
        framework: 框架名称（当前暂未使用）
        version: Go 版本号（如 "1.21", "1.24"），从 go.mod 中读取

    Returns:
        Dockerfile 内容字符串
    """
    go_image = f"golang:{version}-alpine"
    return f"""FROM {go_image} AS builder
WORKDIR /app
COPY go.mod go.sum ./
ENV GOPROXY=https://goproxy.cn,direct
RUN go mod download
COPY . .
RUN {build_cmd or 'CGO_ENABLED=0 GOOS=linux go build -o main .'}

FROM alpine:latest
RUN apk --no-cache add ca-certificates
WORKDIR /root/
COPY --from=builder /app/main .
EXPOSE {port}
CMD ["./main"]
"""
