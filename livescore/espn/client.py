"""Chiamate HTTP verso ESPN: ricerca partita e dettaglio evento."""

from datetime import datetime, timedelta

from livescore.constants import ESPN_BASE, ESPN_TZ
from livescore.core import http as net
from livescore.core import leagues
from livescore.core.log import log_line


# ==============================================================================
# ESPN API
# ==============================================================================
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

    for date_str in dates_to_try:
        for slug in leagues.LEAGUE_SLUGS:
            url = f"{ESPN_BASE}/{slug}/scoreboard"
            try:
                r = net.SESSION.get(url, params={"dates": date_str}, timeout=10)
                if r.status_code != 200:
                    continue
                data        = r.json()
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
