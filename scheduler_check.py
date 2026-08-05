#!/usr/bin/env python3
"""
Scheduler check per LiveScore_JR.

Interroga i feed ESPN delle competizioni della Juventus e verifica se oggi
c'è una partita il cui kickoff cade entro la finestra di dispatch.

Se trova una partita nella finestra prevista, scrive dispatch=true nel
GITHUB_OUTPUT, così il workflow può avviare il bot principale.

Se tutti i feed ESPN risultano irraggiungibili, avvia comunque il bot
principale come controllo di sicurezza.
"""

import os
import sys
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


JUVENTUS_TEAM_ID = "111"

# Competizioni ESPN da controllare.
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
    "club.friendly",              # Amichevoli di club
]

# Lo scheduler gira ogni 30 minuti.
# Con una finestra di 60 minuti, il bot parte tra 30 e 60 minuti
# prima del calcio d'inizio.
DISPATCH_WINDOW_MIN = 60

# Recupero d'emergenza per partite già iniziate.
RECOVERY_WINDOW_MIN = 140

SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/"
    "soccer/{league}/scoreboard?dates={date}"
)


# Stessa impostazione HTTP usata dal bot principale.
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
        pool_connections=10,
        pool_maxsize=10,
    ),
)

SESSION.headers.update(
    {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": "https://www.espn.com/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/127.0.0.0 Safari/537.36"
        ),
    }
)


def write_output(name: str, value: str) -> None:
    """Scrive un valore nel GITHUB_OUTPUT del workflow."""
    github_output = os.environ.get("GITHUB_OUTPUT")

    if github_output:
        with open(github_output, "a", encoding="utf-8") as file:
            file.write(f"{name}={value}\n")
    else:
        print(f"{name}={value}")


def fetch_json(url: str) -> dict:
    """Scarica e restituisce un feed JSON ESPN."""
    response = SESSION.get(
        url,
        timeout=(5, 20),
    )

    response.raise_for_status()

    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise RuntimeError(
            "ESPN ha restituito una risposta non JSON"
        ) from exc

    if not isinstance(data, dict):
        raise RuntimeError(
            f"Risposta ESPN non valida: {type(data).__name__}"
        )

    return data


