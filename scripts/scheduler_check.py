#!/usr/bin/env python3
"""
Scheduler check per LiveScore_JR.

Interroga i feed ESPN delle competizioni della Juventus e verifica se oggi
c'e' una partita il cui kickoff cade entro la finestra di dispatch.
Se si', scrive le informazioni in GITHUB_OUTPUT cosi' che il workflow
possa lanciare il bot principale.

Logica della finestra:
  - il cron esterno (cron-job.org) gira ogni 30 minuti
  - vogliamo che il bot parta 30 minuti prima del kickoff
  - quindi dispatchiamo se il kickoff e' tra 0 e 65 minuti da adesso
    (60 = intervallo cron 30' + anticipo 30')
  - il workflow principale poi dorme fino a kickoff - 30'
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

JUVENTUS_TEAM_ID = "111"  # ID Juventus su ESPN

# Competizioni da controllare (codici lega ESPN)
LEAGUES = [
    "ita.1",                 # Serie A
    "ita.coppa_italia",      # Coppa Italia
    "ita.super_cup",         # Supercoppa Italiana
    "uefa.champions",        # Champions League
    "uefa.europa",           # Europa League
    "uefa.europa.conf",      # Conference League
    "uefa.super_cup",        # Supercoppa UEFA
    "fifa.cwc",              # Mondiale per Club FIFA
    "fifa.intercontinental", # Coppa Intercontinentale FIFA
    "club.friendly",         # Amichevoli di club
]

# Finestra di dispatch in minuti (intervallo cron + anticipo + margine)
DISPATCH_WINDOW_MIN = 60
# Quanto prima del kickoff deve partire il bot (informativo, usato dal main workflow)
LEAD_MINUTES = 30

SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard?dates={date}"
)


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "LiveScoreJR-Scheduler/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def find_juventus_match():
    """Ritorna (event, league) della prossima partita Juve di oggi, o (None, None)."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    now = datetime.now(timezone.utc)
    best = None

    for league in LEAGUES:
        url = SCOREBOARD_URL.format(league=league, date=today)
        try:
            data = fetch_json(url)
        except Exception as exc:  # feed non disponibile: si prosegue
            print(f"[warn] feed {league} non raggiungibile: {exc}", file=sys.stderr)
            continue

        for event in data.get("events", []):
            competitors = (
                event.get("competitions", [{}])[0].get("competitors", [])
            )
            if not any(
                c.get("team", {}).get("id") == JUVENTUS_TEAM_ID for c in competitors
            ):
                continue

            kickoff = datetime.strptime(event["date"], "%Y-%m-%dT%H:%MZ").replace(
                tzinfo=timezone.utc
            )
            # Ignora partite gia' iniziate da piu' di 10 minuti
            # (in quel caso e' comunque meglio partire subito: le gestiamo sotto)
            if best is None or kickoff < best[0]:
                best = (kickoff, event, league)

    if best is None:
        return None, None, None
    return best


def main():
    kickoff, event, league = find_juventus_match()
    github_output = os.environ.get("GITHUB_OUTPUT", "/dev/stdout")

    if kickoff is None:
        print("Nessuna partita della Juventus oggi.")
        with open(github_output, "a") as fh:
            fh.write("dispatch=false\n")
        return

    now = datetime.now(timezone.utc)
    minutes_to_kickoff = (kickoff - now).total_seconds() / 60

    name = event.get("name", "Juventus")
    print(f"Trovata partita: {name} [{league}]")
    print(f"Kickoff (UTC): {kickoff.isoformat()}  ->  tra {minutes_to_kickoff:.0f} minuti")

    # Dispatch se il kickoff e' entro la finestra, oppure se la partita e'
    # ancora potenzialmente in corso: recupero d'emergenza fino a 140 minuti
    # dopo il kickoff (copre recuperi lunghi; a partita davvero finita ci
    # pensa il guard interno del bot a spegnersi subito).
    should_dispatch = -140 <= minutes_to_kickoff <= DISPATCH_WINDOW_MIN

    with open(github_output, "a") as fh:
        fh.write(f"dispatch={'true' if should_dispatch else 'false'}\n")
        fh.write(f"kickoff={kickoff.strftime('%Y-%m-%dT%H:%M:%SZ')}\n")
        fh.write(f"match_name={name}\n")
        fh.write(f"league={league}\n")

    if should_dispatch:
        print(f"-> Dentro la finestra di {DISPATCH_WINDOW_MIN} min: dispatch del bot.")
    else:
        print("-> Fuori finestra: nessun dispatch per ora.")


if __name__ == "__main__":
    main()
