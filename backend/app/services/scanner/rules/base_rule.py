"""语言规则抽象基类"""
from abc import ABC, abstractmethod
from typing import Optional


class BaseRule(ABC):
    """所有语言规则的抽象基类"""

    @classmethod
    @abstractmethod
    def language_id(cls) -> str:
        """返回语言标识符 (如 'node', 'python', 'rust')"""
        ...

    @classmethod
    @abstractmethod
    def detect_language(cls, files: list) -> bool:
        """检测是否属于本语言 (检查标志文件)"""
        ...

    @classmethod
    @abstractmethod
    def detect(cls, dir_path: str) -> dict:
        """
        深度检测: 框架、入口点、包管理器、端口、命令
        返回 dict 包含 framework, entry_point, package_manager,
               build_command, start_command, port
        """
        ...

    @classmethod
    def get_template_name(cls) -> str:
        """返回对应的模板模块名称"""
        return f"{cls.language_id()}_template"
