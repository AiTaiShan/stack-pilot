"""语言规则抽象基类

所有语言规则继承 BaseRule 后自动注册到 _registry，
通过 BaseRule.get_rule(lang_id) 或 BaseRule.all_rules() 获取。
"""
from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .context import ProjectContext


class BaseRule(ABC):
    """所有语言规则的抽象基类"""

    _registry: dict[str, type["BaseRule"]] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # 跳过没有实现 language_id 的中间抽象类
        try:
            lang_id = cls.language_id()
        except NotImplementedError:
            return
        if lang_id:
            BaseRule._registry[lang_id] = cls

    @classmethod
    @abstractmethod
    def language_id(cls) -> str:
        """返回语言标识符 (如 'node', 'python', 'rust')"""
        ...

    @classmethod
    @abstractmethod
    def detect_language(cls, files: list) -> float:
        """检测是否属于本语言，返回 0.0~1.0 的置信度

        0.0 = 完全不匹配，1.0 = 确定是该语言。
        仅基于文件名快速判断，不做文件内容解析。
        """
        ...

    @classmethod
    @abstractmethod
    def detect(cls, ctx: "ProjectContext") -> Optional[dict]:
        """
        深度检测: 框架、入口点、包管理器、端口、命令

        参数:
            ctx: ProjectContext 实例，提供缓存的文件读取

        返回 dict 包含 framework, entry_point, package_manager,
               build_command, start_command, port，或 None 表示不匹配
        """
        ...

    @classmethod
    def get_template_name(cls) -> str:
        """返回对应的模板模块名称"""
        return f"{cls.language_id()}_template"

    # ── 注册表查询 ──────────────────────────────────────────────

    @classmethod
    def get_rule(cls, lang_id: str) -> Optional[type["BaseRule"]]:
        """根据语言 ID 获取规则类"""
        return cls._registry.get(lang_id)

    @classmethod
    def all_rules(cls) -> list[type["BaseRule"]]:
        """返回所有已注册的规则类"""
        return list(cls._registry.values())

    @classmethod
    def registered_languages(cls) -> list[str]:
        """返回所有已注册的语言 ID"""
        return list(cls._registry.keys())
