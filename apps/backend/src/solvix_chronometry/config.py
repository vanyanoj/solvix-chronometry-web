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

    # --- CORS ---
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://localhost:8000"],
        description="Разрешённые origins для CORS (JSON-список в .env).",
    )

    # --- JWT ---
    jwt_secret_key: str = Field(
        description="Секрет для подписи JWT-токенов (см. .env.example)",
    )
    jwt_algorithm: str = "HS256"
    jwt_expires_min: int = 720  # 12 часов = одна смена

    # --- App ---
    app_env: str = "development"

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"


settings = Settings()
