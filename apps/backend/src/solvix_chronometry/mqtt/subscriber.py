"""MQTT subscriber — background task that listens for station events.

Subscribes to solvix/station/+/event (wildcard across all stations),
parses each message into StationEvent, hands off to handle_station_event.

Reconnects forever on connection loss with a fixed 5s backoff.
"""
import asyncio
import logging

import aiomqtt
from pydantic import ValidationError

from solvix_chronometry.config import settings
from solvix_chronometry.db import SessionLocal
from solvix_chronometry.mqtt.handler import handle_station_event
from solvix_chronometry.mqtt.schemas import StationEvent

logger = logging.getLogger(__name__)

EVENT_TOPIC = "solvix/station/+/event"


async def run_subscriber() -> None:
    """Subscribe loop. Reconnects forever — meant to live for the app lifetime."""
    while True:
        try:
            async with aiomqtt.Client(settings.mqtt_host, port=settings.mqtt_port) as client:
                await client.subscribe(EVENT_TOPIC, qos=1)
                logger.info("MQTT connected, subscribed to %s", EVENT_TOPIC)

                async for message in client.messages:
                    await _process_message(message)

        except aiomqtt.MqttError as exc:
            logger.warning("MQTT connection lost: %s — reconnecting in 5s", exc)
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("MQTT subscriber cancelled, shutting down")
            raise


async def _process_message(message: aiomqtt.Message) -> None:
    """Parse one MQTT message and dispatch to handler. Logs and continues on error."""
    try:
        event = StationEvent.model_validate_json(message.payload)
    except ValidationError as exc:
        logger.error(
            "invalid event payload on %s: %s | payload=%r",
            message.topic, exc, message.payload,
        )
        return

    try:
        async with SessionLocal() as session:
            await handle_station_event(event, session)
    except Exception:
        logger.exception("handler failed for event id=%s", event.id)
