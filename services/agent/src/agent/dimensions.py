from typing import Dict, List


REVIEW_DIMENSIONS: Dict[str, List[str]] = {
    "node": ["version_mismatch", "port_mapping", "config_adapt", "pkg_manager"],
    "python": ["version_mismatch", "port_mapping", "config_adapt", "dep_check"],
    "go": ["version_mismatch", "port_mapping", "config_adapt"],
    "java": ["version_mismatch", "port_mapping", "config_adapt", "dep_check"],
    "rust": ["version_mismatch", "port_mapping"],
    "php": ["version_mismatch", "port_mapping"],
    "ruby": ["version_mismatch", "port_mapping"],
    "dotnet": ["version_mismatch", "port_mapping"],
}

FRAMEWORK_DIMENSIONS: Dict[str, List[str]] = {
    "wails": ["frontend_build", "embed_check"],
    "next": ["node_build"],
    "nuxt": ["node_build"],
}


def get_review_dimensions(language: str, framework: str = "") -> List[str]:
    """获取语言和框架对应的审核维度

    Args:
        language: 编程语言
        framework: 框架名称

    Returns:
        去重后的审核维度列表
    """
    dimensions = REVIEW_DIMENSIONS.get(language, ["version_mismatch", "port_mapping"])
    if framework:
        dimensions.extend(FRAMEWORK_DIMENSIONS.get(framework, []))
    return list(set(dimensions))
