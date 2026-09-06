"""Logging compatto e leggibile per i run GitHub Actions del Live Score."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo


ITALY_TZ = ZoneInfo("Europe/Rome")


def log_line(level: str, area: str, message: str, *, timestamp: str | None = None) -> None:
    """Stampa una riga con colonne stabili, adatta ai log GitHub Actions."""
    normalized_level = level.upper()
    debug_enabled = os.getenv("LIVE_LOG_DEBUG", "0").strip().lower() in {
        "1", "true", "yes", "on"
    }
    if normalized_level == "DEBUG" and not debug_enabled:
        return
    current_time = timestamp or datetime.now(ITALY_TZ).strftime("%H:%M:%S")
    print(
        f"[{current_time}] {normalized_level:<6} {area.upper():<10} | {message}",
        flush=True,
    )


def _elapsed_minute(value: object) -> int | None:
    """Converte anche minuti di recupero come ``90+3`` in un intero."""
    raw_value = "" if value is None else value
    match = re.match(r"^\s*(\d+)(?:\+(\d+))?", str(raw_value))
    if not match:
        return None
    return int(match.group(1)) + int(match.group(2) or 0)


@dataclass
class MatchProgressLog:
    """Decide quando il polling merita davvero una riga nel log.

    Sono sempre visibili il primo rilevamento, i cambi di fase e i cambi di
    punteggio. Durante il gioco resta un checkpoint ogni N minuti; se il feed
    rimane fermo, una riga periodica conferma comunque che il bot e vivo.
    """

    heartbeat_minutes: int = 5
    heartbeat_seconds: int = 300
    _last_status: str | None = None
    _last_score: tuple[int, int] | None = None
    _last_minute_bucket: int | None = None
    _last_emit_ts: int = 0

    def should_emit(
        self,
        status: str,
        elapsed: object,
        home_goals: int,
        away_goals: int,
        now_ts: int,
    ) -> bool:
        minute = _elapsed_minute(elapsed)
        bucket = (
            minute // max(1, self.heartbeat_minutes)
            if minute is not None
            else None
        )
        score = (home_goals, away_goals)
        emit = (
            self._last_status is None
            or status != self._last_status
            or score != self._last_score
            or (bucket is not None and bucket != self._last_minute_bucket)
            or now_ts - self._last_emit_ts >= max(60, self.heartbeat_seconds)
        )
        if emit:
            self._last_status = status
            self._last_score = score
            self._last_minute_bucket = bucket
            self._last_emit_ts = now_ts
        return emit
