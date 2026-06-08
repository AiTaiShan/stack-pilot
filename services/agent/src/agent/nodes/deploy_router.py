import logging
from src.agent.deploy_state import DeployState

logger = logging.getLogger(__name__)


def deploy_router_node(state: DeployState) -> dict:
    """路由节点：记录路由决策（实际路由逻辑在 should_fix 中）"""
    failure_category = state.get("failure_category", "infra_error")
    fixable = state.get("fixable_by_agent", False)
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    logger.info("路由决策: category=%s, fixable=%s, retry=%d/%d",
                failure_category, fixable, retry_count, max_retries)

    # 返回诊断结果（确保 LangGraph 有状态更新）
    return {
        "failure_category": failure_category,
        "fixable_by_agent": fixable
    }


def should_fix(state: DeployState) -> str:
    """条件边：根据诊断结果决定是否进入修复节点"""
    failure_category = state.get("failure_category", "infra_error")
    fixable = state.get("fixable_by_agent", False)
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    # 已达到最大重试次数
    if retry_count >= max_retries:
        logger.info("已达最大重试次数 %d/%d，结束流程", retry_count, max_retries)
        return "end"

    # 可修复的问题
    if fixable and failure_category in ("dockerfile_error", "compose_error"):
        logger.info("文件问题且可修复，进入 fixer 节点")
        return "fixer"

    # 不可修复的问题（代码/网络/基础设施）
    logger.info("不可修复的问题 (%s)，结束流程", failure_category)
    return "end"
