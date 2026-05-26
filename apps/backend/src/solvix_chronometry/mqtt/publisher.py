"""MQTT publisher для команд на терминалы.

Используется supervisor-эндпоинтами. На пилоте — открываем новое подключение
на каждую команду. На проде оптимизируем до persistent-клиента.
"""
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import aiomqtt

from solvix_chronometry.config import settings
from solvix_chronometry.uuid_v7 import uuid7


async def publish_command(
    station_id: UUID,
    command: str,
    params: dict[str, Any] | None = None,
) -> str:
    """Опубликовать команду в топик станции.

    Returns: command_id (UUID v7) — для трекинга/логов.
    """
    command_id = str(uuid7())
    payload = {
        "id": command_id,
        "command": command,
        "params": params or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    async with aiomqtt.Client(settings.mqtt_host, port=settings.mqtt_port) as client:
        await client.publish(
            f"solvix/station/{station_id}/command",
            payload=json.dumps(payload),
            qos=1,
        )
    return command_id
