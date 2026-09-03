from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    secret_key: str = "replace-me"
    database_url: str = "sqlite:///./data/app.db"
    upload_dir: str = "./uploads"
    backup_dir: str = "./backups"
    max_upload_mb: int = 25
    maintenance_interval_seconds: int = 3600
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
