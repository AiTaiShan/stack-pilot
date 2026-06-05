"""Dockerfile 审核模块"""

from src.agent.graph import review_graph
from src.agent.state import ReviewState


async def review_dockerfile(project_info: dict, dockerfile_content: str) -> dict:
    """审核 Dockerfile

    Args:
        project_info: 项目信息（名称、语言、框架等）
        dockerfile_content: Dockerfile 文件内容

    Returns:
        审核结果字典，包含 status、issues、fixed_content、suggestions
    """
    initial_state: ReviewState = {
        "project_info": project_info,
        "file_content": dockerfile_content,
        "file_type": "dockerfile",
        "issues": [],
        "fixed_content": None,
        "suggestions": [],
        "status": "reviewing",
        "round": 0,
        "max_rounds": 3,
    }

    result = await review_graph.ainvoke(initial_state)

    return {
        "status": result["status"],
        "issues": result["issues"],
        "fixed_content": result.get("fixed_content"),
        "suggestions": result.get("suggestions", []),
    }
