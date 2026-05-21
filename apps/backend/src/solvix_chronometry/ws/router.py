"""WebSocket-эндпоинт для real-time потока событий.

Клиент подключается → hub.connect() → блокируется на receive_text() пока
жив сокет. При разрыве — hub.disconnect(). События пушит MQTT-handler
через hub.broadcast() — клиент видит их мгновенно.

Initial state клиент грузит отдельно через REST GET /dashboard/stations.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from solvix_chronometry.ws.hub import hub

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/events")
async def ws_events(websocket: WebSocket) -> None:
    await hub.connect(websocket)
    try:
        # Клиент по протоколу ничего не шлёт — receive_text() блочится,
        # но при разрыве сокета бросит WebSocketDisconnect (это нам и нужно)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(websocket)
