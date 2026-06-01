'''Ruby 语言检测规则'''
import os
import re
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

        gemfile_path = os.path.join(dir_path, "Gemfile")
        if not os.path.exists(gemfile_path):
            return result

        try:
            with open(gemfile_path, errors="ignore") as f:
                content = f.read()
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
        except Exception:
            pass

        # .ruby-version 文件
        ruby_version_path = os.path.join(dir_path, ".ruby-version")
        if os.path.exists(ruby_version_path):
            try:
                with open(ruby_version_path, errors="ignore") as f:
                    ver = f.read().strip().lstrip("ruby-")
                    if ver:
                        result["version"] = ver
            except Exception:
                pass

        # 入口点检测（Rails 6+ 优先 bin/rails）
        bin_rails = os.path.join(dir_path, "bin", "rails")
        if os.path.isfile(bin_rails):
            result["entry_point"] = "bin/rails"
        else:
            for entry in ["config.ru", "app.rb", "server.rb"]:
                entry_path = os.path.join(dir_path, entry)
                if os.path.isfile(entry_path):
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
