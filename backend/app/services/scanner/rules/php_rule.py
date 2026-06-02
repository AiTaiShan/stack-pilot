"""PHP 语言检测规则"""
import os
import re
from typing import Optional

from .base_rule import BaseRule
from .context import ProjectContext


class PhpRule(BaseRule):

    @classmethod
    def language_id(cls) -> str:
        return "php"

    @classmethod
    def detect_language(cls, files: list) -> float:
        if "composer.json" in files:
            return 1.0
        if any(f.endswith(".php") for f in files):
            return 0.3
        return 0.0

    @classmethod
    def detect(cls, ctx: ProjectContext) -> Optional[dict]:
        result = {
            "language": "php",
            "framework": "",
            "entry_point": None,
            "package_manager": "composer",
            "build_command": "composer install --no-dev",
            "start_command": None,
            "port": 80,
        }

        composer = ctx.read_json("composer.json")
        if composer is None:
            return result

        # 包管理器检测
        if ctx.exists("composer.lock"):
            result["package_manager"] = "composer"

        # 框架检测：读取 require 中的框架依赖
        requires = composer.get("require", {})
        if requires:
            php_framework_map = [
                ("laravel/framework", "laravel"),
                ("symfony/framework-bundle", "symfony"),
                ("symfony/symfony", "symfony"),
                ("topthink/framework", "thinkphp"),
                ("laminas/laminas-mvc", "laminas"),
                ("laminas/laminas-api-tools", "laminas"),
                ("cakephp/cakephp", "cakephp"),
                ("codeigniter/framework", "codeigniter"),
                ("codeigniter4/framework", "codeigniter"),
                ("yiisoft/yii2", "yii"),
                ("yiisoft/yii", "yii"),
                ("slim/slim", "slim"),
            ]
            for dep, fw in php_framework_map:
                if dep in requires:
                    result["framework"] = fw
                    break

        # 版本检测：从 require 中读取 php 版本
        if "php" in requires:
            php_ver = requires["php"]
            m = re.search(r'(\d+\.\d+)', php_ver)
            if m:
                result["version"] = m.group(1)

        # 入口点检测
        if result["framework"] == "laravel" and ctx.is_file("artisan"):
            result["entry_point"] = "artisan"
            result["start_command"] = "php artisan serve"
        else:
            for entry in ["index.php", "public/index.php", "server.php"]:
                if ctx.is_file(entry):
                    result["entry_point"] = entry
                    result["start_command"] = "php -S 0.0.0.0:80"
                    break

        return result
