"""Node.js / TypeScript 语言检测规则"""
import os
import re
from typing import Optional

from .base_rule import BaseRule
from .context import ProjectContext


class NodeRule(BaseRule):

    @classmethod
    def language_id(cls) -> str:
        return "node"

    @classmethod
    def detect_language(cls, files: list) -> float:
        if "package.json" in files:
            return 1.0
        if any(f.endswith((".js", ".ts", ".mjs", ".cjs")) for f in files):
            return 0.3
        return 0.0

    @classmethod
    def detect(cls, ctx: ProjectContext) -> Optional[dict]:
        result = {
            "language": "node",
            "framework": "",
            "entry_point": None,
            "package_manager": "npm",
            "build_command": "npm run build",
            "start_command": "npm start",
            "port": 3000,
        }
        pkg = ctx.read_json("package.json")
        if pkg is None:
            return result

        # 框架检测（根目录 package.json）
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        frontend_only_frameworks = {"react", "vue", "svelte", "solidjs", "preact"}

        result["framework"] = cls._detect_framework_from_deps(deps, ctx)

        # 如果根目录是纯前端框架，扫描子目录的 package.json 查找后端框架
        if result["framework"] in frontend_only_frameworks:
            for sub in ["backend", "server", "api", "packages/api", "packages/server"]:
                sub_pkg = ctx.read_json(os.path.join(sub, "package.json"))
                if sub_pkg is not None:
                    sub_deps = {**sub_pkg.get("dependencies", {}),
                                **sub_pkg.get("devDependencies", {})}
                    sub_fw = cls._detect_framework_from_deps(sub_deps, ctx, sub)
                    if sub_fw and sub_fw not in frontend_only_frameworks:
                        result["framework"] = sub_fw
                        # 入口点也指向子目录
                        for entry in ["server.js", "index.js", "app.js", "src/main.ts", "src/main.js"]:
                            if ctx.exists(os.path.join(sub, entry)):
                                result["entry_point"] = f"{sub}/{entry}"
                                break
                        break

        # 入口点检测（NestJS 标准入口 src/main.ts 优先）
        for entry in ["src/main.ts", "src/main.js", "app.js", "index.js", "server.js",
                       "app.ts", "index.ts", "server.ts"]:
            if ctx.exists(entry):
                result["entry_point"] = entry
                break

        # 版本检测：从 package.json 的 engines.node 或直接读取
        engines = pkg.get("engines", {})
        if engines and engines.get("node"):
            m = re.search(r'(\d+)', str(engines["node"]))
            if m:
                result["version"] = m.group(1)

        # 包管理器检测（优先级：lock 文件 > packageManager 字段）
        lock_map = {"pnpm-lock.yaml": "pnpm", "yarn.lock": "yarn",
                    "package-lock.json": "npm", "bun.lockb": "bun"}
        for lock, mgr in lock_map.items():
            if ctx.exists(lock):
                result["package_manager"] = mgr
                break

        # packageManager 字段（corepack）
        pkg_manager_field = pkg.get("packageManager", "")
        if pkg_manager_field:
            for mgr_name in ["pnpm", "yarn", "npm", "bun"]:
                if pkg_manager_field.startswith(mgr_name):
                    result["package_manager"] = mgr_name
                    break

        # 版本检测：.nvmrc / .node-version
        if "version" not in result:
            for ver_file in [".nvmrc", ".node-version"]:
                ver = ctx.read_text(ver_file)
                if ver is not None:
                    ver = ver.strip().lstrip("v")
                    if ver:
                        result["version"] = ver
                    break

        # 构建/启动命令
        scripts = pkg.get("scripts", {})
        pm = result["package_manager"]
        pm_cmd = {"pnpm": "pnpm", "yarn": "yarn", "npm": "npm"}
        cmd_prefix = pm_cmd.get(pm, "npm")
        if scripts.get("build"):
            result["build_command"] = f"{cmd_prefix} run build"
        if scripts.get("start"):
            result["start_command"] = f"{cmd_prefix} start"
        elif scripts.get("dev"):
            result["start_command"] = f"{cmd_prefix} run dev"

        return result

    @classmethod
    def _detect_framework_from_deps(cls, deps: dict, ctx: ProjectContext,
                                     sub_dir: str = "") -> str:
        """从 dependencies 检测框架"""
        prefix = sub_dir + "/" if sub_dir else ""
        if "next" in deps or any(ctx.exists(prefix + f) for f in
                                  ["next.config.js", "next.config.ts", "next.config.mjs"]):
            return "next"
        if "nuxt" in deps or any(ctx.exists(prefix + f) for f in
                                    ["nuxt.config.ts", "nuxt.config.js"]):
            return "nuxt"
        if "@nestjs/core" in deps:
            return "nest"
        if "express" in deps:
            return "express"
        if "fastify" in deps:
            return "fastify"
        if "koa" in deps:
            return "koa"
        if "@hapi/hapi" in deps:
            return "hapi"
        if "svelte" in deps or "@sveltejs/kit" in deps:
            return "svelte"
        if "@remix-run/react" in deps:
            return "remix"
        if "astro" in deps:
            return "astro"
        if "solid-js" in deps:
            return "solidjs"
        if "@redwoodjs/core" in deps:
            return "redwoodjs"
        if "vue" in deps:
            return "vue"
        if "react" in deps:
            return "react"
        return ""
