from src.agent.state import ReviewState


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
    if not state["issues"]:
        return {"status": "approved"}

    if state["round"] >= state["max_rounds"]:
        return {"status": "needs_fix"}

    return {"status": "reviewing"}
