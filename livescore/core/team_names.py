"""Traduzione nomi squadra e hashtag (dati in data/teams.json)."""

import json

from livescore.core import text as txt
from livescore.core.log import log_line
from livescore.paths import DATA_DIR


# ==============================================================================
# MAPPA SQUADRE — caricata da teams.json
# ==============================================================================
_TEAMS_JSON_PATH = str(DATA_DIR / "teams.json")


def _load_teams() -> dict:
    try:
        with open(_TEAMS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        log_line("WARN", "SETUP", f"teams.json non trovato | {_TEAMS_JSON_PATH}; nomi non tradotti")
        return {}
    except Exception as e:
        log_line("ERROR", "SETUP", f"Caricamento teams.json fallito: {e}")
        return {}


TEAM_MAP: dict = _load_teams()


def translate_team(name: str) -> str:
    entry = TEAM_MAP.get(name)
    if entry:
        return entry[0]
    name_lower = name.lower()
    for k, v in TEAM_MAP.items():
        if k.lower() == name_lower:
            return v[0]
    return name


def build_hashtag(home_name, away_name):
    def abbr(name):
        entry = TEAM_MAP.get(name)
        if entry:
            return entry[1]
        name_lower = name.lower()
        for k, v in TEAM_MAP.items():
            if k.lower() == name_lower:
                return v[1]
        return name.replace(" ", "")
    return txt.esc(f"#{abbr(home_name)}{abbr(away_name)}")
