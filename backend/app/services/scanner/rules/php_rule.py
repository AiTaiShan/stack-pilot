import json
import os
import re
from .base_rule import BaseRule


class PhpRule(BaseRule):

    @classmethod
    def language_id(cls) -> str:
        return "php"

    @classmethod
    def detect_language(cls, files: list) -> bool:
        return "composer.json" in files

    @classmethod
    def detect(cls, dir_path: str) -> dict:
        result = {
            "language": "php",
            "framework": "",
            "entry_point": None,
            "package_manager": "composer",
            "build_command": "composer install --no-dev",
            "start_command": None,
            "port": 80,
        }

        composer_path = os.path.join(dir_path, "composer.json")
        if not os.path.exists(composer_path):
            return result

        # 读取 composer.json
        try:
            with open(composer_path, "r", encoding="utf-8", errors="ignore") as f:
                composer = json.load(f)
        except Exception:
            return result

        # 包管理器检测
        if os.path.exists(os.path.join(dir_path, "composer.lock")):
            result["package_manager"] = "composer"

        # 框架检测：读取 require 中的框架依赖
        requires = composer.get("require", {})
        if requires:
            # 依赖指纹匹配（按流行度排序）
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
        # Laravel 项目优先使用 artisan（开发），生产用 php-fpm + public/index.php
        if result["framework"] == "laravel" and os.path.isfile(os.path.join(dir_path, "artisan")):
            result["entry_point"] = "artisan"
            result["start_command"] = "php artisan serve"
        else:
            # 通用 PHP 入口点
            for entry in ["index.php", "public/index.php", "server.php"]:
                if os.path.isfile(os.path.join(dir_path, entry)):
                    result["entry_point"] = entry
                    result["start_command"] = "php -S 0.0.0.0:80"
                    break

        return result
