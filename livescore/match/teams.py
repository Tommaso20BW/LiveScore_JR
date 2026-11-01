"""Quale squadra ha le grafiche in una partita, e con quale tema.

- Juventus: grafiche in tutte le competizioni tranne le amichevoli, tema dalla maglia.
- Italia: grafiche in tutte le partite (amichevoli comprese), sempre senza foto,
  tema 'ita_home' (azzurro) in casa e 'ita_away' (bianco) fuori casa.
"""

from livescore.constants import ITALY_ID, JUVE_ID
from livescore.core import leagues
from livescore.kits import detect as kit_detect


def graphics_team(home_id, away_id, league_slug="", league_name=""):
    """ID della squadra con le grafiche (Juventus o Italia), '' se nessuna."""
    ids = (str(home_id), str(away_id))
    if JUVE_ID in ids:
        return "" if leagues.is_friendly_competition(league_slug, league_name) else JUVE_ID
    if ITALY_ID in ids:
        return ITALY_ID
    return ""


def followed_team(home_id, away_id):
    """Squadra seguita in campo (Juventus o Italia), anche nelle amichevoli: serve ai testi."""
    ids = (str(home_id), str(away_id))
    return JUVE_ID if JUVE_ID in ids else ITALY_ID if ITALY_ID in ids else ""


def opponent_of(team, home_id, away_id):
    """ID dell'avversaria della squadra `team`, '' se `team` non gioca."""
    if str(home_id) == team:
        return str(away_id)
    if str(away_id) == team:
        return str(home_id)
    return ""


def is_italy(home_id, away_id):
    return ITALY_ID in (str(home_id), str(away_id)) and JUVE_ID not in (str(home_id), str(away_id))


def italy_kit(data_espn, home_id):
    """'ita_home' (azzurro) o 'ita_away' (bianco) dalla maglia che ESPN indica per l'Italia
    (boxscore.teams[].team.uniform.color): conta il colore, non chi gioca in casa
    (es. Moldova-Italia giocata in azzurro). Senza dati ESPN: casa -> home, fuori -> away."""
    for block in ((data_espn or {}).get("boxscore") or {}).get("teams") or []:
        team = block.get("team") or {}
        if str(team.get("id", "")) != ITALY_ID:
            continue
        uniform = team.get("uniform") or block.get("uniform") or {}
        color = str(uniform.get("color") or "").lstrip("#")
        if len(color) == 6:
            try:
                r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
            except ValueError:
                break
            return "ita_away" if (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 > 0.7 else "ita_home"
        kind = str(uniform.get("type") or "").lower()
        if kind == "home":
            return "ita_home"
        if kind in ("away", "third"):
            return "ita_away"
    return "ita_home" if str(home_id) == ITALY_ID else "ita_away"


def graphics_kit(data_espn, home_id, away_id, home_name, away_name, league_slug="", league_name=""):
    """Tema delle grafiche: Italia (dal colore della maglia), oppure la maglia della Juventus."""
    if is_italy(home_id, away_id):
        return italy_kit(data_espn, home_id)
    return kit_detect.rileva_kit_juve(data_espn, home_id, away_id, home_name, away_name,
                                      league_slug, league_name)
