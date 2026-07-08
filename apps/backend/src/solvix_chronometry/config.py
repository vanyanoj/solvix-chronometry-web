"""Конфиг приложения через переменные окружения / .env."""

from __future__ import annotations

from pydantic import Field, model_validator
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

    @model_validator(mode="after")
    def _check_jwt_secret(self) -> "Settings":
        placeholders = {
            "replace_me_with_a_long_random_string",
            "changeme",
            "secret",
            "dev",
        }
        if self.app_env != "development":
            if self.jwt_secret_key in placeholders or len(self.jwt_secret_key) < 32:
                raise ValueError(
                    "jwt_secret_key is a known placeholder or too short (<32 chars). "
                    "Generate one: python3 -c 'import secrets; print(secrets.token_urlsafe(48))'"
                )
        return self

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"


settings = Settings()
