"""ProjectContext — 项目扫描的统一 IO 缓存层

所有规则通过 ProjectContext 读取文件，避免重复 IO。
提供文本、JSON、TOML、XML 的缓存读取，以及 glob/目录列表缓存。
"""
import json
import os
import xml.etree.ElementTree as ET
from fnmatch import fnmatch
from typing import Optional

import tomli


def _safe_read(path: str) -> Optional[str]:
    """安全读取文本文件，失败返回 None"""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except (FileNotFoundError, PermissionError, OSError):
        return None


class ProjectContext:
    """项目扫描的统一 IO 缓存层

    每个 ProjectContext 实例绑定一个目录，对该目录下的所有文件读取
    进行缓存，避免多个规则重复读取同一文件。

    用法：
        ctx = ProjectContext("/path/to/repo")
        content = ctx.read_text("package.json")
        data = ctx.read_json("package.json")
        pom = ctx.read_xml("pom.xml")
        files, dirs = ctx.list_dir(".")
    """

    def __init__(self, dir_path: str):
        self.dir_path: str = dir_path
        self.warnings: list[str] = []

        # 缓存
        self._text_cache: dict[str, Optional[str]] = {}
        self._json_cache: dict[str, Optional[dict]] = {}
        self._toml_cache: dict[str, Optional[dict]] = {}
        self._xml_cache: dict[str, Optional[ET.Element]] = {}
        self._glob_cache: dict[str, list[str]] = {}
        self._listdir_cache: dict[str, tuple[list[str], list[str]]] = {}
        self._exists_cache: dict[str, bool] = {}
        self._walk_cache: Optional[tuple[list[str], list[str]]] = None

    # ── 基础文件操作 ──────────────────────────────────────────────

    def read_text(self, rel_path: str) -> Optional[str]:
        """读取文本文件（缓存），失败返回 None"""
        if rel_path not in self._text_cache:
            full = os.path.join(self.dir_path, rel_path)
            self._text_cache[rel_path] = _safe_read(full)
        return self._text_cache[rel_path]

    def read_json(self, rel_path: str) -> Optional[dict]:
        """读取并解析 JSON 文件（缓存），失败返回 None"""
        if rel_path not in self._json_cache:
            content = self.read_text(rel_path)
            if content is None:
                self._json_cache[rel_path] = None
            else:
                try:
                    self._json_cache[rel_path] = json.loads(content)
                except json.JSONDecodeError as e:
                    self.warnings.append(f"JSON 解析失败 {rel_path}: {e}")
                    self._json_cache[rel_path] = None
        return self._json_cache[rel_path]

    def read_toml(self, rel_path: str) -> Optional[dict]:
        """读取并解析 TOML 文件（缓存），失败返回 None"""
        if rel_path not in self._toml_cache:
            full = os.path.join(self.dir_path, rel_path)
            try:
                with open(full, "rb") as f:
                    self._toml_cache[rel_path] = tomli.load(f)
            except FileNotFoundError:
                self._toml_cache[rel_path] = None
            except Exception as e:
                self.warnings.append(f"TOML 解析失败 {rel_path}: {e}")
                self._toml_cache[rel_path] = None
        return self._toml_cache[rel_path]

    def read_xml(self, rel_path: str) -> Optional[ET.Element]:
        """读取并解析 XML 文件（缓存），返回根元素，失败返回 None"""
        if rel_path not in self._xml_cache:
            full = os.path.join(self.dir_path, rel_path)
            try:
                tree = ET.parse(full)
                self._xml_cache[rel_path] = tree.getroot()
            except FileNotFoundError:
                self._xml_cache[rel_path] = None
            except ET.ParseError as e:
                self.warnings.append(f"XML 解析失败 {rel_path}: {e}")
                self._xml_cache[rel_path] = None
            except Exception as e:
                self.warnings.append(f"读取 XML 失败 {rel_path}: {e}")
                self._xml_cache[rel_path] = None
        return self._xml_cache[rel_path]

    # ── 文件系统查询 ─────────────────────────────────────────────

    def exists(self, rel_path: str) -> bool:
        """检查文件/目录是否存在（缓存）"""
        if rel_path not in self._exists_cache:
            self._exists_cache[rel_path] = os.path.exists(
                os.path.join(self.dir_path, rel_path)
            )
        return self._exists_cache[rel_path]

    def is_file(self, rel_path: str) -> bool:
        """检查是否为文件"""
        full = os.path.join(self.dir_path, rel_path)
        return os.path.isfile(full)

    def is_dir(self, rel_path: str) -> bool:
        """检查是否为目录"""
        full = os.path.join(self.dir_path, rel_path)
        return os.path.isdir(full)

    def list_dir(self, rel_path: str = ".") -> tuple[list[str], list[str]]:
        """列出目录内容（缓存），返回 (files, dirs)

        files 和 dirs 都是相对路径的列表。
        """
        if rel_path not in self._listdir_cache:
            full = os.path.join(self.dir_path, rel_path)
            try:
                entries = os.listdir(full)
                files = sorted([
                    e for e in entries
                    if os.path.isfile(os.path.join(full, e))
                ])
                dirs = sorted([
                    e for e in entries
                    if os.path.isdir(os.path.join(full, e))
                ])
                self._listdir_cache[rel_path] = (files, dirs)
            except (PermissionError, OSError):
                self._listdir_cache[rel_path] = ([], [])
        return self._listdir_cache[rel_path]

    def glob(self, pattern: str) -> list[str]:
        """在项目目录中按 pattern 匹配文件（缓存）

        返回相对路径列表。pattern 支持 ** 递归匹配。
        """
        if pattern not in self._glob_cache:
            import glob as _glob
            full_pattern = os.path.join(self.dir_path, pattern)
            matches = _glob.glob(full_pattern, recursive=True)
            # 转为相对路径
            self._glob_cache[pattern] = [
                os.path.relpath(m, self.dir_path) for m in matches
            ]
        return self._glob_cache[pattern]

    def walk(self) -> tuple[list[str], list[str]]:
        """遍历项目目录（缓存），返回 (all_files, all_dirs)

        all_files 和 all_dirs 都是相对路径列表。
        """
        if self._walk_cache is None:
            all_files = []
            all_dirs = []
            skip_dirs = {".git", "node_modules", "target", "__pycache__",
                         ".stackpilot", "dist", "build", ".idea", ".vscode",
                         ".mvn", ".venv", "venv"}
            for root, dirs, files in os.walk(self.dir_path):
                dirs[:] = [d for d in dirs if d not in skip_dirs]
                rel_root = os.path.relpath(root, self.dir_path)
                if rel_root == ".":
                    rel_root = ""
                for f in files:
                    all_files.append(os.path.join(rel_root, f) if rel_root else f)
                for d in dirs:
                    all_dirs.append(os.path.join(rel_root, d) if rel_root else d)
            self._walk_cache = (all_files, all_dirs)
        return self._walk_cache

    # ── 便捷方法 ─────────────────────────────────────────────────

    def add_warning(self, msg: str) -> None:
        """添加一条警告信息"""
        self.warnings.append(msg)
