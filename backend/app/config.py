from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    secret_key: str = "dev-secret-change-in-production"
    database_url: str = "sqlite:///./data/spendsense.db"
    cors_origins: str = "http://localhost:5173"
    gemini_api_key: str = ""
    openai_api_key: str = ""
    llm_provider: str = "gemini"
    # Flash-Lite is optimized for low-latency, high-volume classification.
    gemini_model: str = "gemini-3.5-flash-lite"
    openai_model: str = "gpt-6-luna"
    access_token_expire_minutes: int = 60 * 24 * 7

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
