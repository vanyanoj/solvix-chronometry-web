"""WebSocket hub — рассылка событий подписанным фронтам.

In-memory набор активных WS-клиентов. При получении события от MQTT
бэк вызывает hub.broadcast(message) → все клиенты получают мгновенно.

Однопроцессная реализация. При масштабировании на несколько воркеров
потребуется внешний pub/sub (Redis), но пока не нужно.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        logger.info("WS client connected, total=%d", len(self._clients))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)
        logger.info("WS client disconnected, total=%d", len(self._clients))

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Шлёт сообщение всем подключённым клиентам.

        Мёртвых клиентов (сломавшийся send) — выкидываем из набора.
        """
        if not self._clients:
            return

        data = json.dumps(message, default=str)
        dead: list[WebSocket] = []

        for ws in list(self._clients):
            try:
                await ws.send_text(data)
            except Exception as e:
                logger.warning("WS send failed (%s), dropping client", e)
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)


# Singleton — один на весь процесс
hub = WebSocketHub()
