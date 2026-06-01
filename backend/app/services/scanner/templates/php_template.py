#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PHP Dockerfile 模板

提供 generate() 函数，根据输入的端口、构建命令、启动命令和框架
生成标准化的 PHP Dockerfile 内容。
"""


def generate(port: int, build_cmd: str, start_cmd: str, framework: str = "", version: str = "8.2") -> str:
    """生成 PHP Dockerfile 内容。

    Args:
        port: 应用监听端口
        build_cmd: 构建/安装依赖命令（如 composer install --no-dev）
        start_cmd: 启动命令（如 php artisan serve，当前暂未使用）
        framework: 框架名称（如 "laravel"，当前暂未使用）

    Returns:
        Dockerfile 内容字符串
    """
    php_image = f"php:{version}-apache"
    return f"""FROM {php_image}
WORKDIR /var/www/html
COPY . .
RUN {build_cmd or 'composer install --no-dev'}
EXPOSE {port}
CMD ["apache2-foreground"]
"""
