"""Node.js / TypeScript 语言检测规则"""
import json
import os
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

        # 框架检测
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        if "next" in deps or os.path.exists(os.path.join(dir_path, "next.config.js")):
            result["framework"] = "next"
        elif "nuxt" in deps:
            result["framework"] = "nuxt"
        elif "@nestjs/core" in deps:
            result["framework"] = "nest"
        elif "express" in deps:
            result["framework"] = "express"
        elif "vue" in deps:
            result["framework"] = "vue"
        elif "react" in deps:
            result["framework"] = "react"

        # 入口点检测
        for entry in ["app.js", "index.js", "server.js", "app.ts", "index.ts", "server.ts"]:
            if os.path.exists(os.path.join(dir_path, entry)):
                result["entry_point"] = entry
                break

        # 包管理器检测
        lock_map = {"pnpm-lock.yaml": "pnpm", "yarn.lock": "yarn", "package-lock.json": "npm"}
        for lock, mgr in lock_map.items():
            if os.path.exists(os.path.join(dir_path, lock)):
                result["package_manager"] = mgr
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
