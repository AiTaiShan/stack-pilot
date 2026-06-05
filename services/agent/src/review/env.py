"""环境变量审核模块"""

from src.agent.graph import review_graph
from src.agent.state import ReviewState


async def review_env(project_info: dict, env_vars: dict) -> dict:
    """审核环境变量

    Args:
        project_info: 项目信息（名称、语言、框架等）
        env_vars: 环境变量字典，格式为 {key: value}

    Returns:
        审核结果字典，包含 status、issues、fixed_content、suggestions
    """
    env_content = "\n".join([f"{k}={v}" for k, v in env_vars.items()])

    initial_state: ReviewState = {
        "project_info": project_info,
        "file_content": env_content,
        "file_type": "env",
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
