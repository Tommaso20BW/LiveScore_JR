"""Campionati e coppe (dati in data/leagues.json)."""

import json

from livescore.core.log import log_line
from livescore.paths import DATA_DIR


# ==============================================================================
# LEGHE — caricato da leagues.json
# Formato: { "slug": { "emoji": "🇮🇹" } }
# ==============================================================================
_LEAGUES_JSON_PATH = str(DATA_DIR / "leagues.json")


def _load_leagues() -> dict:
    try:
        with open(_LEAGUES_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        log_line("WARN", "SETUP", "leagues.json non trovato; emoji leghe disabilitate")
        return {}
    except Exception as e:
        log_line("ERROR", "SETUP", f"Caricamento leagues.json fallito: {e}")
        return {}


LEAGUE_MAP: dict = _load_leagues()


LEAGUE_SLUGS: list = list(LEAGUE_MAP.keys())


def get_league_emoji(slug): return LEAGUE_MAP.get(slug, {}).get("emoji", "⚽️")


def _is_league_slug(slug: str) -> bool:
    """True se lo slug ESPN è un campionato (es. 'ita.1', 'eng.2'):
    3 lettere + '.' + numero. Tutto il resto è considerato coppa."""
    parts = (slug or "").split(".")
    return (len(parts) == 2 and len(parts[0]) == 3
            and parts[0].isalpha() and parts[1].isdigit())


# Parole chiave di fallback per riconoscere una coppa dal nome/slug
_CUP_KEYWORDS = (
    "copp", "cup", "champions", "europa", "conference", "super",
    "supercoppa", "mondiale", "club world", "cwc", "shield",
    "playoff", "play-off",
)


# Parole chiave di fallback per riconoscere un'amichevole dal nome/slug
# (slug ESPN tipici: 'friendly.club', 'fifa.friendly')
_FRIENDLY_KEYWORDS = ("friendly", "amichev")


def is_cup_competition(league_slug: str, league_name: str = "") -> bool:
    """Determina se la competizione è una coppa.
    Priorità: override esplicito in leagues.json ({"slug": {"type": "cup"}})
    → formato slug campionato → keyword di fallback."""
    slug = (league_slug or "").lower()
    name = (league_name or "").lower()

    # 1) override esplicito da leagues.json
    tipo = str(LEAGUE_MAP.get(league_slug, {}).get("type", "")).lower()
    if tipo in ("cup", "coppa"):
        return True
    if tipo in ("league", "campionato"):
        return False

    # 2) formato slug: i campionati sono "xxx.N"
    if _is_league_slug(slug):
        return False

    # 3) fallback per keyword
    return any(k in slug or k in name for k in _CUP_KEYWORDS)


def is_friendly_competition(league_slug: str, league_name: str = "") -> bool:
    """Determina se la competizione è un'amichevole.
    Priorità: override esplicito in leagues.json ({"slug": {"type": "friendly"}})
    → keyword di fallback."""
    slug = (league_slug or "").lower()
    name = (league_name or "").lower()

    # 1) override esplicito da leagues.json
    tipo = str(LEAGUE_MAP.get(league_slug, {}).get("type", "")).lower()
    if tipo in ("friendly", "amichevole"):
        return True

    # 2) fallback per keyword
    return any(k in slug or k in name for k in _FRIENDLY_KEYWORDS)
