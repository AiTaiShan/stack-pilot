"""Python 语言检测规则"""
import os
from .base_rule import BaseRule


class PythonRule(BaseRule):

    @classmethod
    def language_id(cls) -> str:
        return "python"

    @classmethod
    def detect_language(cls, files: list) -> bool:
        indicators = ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"]
        return any(f in files for f in indicators)

    @classmethod
    def detect(cls, dir_path: str) -> dict:
        result = {
            "language": "python",
            "framework": "",
            "entry_point": None,
            "package_manager": "pip",
            "build_command": "pip install -r requirements.txt",
            "start_command": None,
            "port": 8000,
        }
        files = os.listdir(dir_path)

        # 框架检测
        if "manage.py" in files and os.path.isfile(os.path.join(dir_path, "manage.py")):
            result["framework"] = "django"
        else:
            # 检查依赖文件中的框架
            for dep_file in ["requirements.txt", "pyproject.toml", "setup.py"]:
                dep_path = os.path.join(dir_path, dep_file)
                if os.path.exists(dep_path):
                    try:
                        content = open(dep_path, errors="ignore").read().lower()
                        if "fastapi" in content:
                            result["framework"] = "fastapi"
                        elif "flask" in content:
                            result["framework"] = "flask"
                    except Exception:
                        pass
                    break

        # 入口点检测
        for entry in ["main.py", "app.py", "manage.py", "server.py", "wsgi.py"]:
            if entry in files and os.path.isfile(os.path.join(dir_path, entry)):
                result["entry_point"] = entry
                if entry == "manage.py":
                    result["start_command"] = "python manage.py runserver 0.0.0.0:8000"
                elif entry in ("main.py", "app.py", "server.py"):
                    result["start_command"] = f"python {entry}"
                elif entry == "wsgi.py":
                    result["start_command"] = "gunicorn wsgi:app -b 0.0.0.0:8000"
                break

        # 包管理器检测
        lock_map = {"poetry.lock": "poetry", "Pipfile.lock": "pipenv"}
        for lock, mgr in lock_map.items():
            if os.path.exists(os.path.join(dir_path, lock)):
                result["package_manager"] = mgr
                if mgr == "poetry":
                    result["build_command"] = "poetry install"
                elif mgr == "pipenv":
                    result["build_command"] = "pipenv install"
                break

        # FastAPI 启动命令特殊处理
        if result["framework"] == "fastapi":
            entry = result.get("entry_point", "main.py")
            app_name = entry.replace(".py", "")
            result["start_command"] = f"uvicorn {app_name}:app --host 0.0.0.0 --port 8000"
            result["port"] = 8000

        return result
