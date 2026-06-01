#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Node.js Dockerfile 模板

提供 generate() 函数，根据输入的端口、构建命令、启动命令和框架
生成标准化的 Node.js Dockerfile 内容。
"""


def generate(port: int, build_cmd: str, start_cmd: str, framework: str = "", version: str = "18") -> str:
    """生成 Node.js Dockerfile 内容。

    Args:
        port: 应用监听端口
        build_cmd: 构建命令（如 npm run build、pnpm run build、yarn build）
        start_cmd: 启动命令（如 npm start、pnpm start、yarn start）
        framework: 框架名称（如 "next"、"nextjs"）

    Returns:
        Dockerfile 内容字符串
    """
    # 从命令中检测包管理器
    pkg_manager = _detect_package_manager(build_cmd, start_cmd)

    # 生成安装命令
    install_cmd = _get_install_command(pkg_manager)

    if framework.lower() in ("next", "nextjs"):
        return _nextjs_template(port, install_cmd, build_cmd, start_cmd)

    return _node_template(port, install_cmd, build_cmd, start_cmd)


def _detect_package_manager(build_cmd: str, start_cmd: str) -> str:
    """从构建命令和启动命令中检测包管理器。"""
    if "pnpm" in build_cmd or "pnpm" in start_cmd:
        return "pnpm"
    if "yarn" in build_cmd or "yarn" in start_cmd:
        return "yarn"
    return "npm"


def _get_install_command(pkg_manager: str) -> str:
    """根据包管理器生成安装依赖的命令。"""
    commands = {
        "pnpm": "RUN npm install -g pnpm && pnpm install --registry=https://registry.npmmirror.com",
        "yarn": "RUN yarn install --registry=https://registry.npmmirror.com",
        "npm": "RUN npm install --registry=https://registry.npmmirror.com",
    }
    return commands.get(pkg_manager, commands["npm"])


def _nextjs_template(port: int, install_cmd: str, build_cmd: str, start_cmd: str, version: str = "18") -> str:
    """Next.js 应用的多阶段构建 Dockerfile。"""
    node_image = f"node:{version}-alpine"
    return f"""FROM {node_image} AS builder
WORKDIR /app
COPY package*.json ./
{install_cmd}
COPY . .
RUN {build_cmd}

FROM {node_image} AS runner
WORKDIR /app
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./
COPY --from=builder /app/public ./public
ENV NODE_ENV=production
EXPOSE {port}
CMD ["sh", "-c", "{start_cmd}"]
"""


def _node_template(port: int, install_cmd: str, build_cmd: str, start_cmd: str, version: str = "18") -> str:
    """标准 Node.js 单阶段构建 Dockerfile。"""
    node_image = f"node:{version}-alpine"
    return f"""FROM {node_image}
WORKDIR /app
COPY package*.json ./
{install_cmd}
COPY . .
RUN {build_cmd}
EXPOSE {port}
CMD ["sh", "-c", "{start_cmd}"]
"""
