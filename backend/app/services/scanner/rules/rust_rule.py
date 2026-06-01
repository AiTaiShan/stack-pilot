'''Rust 语言检测规则'''
import os
import re
from .base_rule import BaseRule


class RustRule(BaseRule):

    @classmethod
    def language_id(cls) -> str:
        return "rust"

    @classmethod
    def detect_language(cls, files: list) -> bool:
        return "Cargo.toml" in files

    @classmethod
    def detect(cls, dir_path: str) -> dict:
        result = {
            "language": "rust",
            "framework": "",
            "entry_point": None,
            "package_manager": "cargo",
            "build_command": "cargo build --release",
            "start_command": None,
            "port": 8080,
        }

        cargo_path = os.path.join(dir_path, "Cargo.toml")
        if not os.path.exists(cargo_path):
            return result

        try:
            with open(cargo_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            return result

        # ---------- 读取包名 ----------
        package_name = None
        pkg_match = re.search(r'^\[package\]\s*\n(?:^[^\[].*\n)*', content, re.MULTILINE)
        if pkg_match:
            pkg_section = pkg_match.group(0)
            name_match = re.search(r'^name\s*=\s*"([^"]+)"', pkg_section, re.MULTILINE)
            if name_match:
                package_name = name_match.group(1)

        # ---------- 框架检测 ----------
        # 提取 [dependencies] 内容
        deps_match = re.search(r'\[dependencies\](.*?)(?:\[|$)', content, re.DOTALL)
        if deps_match:
            deps_content = deps_match.group(1)
            if "actix-web" in deps_content:
                result["framework"] = "actix-web"
            elif "rocket" in deps_content:
                result["framework"] = "rocket"
            elif "axum" in deps_content:
                result["framework"] = "axum"

        # ---------- 入口点检测 ----------
        main_rs = os.path.join(dir_path, "src", "main.rs")
        if os.path.isfile(main_rs):
            result["entry_point"] = "src/main.rs"

        # ---------- 包管理器确认 ----------
        if os.path.exists(os.path.join(dir_path, "Cargo.lock")):
            result["package_manager"] = "cargo"

        # ---------- 启动命令 ----------
        if package_name and result["entry_point"]:
            result["start_command"] = f"./target/release/{package_name}"

        return result
