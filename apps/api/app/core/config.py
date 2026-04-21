from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Trace - Sovereign Discovery Copilot"
    env: str = "development"
    secret_key: str = "change-me"
    session_cookie: str = "trace_session"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "trace"
    postgres_user: str = "trace"
    postgres_password: str = "trace"
    redis_url: str = "redis://redis:6379/0"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "trace-documents"
    max_upload_bytes: int = 25 * 1024 * 1024
    model_provider: str = "mock"
    model_name: str = "trace-mock-local"
    model_base_url: str = "http://vllm:8001/v1"
    model_timeout_seconds: int = 30
    ocr_provider: str = "disabled"
    ocr_base_url: str = "http://ocr:8010"
    embedding_provider: str = "hash"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    allow_insecure_demo_login: bool = True

    model_config = SettingsConfigDict(env_prefix="TRACE_", case_sensitive=False, env_file=".env")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
