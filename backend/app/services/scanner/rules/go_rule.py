"""Go 语言检测规则"""
import os
from typing import Optional

from .base_rule import BaseRule
from .context import ProjectContext


class GoRule(BaseRule):

    @classmethod
    def language_id(cls) -> str:
        return "go"

    @classmethod
    def detect_language(cls, files: list) -> float:
        if "go.mod" in files:
            return 1.0
        if any(f.endswith(".go") for f in files):
            return 0.4
        return 0.0

    @classmethod
    def detect(cls, ctx: ProjectContext) -> Optional[dict]:
        result = {
            "language": "go",
            "framework": "",
            "entry_point": None,
            "package_manager": "go_mod",
            "build_command": "go build -o main .",
            "start_command": "./main",
            "port": 8080,
        }

        content = ctx.read_text("go.mod")
        if content is None:
            return result

        content_lower = content.lower()

        # 框架检测：通过 require 块或单行 require 检测框架（依赖指纹优先）
        if "wailsapp/wails" in content_lower or ctx.exists("wails.json"):
            result["framework"] = "wails"
        else:
            go_framework_map = [
                ("zeromicro/go-zero", "go-zero"),
                ("beego/beego", "beego"),
                ("astaxie/beego", "beego"),
                ("gogf/gf", "goframe"),
                ("gin-gonic/gin", "gin"),
                ("labstack/echo", "echo"),
                ("gofiber/fiber", "fiber"),
                ("go-chi/chi", "chi"),
                ("gorilla/mux", "gorilla"),
            ]
            for dep, fw in go_framework_map:
                if dep in content_lower:
                    result["framework"] = fw
                    break

        # Wails 项目需要先构建前端
        if result["framework"] == "wails":
            result["build_command"] = "cd frontend && npm install && npm run build && cd .. && CGO_ENABLED=0 GOOS=linux go build -o main ."
            result["start_command"] = "./main"
            if ctx.exists("frontend/package.json"):
                result["has_frontend"] = True

        # go:embed 前端资源检测
        if result["framework"] != "wails":
            go_files = ctx.glob("*.go")
            for go_file in go_files:
                file_content = ctx.read_text(go_file)
                if file_content and "//go:embed" in file_content and "frontend" in file_content.lower():
                    result["has_frontend"] = True
                    break

        # 版本检测：读取 go.mod 中的 go 版本
        for line in content.splitlines():
            if line.startswith("go "):
                ver = line.strip()[3:].strip()
                if ver:
                    result["version"] = ver
                break

        # 入口点检测：查找 main.go（或 cmd/ 子目录中的 main.go）并检查 package main
        main_candidates = ["main.go"]

        # 检查 cmd/ 目录
        if ctx.is_dir("cmd"):
            cmd_files = ctx.glob("cmd/**/main.go")
            main_candidates.extend(cmd_files)

        for candidate in main_candidates:
            if ctx.is_file(candidate):
                file_content = ctx.read_text(candidate)
                if file_content:
                    # 跳过注释和空行，查找 package main
                    for line in file_content.splitlines()[:20]:
                        stripped = line.strip()
                        if stripped.startswith("//") or stripped.startswith("/*") or not stripped:
                            continue
                        if stripped == "package main":
                            result["entry_point"] = candidate
                        break
            if result["entry_point"]:
                break

        # 包管理器检测：检查 go.sum
        if ctx.exists("go.sum"):
            result["package_manager"] = "go_mod"

        return result
