import logging
from langgraph.graph import StateGraph, END
from src.agent.state import ReviewState
from src.agent.nodes.reviewer import reviewer_node
from src.agent.nodes.dispatcher import dispatcher_node
from src.agent.nodes.fixer import fixer_node

logger = logging.getLogger(__name__)


def should_continue(state: ReviewState) -> str:
    """根据状态决定下一步

    Args:
        state: 审核状态

    Returns:
        下一步节点名称："reviewer"、"fixer" 或 "end"
    """
    if state["status"] == "approved":
        logger.debug("审核通过，结束流程")
        return "end"
    if state["status"] == "needs_fix":
        logger.debug("需要修复，进入 fixer 节点")
        return "fixer"
    if state["round"] >= state["max_rounds"]:
        logger.debug("已达最大轮次 %d/%d，结束流程", state["round"], state["max_rounds"])
        return "end"
    logger.debug("继续审核，进入 reviewer 节点 (round %d/%d)", state["round"], state["max_rounds"])
    return "reviewer"


def create_review_graph():
    """创建审核状态图

    状态转换逻辑：
    reviewer → dispatcher → (reviewer | fixer | END)

    Returns:
        编译后的 LangGraph 状态图
    """
    workflow = StateGraph(ReviewState)

    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("dispatcher", dispatcher_node)
    workflow.add_node("fixer", fixer_node)

    workflow.set_entry_point("reviewer")
    workflow.add_edge("reviewer", "dispatcher")
    workflow.add_conditional_edges(
        "dispatcher",
        should_continue,
        {
            "reviewer": "reviewer",
            "fixer": "fixer",
            "end": END
        }
    )
    workflow.add_edge("fixer", END)

    logger.info("审核状态图创建完成: reviewer → dispatcher → (reviewer | fixer | END)")
    return workflow.compile()


review_graph = create_review_graph()
