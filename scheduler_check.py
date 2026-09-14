#!/usr/bin/env python3
"""
Scheduler check per LiveScore_JR.

Interroga i feed ESPN delle competizioni della Juventus e verifica se oggi
c'è una partita il cui kickoff cade entro la finestra di dispatch.

Il bot principale viene avviato esclusivamente quando viene trovata davvero
una partita della Juventus nella finestra prevista e la partita non risulta
già conclusa secondo ESPN.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


JUVENTUS_TEAM_ID = "111"

# ESPN indicizza gli eventi secondo l'orario US Eastern.
# Manteniamo lo scheduler allineato al criterio usato dal bot principale.
ESPN_TZ = ZoneInfo("America/New_York")

LEAGUES = [
    "ita.1",                      # Serie A
    "ita.coppa_italia",           # Coppa Italia
    "ita.super_cup",              # Supercoppa Italiana
    "uefa.champions",             # Champions League
    "uefa.europa",                # Europa League
    "uefa.europa.conf",           # Conference League
    "uefa.super_cup",             # Supercoppa UEFA
    "fifa.cwc",                   # Mondiale per Club FIFA
    "fifa.intercontinental_cup",  # Coppa Intercontinentale FIFA
    "club.friendly",              # Amichevoli
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


def contains_juventus(event: dict) -> bool:
    """Controlla se la Juventus è presente nell'evento."""
    for competition in event.get("competitions") or []:
        for competitor in competition.get("competitors") or []:
            team_id = str(
                competitor.get("team", {}).get("id", "")
            )

            if team_id == JUVENTUS_TEAM_ID:
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


def find_juventus_match():
    """
    Cerca la prossima partita della Juventus usando le stesse date ESPN
    del bot principale: oggi e domani secondo il fuso US Eastern.

    Restituisce:
        (kickoff, evento, lega), oppure (None, None, None).
    """
    now_espn = datetime.now(ESPN_TZ)

    dates_to_try = [
        now_espn.strftime("%Y%m%d"),
        (now_espn + timedelta(days=1)).strftime("%Y%m%d"),
    ]

    best = None

    successful_feeds = 0
    failed_feeds = []

    for date in dates_to_try:
        for league in LEAGUES:
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
                if not contains_juventus(event):
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

                if best is None or kickoff < best[0]:
                    best = (
                        kickoff,
                        event,
                        league,
                    )

    total_feeds = len(LEAGUES) * len(dates_to_try)

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

    if best is None:
        return None, None, None

    return best


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
    kickoff, event, league = find_juventus_match()

    if kickoff is None:
        print("Nessuna partita della Juventus trovata.")

        write_output("dispatch", "false")
        write_output("kickoff", "")
        write_output("match_name", "")
        write_output("league", "")
        return

    now = datetime.now(timezone.utc)

    minutes_to_kickoff = (
        kickoff - now
    ).total_seconds() / 60

    match_name = str(
        event.get("name") or "Partita Juventus"
    )

    # Stato reale ESPN.
    match_finished = is_match_finished(event)

    state, completed, status_description = get_match_status(event)

    # Il bot viene avviato solo se:
    # - siamo nella finestra temporale prevista
    # - ESPN NON considera la partita conclusa
    should_dispatch = (
        not match_finished
        and -RECOVERY_WINDOW_MIN
        <= minutes_to_kickoff
        <= DISPATCH_WINDOW_MIN
    )

    print(f"Trovata partita: {match_name} [{league}]")
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
