import logging
from src.agent.deploy_state import DeployState

logger = logging.getLogger(__name__)


def deploy_router_node(state: DeployState) -> dict:
    """路由节点：根据诊断结果决定下一步"""
    failure_category = state.get("failure_category", "infra_error")
    fixable = state.get("fixable_by_agent", False)
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    logger.info("路由决策: category=%s, fixable=%s, retry=%d/%d",
                failure_category, fixable, retry_count, max_retries)

    # 已达到最大重试次数
    if retry_count >= max_retries:
        logger.info("已达最大重试次数 %d/%d，结束流程", retry_count, max_retries)
        return {"_next": "end"}

    # 可修复的问题
    if fixable and failure_category in ("dockerfile_error", "compose_error"):
        logger.info("文件问题且可修复，进入 fixer 节点")
        return {"_next": "fixer"}

    # 不可修复的问题（代码/网络/基础设施）
    logger.info("不可修复的问题 (%s)，结束流程", failure_category)
    return {"_next": "end"}


def should_fix(state: DeployState) -> str:
    """条件边：决定是否进入修复节点"""
    return state.get("_next", "end")
