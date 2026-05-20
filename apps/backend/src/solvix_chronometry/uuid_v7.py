"""
UUID v7 — генерация идентификаторов с timestamp в начале.

См. [Решение №53] в Обсидиане: все PK — UUID v7 ради распределённой генерации
(сервер + ESP32 + будущий Central) без коллизий, плюс v7 сортируется по времени
→ B-tree индекс работает почти как обычный bigint.

Имплементация — спецификация RFC 9562 (UUID v7), 48 бит unix timestamp в мс,
4 бита версии, 12 бит rand_a, 2 бита variant, 62 бита rand_b.
"""

from __future__ import annotations

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """Сгенерировать UUID v7."""
    # 48 бит unix-времени в миллисекундах
    timestamp_ms = int(time.time() * 1000)

    # 10 рандомных байт (для rand_a + rand_b)
    rand_bytes = os.urandom(10)

    # Собираем 128 бит:
    #   octets 0-5  : timestamp_ms (big-endian)
    #   octet  6    : 0111xxxx — версия 7 в старших 4 битах, rand_a в младших 4
    #   octet  7    : rand_a (8 бит)
    #   octet  8    : 10xxxxxx — variant 10, rand_b в младших 6 битах
    #   octets 9-15 : rand_b
    ts_bytes = timestamp_ms.to_bytes(6, "big")

    octet_6 = 0x70 | (rand_bytes[0] & 0x0F)
    octet_7 = rand_bytes[1]
    octet_8 = 0x80 | (rand_bytes[2] & 0x3F)

    full = ts_bytes + bytes([octet_6, octet_7, octet_8]) + rand_bytes[3:10]
    return uuid.UUID(bytes=full)
