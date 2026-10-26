"""Impostazioni del bot.

* **Segreti e identificativi** arrivano dall'ambiente (GitHub Secrets nei workflow).
* **Parametri regolabili** stanno in `data/settings.json` e si cambiano da terminale
  (`python -m livescore config set poll_seconds 5`). Una variabile d'ambiente con lo
  stesso scopo, se presente, ha la precedenza sul file.

Per aggiungere un parametro regolabile basta una riga in `TUNABLES`: compare da solo
nel menu e nei comandi `config`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from livescore.paths import SETTINGS_FILE


@dataclass(frozen=True)
class Tunable:
    default: int
    minimum: int
    maximum: int
    description: str
    env: str = ""          # variabile d'ambiente che ha la precedenza (opzionale)


TUNABLES: dict[str, Tunable] = {
    "poll_seconds": Tunable(
        6, 2, 60, "Ogni quanti secondi controllare ESPN durante la partita"),
    "goal_confirm_seconds": Tunable(
        6, 0, 60, "Attesa prima di annunciare un gol, per verificare che il punteggio sia stabile"),
    "stats_delay_seconds": Tunable(
        300, 0, 3600, "Attesa prima delle statistiche dopo HT / fine tempi / fine partita"),
    "sub_group_seconds": Tunable(
        10, 0, 60, "Finestra per unire piu' cambi ravvicinati in un solo messaggio"),
    "log_heartbeat_minutes": Tunable(
        5, 1, 60, "Ogni quanti minuti scrivere un punto di stato nel log live",
        env="LIVE_LOG_HEARTBEAT_MINUTES"),
}


def load_file() -> dict:
    """Contenuto di data/settings.json ({} se manca o e' illeggibile)."""
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def tunable(key: str) -> int:
    """Valore effettivo di un parametro: ambiente > settings.json > default, sempre nei limiti."""
    spec = TUNABLES[key]
    raw = os.getenv(spec.env) if spec.env else None
    if raw is None or str(raw).strip() == "":
        raw = load_file().get(key, spec.default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = spec.default
    return max(spec.minimum, min(spec.maximum, value))


# ── Segreti e identificativi (ambiente) ──────────────────────────────────────
BOT_TOKEN           = os.getenv('TELEGRAM_TOKEN')
CHAT_ID             = os.getenv('TELEGRAM_TO')
BOT_JR_CHAT_ID      = os.getenv('TELEGRAM_TO_BOT')
TEAM_ID             = os.getenv('TEAM_ID', '111')
GH_PAT              = os.getenv('GH_PAT')
GITHUB_REPOSITORY   = os.getenv('GITHUB_REPOSITORY')
GIST_ID             = os.getenv('GIST_ID')
GOAL_GRAPHICS_ENABLED = os.getenv('GOAL_GRAPHICS_ENABLED', '0').strip().lower() in (
    '1', 'true', 'yes', 'on'
)

# Foto per HALF TIME / END OF 90' / FULL TIME: avviso nella chat privata con il bot
# (la stessa di ImageGEN) e editor nella Mini App di ImageGEN in modalita' live.
PHOTO_CHAT_ID = os.getenv('PHOTO_CHAT_ID') or os.getenv('MANUAL_GRAPHICS_TELEGRAM_CHAT_ID')
PHOTO_WEBAPP_URL = os.getenv('PHOTO_WEBAPP_URL', 'https://tommaso20bw.github.io/ImageGEN_JR/')

# ── Parametri regolabili ─────────────────────────────────────────────────────
POLL_SECONDS = tunable("poll_seconds")
GOAL_CONFIRM_SECONDS = tunable("goal_confirm_seconds")
STATS_DELAY_SECONDS = tunable("stats_delay_seconds")
SUB_GROUP_SECONDS = tunable("sub_group_seconds")
LIVE_LOG_HEARTBEAT_MINUTES = tunable("log_heartbeat_minutes")
