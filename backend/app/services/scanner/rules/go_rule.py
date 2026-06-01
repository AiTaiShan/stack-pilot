"""Go 语言检测规则"""
import os
from .base_rule import BaseRule


class GoRule(BaseRule):

    @classmethod
    def language_id(cls) -> str:
        return "go"

    @classmethod
    def detect_language(cls, files: list) -> bool:
        return "go.mod" in files

    @classmethod
    def detect(cls, dir_path: str) -> dict:
        result = {
            "language": "go",
            "framework": "",
            "entry_point": None,
            "package_manager": "go_mod",
            "build_command": "go build -o main .",
            "start_command": "./main",
            "port": 8080,
        }

        mod_path = os.path.join(dir_path, "go.mod")
        if not os.path.exists(mod_path):
            return result

        # 框架检测：读取 go.mod 中的依赖
        try:
            with open(mod_path, errors="ignore") as f:
                content = f.read().lower()

            # 通过 require 块或单行 require 检测框架
            # gin
            if "gin-gonic/gin" in content:
                result["framework"] = "gin"
            # echo
            elif "labstack/echo" in content:
                result["framework"] = "echo"
            # fiber
            elif "gofiber/fiber" in content:
                result["framework"] = "fiber"
        except Exception:
            pass

        # 入口点检测：查找 main.go（或 cmd/ 子目录中的 main.go）并检查 package main
        # 首先检查根目录下的 main.go
        main_candidates = ["main.go"]

        # 检查 cmd/ 目录
        cmd_dir = os.path.join(dir_path, "cmd")
        if os.path.isdir(cmd_dir):
            for root, dirs, files in os.walk(cmd_dir):
                for f in files:
                    if f == "main.go":
                        rel = os.path.relpath(os.path.join(root, f), dir_path)
                        main_candidates.append(rel)

        for candidate in main_candidates:
            candidate_path = os.path.join(dir_path, candidate)
            if os.path.isfile(candidate_path):
                try:
                    with open(candidate_path, errors="ignore") as f:
                        first_line = f.readline().strip()
                    if first_line == "package main":
                        result["entry_point"] = candidate
                        break
                except Exception:
                    continue

        # 包管理器检测：检查 go.sum
        if os.path.exists(os.path.join(dir_path, "go.sum")):
            result["package_manager"] = "go_mod"

        return result
