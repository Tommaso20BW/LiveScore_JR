"""Testi dei messaggi di partita: marcatori e punteggi."""

import html

from livescore.constants import E_ASSIST, E_BALL, JUVE_ID
from livescore.core import text as txt
from livescore.graphics import goal as goal_graphics


def phase_scorers_line(events, home_id, away_id, kind):
    """FT-style scorer summary for HT and regulation end, never ET notices."""
    limits = {'half': (1, 45), 'end_of_90': (2, 90)}
    if kind not in limits:
        return ''
    period_limit, minute_limit = limits[kind]
    teams = {str(home_id): {}, str(away_id): {}}
    for event in events:
        if event.get('type') not in ('goal', 'own goal', 'penalty goal'):
            continue
        period = int(event.get('period') or 0)
        display = str(event.get('minute_disp') or event.get('minute', ''))
        if period:
            if period > period_limit:
                continue
        else:
            try:
                if int(display.split('+')[0].rstrip("'’")) > minute_limit:
                    continue
            except ValueError:
                continue
        team = str(goal_scoring_team_id(event, home_id, away_id))
        if team not in teams:
            continue
        suffix = ' (Autogol)' if event['type'] == 'own goal' else ''
        key = (txt.fmt_player(event['player_name']), suffix)
        teams[team].setdefault(key, []).append(display)
    parts = []
    for grouped in teams.values():
        entries = [', '.join(f"{minute}'" for minute in minutes) + f' {player}{suffix}'
                   for (player, suffix), minutes in grouped.items()]
        if entries:
            parts.append(', '.join(entries))
    return f"{E_BALL} <i>{' // '.join(parts)}</i>\n" if parts else ''


def goal_scoring_team_id(event: dict, home_id: str, away_id: str) -> str:
    """Restituisce la squadra a cui va assegnato il gol, invertendo l'autogol."""
    event_team_id = str(event.get("team_id", ""))
    if event.get("type") == "own goal":
        if event_team_id == str(home_id):
            return str(away_id)
        if event_team_id == str(away_id):
            return str(home_id)
    return event_team_id


def goal_player_lines(
    player_name: str,
    assist_name: str,
    goal_type: str,
    scoring_team_id: str,
) -> tuple[str, str]:
    """Formatta marcatore/assist applicando il fallback speciale solo alla Juve."""
    if not player_name:
        return "", ""

    player_text = txt.fmt_player(player_name)
    if goal_type == "own goal":
        player_text += " (Autogol)"
    elif goal_type == "penalty goal":
        player_text += " (Rig.)"

    scorer_line = f"{E_BALL} <i>{player_text}</i>\n"
    registered = goal_graphics.find_player(html.unescape(player_name)) is not None
    juventus_name_only = (
        str(scoring_team_id) == JUVE_ID
        and (goal_type == "own goal" or not registered)
    )
    if juventus_name_only:
        return scorer_line, ""

    assist_line = ""
    if assist_name and txt._norm_name(assist_name) != txt._norm_name(player_name):
        assist_line = f"{E_ASSIST} <i>{txt.fmt_player(assist_name)}</i>\n"
    return scorer_line, assist_line


def build_score_str(home_name, away_name, g_home, g_away):
    if g_home > g_away:
        return f"<b>{home_name} {g_home}</b>-{g_away} {away_name}"
    elif g_away > g_home:
        return f"{home_name} {g_home}-<b>{g_away} {away_name}</b>"
    else:
        return f"{home_name} {g_home}-{g_away} {away_name}"
