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
    pass_code_pepper: str = Field(
        description="Секретный pepper для HMAC-хэширования pass_code (см. .env.example)",
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
            for name in ("jwt_secret_key", "pass_code_pepper"):
                value = getattr(self, name)
                if value in placeholders or len(value) < 32:
                    raise ValueError(
                        f"{name} is a known placeholder or too short (<32 chars). "
                        "Generate one: python3 -c "
                        "'import secrets; print(secrets.token_urlsafe(48))'"
                    )
        return self

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"


settings = Settings()
