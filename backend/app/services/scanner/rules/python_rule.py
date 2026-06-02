"""Python 语言检测规则"""
import os
import re
from typing import Optional

from .base_rule import BaseRule
from .context import ProjectContext


class PythonRule(BaseRule):

    @classmethod
    def language_id(cls) -> str:
        return "python"

    @classmethod
    def detect_language(cls, files: list) -> float:
        indicators = ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"]
        if any(f in files for f in indicators):
            return 1.0
        if any(f.endswith(".py") for f in files):
            return 0.3
        return 0.0

    @classmethod
    def detect(cls, ctx: ProjectContext) -> Optional[dict]:
        result = {
            "language": "python",
            "framework": "",
            "entry_point": None,
            "package_manager": "pip",
            "build_command": "pip install -r requirements.txt",
            "start_command": None,
            "port": 8000,
        }
        files, _ = ctx.list_dir(".")

        # 框架检测
        if "manage.py" in files and ctx.is_file("manage.py"):
            result["framework"] = "django"
        else:
            # 检查依赖文件中的框架（含 Pipfile）
            for dep_file in ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"]:
                content = ctx.read_text(dep_file)
                if content is not None:
                    content_lower = content.lower()
                    # 依赖指纹匹配（按流行度排序）
                    py_framework_map = [
                        ("fastapi", "fastapi"),
                        ("django", "django"),
                        ("flask", "flask"),
                        ("odoo", "odoo"),
                        ("openerp", "odoo"),
                        ("frappe", "frappe"),
                        ("tornado", "tornado"),
                        ("sanic", "sanic"),
                        ("aiohttp", "aiohttp"),
                        ("bottle", "bottle"),
                        ("pyramid", "pyramid"),
                    ]
                    for dep, fw in py_framework_map:
                        if dep in content_lower:
                            result["framework"] = fw
                            break
                    break

        # 入口点检测
        for entry in ["main.py", "app.py", "manage.py", "server.py", "wsgi.py"]:
            if entry in files and ctx.is_file(entry):
                result["entry_point"] = entry
                if entry == "manage.py":
                    result["start_command"] = "python manage.py runserver 0.0.0.0:8000"
                elif entry in ("main.py", "app.py", "server.py"):
                    result["start_command"] = f"python {entry}"
                elif entry == "wsgi.py":
                    result["start_command"] = "gunicorn wsgi:app -b 0.0.0.0:8000"
                break

        # 包管理器检测（lock 文件优先，再检查 pyproject.toml build-system）
        lock_map = {"poetry.lock": "poetry", "Pipfile.lock": "pipenv", "uv.lock": "uv"}
        for lock, mgr in lock_map.items():
            if ctx.exists(lock):
                result["package_manager"] = mgr
                if mgr == "poetry":
                    result["build_command"] = "poetry install"
                elif mgr == "pipenv":
                    result["build_command"] = "pipenv install"
                elif mgr == "uv":
                    result["build_command"] = "uv sync"
                break

        # 从 pyproject.toml build-system 推断包管理器
        if result["package_manager"] == "pip":
            content = ctx.read_text("pyproject.toml")
            if content is not None:
                m = re.search(r'build-backend\s*=\s*"([^"]+)"', content)
                if m:
                    build_backend = m.group(1)
                    if "poetry" in build_backend:
                        result["package_manager"] = "poetry"
                        result["build_command"] = "poetry install"
                    elif "flit" in build_backend:
                        result["package_manager"] = "flit"
                    elif "hatchling" in build_backend:
                        result["package_manager"] = "hatch"
                        result["build_command"] = "hatch build"

        # 版本检测
        for dep_file in ["runtime.txt", "pyproject.toml", "Pipfile"]:
            content = ctx.read_text(dep_file)
            if content is not None:
                # runtime.txt: "python-3.11.x"
                m = re.search(r'python-?(\d+\.\d+)', content)
                if m:
                    result["version"] = m.group(1)
                # pyproject.toml: requires-python = ">=3.11" / "~=3.10" / ">=3.8,<4.0"
                m = re.search(r'requires-python\s*=\s*["\']([><=~!^]*\s*\d+\.\d+)', content)
                if m:
                    ver = re.search(r'(\d+\.\d+)', m.group(1))
                    if ver:
                        result["version"] = ver.group(1)
                # Pipfile: python_version = "3.11" 或 python_full_version = "3.11.0"
                m = re.search(r'python_(?:full_)?version\s*=\s*["\'](\d+\.\d+)', content)
                if m and "version" not in result:
                    result["version"] = m.group(1)
                break

        # ASGI 检测（FastAPI / Django Channels）
        has_asgi = ctx.exists("asgi.py")

        # 框架级启动命令定制
        if result["framework"] == "fastapi":
            entry = result.get("entry_point", "main.py")
            app_name = entry.replace(".py", "")
            result["start_command"] = f"uvicorn {app_name}:app --host 0.0.0.0 --port 8000"
            result["port"] = 8000
        elif result["framework"] == "django" and has_asgi:
            result["start_command"] = "daphne -b 0.0.0.0 -p 8000 config.asgi:application"
        elif result["framework"] == "odoo":
            if ctx.is_file("odoo-bin"):
                result["entry_point"] = "odoo-bin"
                result["start_command"] = "python odoo-bin -c odoo.conf"
            result["port"] = 8069
        elif result["framework"] == "frappe":
            result["port"] = 8000

        return result
