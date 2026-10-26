"""Grafiche di partita (gol, parate, fasi) e portieri."""

import html
from pathlib import Path

from livescore import settings
from livescore.constants import JUVE_ID
from livescore.core import http as net
from livescore.core import leagues
from livescore.core.log import log_line
from livescore.graphics import goal as goal_graphics
from livescore.kits import detect as kit_detect
from livescore.match import phase_photo
from livescore.telegram import api as tg


def prepara_grafica_goal(*, data_espn: dict, scorer_name: str,
                         goal_type: str, scoring_team_id: str,
                         minute: str | int, home_name: str, away_name: str,
                         home_id: str, away_id: str,
                         home_goals: int, away_goals: int,
                         league_slug: str, league_name: str,
                         event_key: str) -> goal_graphics.RenderedGoal | None:
    """Crea la card solo per un gol assegnato alla Juventus.

    I marcatori senza asset e gli autogol a favore della Juventus ricevono la
    stessa card, ma senza la sagoma del calciatore. Se manca anche il nome, il
    bot invia il testo e lo converte nella card sullo stesso message_id quando
    ESPN comunica il marcatore. Marcatori avversari e lotteria restano testuali.
    """
    if not settings.GOAL_GRAPHICS_ENABLED:
        return None
    if leagues.is_friendly_competition(league_slug, league_name):
        return None
    if (
        str(scoring_team_id) != JUVE_ID
        or goal_type not in ("goal", "penalty goal", "own goal")
        or not scorer_name
    ):
        return None
    try:
        juve_kit = kit_detect.rileva_kit_juve(
            data_espn,
            home_id,
            away_id,
            home_name,
            away_name,
            league_slug,
            league_name,
        )
        if juve_kit not in ("home", "away", "third"):
            juve_kit = "home" if str(home_id) == JUVE_ID else "away"
        rendered = goal_graphics.render_goal_card(
            scorer_name=scorer_name,
            minute=minute,
            home_name=home_name,
            away_name=away_name,
            home_id=home_id,
            away_id=away_id,
            home_goals=home_goals,
            away_goals=away_goals,
            kit=juve_kit,
            competition=league_slug,
            goal_type=goal_type,
            event_key=event_key,
        )
        rendered_name = (
            rendered.player.name if rendered.player else rendered.scorer_name
        )
        log_line(
            "DEBUG",
            "GRAPHICS",
            f"GOAL pronta | {rendered_name} | kit={rendered.kit} | "
            f"posa={rendered.pose} | sagoma={'sì' if rendered.player else 'no'}",
        )
        return rendered
    except goal_graphics.GoalGraphicUnavailable as e:
        log_line("WARN", "GRAPHICS", f"GOAL non disponibile: {e}; invio testo")
        return None
    except Exception as e:
        log_line("WARN", "GRAPHICS", f"Composizione GOAL fallita: {e}; invio testo")
        return None


def _nome_portiere_registrato(name: str) -> str:
    player = goal_graphics.find_player(html.unescape(name or ""))
    return player.name if player and player.role == "goalkeeper" else ""


