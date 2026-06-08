import logging
from src.agent.state import ReviewState

logger = logging.getLogger(__name__)


def dispatcher_node(state: ReviewState) -> dict:
    """调度节点：判断是否还有问题需要处理

    根据当前状态决定下一步操作：
    - 无问题 → approved
    - 达到最大轮次 → needs_fix
    - 仍有问题且未达上限 → reviewing

    Args:
        state: 审核状态

    Returns:
        包含新 status 的字典
    """
    issues_count = len(state["issues"])
    current_round = state["round"]
    max_rounds = state["max_rounds"]

    if not state["issues"]:
        logger.debug("调度决策: 无问题 → approved (round=%d/%d)", current_round, max_rounds)
        return {"status": "approved"}

    if state["round"] >= state["max_rounds"]:
        logger.info("调度决策: 达到最大轮次 → needs_fix (round=%d/%d, issues=%d)",
                     current_round, max_rounds, issues_count)
        return {"status": "needs_fix"}

    logger.debug("调度决策: 仍有问题 → reviewing (round=%d/%d, issues=%d)",
                  current_round, max_rounds, issues_count)
    return {"status": "reviewing"}
