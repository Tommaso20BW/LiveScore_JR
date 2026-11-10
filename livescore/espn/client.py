"""Chiamate HTTP verso ESPN: ricerca partita e dettaglio evento."""

import time
from datetime import datetime, timedelta

from livescore.constants import ESPN_BASE, ESPN_TZ
from livescore.core import http as net
from livescore.core import leagues
from livescore.core.log import log_line


# ==============================================================================
# ESPN API
# ==============================================================================
# ESPN (Akamai) risponde 403/429 se riceve troppe richieste ravvicinate: per questo la ricerca
# resta una richiesta alla volta e, sulle leghe della squadra, un rifiuto si ritenta.
_BUSY_STATUSES = (403, 429)
_BUSY_RETRIES = 2
_BUSY_WAIT_SECONDS = 2


def _search_order(team_id: str) -> tuple[list, int]:
    """Leghe da interrogare: prima quelle in cui gioca la squadra (le stesse dello scheduler),
    poi tutte le altre di leagues.json nell'ordine di sempre. Restituisce anche quante sono
    le prime, che meritano un nuovo tentativo se ESPN rifiuta la richiesta."""
    from livescore import scheduler

    first = []
    for team in scheduler.MONITORED_TEAMS:
        if team["id"] == team_id:
            first = [slug for slug in team["leagues"] if slug in leagues.LEAGUE_SLUGS]
    rest = [slug for slug in leagues.LEAGUE_SLUGS if slug not in first]
    return first + rest, len(first)


def _scoreboard(slug: str, date_str: str, retries: int = 0):
    """(tabellone, rifiutata): il tabellone ESPN di una lega per una data, o None se la lega
    non risponde; rifiutata=True se ESPN ha negato la richiesta (403/429) fino all'ultimo."""
    busy = False
    for attempt in range(retries + 1):
        try:
            r = net.SESSION.get(f"{ESPN_BASE}/{slug}/scoreboard", params={"dates": date_str}, timeout=10)
            busy = r.status_code in _BUSY_STATUSES
            if r.status_code == 200:
                return r.json(), False
            if not busy:
                return None, False
        except Exception:
            return None, False
        if attempt < retries:
            time.sleep(_BUSY_WAIT_SECONDS * (attempt + 1))
    return None, busy


def _match_in_scoreboard(data, slug: str, team_id: str):
    """La partita della squadra dentro un tabellone, oppure None."""
    try:
        if not data:
            return None
        league_name = data.get("leagues", [{}])[0].get("name", slug)
        for event in data.get("events", []):
            competitions = event.get("competitions", [])
            if not competitions:
                continue
            competitors = competitions[0].get("competitors", [])
            ids = [c.get("team", {}).get("id", "") for c in competitors]
            if team_id in ids:
                return {
                    "event_id":    event["id"],
                    "league_slug": slug,
                    "league_name": league_name,
                    "competitors": competitors,
                    "competition": competitions[0],
                    "date": event.get("date", ""),
                }
    except Exception:
        pass
    return None


def trova_partita_oggi(team_id: str):
    # ESPN archivia le partite secondo l'orario US Eastern, non UTC: le gare serali
    # americane (es. amichevoli "Road to 26") restano sul giorno locale anche quando
    # in UTC è gia il giorno dopo. Calcolando "oggi" sull'orologio di ESPN la partita
    # rientra sempre nella ricerca finche e in diretta — niente cuscinetto su ieri.
    now_espn      = datetime.now(ESPN_TZ)
    dates_to_try  = [
        now_espn.strftime("%Y%m%d"),                        # "oggi" secondo ESPN
        (now_espn + timedelta(days=1)).strftime("%Y%m%d"),  # "domani" secondo ESPN
    ]
    log_line("DEBUG", "ESPN", f"Ricerca partita | team_id={team_id}")

    slugs, first = _search_order(team_id)
    refused = 0
    for date_str in dates_to_try:
        for index, slug in enumerate(slugs):
            data, busy = _scoreboard(slug, date_str, retries=_BUSY_RETRIES if index < first else 0)
            refused += busy
            found = _match_in_scoreboard(data, slug, team_id)
            if found:
                return found

    if refused:
        log_line("WARN", "ESPN", f"Ricerca partita: {refused} richieste rifiutate da ESPN (403/429)")
    return None


def fetch_evento(event_id: str, league_slug: str):
    try:
        r = net.SESSION.get(f"{ESPN_BASE}/{league_slug}/summary",
                        params={"event": event_id}, timeout=15)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception as e:
        log_line("ERROR", "ESPN", f"Lettura evento fallita: {e}")
        return None
