"""Contesto condiviso dai gestori del ciclo di partita."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Flow(Enum):
    """Cosa deve fare il ciclo dopo un gestore."""

    CONTINUE = 1   # salta il resto del ciclo e ricomincia (senza attendere)
    STOP = 2       # termina il ciclo di partita


@dataclass
class MatchContext:
    """Tutto cio' che i gestori si scambiano.

    *Partita*: fissati all'avvio. *Ciclo*: ricalcolati a ogni giro di polling.
    """

    # --- partita (fissi o aggiornati nel tempo) ---
    event_id: Any = None
    league_name: Any = None
    league_slug: Any = None
    partita: Any = None
    progress_log: Any = None
    state: Any = None
    sub_hold_since: Any = None   # da quando ci sono cambi nuovi in attesa di essere raggruppati

    # --- ciclo corrente ---
    _now_ts: Any = None
    away_id: Any = None
    away_name: Any = None
    away_name_raw: Any = None
    competitors: Any = None
    data: Any = None
    e_comp: Any = None
    elapsed: Any = None
    events: Any = None
    g_away: Any = None
    g_home: Any = None
    hashtag: Any = None
    home_id: Any = None
    home_name: Any = None
    home_name_raw: Any = None
    score_str: Any = None
    sleep_time: Any = None
    state_changed: Any = None
    status: Any = None
