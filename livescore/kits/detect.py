"""Scelta del kit Juventus (home / away / third)."""


from livescore.constants import JUVE_ID
from livescore.core import leagues
from livescore.kits import analyzer as kit_analyzer


def determina_kit(home_id, away_id, league_slug: str = "", league_name: str = "") -> str:
    """Restituisce il tema della maglia da applicare alla grafica stats."""
    # Amichevoli → sempre kit 'default' (anche se gioca la Juve)
    if leagues.is_friendly_competition(league_slug, league_name):
        return "default"
    juve_in_casa       = str(home_id) == JUVE_ID
    juve_in_trasferta  = str(away_id) == JUVE_ID
    if not (juve_in_casa or juve_in_trasferta):
        return "default"
    if leagues.is_cup_competition(league_slug, league_name):
        return "third"
    return "home" if juve_in_casa else "away"


def rileva_kit_juve(data_espn: dict, home_id: str, away_id: str,
                    home_name: str, away_name: str,
                    league_slug: str = "", league_name: str = "") -> str:
    """Restituisce il kit realmente indossato usando la stessa cascata ESPN
    gia usata dalle stats. La funzione e separata per poterla riusare al gol."""
    try:
        competitors = data_espn["header"]["competitions"][0]["competitors"]
    except Exception:
        competitors = []
    boxscore_teams = (data_espn.get("boxscore") or {}).get("teams", [])
    fallback_kit = determina_kit(home_id, away_id, league_slug, league_name)
    result = kit_analyzer.analizza(
        home_name=home_name,
        away_name=away_name,
        home_id=home_id,
        away_id=away_id,
        league_name=league_name,
        competitors=competitors,
        boxscore_teams=boxscore_teams,
        fallback_kit=fallback_kit,
    )
    return result["kit"] if result["kit"] in ("home", "away", "third") else fallback_kit
