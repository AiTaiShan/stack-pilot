import os
import json
import tempfile
import subprocess
from typing import Dict, List, Any
from pathlib import Path


class ScannerService:
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()

    def clone_repository(self, git_url: str) -> str:
        """克隆Git仓库"""
        repo_dir = os.path.join(self.temp_dir, "repo")
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", git_url, repo_dir],
                check=True, capture_output=True, text=True
            )
            return repo_dir
        except subprocess.CalledProcessError as e:
            raise Exception(f"代码克隆失败: {e.stderr}")

    def scan_tech_stack(self, repo_dir: str) -> Dict[str, Any]:
        """扫描技术栈"""
        tech_stack = {
            "language": None, "framework": None, "build_tool": None,
            "package_manager": None, "dependencies": []
        }

        # 检测Node.js项目
        if os.path.exists(os.path.join(repo_dir, "package.json")):
            tech_stack["language"] = "javascript"
            tech_stack["package_manager"] = "npm"
            tech_stack["build_tool"] = "npm"
            with open(os.path.join(repo_dir, "package.json"), "r") as f:
                package_json = json.load(f)
            dependencies = package_json.get("dependencies", {})
            dev_dependencies = package_json.get("devDependencies", {})
            if "react" in dependencies:
                tech_stack["framework"] = "react"
            elif "vue" in dependencies:
                tech_stack["framework"] = "vue"
            elif "next" in dependencies:
                tech_stack["framework"] = "nextjs"
            elif "nuxt" in dependencies:
                tech_stack["framework"] = "nuxtjs"
            tech_stack["dependencies"] = list(dependencies.keys())

        # 检测Python项目
        elif os.path.exists(os.path.join(repo_dir, "requirements.txt")):
            tech_stack["language"] = "python"
            tech_stack["package_manager"] = "pip"
            with open(os.path.join(repo_dir, "requirements.txt"), "r") as f:
                requirements = f.read().splitlines()
            tech_stack["dependencies"] = [
                req.split("==")[0].split(">=")[0].split("<=")[0].strip()
                for req in requirements
                if req.strip() and not req.startswith("#")
            ]
            if "django" in tech_stack["dependencies"]:
                tech_stack["framework"] = "django"
            elif "flask" in tech_stack["dependencies"]:
                tech_stack["framework"] = "flask"
            elif "fastapi" in tech_stack["dependencies"]:
                tech_stack["framework"] = "fastapi"

        # 检测Java项目
        elif os.path.exists(os.path.join(repo_dir, "pom.xml")):
            tech_stack["language"] = "java"
            tech_stack["build_tool"] = "maven"
            tech_stack["package_manager"] = "maven"

        # 检测Go项目
        elif os.path.exists(os.path.join(repo_dir, "go.mod")):
            tech_stack["language"] = "go"
            tech_stack["build_tool"] = "go"
            tech_stack["package_manager"] = "go"

        return tech_stack

    def scan_config_files(self, repo_dir: str) -> Dict[str, Any]:
        """扫描配置文件"""
        config_files = {}
        config_patterns = [
            ".env", ".env.example", "docker-compose.yml", "Dockerfile",
            "nginx.conf", "config.json", "config.yaml", "config.yml"
        ]
        for pattern in config_patterns:
            config_path = os.path.join(repo_dir, pattern)
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    config_files[pattern] = f.read()
        return config_files

    def analyze_project(self, git_url: str) -> Dict[str, Any]:
        """分析项目"""
        try:
            repo_dir = self.clone_repository(git_url)
            tech_stack = self.scan_tech_stack(repo_dir)
            config_files = self.scan_config_files(repo_dir)
            return {
                "tech_stack": tech_stack,
                "config_files": config_files,
                "repo_dir": repo_dir
            }
        except Exception as e:
            raise Exception(f"项目分析失败: {str(e)}")
        finally:
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)
