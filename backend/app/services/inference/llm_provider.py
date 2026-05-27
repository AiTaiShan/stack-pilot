"""OpenAI 兼容的 LLM Provider（支持阿里百炼、OpenAI 等）"""

import json
import logging
from typing import Dict, List, Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider:
    """OpenAI 兼容接口的 LLM Provider

    支持：
    - OpenAI (api.openai.com)
    - 阿里百炼 (dashscope.aliyuncs.com/compatible-mode/v1)
    - 其他兼容 OpenAI API 格式的服务
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or settings.LLM_API_KEY
        self.base_url = base_url or settings.LLM_BASE_URL
        self.model = model or settings.LLM_MODEL

    def infer_resources(self, dependencies: List[str]) -> Dict[str, List[str]]:
        """调用 LLM 推断资源需求"""
        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置")

        prompt = self._build_prompt(dependencies)

        try:
            import httpx

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            body = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个部署专家，根据项目依赖推断所需的基础设施资源。只返回 JSON，不要其他文字。",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
            }

            url = f"{self.base_url}/chat/completions" if self.base_url else "https://api.openai.com/v1/chat/completions"

            with httpx.Client(timeout=30) as client:
                response = client.post(url, headers=headers, json=body)
                response.raise_for_status()

            content = response.json()["choices"][0]["message"]["content"]
            return self._parse_response(content)

        except Exception as e:
            logger.warning("LLM 调用失败: %s", e)
            raise

    def _build_prompt(self, dependencies: List[str]) -> str:
        return f"""分析以下项目依赖，推断部署所需的基础设施资源。

依赖列表：{', '.join(dependencies)}

请返回如下 JSON 格式：
{{
    "database": ["postgresql"],
    "cache": ["redis"],
    "queue": [],
    "storage": [],
    "compute": []
}}

只包含确实需要的资源，不确定的留空数组。"""

    def _parse_response(self, content: str) -> Dict[str, List[str]]:
        """解析 LLM 返回的 JSON"""
        default = {"database": [], "cache": [], "queue": [], "storage": [], "compute": []}
        try:
            # 尝试提取 JSON 块
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            result = json.loads(content.strip())
            # 确保所有 key 都存在
            for key in default:
                if key not in result:
                    result[key] = []
            return result
        except (json.JSONDecodeError, IndexError):
            logger.warning("LLM 返回内容解析失败: %s", content)
            return default
