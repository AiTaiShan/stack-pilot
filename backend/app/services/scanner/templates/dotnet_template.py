#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
.NET Dockerfile 模板（多阶段构建）

提供 generate() 函数，根据输入的端口、构建命令、启动命令和框架
生成标准化的 .NET 多阶段构建 Dockerfile 内容。
"""


def generate(port: int, build_cmd: str, start_cmd: str, framework: str = "", version: str = "8.0") -> str:
    """生成 .NET Dockerfile 内容（多阶段构建）。

    Args:
        port: 应用监听端口
        build_cmd: 构建命令（如 dotnet publish -c Release -o out）
        start_cmd: 启动命令（如 dotnet app.dll，当前暂未使用）
        framework: 框架名称（如 "aspnet"，当前暂未使用）

    Returns:
        Dockerfile 内容字符串
    """
    sdk_image = f"mcr.microsoft.com/dotnet/sdk:{version}"
    runtime_image = f"mcr.microsoft.com/dotnet/aspnet:{version}"
    return f"""FROM {sdk_image} AS builder
WORKDIR /app
COPY . .
RUN {build_cmd or 'dotnet publish -c Release -o out'}

FROM {runtime_image}
WORKDIR /app
COPY --from=builder /app/out ./
EXPOSE {port}
CMD ["dotnet", "app.dll"]
"""
