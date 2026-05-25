"""환경변수 로드 — .env 파일을 자동으로 읽어 settings 객체에 매핑."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 앱
    app_env: str = "development"
    log_level: str = "INFO"

    # OpenAI
    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_key: str
    database_url: str

    # 한도·CORS
    daily_llm_limit_per_user: int = 100
    cors_origins: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]


# 전역 설정 (다른 모듈에서 `from app.config import settings`)
settings = Settings()
