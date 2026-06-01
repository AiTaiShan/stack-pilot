#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ruby Dockerfile 模板

提供 generate() 函数，根据输入的端口、构建命令、启动命令和框架
生成标准化的 Ruby Dockerfile 内容。
"""


def generate(port: int, build_cmd: str, start_cmd: str, framework: str = "") -> str:
    """生成 Ruby Dockerfile 内容。

    Args:
        port: 应用监听端口
        build_cmd: 构建/安装依赖命令（如 bundle install）
        start_cmd: 启动命令（如 bundle exec rails server、ruby app.rb）
        framework: 框架名称（如 "rails"、"sinatra"）

    Returns:
        Dockerfile 内容字符串
    """
    cmd = "bundle exec rails server -b 0.0.0.0" if framework == "rails" else (start_cmd or "ruby app.rb")
    return f"""FROM ruby:3.2-slim
WORKDIR /app
COPY Gemfile Gemfile.lock ./
RUN {build_cmd or 'bundle install'}
COPY . .
EXPOSE {port}
CMD ["sh", "-c", "{cmd}"]
"""