def parse_kickoff(value: str) -> datetime:
    """Converte la data ESPN in datetime UTC."""
    if not value:
        raise ValueError("data kickoff mancante")

    # ESPN normalmente restituisce:
    # 2026-08-05T11:30Z
    try:
        return datetime.strptime(
            value,
            "%Y-%m-%dT%H:%MZ",
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    # Fallback per timestamp con secondi:
    # 2026-08-05T11:30:00Z
    try:
        return datetime.strptime(
            value,
            "%Y-%m-%dT%H:%M:%SZ",
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    # Fallback ISO generico.
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    ).astimezone(timezone.utc)


def event_contains_juventus(event: dict) -> bool:
    """Controlla se la Juventus è presente nell'evento ESPN."""
    competitions = event.get("competitions") or []

    for competition in competitions:
        competitors = competition.get("competitors") or []

        for competitor in competitors:
            team_id = str(
                competitor.get("team", {}).get("id", "")
            )

            if team_id == JUVENTUS_TEAM_ID:
                return True

    return False


def find_juventus_match():
    """
    Cerca la prossima partita della Juventus.

    Restituisce:
        best:
            tupla (kickoff, event, league), oppure None.
        successful_feeds:
            numero di feed letti correttamente.
        failed_feeds:
            elenco dei feed non raggiungibili.
    """
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y%m%d")

    best = None
    successful_feeds = 0
    failed_feeds = []

    for league in LEAGUES:
        url = SCOREBOARD_URL.format(
            league=league,
            date=today,
        )

        try:
            data = fetch_json(url)
            successful_feeds += 1

        except requests.exceptions.HTTPError as exc:
            status_code = (
                exc.response.status_code
                if exc.response is not None
                else "sconosciuto"
            )

            failed_feeds.append(league)

            print(
                f"[warn] feed {league} non raggiungibile: "
                f"HTTP {status_code}",
                file=sys.stderr,
            )
            continue

        except requests.exceptions.RequestException as exc:
            failed_feeds.append(league)

            print(
                f"[warn] feed {league} non raggiungibile: {exc}",
                file=sys.stderr,
            )
            continue

        except Exception as exc:
            failed_feeds.append(league)

            print(
                f"[warn] errore nel feed {league}: {exc}",
                file=sys.stderr,
            )
            continue

        events = data.get("events") or []

        for event in events:
            if not event_contains_juventus(event):
                continue

            try:
                kickoff = parse_kickoff(
                    str(event.get("date", ""))
                )
            except (ValueError, TypeError) as exc:
                print(
                    f"[warn] kickoff non valido nel feed "
                    f"{league}: {exc}",
                    file=sys.stderr,
                )
                continue

            if best is None or kickoff < best[0]:
                best = (
                    kickoff,
                    event,
                    league,
                )

    return best, successful_feeds, failed_feeds


def dispatch_fallback(failed_feeds: list[str]) -> None:
    """
    Avvia il bot principale quando lo scheduler non è riuscito
    a verificare nessun feed.
    """
    print(
        "[fallback] Tutti i feed ESPN sono irraggiungibili."
    )
    print(
        "[fallback] Avvio comunque il bot principale, "
        "che effettuerà il controllo completo."
    )
    print(
        "[fallback] Feed falliti: "
        + ", ".join(failed_feeds)
    )

    write_output("dispatch", "true")
    write_output("kickoff", "non_verificato")
    write_output(
        "match_name",
        "Controllo di sicurezza ESPN",
    )
    write_output("league", "fallback")


def main() -> None:
    best, successful_feeds, failed_feeds = (
        find_juventus_match()
    )

    print(
        f"Feed ESPN riusciti: "
        f"{successful_feeds}/{len(LEAGUES)}"
    )

    if best is None:
        # Nessun feed è stato controllato correttamente.
        # Non possiamo affermare che non ci sia una partita.
        if successful_feeds == 0:
            dispatch_fallback(failed_feeds)
            return

        # Alcuni feed hanno funzionato, altri no.
        # Lo segnaliamo chiaramente.
        if failed_feeds:
            print(
                "[warn] Controllo ESPN incompleto: "
                f"{len(failed_feeds)} feed non raggiungibili.",
                file=sys.stderr,
            )
            print(
                "[warn] Feed falliti: "
                + ", ".join(failed_feeds),
                file=sys.stderr,
            )

        print(
            "Nessuna partita della Juventus trovata "
            "nei feed ESPN disponibili."
        )

        write_output("dispatch", "false")
        write_output("kickoff", "")
        write_output("match_name", "")
        write_output("league", "")
        return

    kickoff, event, league = best

    now = datetime.now(timezone.utc)
    minutes_to_kickoff = (
        kickoff - now
    ).total_seconds() / 60

    match_name = str(
        event.get("name") or "Partita Juventus"
    )

    should_dispatch = (
        -RECOVERY_WINDOW_MIN
        <= minutes_to_kickoff
        <= DISPATCH_WINDOW_MIN
    )

    print(
        f"Trovata partita: {match_name} [{league}]"
    )
    print(
        f"Kickoff UTC: {kickoff.isoformat()}"
    )
    print(
        f"Minuti al kickoff: {minutes_to_kickoff:.1f}"
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

    if should_dispatch:
        print(
            f"Partita dentro la finestra "
            f"(-{RECOVERY_WINDOW_MIN}/"
            f"+{DISPATCH_WINDOW_MIN} minuti): "
            "avvio del bot."
        )
    else:
        print(
            "Partita trovata, ma fuori dalla "
            "finestra di avvio."
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Ultima protezione: un errore imprevisto dello scheduler
        # non deve impedire l'avvio del bot principale.
        print(
            f"[error] Errore imprevisto scheduler: {exc}",
            file=sys.stderr,
        )
        print(
            "[fallback] Avvio comunque il bot principale.",
            file=sys.stderr,
        )

        write_output("dispatch", "true")
        write_output("kickoff", "non_verificato")
        write_output(
            "match_name",
            "Errore scheduler - controllo di sicurezza",
        )
        write_output("league", "fallback")