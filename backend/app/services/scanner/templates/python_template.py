#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Python Dockerfile 模板

提供 generate() 函数，根据输入的端口、构建命令、启动命令和框架
生成标准化的 Python Dockerfile 内容。
"""


def generate(port: int, build_cmd: str, start_cmd: str, framework: str = "") -> str:
    """生成 Python Dockerfile 内容。

    Args:
        port: 应用监听端口
        build_cmd: 构建/安装依赖命令（如 pip install -r requirements.txt）
        start_cmd: 启动命令（如 python manage.py runserver、uvicorn main:app）
        framework: 框架名称（如 "django"、"fastapi"、"flask"）

    Returns:
        Dockerfile 内容字符串
    """
    return f"""FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN {build_cmd}
COPY . .
EXPOSE {port}
CMD ["sh", "-c", "{start_cmd}"]
"""
