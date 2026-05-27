import warnings
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "StackPilot"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/stackpilot"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # JWT
    JWT_SECRET_KEY: str = "your-secret-key-here"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:5173"]

    # LLM
    LLM_PROVIDER: str = "openai"
    LLM_API_KEY: Optional[str] = None
    LLM_MODEL: str = "gpt-4"
    LLM_BASE_URL: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    @model_validator(mode="after")
    def check_jwt_secret(self) -> "Settings":
        if not self.DEBUG and self.JWT_SECRET_KEY == "your-secret-key-here":
            raise ValueError("生产环境必须设置 JWT_SECRET_KEY，不能使用默认值")
        if self.JWT_SECRET_KEY == "your-secret-key-here":
            warnings.warn("JWT_SECRET_KEY 使用了默认值，生产环境请务必更换", UserWarning)
        return self


settings = Settings()
