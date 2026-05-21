"""Publish one fake station event to MQTT for testing.
Usage: python scripts/publish_test_event.py <station_id> [event_type]
"""
import asyncio
import json
import sys
from datetime import datetime, timezone

import aiomqtt

from solvix_chronometry.uuid_v7 import uuid7


async def main():
    if len(sys.argv) < 2:
        print("usage: publish_test_event.py <station_id> [event_type]")
        sys.exit(1)

    station_id = sys.argv[1]
    event_type = sys.argv[2] if len(sys.argv) > 2 else "scan_in"

    payload = {
        "id": str(uuid7()),
        "station_id": station_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "part_id": None,
        "details": None,
    }

    async with aiomqtt.Client("localhost", port=1883) as client:
        await client.publish(
            f"solvix/station/{station_id}/event",
            payload=json.dumps(payload),
            qos=1,
        )
        print(f"published: {payload}")


if __name__ == "__main__":
    asyncio.run(main())
