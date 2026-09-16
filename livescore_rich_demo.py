#!/usr/bin/env python3
"""Demo di 5 minuti del LiveScore JR in formato Telegram Rich Message.

La demo NON usa ESPN, Canva, stato partita o logiche del LiveScore reale.
Invia solo al Bot JR usando TELEGRAM_TO_BOT e simula una partita Juventus-Inter.

Variabili richieste:
    TELEGRAM_TOKEN
    TELEGRAM_TO_BOT

Uso normale:
    python -u livescore_rich_demo.py

Test rapido da terminale senza inviare nulla:
    python -u livescore_rich_demo.py --dry-run --duration 30 --tick 2
"""

from __future__ import annotations

import argparse
import html
import os
import sys
import time
from datetime import datetime
from typing import NamedTuple, Protocol

import requests

API_BASE = "https://api.telegram.org"
DEFAULT_DURATION_SECONDS = 300
DEFAULT_TICK_SECONDS = 10


class DemoState(NamedTuple):
    at_second: int
    status: str
    minute: str
    home_score: int
    away_score: int
    possession_home: int
    shots_home: int
    shots_away: int
    shots_on_target_home: int
    shots_on_target_away: int
    corners_home: int
    corners_away: int
    latest_event: str
    event_log: tuple[str, ...]
    event_key: str = ""


class Transport(Protocol):
    def post(self, method: str, payload: dict) -> dict | bool | None:
        ...


def resolve_chat_id() -> str:
    """Usa esclusivamente il target Bot JR per evitare invii al canale reale."""
    chat_id = (os.getenv("TELEGRAM_TO_BOT") or "").strip()
    if not chat_id:
        raise RuntimeError(
            "TELEGRAM_TO_BOT mancante. La demo rifiuta volutamente di usare "
            "TELEGRAM_TO per non rischiare invii sul canale principale."
        )
    return chat_id


