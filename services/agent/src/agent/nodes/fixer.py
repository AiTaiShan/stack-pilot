import json
import logging
from src.agent.state import ReviewState
from src.llm import get_llm_provider

logger = logging.getLogger(__name__)


async def fixer_node(state: ReviewState) -> dict:
    """修复节点：自动修复发现的问题

    调用 LLM 根据问题列表修复代码，返回修复后的内容。

    Args:
        state: 审核状态，包含 issues 和 file_content

    Returns:
        包含 fixed_content 和 status 的字典
    """
    llm = get_llm_provider()
    issues = state["issues"]
    file_content = state["file_content"]
    file_type = state["file_type"]

    logger.info("开始修复 %s: 待修复 issues=%d", file_type, len(issues))

    system_prompt = f"""你是一个{file_type}修复专家。请根据问题列表修复代码。

要求：
1. 保留原始代码的结构和风格
2. 只修复问题，不做额外修改
3. 返回修复后的完整代码"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"问题列表：{json.dumps(issues, ensure_ascii=False)}\n\n原始代码：\n{file_content}"}
    ]

    try:
        logger.debug("发送 LLM 修复请求: model=%s, message_count=%d", llm.model, len(messages))
        response = await llm.chat(messages)
        logger.info("修复完成 %s: 返回内容长度=%d", file_type, len(response))
        return {
            "fixed_content": response,
            "status": "needs_fix"
        }
    except Exception as e:
        logger.error("修复节点异常 %s: %s", file_type, str(e), exc_info=True)
        return {
            "fixed_content": None,
            "status": "rejected",
            "suggestions": [f"修复过程出错: {str(e)}"]
        }
