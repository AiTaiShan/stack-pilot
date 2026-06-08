import json
import logging
from src.agent.state import ReviewState
from src.llm import get_llm_provider
from src.agent.dimensions import get_review_dimensions

logger = logging.getLogger(__name__)


async def reviewer_node(state: ReviewState) -> dict:
    """审核节点：检查文件并发现问题

    Args:
        state: 审核状态，包含项目信息、文件内容等

    Returns:
        包含 issues、suggestions 和更新后 round 的字典
    """
    llm = get_llm_provider()
    project_info = state["project_info"]
    file_content = state["file_content"]
    file_type = state["file_type"]
    language = project_info.get("language", "unknown")
    framework = project_info.get("framework", "")
    dimensions = get_review_dimensions(language, framework)

    logger.info("开始审核 %s: language=%s, framework=%s, round=%d",
                file_type, language, framework, state["round"] + 1)

    system_prompt = f"""你是一个{file_type}审核专家。请检查以下内容并发现问题。

审核维度：{', '.join(dimensions)}

请以 JSON 格式返回发现的问题列表，格式如下：
{{
  "issues": [
    {{
      "category": "问题分类",
      "severity": "low/medium/high",
      "description": "问题描述",
      "file_path": "文件路径",
      "fix_suggestion": "修复建议"
    }}
  ],
  "suggestions": ["优化建议1", "优化建议2"]
}}

如果没有发现问题，返回 {{"issues": [], "suggestions": []}}"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"项目信息：{json.dumps(project_info, ensure_ascii=False)}\n\n文件内容：\n{file_content}"}
    ]

    try:
        logger.debug("发送 LLM 审核请求: model=%s, message_count=%d", llm.model, len(messages))
        response = await llm.chat(messages)
        result = json.loads(response)
        issues = result.get("issues", [])
        suggestions = result.get("suggestions", [])

        severity_count = {}
        for issue in issues:
            sev = issue.get("severity", "unknown")
            severity_count[sev] = severity_count.get(sev, 0) + 1

        logger.info("审核完成 %s: issues=%d, severity=%s, suggestions=%d",
                     file_type, len(issues), severity_count, len(suggestions))

        return {
            "issues": issues,
            "suggestions": suggestions,
            "round": state["round"] + 1
        }
    except Exception as e:
        logger.error("审核节点异常 %s: %s", file_type, str(e), exc_info=True)
        return {
            "issues": [],
            "suggestions": [f"审核过程出错: {str(e)}"],
            "round": state["round"] + 1
        }
