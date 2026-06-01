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

            # 通过 require 块或单行 require 检测框架（依赖指纹优先）
            # wails（优先检测，避免被 echo 等短路）
            if "wailsapp/wails" in content or os.path.exists(os.path.join(dir_path, "wails.json")):
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
                    if dep in content:
                        result["framework"] = fw
                        break
        except Exception:
            pass

        # Wails 项目需要先构建前端（registry 由部署层注入，不在规则层硬编码）
        if result["framework"] == "wails":
            result["build_command"] = "cd frontend && npm install && npm run build && cd .. && CGO_ENABLED=0 GOOS=linux go build -o main ."
            result["start_command"] = "./main"
            # 检测前端目录是否存在
            frontend_dir = os.path.join(dir_path, "frontend")
            if os.path.isdir(frontend_dir):
                pkg_json = os.path.join(frontend_dir, "package.json")
                if os.path.exists(pkg_json):
                    result["has_frontend"] = True

        # go:embed 前端资源检测（通用，非 Wails 项目也可能有）
        if result["framework"] != "wails":
            try:
                import glob as _glob
                for go_file in _glob.glob(os.path.join(dir_path, "*.go")):
                    with open(go_file, errors="ignore") as gf:
                        content_text = gf.read()
                    if "//go:embed" in content_text and "frontend" in content_text.lower():
                        result["has_frontend"] = True
                        break
            except Exception:
                pass

        # 版本检测：读取 go.mod 中的 go 版本
        try:
            with open(mod_path, errors="ignore") as f:
                for line in f:
                    if line.startswith("go "):
                        ver = line.strip()[3:].strip()
                        if ver:
                            result["version"] = ver
                        break
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
                        # 跳过注释和空行，查找 package main
                        for _ in range(20):
                            line = f.readline()
                            if not line:
                                break
                            stripped = line.strip()
                            if stripped.startswith("//") or stripped.startswith("/*") or not stripped:
                                continue
                            if stripped == "package main":
                                result["entry_point"] = candidate
                            break
                except Exception:
                    continue
            if result["entry_point"]:
                break

        # 包管理器检测：检查 go.sum
        if os.path.exists(os.path.join(dir_path, "go.sum")):
            result["package_manager"] = "go_mod"

        return result
