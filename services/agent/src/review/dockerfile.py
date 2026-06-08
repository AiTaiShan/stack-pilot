"""Dockerfile 审核模块"""

import logging
from src.agent.graph import review_graph
from src.agent.state import ReviewState

logger = logging.getLogger(__name__)


async def review_dockerfile(project_info: dict, dockerfile_content: str) -> dict:
    """审核 Dockerfile

    Args:
        project_info: 项目信息（名称、语言、框架等）
        dockerfile_content: Dockerfile 文件内容

    Returns:
        审核结果字典，包含 status、issues、fixed_content、suggestions
    """
    lang = project_info.get("language", "unknown")
    framework = project_info.get("framework", "")
    logger.info("开始 Dockerfile 审核: language=%s, framework=%s", lang, framework)

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

    try:
        result = await review_graph.ainvoke(initial_state)
        logger.info("Dockerfile 审核完成: status=%s, issues=%d, suggestions=%d",
                     result["status"], len(result["issues"]), len(result.get("suggestions", [])))

        return {
            "status": result["status"],
            "issues": result["issues"],
            "fixed_content": result.get("fixed_content"),
            "suggestions": result.get("suggestions", []),
        }
    except Exception as e:
        logger.error("Dockerfile 审核流程异常: %s", str(e), exc_info=True)
        raise
