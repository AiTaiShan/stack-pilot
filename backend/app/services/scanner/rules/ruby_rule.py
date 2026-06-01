'''Ruby 语言检测规则'''
import os
from .base_rule import BaseRule


class RubyRule(BaseRule):

    @classmethod
    def language_id(cls) -> str:
        return "ruby"

    @classmethod
    def detect_language(cls, files: list) -> bool:
        indicators = ["Gemfile", "Gemfile.lock", "Rakefile"]
        return any(f in files for f in indicators)

    @classmethod
    def detect(cls, dir_path: str) -> dict:
        result = {
            "language": "ruby",
            "framework": "",
            "entry_point": None,
            "package_manager": "bundler",
            "build_command": "bundle install",
            "start_command": None,
            "port": 3000,
        }

        # 框架检测：读取 Gemfile 中的 rails / sinatra 依赖
        gemfile_path = os.path.join(dir_path, "Gemfile")
        if os.path.exists(gemfile_path):
            try:
                with open(gemfile_path, errors="ignore") as f:
                    content = f.read().lower()

                if "gem 'rails'" in content or 'gem "rails"' in content:
                    result["framework"] = "rails"
                elif "gem 'sinatra'" in content or 'gem "sinatra"' in content:
                    result["framework"] = "sinatra"
            except Exception:
                pass

        # 入口点检测
        for entry in ["config.ru", "app.rb", "server.rb"]:
            entry_path = os.path.join(dir_path, entry)
            if os.path.isfile(entry_path):
                result["entry_point"] = entry
                break

        # 包管理器检测：Gemfile.lock 存在 -> bundler
        if os.path.exists(os.path.join(dir_path, "Gemfile.lock")):
            result["package_manager"] = "bundler"

        # 启动命令
        if result["framework"] == "rails":
            result["start_command"] = "bundle exec rails server -b 0.0.0.0 -p 3000"
        elif result["entry_point"] == "config.ru":
            if result["framework"] == "rails":
                result["start_command"] = "bundle exec rails server -b 0.0.0.0 -p 3000"
            else:
                result["start_command"] = "bundle exec rackup config.ru -p 3000 -o 0.0.0.0"
        elif result["entry_point"]:
            result["start_command"] = f"ruby {result['entry_point']}"

        return result
