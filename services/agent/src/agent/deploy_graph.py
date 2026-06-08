import logging
from langgraph.graph import StateGraph, END
from src.agent.deploy_state import DeployState
from src.agent.nodes.diagnose import diagnose_node
from src.agent.nodes.deploy_router import deploy_router_node, should_fix
from src.agent.nodes.deploy_fixer import deploy_fixer_node

logger = logging.getLogger(__name__)


def create_deploy_graph():
    """创建部署诊断状态图

    状态转换逻辑：
    diagnose → router → (fixer | END)

    Returns:
        编译后的 LangGraph 状态图
    """
    workflow = StateGraph(DeployState)

    workflow.add_node("diagnose", diagnose_node)
    workflow.add_node("router", deploy_router_node)
    workflow.add_node("fixer", deploy_fixer_node)

    workflow.set_entry_point("diagnose")
    workflow.add_edge("diagnose", "router")
    workflow.add_conditional_edges(
        "router",
        should_fix,
        {
            "fixer": "fixer",
            "end": END
        }
    )
    workflow.add_edge("fixer", END)

    logger.info("部署诊断状态图创建完成: diagnose → router → (fixer | END)")
    return workflow.compile()


deploy_graph = create_deploy_graph()