def resolve_token() -> str:
    token = (os.getenv("TELEGRAM_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_TOKEN mancante.")
    return token


def _scale(second: int, duration: int) -> int:
    if duration <= 0:
        raise ValueError("duration deve essere maggiore di zero")
    return min(duration, max(0, round(second * duration / DEFAULT_DURATION_SECONDS)))


def demo_timeline(duration: int = DEFAULT_DURATION_SECONDS) -> list[DemoState]:
    """Storyboard compresso di una partita completa in circa 5 minuti."""
    raw = [
        DemoState(
            0, "PRE MATCH", "-", 0, 0,
            50, 0, 0, 0, 0, 0, 0,
            "Le squadre stanno entrando in campo.",
            (),
            "",
        ),
        DemoState(
            15, "1° TEMPO", "1'", 0, 0,
            51, 1, 0, 0, 0, 0, 0,
            "▶️ Calcio d'inizio.",
            ("1' ▶️ Calcio d'inizio",),
            "kickoff",
        ),
        DemoState(
            45, "1° TEMPO", "12'", 0, 0,
            53, 3, 2, 1, 0, 1, 0,
            "🟨 12' Locatelli ammonito.",
            (
                "1' ▶️ Calcio d'inizio",
                "12' 🟨 Locatelli ammonito",
            ),
            "yellow_home",
        ),
        DemoState(
            75, "1° TEMPO", "23'", 1, 0,
            55, 6, 3, 3, 1, 2, 1,
            "⚽️ 23' Yildiz. Assist: K. Thuram.",
            (
                "1' ▶️ Calcio d'inizio",
                "12' 🟨 Locatelli ammonito",
                "23' ⚽️ Yildiz, assist K. Thuram",
            ),
            "goal_home_1",
        ),
        DemoState(
            105, "1° TEMPO", "35'", 1, 0,
            54, 8, 5, 3, 2, 3, 2,
            "🧤 34' Di Gregorio salva su Lautaro.",
            (
                "1' ▶️ Calcio d'inizio",
                "12' 🟨 Locatelli ammonito",
                "23' ⚽️ Yildiz, assist K. Thuram",
                "34' 🧤 Parata Di Gregorio",
            ),
            "save_home",
        ),
        DemoState(
            135, "HALF TIME", "45'", 1, 0,
            53, 9, 6, 4, 2, 4, 2,
            "⏸ Fine primo tempo.",
            (
                "12' 🟨 Locatelli ammonito",
                "23' ⚽️ Yildiz, assist K. Thuram",
                "34' 🧤 Parata Di Gregorio",
                "45' ⏸ Fine primo tempo",
            ),
            "halftime",
        ),
        DemoState(
            160, "2° TEMPO", "46'", 1, 0,
            52, 9, 6, 4, 2, 4, 2,
            "▶️ Inizia il secondo tempo.",
            (
                "23' ⚽️ Yildiz, assist K. Thuram",
                "34' 🧤 Parata Di Gregorio",
                "45' ⏸ Fine primo tempo",
                "46' ▶️ Inizia il secondo tempo",
            ),
            "second_half",
        ),
        DemoState(
            195, "2° TEMPO", "58'", 1, 0,
            51, 11, 8, 4, 3, 5, 3,
            "🔄 58' McKennie entra per Koopmeiners.",
            (
                "45' ⏸ Fine primo tempo",
                "46' ▶️ Inizia il secondo tempo",
                "58' 🔄 McKennie ⇢ Koopmeiners",
            ),
            "substitution",
        ),
        DemoState(
            225, "2° TEMPO", "67'", 1, 1,
            50, 12, 10, 4, 4, 5, 4,
            "⚽️ 67' Lautaro Martinez pareggia.",
            (
                "46' ▶️ Inizia il secondo tempo",
                "58' 🔄 McKennie ⇢ Koopmeiners",
                "67' ⚽️ Lautaro Martinez",
            ),
            "goal_away",
        ),
        DemoState(
            255, "2° TEMPO", "78'", 2, 1,
            52, 15, 11, 6, 4, 7, 4,
            "⚽️ 78' Jonathan David. Assist: Yildiz.",
            (
                "58' 🔄 McKennie ⇢ Koopmeiners",
                "67' ⚽️ Lautaro Martinez",
                "78' ⚽️ Jonathan David, assist Yildiz",
            ),
            "goal_home_2",
        ),
        DemoState(
            285, "FULL TIME", "90+4'", 2, 1,
            52, 16, 12, 7, 4, 7, 5,
            "🏁 Fine partita.",
            (
                "67' ⚽️ Lautaro Martinez",
                "78' ⚽️ Jonathan David, assist Yildiz",
                "90+4' 🏁 Fine partita",
            ),
            "fulltime",
        ),
    ]

    scaled: list[DemoState] = []
    last_second = -1
    for state in raw:
        second = _scale(state.at_second, duration)
        if second <= last_second:
            second = min(duration, last_second + 1)
        last_second = second
        scaled.append(state._replace(at_second=second))

    if scaled[-1].at_second > duration:
        scaled[-1] = scaled[-1]._replace(at_second=duration)
    return scaled


def _esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def _score(state: DemoState) -> str:
    return f"JUVENTUS {state.home_score} – {state.away_score} INTER"


def _stats_table(state: DemoState) -> str:
    possession_away = 100 - state.possession_home
    return (
        '<table bordered striped>'
        '<caption>STATISTICHE LIVE</caption>'
        '<tr><th align="left">Dato</th><th align="center">JUV</th><th align="center">INT</th></tr>'
        f'<tr><td>Possesso</td><td align="center">{state.possession_home}%</td>'
        f'<td align="center">{possession_away}%</td></tr>'
        f'<tr><td>Tiri</td><td align="center">{state.shots_home}</td>'
        f'<td align="center">{state.shots_away}</td></tr>'
        f'<tr><td>In porta</td><td align="center">{state.shots_on_target_home}</td>'
        f'<td align="center">{state.shots_on_target_away}</td></tr>'
        f'<tr><td>Corner</td><td align="center">{state.corners_home}</td>'
        f'<td align="center">{state.corners_away}</td></tr>'
        '</table>'
    )


def _events_details(state: DemoState) -> str:
    if not state.event_log:
        body = '<p>Nessun evento ancora.</p>'
    else:
        items = ''.join(f'<li>{_esc(item)}</li>' for item in state.event_log)
        body = f'<ul>{items}</ul>'
    return f'<details><summary>CRONOLOGIA EVENTI</summary>{body}</details>'


def build_match_center_html(state: DemoState, *, elapsed_seconds: int) -> str:
    """Messaggio principale che in produzione verrebbe aggiornato in-place."""
    elapsed_seconds = max(0, elapsed_seconds)
    elapsed_min, elapsed_sec = divmod(elapsed_seconds, 60)
    now = datetime.now().strftime("%H:%M:%S")

    if state.status == "PRE MATCH":
        minute_line = "Calcio d'inizio tra pochi istanti"
    elif state.status == "HALF TIME":
        minute_line = "INTERVALLO"
    elif state.status == "FULL TIME":
        minute_line = "FINALE"
    else:
        minute_line = f"{_esc(state.minute)} • {_esc(state.status)}"

    return (
        '<h2>🇮🇹 SERIE A • LIVE DEMO</h2>'
        f'<h1>{_score(state)}</h1>'
        f'<h3>{minute_line}</h3>'
        '<hr/>'
        f'{_stats_table(state)}'
        '<h4>ULTIMO EVENTO</h4>'
        f'<p>{_esc(state.latest_event)}</p>'
        f'{_events_details(state)}'
        '<footer>'
        f'Match Center JR • demo {elapsed_min:02d}:{elapsed_sec:02d} • aggiornato {now}'
        '</footer>'
    )


def build_event_html(state: DemoState) -> str:
    """Card Rich separata per gli eventi che meritano una notifica."""
    key = state.event_key
    score = _score(state)

    if key == "kickoff":
        return (
            '<h2>▶️ KICK OFF</h2>'
            '<h1>JUVENTUS – INTER</h1>'
            '<p>È iniziata la partita.</p>'
            '<footer>LiveScore JR • Rich Message demo</footer>'
        )

    if key == "yellow_home":
        return (
            '<h2>🟨 AMMONIZIONE JUVENTUS</h2>'
            '<h1>MANUEL LOCATELLI</h1>'
            '<p>12\' • Cartellino giallo.</p>'
            f'<p><mark>{score}</mark></p>'
            '<footer>LiveScore JR • evento live</footer>'
        )

    if key == "goal_home_1":
        return (
            '<h2>⚽️ GOOOOOOOL JUVENTUS</h2>'
            '<h1>Kenan Yildiz</h1>'
            f'<p><mark>{score}</mark></p>'
            '<p>23\' • Assist: Khephren Thuram</p>'
            '<footer>LiveScore JR • evento live</footer>'
        )

    if key == "save_home":
        return (
            '<h2>🧤 PARATA JUVENTUS</h2>'
            '<h1>MICHELE DI GREGORIO</h1>'
            '<p>34\' • Salva il risultato su Lautaro Martinez.</p>'
            f'<p><mark>{score}</mark></p>'
            '<footer>LiveScore JR • evento live</footer>'
        )

    if key == "halftime":
        return (
            '<h2>⏸ HALF TIME</h2>'
            f'<h1>{score}</h1>'
            f'{_stats_table(state)}'
            '<footer>LiveScore JR • fine primo tempo</footer>'
        )

    if key == "second_half":
        return (
            '<h2>▶️ SECOND HALF</h2>'
            f'<h1>{score}</h1>'
            '<p>Si riparte all’Allianz Stadium.</p>'
            '<footer>LiveScore JR • ripresa</footer>'
        )

    if key == "substitution":
        return (
            '<h2>🔄 SOSTITUZIONE JUVENTUS</h2>'
            '<h1>McKENNIE ⇢ KOOPMEINERS</h1>'
            '<p>58\' • Cambio bianconero.</p>'
            f'<p><mark>{score}</mark></p>'
            '<footer>LiveScore JR • evento live</footer>'
        )

    if key == "goal_away":
        return (
            '<h2>⚽️ GOL INTER</h2>'
            '<h1>LAUTARO MARTINEZ</h1>'
            f'<p><mark>{score}</mark></p>'
            '<p>67\' • Pareggio nerazzurro.</p>'
            '<footer>LiveScore JR • evento live</footer>'
        )

    if key == "goal_home_2":
        return (
            '<h2>⚽️ GOOOOOOOL JUVENTUS</h2>'
            '<h1>JONATHAN DAVID</h1>'
            f'<p><mark>{score}</mark></p>'
            '<p>78\' • Assist: Kenan Yildiz</p>'
            '<footer>LiveScore JR • evento live</footer>'
        )

    if key == "fulltime":
        return (
            '<h2>🏁 FULL TIME</h2>'
            f'<h1>{score}</h1>'
            f'{_stats_table(state)}'
            f'{_events_details(state)}'
            '<footer>LiveScore JR • partita terminata</footer>'
        )

    return (
        '<h2>ℹ️ EVENTO LIVE</h2>'
        f'<h1>{score}</h1>'
        f'<p>{_esc(state.latest_event)}</p>'
        '<footer>LiveScore JR • Rich Message demo</footer>'
    )


class RequestsTransport:
    def __init__(self, token: str) -> None:
        self.api_root = f"{API_BASE}/bot{token}"
        self.session = requests.Session()

    def post(self, method: str, payload: dict) -> dict | bool | None:
        last_error = "errore sconosciuto"
        for attempt in range(1, 4):
            try:
                response = self.session.post(
                    f"{self.api_root}/{method}",
                    json=payload,
                    timeout=30,
                )
            except requests.RequestException as exc:
                last_error = f"rete: {exc}"
                if attempt < 3:
                    time.sleep(attempt)
                    continue
                raise RuntimeError(f"Telegram {method}: {last_error}") from exc

            try:
                data = response.json()
            except ValueError as exc:
                raise RuntimeError(
                    f"Telegram {method}: risposta non JSON, HTTP {response.status_code}"
                ) from exc

            if response.ok and data.get("ok") is True:
                return data.get("result")

            description = str(data.get("description") or response.text)
            last_error = f"HTTP {response.status_code}: {description}"

            if method == "editMessageText" and "message is not modified" in description.lower():
                return {"message_id": payload.get("message_id")}

            retry_after = data.get("parameters", {}).get("retry_after")
            retryable = response.status_code in {429, 500, 502, 503, 504}
            if retryable and attempt < 3:
                try:
                    delay = max(float(retry_after), 1.0)
                except (TypeError, ValueError):
                    delay = float(attempt)
                time.sleep(delay)
                continue

            raise RuntimeError(f"Telegram {method}: {last_error}")

        raise RuntimeError(f"Telegram {method}: {last_error}")


class DryRunTransport:
    def __init__(self) -> None:
        self.next_message_id = 1000

    def post(self, method: str, payload: dict) -> dict | bool | None:
        rich = payload.get("rich_message") or {}
        preview = rich.get("html", "") if isinstance(rich, dict) else str(rich)
        print(f"\n[DRY RUN] {method}")
        print(preview)
        if method == "sendRichMessage":
            self.next_message_id += 1
            return {"message_id": self.next_message_id}
        return {"message_id": payload.get("message_id", self.next_message_id)}


class TelegramRichClient:
    def __init__(
        self,
        token: str,
        chat_id: str,
        *,
        transport: Transport | None = None,
    ) -> None:
        self.chat_id = str(chat_id)
        self.transport = transport or RequestsTransport(token)

    def send_rich(self, rich_html: str, *, silent: bool = False) -> int:
        result = self.transport.post(
            "sendRichMessage",
            {
                "chat_id": self.chat_id,
                "rich_message": {"html": rich_html},
                "disable_notification": bool(silent),
            },
        )
        if not isinstance(result, dict) or result.get("message_id") is None:
            raise RuntimeError("sendRichMessage non ha restituito message_id")
        return int(result["message_id"])

    def edit_rich(self, message_id: int, rich_html: str) -> int:
        result = self.transport.post(
            "editMessageText",
            {
                "chat_id": self.chat_id,
                "message_id": int(message_id),
                "rich_message": {"html": rich_html},
            },
        )
        if isinstance(result, dict) and result.get("message_id") is not None:
            return int(result["message_id"])
        return int(message_id)


def _current_state(timeline: list[DemoState], elapsed: int) -> DemoState:
    state = timeline[0]
    for candidate in timeline:
        if candidate.at_second <= elapsed:
            state = candidate
        else:
            break
    return state


def _event_should_notify(key: str) -> bool:
    return bool(key)


def _event_is_silent(key: str) -> bool:
    # In una chat di test teniamo sonore solo le notifiche più importanti.
    return key not in {"goal_home_1", "goal_away", "goal_home_2", "fulltime"}


def run_demo(
    *,
    duration: int = DEFAULT_DURATION_SECONDS,
    tick: int = DEFAULT_TICK_SECONDS,
    dry_run: bool = False,
) -> None:
    if duration < 10:
        raise ValueError("La demo deve durare almeno 10 secondi.")
    if tick < 1:
        raise ValueError("tick deve essere almeno 1 secondo.")

    token = "dry-run-token" if dry_run else resolve_token()
    chat_id = "dry-run-bot-jr" if dry_run else resolve_chat_id()
    transport: Transport = DryRunTransport() if dry_run else RequestsTransport(token)
    telegram = TelegramRichClient(token, chat_id, transport=transport)
    timeline = demo_timeline(duration)

    print(
        f"Avvio demo Rich LiveScore: durata={duration}s, tick={tick}s, "
        f"target={'DRY RUN' if dry_run else 'TELEGRAM_TO_BOT'}"
    )

    center_id = telegram.send_rich(
        build_match_center_html(timeline[0], elapsed_seconds=0),
        silent=True,
    )
    print(f"Match Center creato: message_id={center_id}")

    notified: set[str] = set()
    started = time.monotonic()
    last_rendered_second = -1

    while True:
        elapsed = min(duration, int(time.monotonic() - started))
        state = _current_state(timeline, elapsed)

        if elapsed != last_rendered_second:
            telegram.edit_rich(
                center_id,
                build_match_center_html(state, elapsed_seconds=elapsed),
            )
            last_rendered_second = elapsed
            print(
                f"[{elapsed:03d}s] Match Center -> {state.status} "
                f"{state.minute} | {state.home_score}-{state.away_score}"
            )

        due_events = [
            item
            for item in timeline
            if item.at_second <= elapsed
            and _event_should_notify(item.event_key)
            and item.event_key not in notified
        ]
        for event_state in due_events:
            telegram.send_rich(
                build_event_html(event_state),
                silent=_event_is_silent(event_state.event_key),
            )
            notified.add(event_state.event_key)
            print(f"[{elapsed:03d}s] Evento Rich -> {event_state.event_key}")

        if elapsed >= duration:
            break

        sleep_for = min(tick, max(0.1, duration - elapsed))
        time.sleep(sleep_for)

    # Forza il Match Center sul frame finale, anche se la durata personalizzata
    # termina pochi secondi dopo il frame FULL TIME scalato.
    final_state = timeline[-1]
    telegram.edit_rich(
        center_id,
        build_match_center_html(final_state, elapsed_seconds=duration),
    )

    if final_state.event_key not in notified:
        telegram.send_rich(
            build_event_html(final_state),
            silent=False,
        )

    print("Demo terminata. Il Match Center resta in chat nella versione FULL TIME.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simula 5 minuti di LiveScore JR usando Telegram Rich Messages."
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=DEFAULT_DURATION_SECONDS,
        help="durata totale in secondi, default 300",
    )
    parser.add_argument(
        "--tick",
        type=int,
        default=DEFAULT_TICK_SECONDS,
        help="ogni quanti secondi aggiornare il Match Center, default 10",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="stampa i Rich Message senza inviarli a Telegram",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        run_demo(
            duration=args.duration,
            tick=args.tick,
            dry_run=args.dry_run,
        )
    except KeyboardInterrupt:
        print("Demo interrotta manualmente.")
        return 130
    except Exception as exc:
        print(f"ERRORE: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
