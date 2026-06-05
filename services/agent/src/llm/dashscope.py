from openai import AsyncOpenAI
from src.llm.provider import LLMProvider
from src.config import settings
from typing import List, Dict


class DashScopeProvider(LLMProvider):
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.LLM_API_KEY or "",
            base_url=settings.LLM_BASE_URL or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.model = settings.LLM_MODEL

    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            timeout=settings.LLM_TIMEOUT
        )
        return response.choices[0].message.content or ""
