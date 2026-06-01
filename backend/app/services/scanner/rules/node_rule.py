"""Node.js / TypeScript 语言检测规则"""
import json
import os
import re
from .base_rule import BaseRule


class NodeRule(BaseRule):

    @classmethod
    def language_id(cls) -> str:
        return "node"

    @classmethod
    def detect_language(cls, files: list) -> bool:
        return "package.json" in files

    @classmethod
    def detect(cls, dir_path: str) -> dict:
        result = {
            "language": "node",
            "framework": "",
            "entry_point": None,
            "package_manager": "npm",
            "build_command": "npm run build",
            "start_command": "npm start",
            "port": 3000,
        }
        pkg_path = os.path.join(dir_path, "package.json")
        if not os.path.exists(pkg_path):
            return result

        with open(pkg_path) as f:
            pkg = json.load(f)

        # 框架检测（根目录 package.json）
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        frontend_only_frameworks = {"react", "vue", "svelte", "solidjs", "preact"}

        result["framework"] = cls._detect_framework_from_deps(deps, dir_path)

        # 如果根目录是纯前端框架，扫描子目录的 package.json 查找后端框架
        if result["framework"] in frontend_only_frameworks:
            for sub in ["backend", "server", "api", "packages/api", "packages/server"]:
                sub_pkg = os.path.join(dir_path, sub, "package.json")
                if os.path.exists(sub_pkg):
                    try:
                        with open(sub_pkg) as f:
                            sub_pkg_data = json.load(f)
                        sub_deps = {**sub_pkg_data.get("dependencies", {}),
                                    **sub_pkg_data.get("devDependencies", {})}
                        sub_fw = cls._detect_framework_from_deps(sub_deps, os.path.join(dir_path, sub))
                        if sub_fw and sub_fw not in frontend_only_frameworks:
                            result["framework"] = sub_fw
                            # 入口点也指向子目录
                            for entry in ["server.js", "index.js", "app.js", "src/main.ts", "src/main.js"]:
                                if os.path.exists(os.path.join(dir_path, sub, entry)):
                                    result["entry_point"] = f"{sub}/{entry}"
                                    break
                            break
                    except Exception:
                        pass

        # 入口点检测（NestJS 标准入口 src/main.ts 优先）
        for entry in ["src/main.ts", "src/main.js", "app.js", "index.js", "server.js",
                       "app.ts", "index.ts", "server.ts"]:
            if os.path.exists(os.path.join(dir_path, entry)):
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
            if os.path.exists(os.path.join(dir_path, lock)):
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
                ver_path = os.path.join(dir_path, ver_file)
                if os.path.exists(ver_path):
                    try:
                        with open(ver_path, errors="ignore") as f:
                            ver = f.read().strip().lstrip("v")
                            if ver:
                                result["version"] = ver
                    except Exception:
                        pass
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
    def _detect_framework_from_deps(cls, deps: dict, dir_path: str = "") -> str:
        """从 dependencies 检测框架"""
        if "next" in deps or (dir_path and any(os.path.exists(os.path.join(dir_path, f)) for f in
                                  ["next.config.js", "next.config.ts", "next.config.mjs"])):
            return "next"
        if "nuxt" in deps or (dir_path and any(os.path.exists(os.path.join(dir_path, f)) for f in
                                    ["nuxt.config.ts", "nuxt.config.js"])):
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
