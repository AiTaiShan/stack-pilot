import logging
from openai import AsyncOpenAI
from src.llm.provider import LLMProvider
from src.config import settings
from typing import List, Dict

logger = logging.getLogger(__name__)


class DashScopeProvider(LLMProvider):
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.LLM_API_KEY or "",
            base_url=settings.LLM_BASE_URL or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.model = settings.LLM_MODEL
        logger.info("DashScope LLM 初始化: model=%s, base_url=%s", self.model, self.client.base_url)

    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
        logger.debug("LLM 请求: model=%s, temperature=%s, messages=%d",
                      self.model, temperature, len(messages))
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                timeout=settings.LLM_TIMEOUT
            )
            content = response.choices[0].message.content or ""
            logger.debug("LLM 响应: model=%s, response_length=%d", self.model, len(content))
            return content
        except Exception as e:
            logger.error("LLM 调用失败: model=%s, error=%s", self.model, str(e), exc_info=True)
            raise
