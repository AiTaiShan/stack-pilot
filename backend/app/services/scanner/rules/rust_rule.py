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
        # 提取 [dependencies] 内容（包括 [dependencies.xxx] 段）
        deps_sections = re.findall(r'\[dependencies[^\]]*\](.*?)(?:\n\[|$)', content, re.DOTALL)
        deps_content = "\n".join(deps_sections)
        framework_map = {
            "actix-web": "actix-web", "rocket": "rocket", "axum": "axum",
            "warp": "warp", "tide": "tide", "hyper": "hyper",
            "salvo": "salvo", "poem": "poem", "tauri": "tauri",
        }
        for dep, fw in framework_map.items():
            if dep in deps_content:
                result["framework"] = fw
                break

        # Workspace 项目：根 Cargo.toml 可能无框架依赖，递归扫描子 crate
        if not result["framework"] and "[workspace]" in content:
            members = re.findall(r'members\s*=\s*\[([^\]]+)\]', content)
            if members:
                member_paths = re.findall(r'"([^"]+)"', members[0])
                for member in member_paths:
                    member_cargo = os.path.join(dir_path, member, "Cargo.toml")
                    if os.path.exists(member_cargo):
                        try:
                            with open(member_cargo, errors="ignore") as f:
                                member_content = f.read()
                            member_deps = re.findall(r'\[dependencies[^\]]*\](.*?)(?:\n\[|$)', member_content, re.DOTALL)
                            member_deps_content = "\n".join(member_deps)
                            for dep, fw in framework_map.items():
                                if dep in member_deps_content:
                                    result["framework"] = fw
                                    break
                        except Exception:
                            pass
                    if result["framework"]:
                        break

        # ---------- workspace 检测 ----------
        if "[workspace]" in content:
            result["is_workspace"] = True

        # ---------- 版本检测 ----------
        edition_match = re.search(r'^edition\s*=\s*"(\d+)"', content, re.MULTILINE)
        if edition_match:
            result["version"] = edition_match.group(1)

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