def trova_portiere_juve(data_espn: dict, event_candidate: str = "") -> str:
    """Trova il portiere Juventus nei partecipanti evento o nelle formazioni ESPN."""
    direct = _nome_portiere_registrato(event_candidate)
    if direct:
        return direct

    candidates: list[tuple[int, str]] = []

    def add_candidate(entry: dict, base_priority: int) -> None:
        athlete = entry.get("athlete") or entry.get("player") or entry
        if not isinstance(athlete, dict):
            return
        name = (
            athlete.get("displayName") or athlete.get("fullName")
            or athlete.get("shortName") or ""
        )
        canonical = _nome_portiere_registrato(name)
        if not canonical:
            return
        position = entry.get("position") or athlete.get("position") or {}
        if isinstance(position, dict):
            position_text = " ".join(str(position.get(key, "")) for key in (
                "abbreviation", "name", "displayName"
            )).lower()
        else:
            position_text = str(position).lower()
        is_goalkeeper = any(token in position_text for token in (
            "gk", "goalkeeper", "portiere", "keeper"
        ))
        priority = base_priority
        if is_goalkeeper:
            priority += 30
        if entry.get("starter") is True:
            priority += 20
        if entry.get("active") is True or entry.get("didPlay") is True:
            priority += 10
        candidates.append((priority, canonical))

    # Summary ESPN: rosters[].roster[]
    for team_block in data_espn.get("rosters") or []:
        team = team_block.get("team") or {}
        if str(team.get("id", team_block.get("id", ""))) != JUVE_ID:
            continue
        for entry in team_block.get("roster") or team_block.get("athletes") or []:
            if isinstance(entry, dict):
                add_candidate(entry, 200)

    # Summary ESPN: boxscore.players[].statistics[].athletes[]
    for team_block in ((data_espn.get("boxscore") or {}).get("players") or []):
        team = team_block.get("team") or {}
        if str(team.get("id", "")) != JUVE_ID:
            continue
        for category in team_block.get("statistics") or []:
            for entry in category.get("athletes") or []:
                if isinstance(entry, dict):
                    add_candidate(entry, 100)

    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def prepara_grafica_parata_rigore(
    *,
    data_espn: dict,
    penalty_event: dict,
    goalkeeper_name: str,
    minute: str | int,
    home_name: str,
    away_name: str,
    home_id: str,
    away_id: str,
    home_goals: int,
    away_goals: int,
    event_key: str,
    league_slug: str = "",
    league_name: str = "",
) -> goal_graphics.RenderedGoal | None:
    """Crea SAVED solo per un rigore avversario realmente parato dalla Juve."""
    if not settings.GOAL_GRAPHICS_ENABLED or leagues.is_friendly_competition(
        league_slug, league_name
    ) or penalty_event.get("type") not in (
        "penalty saved", "shootout saved"
    ):
        return None
    opponent_id = away_id if str(home_id) == JUVE_ID else (
        home_id if str(away_id) == JUVE_ID else ""
    )
    if not opponent_id or str(penalty_event.get("team_id", "")) != str(opponent_id):
        return None
    if not _nome_portiere_registrato(goalkeeper_name):
        return None
    try:
        rendered = goal_graphics.render_saved_card(
            goalkeeper_name=goalkeeper_name,
            kit=kit_detect.rileva_kit_juve(data_espn, home_id, away_id, home_name, away_name,
                               league_slug, league_name),
            competition=league_slug,
            minute=minute,
            home_name=home_name,
            away_name=away_name,
            home_id=home_id,
            away_id=away_id,
            home_goals=home_goals,
            away_goals=away_goals,
            event_key=event_key,
        )
        log_line(
            "DEBUG", "GRAPHICS", f"SAVED pronta | {rendered.player.name} | posa={rendered.pose}"
        )
        return rendered
    except goal_graphics.GoalGraphicUnavailable as e:
        log_line("WARN", "GRAPHICS", f"SAVED non disponibile: {e}; invio testo")
        return None
    except Exception as e:
        log_line("WARN", "GRAPHICS", f"Composizione SAVED fallita: {e}; invio testo")
        return None


# Fasi con grafica. 'second' = inizio secondo tempo: come 'kick', senza foto.
PHASE_GRAPHIC_KINDS = ('kick', 'second', 'half', 'full', 'end_of_90')
NO_PHOTO_KINDS = ('kick', 'second')


def build_phase_graphic(*, kind, data_espn, home_id, away_id, home_name, away_name,
                        league_slug, league_name, home_goals=0, away_goals=0, shootout=None,
                        extra_time=False):
    """Compose each supported phase; HALF/END/FULL TIME use the photo confirmed in the Mini App."""
    if (not settings.GOAL_GRAPHICS_ENABLED or JUVE_ID not in (str(home_id), str(away_id))
            or leagues.is_friendly_competition(league_slug, league_name)
            or kind not in PHASE_GRAPHIC_KINDS):
        return None
    try:
        from livescore.graphics import portrait as portrait_graphics
        layers = None
        if kind not in NO_PHOTO_KINDS:
            layers = phase_photo.layers_for(kind, extra_time=extra_time, shootout=shootout)
            if layers is None:
                log_line("INFO", "GRAPHICS", f"{kind.upper()}: nessuna foto confermata; invio testo")
                return None
        kit = kit_detect.rileva_kit_juve(data_espn, home_id, away_id, home_name, away_name,
                             league_slug, league_name)
        return portrait_graphics.phase(kind=kind, home_name=home_name, away_name=away_name,
            home_id=home_id, away_id=away_id, home_goals=home_goals, away_goals=away_goals,
            kit=kit, competition=league_slug, layers=layers, shootout=shootout,
            extra_time=extra_time)
    except Exception as exc:
        log_line("WARN", "GRAPHICS", f"{kind.upper()} non disponibile: {type(exc).__name__}; invio testo")
        return None


def send_phase_message(text, **kwargs):
    photo = build_phase_graphic(**kwargs)
    eligible = (settings.GOAL_GRAPHICS_ENABLED
        and JUVE_ID in (str(kwargs['home_id']), str(kwargs['away_id']))
        and not leagues.is_friendly_competition(kwargs['league_slug'], kwargs['league_name'])
        and kwargs['kind'] in PHASE_GRAPHIC_KINDS)
    return tg._send_telegram_event_photo_get_id(text, photo, filename='phase.png',
        label=kwargs['kind'], retry_factory=(lambda: build_phase_graphic(**kwargs)) if eligible else None)[0]
