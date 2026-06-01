#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Java Dockerfile 模板

提供 generate() 函数，根据输入的端口、构建命令、启动命令和框架
生成标准化的 Java 多阶段构建 Dockerfile 内容。
"""


def generate(port: int, build_cmd: str, start_cmd: str, framework: str = "") -> str:
    """生成 Java Dockerfile 内容（多阶段构建）。

    Args:
        port: 应用监听端口
        build_cmd: 构建命令（如 mvn package -DskipTests）
        start_cmd: 启动命令（如 java -jar app.jar）
        framework: 框架名称（如 "spring-boot"）

    Returns:
        Dockerfile 内容字符串
    """
    return f"""FROM eclipse-temurin:17-jdk-alpine AS builder
WORKDIR /app
COPY . .
RUN {build_cmd or 'mvn package -DskipTests'}

FROM eclipse-temurin:17-jre-alpine
WORKDIR /app
COPY --from=builder /app/target/*.jar app.jar
EXPOSE {port}
CMD ["java", "-jar", "app.jar"]
"""
