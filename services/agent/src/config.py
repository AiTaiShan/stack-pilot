import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

# 项目根目录：services/agent/ 的上两级
_AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_AGENT_DIR))
_ENV_FILE = os.path.join(_PROJECT_ROOT, ".env")

class Settings(BaseSettings):
    APP_NAME: str = "StackPilot Agent"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    SERVER_PORT: int = 8066

    LLM_PROVIDER: str = "dashscope"
    LLM_API_KEY: Optional[str] = None
    LLM_MODEL: str = "qwen-plus"
    LLM_BASE_URL: Optional[str] = None
    LLM_TIMEOUT: int = 60

    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "logs"

    model_config = SettingsConfigDict(env_file=_ENV_FILE, case_sensitive=True, extra="ignore")

settings = Settings()
