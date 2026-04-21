from dataclasses import dataclass
import os


@dataclass(slots=True)
class WorkerSettings:
    redis_url: str = os.getenv("TRACE_REDIS_URL", "redis://redis:6379/0")
    postgres_host: str = os.getenv("TRACE_POSTGRES_HOST", "postgres")
    postgres_port: int = int(os.getenv("TRACE_POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("TRACE_POSTGRES_DB", "trace")
    postgres_user: str = os.getenv("TRACE_POSTGRES_USER", "trace")
    postgres_password: str = os.getenv("TRACE_POSTGRES_PASSWORD", "trace")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = WorkerSettings()
