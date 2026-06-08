import json
import logging
from src.agent.deploy_state import DeployState
from src.llm import get_llm_provider

logger = logging.getLogger(__name__)


async def deploy_fixer_node(state: DeployState) -> dict:
    """修复节点：修复 Dockerfile 或 compose 文件"""
    failure_category = state.get("failure_category", "")
    diagnosis = state.get("diagnosis", "")
    suggestions = state.get("suggestions", [])
    language = state.get("language", "unknown")
    framework = state.get("framework", "")

    # 根据失败类别确定修复哪个文件
    if failure_category == "dockerfile_error":
        file_type = "dockerfile"
        file_content = state.get("dockerfile_content", "")
        file_label = "Dockerfile"
    elif failure_category == "compose_error":
        file_type = "compose"
        file_content = state.get("compose_content", "")
        file_label = "docker-compose.yml"
    else:
        logger.warning("无法修复的失败类别: %s", failure_category)
        return {
            "fixable_by_agent": False,
            "fixed_content": None,
            "fixed_file_type": None
        }

    if not file_content:
        logger.warning("%s 内容为空，无法修复", file_label)
        return {
            "fixable_by_agent": False,
            "fixed_content": None,
            "fixed_file_type": None
        }

    logger.info("开始修复 %s: language=%s, framework=%s", file_label, language, framework)

    system_prompt = f"""你是一个 {file_label} 修复专家。请根据诊断结果修复以下文件。

项目语言: {language}
项目框架: {framework}
失败原因: {diagnosis}
修复建议: {', '.join(suggestions)}

要求：
1. 只修复问题，不做额外修改
2. 保留原始文件的结构和风格
3. 返回修复后的完整文件内容
4. 直接返回文件内容，不要包含任何解释或 markdown 格式"""

    user_prompt = f"""原始 {file_label} 内容:
```
{file_content}
```

请返回修复后的完整内容："""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    try:
        llm = get_llm_provider()
        logger.debug("调用 LLM 修复: model=%s", llm.model)
        response = await llm.chat(messages, temperature=0.2)

        # 清理可能的 markdown 格式
        fixed_content = response.strip()
        if fixed_content.startswith("```"):
            # 去掉 ```dockerfile 或 ```yaml 等标记
            lines = fixed_content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            fixed_content = "\n".join(lines)

        logger.info("修复完成 %s: 原始长度=%d, 修复后长度=%d",
                     file_label, len(file_content), len(fixed_content))

        return {
            "fixed_content": fixed_content,
            "fixed_file_type": file_type
        }
    except Exception as e:
        logger.error("修复异常 %s: %s", file_label, str(e), exc_info=True)
        return {
            "fixable_by_agent": False,
            "fixed_content": None,
            "fixed_file_type": None
        }
