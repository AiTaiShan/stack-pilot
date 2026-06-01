#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Java Dockerfile 模板

提供 generate() 函数，根据输入的端口、构建命令、启动命令和框架
生成标准化的 Java 多阶段构建 Dockerfile 内容。
"""


def generate(port: int, build_cmd: str, start_cmd: str, framework: str = "", version: str = "17") -> str:
    """生成 Java Dockerfile 内容（多阶段构建）。

    Args:
        port: 应用监听端口
        build_cmd: 构建命令（如 mvn package -DskipTests）
        start_cmd: 启动命令（如 java -jar app.jar）
        framework: 框架名称（如 "spring-boot"）
        version: Java 版本号（如 "17", "21"），从 pom.xml 读取

    Returns:
        Dockerfile 内容字符串
    """
    jdk_image = f"eclipse-temurin:{version}-jdk-alpine"
    jre_image = f"eclipse-temurin:{version}-jre-alpine"
    return f"""FROM {jdk_image} AS builder
WORKDIR /app
COPY . .
RUN {build_cmd or 'mvn package -DskipTests'}

FROM {jre_image}
WORKDIR /app
COPY --from=builder /app/target/*.jar app.jar
EXPOSE {port}
CMD ["java", "-jar", "app.jar"]
"""
