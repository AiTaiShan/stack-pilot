import json
import logging
from src.agent.deploy_state import DeployState
from src.llm import get_llm_provider

logger = logging.getLogger(__name__)

# 失败类别定义
FAILURE_CATEGORIES = {
    "dockerfile_error": {
        "description": "Dockerfile 语法或配置错误",
        "fixable": True,
        "file_type": "dockerfile"
    },
    "compose_error": {
        "description": "docker-compose.yml 配置错误",
        "fixable": True,
        "file_type": "compose"
    },
    "code_error": {
        "description": "代码编译错误或依赖缺失",
        "fixable": False,
        "file_type": None
    },
    "network_error": {
        "description": "网络超时或镜像拉取失败",
        "fixable": False,
        "file_type": None
    },
    "infra_error": {
        "description": "基础设施问题（Docker/K8s 异常）",
        "fixable": False,
        "file_type": None
    }
}


async def diagnose_node(state: DeployState) -> dict:
    """诊断节点：分析部署失败原因"""
    failed_step = state["failed_step"]
    language = state["language"]
    framework = state["framework"]
    logs = state["logs"]

    logger.info("开始诊断: step=%s, language=%s, framework=%s", failed_step, language, framework)

    system_prompt = f"""你是一个 DevOps 部署诊断专家。请根据以下部署失败信息，分析失败原因。

项目语言: {language}
项目框架: {framework}
失败步骤: {failed_step}

请以 JSON 格式返回：
{{
  "diagnosis": "失败原因的详细分析",
  "suggestions": ["修复建议1", "修复建议2"],
  "failure_category": "类别代码"
}}

failure_category 必须是以下之一：
- dockerfile_error: Dockerfile 语法或配置错误（如基础镜像不对、命令错误、端口未暴露）
- compose_error: docker-compose.yml 配置错误（如服务依赖、卷挂载、网络配置）
- code_error: 代码编译错误或依赖缺失（如 package.json 错误、import 失败、编译报错）
- network_error: 网络超时或镜像拉取失败（如 DNS 解析失败、连接超时、镜像仓库不可达）
- infra_error: 基础设施问题（如 Docker daemon 未运行、磁盘空间不足、K8s 集群异常）

分析要点：
1. 仔细阅读日志中的错误信息
2. 识别根本原因，不要被表面现象误导
3. 如果是 Dockerfile/compose 问题，给出具体的修复建议
4. 如果是代码问题，指出具体的文件和位置"""

    logs_text = "\n".join(logs) if logs else "无日志"
    user_prompt = f"""部署日志（关键部分）:
{logs_text}"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    try:
        llm = get_llm_provider()
        logger.debug("调用 LLM 诊断: model=%s", llm.model)
        response = await llm.chat(messages, temperature=0.3)
        result = json.loads(response)

        diagnosis = result.get("diagnosis", "无法解析诊断结果")
        suggestions = result.get("suggestions", [])
        failure_category = result.get("failure_category", "infra_error")

        # 验证 failure_category 是否有效
        if failure_category not in FAILURE_CATEGORIES:
            logger.warning("无效的 failure_category: %s, 使用默认值 infra_error", failure_category)
            failure_category = "infra_error"

        category_info = FAILURE_CATEGORIES[failure_category]
        fixable = category_info["fixable"]

        # 检查是否有可修复的文件
        if fixable:
            if failure_category == "dockerfile_error" and not state.get("dockerfile_content"):
                fixable = False
                logger.info("Dockerfile 内容为空，无法自动修复")
            elif failure_category == "compose_error" and not state.get("compose_content"):
                fixable = False
                logger.info("Compose 内容为空，无法自动修复")

        logger.info("诊断完成: category=%s, fixable=%s, suggestions=%d",
                     failure_category, fixable, len(suggestions))

        return {
            "diagnosis": diagnosis,
            "suggestions": suggestions,
            "failure_category": failure_category,
            "fixable_by_agent": fixable
        }
    except json.JSONDecodeError:
        logger.warning("LLM 返回非 JSON 格式")
        return {
            "diagnosis": response if 'response' in dir() else "诊断失败",
            "suggestions": ["请根据诊断结果手动排查"],
            "failure_category": "infra_error",
            "fixable_by_agent": False
        }
    except Exception as e:
        logger.error("诊断异常: %s", str(e), exc_info=True)
        return {
            "diagnosis": f"诊断过程出错: {str(e)}",
            "suggestions": ["诊断服务异常，请稍后重试"],
            "failure_category": "infra_error",
            "fixable_by_agent": False
        }
