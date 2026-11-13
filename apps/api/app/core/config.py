from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Trace"
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
    storage_backend: str = "filesystem"  # filesystem | s3
    storage_root: str = "/data/objects"
    s3_endpoint_url: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str = "trace-documents"
    max_upload_bytes: int = 25 * 1024 * 1024
    # mock (tests/CI) | local (Ollama, llama.cpp, vLLM on this machine/network) | hosted
    model_provider: str = "mock"
    model_name: str = "qwen2.5:7b-instruct"
    model_base_url: str = "http://host.docker.internal:11434/v1"
    model_api_key: str | None = None
    model_timeout_seconds: int = 180
    model_max_output_tokens: int = 1500
    model_max_retries: int = 2
    model_structured_output: str = "json_schema"  # json_schema | json_object
    model_max_calls_per_run: int = 12
    # Must be explicitly true before a hosted provider may receive any document text.
    hosted_egress_acknowledged: bool = False
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


class UnsafeConfigurationError(RuntimeError):
    pass


def assert_safe_for_environment(config: Settings) -> None:
    """Refuse to start outside development/test with demo-grade security settings."""
    if config.env in {"development", "test"}:
        return
    problems = []
    if config.secret_key in {"", "change-me"} or len(config.secret_key) < 32:
        problems.append("TRACE_SECRET_KEY must be a random value of at least 32 characters")
    if config.allow_insecure_demo_login:
        problems.append("TRACE_ALLOW_INSECURE_DEMO_LOGIN must be false")
    if problems:
        raise UnsafeConfigurationError("; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    config = Settings()
    assert_safe_for_environment(config)
    return config


settings = get_settings()
