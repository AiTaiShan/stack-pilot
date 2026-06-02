"""Ruby 语言检测规则"""
import os
import re
from typing import Optional

from .base_rule import BaseRule
from .context import ProjectContext


class RubyRule(BaseRule):

    @classmethod
    def language_id(cls) -> str:
        return "ruby"

    @classmethod
    def detect_language(cls, files: list) -> float:
        indicators = ["Gemfile", "Gemfile.lock", "Rakefile"]
        if any(f in files for f in indicators):
            return 1.0
        if any(f.endswith(".rb") for f in files):
            return 0.3
        return 0.0

    @classmethod
    def detect(cls, ctx: ProjectContext) -> Optional[dict]:
        result = {
            "language": "ruby",
            "framework": "",
            "entry_point": None,
            "package_manager": "bundler",
            "build_command": "bundle install",
            "start_command": None,
            "port": 3000,
        }

        content = ctx.read_text("Gemfile")
        if content is None:
            return result

        content_lower = content.lower()

        # 框架检测
        framework_map = {
            "gem 'rails'": "rails", 'gem "rails"': "rails",
            "gem 'sinatra'": "sinatra", 'gem "sinatra"': "sinatra",
            "gem 'hanami'": "hanami", 'gem "hanami"': "hanami",
            "gem 'padrino'": "padrino", 'gem "padrino"': "padrino",
            "gem 'grape'": "grape", 'gem "grape"': "grape",
            "gem 'roda'": "roda", 'gem "roda"': "roda",
        }
        for pattern, fw in framework_map.items():
            if pattern in content_lower:
                result["framework"] = fw
                break

        # 版本检测：Gemfile 中的 ruby 声明
        m = re.search(r'ruby\s+["\']([\d\.]+)["\']', content)
        if m:
            result["version"] = m.group(1)

        # .ruby-version 文件
        ver = ctx.read_text(".ruby-version")
        if ver is not None:
            ver = ver.strip().lstrip("ruby-")
            if ver:
                result["version"] = ver

        # 入口点检测（Rails 6+ 优先 bin/rails）
        if ctx.is_file("bin/rails"):
            result["entry_point"] = "bin/rails"
        else:
            for entry in ["config.ru", "app.rb", "server.rb"]:
                if ctx.is_file(entry):
                    result["entry_point"] = entry
                    break

        # 启动命令
        if result["framework"] == "rails":
            result["start_command"] = "bundle exec rails server -b 0.0.0.0 -p 3000"
        elif result["entry_point"] == "config.ru":
            result["start_command"] = "bundle exec rackup config.ru -p 3000 -o 0.0.0.0"
        elif result["entry_point"]:
            result["start_command"] = f"ruby {result['entry_point']}"

        return result
