"""Конфиг приложения через переменные окружения / .env."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- БД ---
    database_url: str = Field(
        default="postgresql+asyncpg://solvix:solvix_dev_password@localhost:5432/solvix_chronometry",
        description="Async URL для SQLAlchemy (asyncpg драйвер).",
    )

    # --- MQTT ---
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883

    # --- App ---
    app_env: str = "development"

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"


settings = Settings()
