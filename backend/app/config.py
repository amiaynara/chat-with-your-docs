from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5433/app"
    redis_url: str = "redis://localhost:6379/0"

    celery_task_always_eager: bool = False

    object_storage_endpoint_url: str = "http://localhost:9000"
    object_storage_access_key: str = "minioadmin"
    object_storage_secret_key: str = "minioadmin"
    object_storage_bucket: str = "documents"

    llm_provider: str = "anthropic"
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"
    embedding_model_version: str = "1"
    embedding_dimensions: int = 1536

    max_upload_bytes: int = 20 * 1024 * 1024
    allowed_upload_extensions: tuple[str, ...] = (".pdf", ".txt", ".md")

    chunk_size_chars: int = 1000
    chunk_overlap_ratio: float = 0.1

    session_cookie_name: str = "session_id"


settings = Settings()
