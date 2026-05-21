"""Pydantic schemas for MQTT message payloads.

Contract is defined in Обсидиан → Решения.md → раздел MQTT (Решения №76-80).
- Topic: solvix/station/{station_id}/event
- Format: JSON, snake_case keys, ISO 8601 timestamps
- Event id is UUID v7 generated on terminal (becomes events.id in DB directly)
"""
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# Event types emitted by ESP32 terminal.
# Note: `anomaly` is NOT here — anomalies are server-side only (watchdog).
StationEventType = Literal[
    "scan_in",
    "start",
    "stop",
    "scan_out",
    "break_start",
    "break_end",
    "error",
    "interrupted",
]


class StationEvent(BaseModel):
    """Event payload published by ESP32 to solvix/station/{station_id}/event.

    Strict by design — unknown fields raise ValidationError so we catch
    firmware/contract drift early. If a new field needs to be added later,
    update this schema in lockstep with firmware.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID  # UUID v7 from terminal — becomes events.id in DB (dedup-free)
    station_id: UUID  # duplicated in payload for self-containedness (Решение №77)
    timestamp: datetime  # when event happened (terminal clock), ISO 8601
    event_type: StationEventType
    part_id: str | None = None  # composite string like "D-0001.2", null for non-scan events
    details: dict[str, Any] | None = None  # shape varies by event_type
