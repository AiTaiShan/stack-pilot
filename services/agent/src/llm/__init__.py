from src.llm.provider import LLMProvider
from src.llm.dashscope import DashScopeProvider
from src.llm.openai import OpenAIProvider


def get_llm_provider() -> LLMProvider:
    from src.config import settings
    if settings.LLM_PROVIDER == "dashscope":
        return DashScopeProvider()
    return OpenAIProvider()


__all__ = ["LLMProvider", "DashScopeProvider", "OpenAIProvider", "get_llm_provider"]
