"""scanner 数据模型"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ServiceInfo:
    """微服务 / 多模块中的单个服务"""
    name: str
    dir: str
    language: str
    framework: Optional[str] = None
    entry_point: Optional[str] = None
    port: int = 8080
    type: str = "service"  # service | common | gateway | registry | config
    build_cmd: Optional[str] = None
    start_cmd: Optional[str] = None


@dataclass
class FrontendInfo:
    """前端项目信息"""
    dir: str
    language: str
    framework: Optional[str] = None
    port: int = 3000
    version: Optional[str] = None
    build_cmd: str = ""
    start_cmd: str = ""


@dataclass
class BackendInfo:
    """后端项目信息"""
    dir: str
    language: str
    framework: Optional[str] = None
    port: int = 8000
    version: Optional[str] = None
    entry_point: Optional[str] = None
    start_cmd: Optional[str] = None


@dataclass
class ScanResult:
    """完整的检测结果"""
    project_type: str  # single | monorepo | microservices | multi-module-java
    languages: list = field(default_factory=list)
    language: str = "unknown"
    framework: Optional[str] = None
    entry_point: Optional[str] = None
    package_manager: Optional[str] = None
    build_command: Optional[str] = None
    start_command: Optional[str] = None
    port: int = 8080
    version: Optional[str] = None  # 从项目配置中检测的语言版本
    services: list = field(default_factory=list)
    frontend: Optional[FrontendInfo] = None
    backend: Optional[BackendInfo] = None
    dependencies: dict = field(default_factory=dict)
    key_files: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
