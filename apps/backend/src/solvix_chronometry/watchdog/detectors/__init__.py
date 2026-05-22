"""Детекторы аномалий — каждая аномалия отдельным модулем."""

from solvix_chronometry.watchdog.detectors.norm_exceeded import detect_norm_exceeded
from solvix_chronometry.watchdog.detectors.pause_exceeded import detect_pause_exceeded
from solvix_chronometry.watchdog.detectors.station_idle import detect_station_idle
from solvix_chronometry.watchdog.detectors.transit_stuck import detect_transit_stuck

__all__ = [
    "detect_norm_exceeded",
    "detect_pause_exceeded",
    "detect_station_idle",
    "detect_transit_stuck",
]
