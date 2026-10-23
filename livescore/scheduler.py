#!/usr/bin/env python3
"""
Scheduler check per LiveScore_JR.

Interroga i feed ESPN delle competizioni di Juventus e Italia e verifica se
c'è una partita il cui kickoff cade entro la finestra di dispatch.

Il bot principale viene avviato esclusivamente quando viene trovata davvero
una partita di una squadra monitorata nella finestra prevista e la partita
non risulta già conclusa secondo ESPN. Se più squadre sono nella finestra,
vince la prima della lista MONITORED_TEAMS (la Juventus ha sempre priorità).
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


JUVENTUS_TEAM_ID = "111"
ITALY_TEAM_ID = "162"

# ESPN indicizza gli eventi secondo l'orario US Eastern.
# Manteniamo lo scheduler allineato al criterio usato dal bot principale.
ESPN_TZ = ZoneInfo("America/New_York")

CLUB_LEAGUES = [
    "ita.1",                      # Serie A
    "ita.coppa_italia",           # Coppa Italia
    "ita.super_cup",              # Supercoppa Italiana
    "uefa.champions",             # Champions League
    "uefa.champions_qual",        # Champions League - qualificazioni
    "uefa.europa",                # Europa League
    "uefa.europa_qual",           # Europa League - qualificazioni
    "uefa.europa.conf",           # Conference League
    "uefa.europa.conf_qual",      # Conference League - qualificazioni
    "uefa.super_cup",             # Supercoppa UEFA
    "fifa.cwc",                   # Mondiale per Club FIFA
    "fifa.intercontinental_cup",  # Coppa Intercontinentale FIFA
    "club.friendly",              # Amichevoli
]

NATIONAL_LEAGUES = [
    "fifa.world",                 # Mondiali
    "fifa.worldq.uefa",           # Qualificazioni Mondiali UEFA
    "fifa.wcq.ply",               # Spareggi Mondiali
    "uefa.euro",                  # Europei
    "uefa.euroq",                 # Qualificazioni Europei
    "uefa.nations",               # Nations League
    "fifa.friendly",              # Amichevoli internazionali
]

# Squadre monitorate, in ordine di priorita' (la prima vince).
# label = valore dell'opzione 'team_id' di main_espn.yml.
MONITORED_TEAMS = [
    {"id": JUVENTUS_TEAM_ID, "name": "Juventus", "label": "Juventus",
     "leagues": CLUB_LEAGUES},
    {"id": ITALY_TEAM_ID, "name": "Italia", "label": "Italia",
     "leagues": NATIONAL_LEAGUES},
]

# Il controllo esterno gira ogni 30 minuti.
# Il bot viene avviato quando il kickoff è entro 60 minuti.
DISPATCH_WINDOW_MIN = 60

# Recupero nel caso in cui lo scheduler parta dopo il kickoff.
RECOVERY_WINDOW_MIN = 140

SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/"
    "soccer/{league}/scoreboard?dates={date}"
)


SESSION = requests.Session()

RETRY_CONFIG = Retry(
    total=3,
    connect=3,
    read=3,
    status=3,
    backoff_factor=1,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset({"GET"}),
    raise_on_status=False,
)

SESSION.mount(
    "https://",
    HTTPAdapter(
        max_retries=RETRY_CONFIG,
        pool_maxsize=10,
    ),
)


def fetch_json(url: str) -> dict:
    """Scarica un feed JSON ESPN usando lo stesso client del bot principale."""
    response = SESSION.get(
        url,
        timeout=(5, 20),
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, dict):
        raise RuntimeError("Risposta ESPN non valida")

    return data


def parse_kickoff(value: str) -> datetime:
    """Converte il timestamp ESPN in datetime UTC."""
    if not value:
        raise ValueError("Kickoff mancante")

    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    ).astimezone(timezone.utc)


def contains_team(event: dict, team_id: str) -> bool:
    """Controlla se la squadra indicata e' presente nell'evento."""
    for competition in event.get("competitions") or []:
        for competitor in competition.get("competitors") or []:
            found = str(
                competitor.get("team", {}).get("id", "")
            )

            if found == str(team_id):
                return True

    return False


def is_match_finished(event: dict) -> bool:
    """
    Controlla se ESPN considera la partita già conclusa.

    ESPN normalmente espone:
        event.status.type.completed
        event.status.type.state

    Viene controllato anche competition.status come fallback.
    """
    statuses = [event.get("status") or {}]

    for competition in event.get("competitions") or []:
        statuses.append(
            competition.get("status") or {}
        )

    for status in statuses:
        status_type = status.get("type") or {}

        completed = status_type.get("completed")

        if completed is True:
            return True

        if str(completed).strip().lower() == "true":
            return True

        state = str(
            status_type.get("state") or ""
        ).strip().lower()

        if state == "post":
            return True

    return False


def get_match_status(event: dict) -> tuple[str, bool, str]:
    """
    Restituisce informazioni sullo stato ESPN per il log.

    Returns:
        (state, completed, description)
    """
    status = event.get("status") or {}
    status_type = status.get("type") or {}

    state = str(
        status_type.get("state") or ""
    ).strip()

    completed_raw = status_type.get("completed")

    completed = (
        completed_raw is True
        or str(completed_raw).strip().lower() == "true"
    )

    description = str(
        status_type.get("description")
        or status_type.get("detail")
        or status_type.get("name")
        or ""
    ).strip()

    return state, completed, description


def find_team_matches():
    """
    Cerca la prossima partita di ogni squadra monitorata usando le stesse date
    ESPN del bot principale: oggi e domani secondo il fuso US Eastern.

    Restituisce:
        {team_id: (kickoff, evento, lega)} solo per le squadre con una partita.
    """
    now_espn = datetime.now(ESPN_TZ)

    dates_to_try = [
        now_espn.strftime("%Y%m%d"),
        (now_espn + timedelta(days=1)).strftime("%Y%m%d"),
    ]

    # Ogni feed viene scaricato una sola volta anche se condiviso.
    leagues_to_fetch = []
    for team in MONITORED_TEAMS:
        for league in team["leagues"]:
            if league not in leagues_to_fetch:
                leagues_to_fetch.append(league)

    best = {}

    successful_feeds = 0
    failed_feeds = []

    for date in dates_to_try:
        for league in leagues_to_fetch:
            url = SCOREBOARD_URL.format(
                league=league,
                date=date,
            )

            try:
                data = fetch_json(url)
                successful_feeds += 1

            except requests.RequestException as exc:
                failed_feeds.append(f"{league}@{date}")

                print(
                    f"[warn] feed {league} ({date}) non raggiungibile: {exc}",
                    file=sys.stderr,
                )
                continue

            except Exception as exc:
                failed_feeds.append(f"{league}@{date}")

                print(
                    f"[warn] feed {league} ({date}) non valido: {exc}",
                    file=sys.stderr,
                )
                continue

            for event in data.get("events") or []:
                for team in MONITORED_TEAMS:
                    if league not in team["leagues"]:
                        continue

                    if not contains_team(event, team["id"]):
                        continue

                    try:
                        kickoff = parse_kickoff(
                            str(event.get("date", ""))
                        )
                    except (TypeError, ValueError) as exc:
                        print(
                            f"[warn] kickoff non valido in {league}: {exc}",
                            file=sys.stderr,
                        )
                        continue

                    current = best.get(team["id"])

                    if current is None or kickoff < current[0]:
                        best[team["id"]] = (
                            kickoff,
                            event,
                            league,
                        )

    total_feeds = len(leagues_to_fetch) * len(dates_to_try)

    print(
        f"Feed ESPN raggiungibili: "
        f"{successful_feeds}/{total_feeds}"
    )

    if failed_feeds:
        print(
            "Feed non raggiungibili: "
            + ", ".join(failed_feeds),
            file=sys.stderr,
        )

    # Se nessun feed ha funzionato, il controllo è fallito.
    # Non si avvia il bot principale.
    if successful_feeds == 0:
        raise RuntimeError(
            "Impossibile controllare le partite: "
            "tutti i feed ESPN sono irraggiungibili"
        )

    return best


def evaluate_match(kickoff: datetime, event: dict, now: datetime):
    """Restituisce (should_dispatch, minuti_al_kickoff, match_finished)."""
    minutes_to_kickoff = (kickoff - now).total_seconds() / 60

    match_finished = is_match_finished(event)

    should_dispatch = (
        not match_finished
        and -RECOVERY_WINDOW_MIN
        <= minutes_to_kickoff
        <= DISPATCH_WINDOW_MIN
    )

    return should_dispatch, minutes_to_kickoff, match_finished


def choose_match(matches: dict, now: datetime):
    """
    Sceglie la partita da gestire.

    Priorita': la prima squadra di MONITORED_TEAMS che e' nella finestra di
    avvio. Se nessuna lo e', si riporta quella con il kickoff piu' vicino
    (solo per il log, senza dispatch).

    Restituisce (team, kickoff, event, league) oppure None.
    """
    for team in MONITORED_TEAMS:
        found = matches.get(team["id"])

        if found is None:
            continue

        kickoff, event, league = found

        should_dispatch, _, _ = evaluate_match(kickoff, event, now)

        if should_dispatch:
            return team, kickoff, event, league

    candidates = [
        (matches[team["id"]][0], team, matches[team["id"]])
        for team in MONITORED_TEAMS
        if team["id"] in matches
    ]

    if not candidates:
        return None

    _, team, (kickoff, event, league) = min(
        candidates, key=lambda item: item[0]
    )

    return team, kickoff, event, league


def write_output(name: str, value: str) -> None:
    """Scrive un output utilizzabile dal workflow GitHub Actions."""
    github_output = os.environ.get("GITHUB_OUTPUT")

    if not github_output:
        print(f"{name}={value}")
        return

    with open(
        github_output,
        "a",
        encoding="utf-8",
    ) as file:
        file.write(f"{name}={value}\n")


def main() -> None:
    now = datetime.now(timezone.utc)

    chosen = choose_match(find_team_matches(), now)

    if chosen is None:
        print("Nessuna partita delle squadre monitorate trovata.")

        write_output("dispatch", "false")
        write_output("kickoff", "")
        write_output("match_name", "")
        write_output("league", "")
        write_output("team_id", "")
        write_output("team_choice", "")
        return

    team, kickoff, event, league = chosen

    should_dispatch, minutes_to_kickoff, match_finished = evaluate_match(
        kickoff, event, now
    )

    match_name = str(
        event.get("name") or f"Partita {team['name']}"
    )

    state, completed, status_description = get_match_status(event)

    print(f"Trovata partita ({team['name']}): {match_name} [{league}]")
    print(f"Kickoff UTC: {kickoff.isoformat()}")
    print(f"Minuti al kickoff: {minutes_to_kickoff:.1f}")

    print(
        "Stato ESPN: "
        f"state={state or 'N/A'}, "
        f"completed={completed}, "
        f"description={status_description or 'N/A'}"
    )

    write_output(
        "dispatch",
        "true" if should_dispatch else "false",
    )

    write_output(
        "kickoff",
        kickoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    write_output("match_name", match_name)
    write_output("league", league)
    write_output("team_id", team["id"])
    write_output("team_choice", team["label"])

    if match_finished:
        print(
            "Partita già conclusa secondo ESPN: "
            "il bot LiveScore NON viene avviato."
        )

    elif should_dispatch:
        print(
            "Partita nella finestra prevista e ancora attiva: "
            "avvio del bot LiveScore."
        )

    else:
        print(
            "Partita trovata, ma fuori dalla finestra "
            "di avvio."
        )


if __name__ == "__main__":
    main()
