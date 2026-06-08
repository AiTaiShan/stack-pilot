from typing import List, Optional, TypedDict


class DeployState(TypedDict):
    """部署诊断状态"""
    # 部署信息
    deployment_id: str
    failed_step: str

    # 项目信息
    project_type: str
    language: str
    framework: str

    # 部署文件（修复用）
    dockerfile_content: Optional[str]
    compose_content: Optional[str]

    # 筛选后的关键日志
    logs: List[str]

    # 重试控制
    retry_count: int
    max_retries: int

    # 输出字段
    diagnosis: str
    suggestions: List[str]
    failure_category: str       # dockerfile_error/compose_error/code_error/network_error/infra_error
    fixable_by_agent: bool
    fixed_content: Optional[str]
    fixed_file_type: Optional[str]  # dockerfile/compose
