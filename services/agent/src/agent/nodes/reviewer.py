import json
from src.agent.state import ReviewState
from src.llm import get_llm_provider
from src.agent.dimensions import get_review_dimensions


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
        response = await llm.chat(messages)
        result = json.loads(response)
        return {
            "issues": result.get("issues", []),
            "suggestions": result.get("suggestions", []),
            "round": state["round"] + 1
        }
    except Exception as e:
        return {
            "issues": [],
            "suggestions": [f"审核过程出错: {str(e)}"],
            "round": state["round"] + 1
        }
