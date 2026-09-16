#!/usr/bin/env python3
"""Demo di 5 minuti del LiveScore JR con Telegram Rich Messages + grafiche reali.

Questa demo e' volutamente separata dal LiveScore vero:
- NON usa ESPN;
- NON usa Canva;
- NON modifica stato partita, snapshot o scheduler;
- invia SOLO a TELEGRAM_TO_BOT;
- riusa le grafiche REALI del repository:
  * goal_graphics.render_goal_card() per i gol Juventus;
  * goal_graphics.render_saved_card() per un rigore parato;
  * stats_graphics.build_html()/render() per HALF TIME e FULL TIME.

Lo scopo e' mostrare come imposterei il LiveScore Rich in produzione:
un Match Center compatto e aggiornabile + notifiche separate dove la grafica JR
resta protagonista dentro lo stesso Rich Message.

Variabili richieste:
    TELEGRAM_TOKEN
    TELEGRAM_TO_BOT

Uso:
    python -u livescore_rich_demo.py

Test rapido senza Telegram e senza render grafici pesanti:
    python -u livescore_rich_demo.py --dry-run --duration 30 --tick 2
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import NamedTuple, Protocol

import requests

API_BASE = "https://api.telegram.org"
DEFAULT_DURATION_SECONDS = 300
DEFAULT_TICK_SECONDS = 10

HOME_NAME = "Juventus"
AWAY_NAME = "Inter"
HOME_ID = "111"
AWAY_ID = "110"
COMPETITION = "ita.1"
LEAGUE_NAME = "Serie A"
KIT = "home"

GRAPHIC_SLOT = "__JR_GRAPHIC__"
GRAPHIC_MEDIA_ID = "jr_graphic"
GRAPHIC_FILE_FIELD = "jr_graphic_file"


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
    def post(
        self,
        method: str,
        payload: dict,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> dict | bool | None:
        ...


def resolve_chat_id() -> str:
    """Usa esclusivamente Bot JR, mai il canale principale."""
    chat_id = (os.getenv("TELEGRAM_TO_BOT") or "").strip()
    if not chat_id:
        raise RuntimeError(
            "TELEGRAM_TO_BOT mancante. La demo rifiuta volutamente di usare "
            "TELEGRAM_TO per evitare invii sul canale principale."
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
    """Storyboard di una partita completa compresso in circa cinque minuti."""
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
            "🟨 12' Manuel Locatelli ammonito.",
            (
                "1' ▶️ Calcio d'inizio",
                "12' 🟨 Manuel Locatelli ammonito",
            ),
            "yellow_home",
        ),
        DemoState(
            75, "1° TEMPO", "23'", 1, 0,
            55, 6, 3, 3, 1, 2, 1,
            "⚽️ 23' Kenan Yildiz. Assist: K. Thuram.",
            (
                "1' ▶️ Calcio d'inizio",
                "12' 🟨 Manuel Locatelli ammonito",
                "23' ⚽️ Kenan Yildiz, assist K. Thuram",
            ),
            "goal_home_1",
        ),
        DemoState(
            105, "1° TEMPO", "34'", 1, 0,
            54, 8, 6, 3, 3, 3, 2,
            "🧤 34' Guglielmo Vicario para un rigore.",
            (
                "12' 🟨 Manuel Locatelli ammonito",
                "23' ⚽️ Kenan Yildiz, assist K. Thuram",
                "34' 🧤 Rigore parato da Guglielmo Vicario",
            ),
            "saved_penalty",
        ),
        DemoState(
            135, "HALF TIME", "45'", 1, 0,
            53, 9, 7, 4, 3, 4, 2,
            "⏸ Fine primo tempo.",
            (
                "23' ⚽️ Kenan Yildiz, assist K. Thuram",
                "34' 🧤 Rigore parato da Guglielmo Vicario",
                "45' ⏸ Fine primo tempo",
            ),
            "halftime",
        ),
        DemoState(
            160, "2° TEMPO", "46'", 1, 0,
            52, 9, 7, 4, 3, 4, 2,
            "▶️ Inizia il secondo tempo.",
            (
                "34' 🧤 Rigore parato da Guglielmo Vicario",
                "45' ⏸ Fine primo tempo",
                "46' ▶️ Inizia il secondo tempo",
            ),
            "second_half",
        ),
        DemoState(
            195, "2° TEMPO", "58'", 1, 0,
            51, 11, 9, 4, 3, 5, 3,
            "🔄 58' Weston McKennie entra per Koopmeiners.",
            (
                "45' ⏸ Fine primo tempo",
                "46' ▶️ Inizia il secondo tempo",
                "58' 🔄 McKennie ↔ Koopmeiners",
            ),
            "substitution",
        ),
        DemoState(
            225, "2° TEMPO", "67'", 1, 1,
            50, 12, 11, 4, 5, 5, 4,
            "⚽️ 67' Lautaro Martinez pareggia.",
            (
                "46' ▶️ Inizia il secondo tempo",
                "58' 🔄 McKennie ↔ Koopmeiners",
                "67' ⚽️ Lautaro Martinez",
            ),
            "goal_away",
        ),
        DemoState(
            255, "2° TEMPO", "78'", 2, 1,
            52, 15, 11, 6, 5, 7, 4,
            "⚽️ 78' Randal Kolo Muani. Assist: Kenan Yildiz.",
            (
                "58' 🔄 McKennie ↔ Koopmeiners",
                "67' ⚽️ Lautaro Martinez",
                "78' ⚽️ Randal Kolo Muani, assist Kenan Yildiz",
            ),
            "goal_home_2",
        ),
        DemoState(
            285, "FULL TIME", "90+4'", 2, 1,
            52, 16, 12, 7, 5, 7, 5,
            "🏁 Fine partita.",
            (
                "67' ⚽️ Lautaro Martinez",
                "78' ⚽️ Randal Kolo Muani, assist Kenan Yildiz",
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


def _minute_number(value: str) -> int:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else 0


def stats_rows_for_state(state: DemoState) -> list[tuple[str, str, str]]:
    """Dati demo nel formato atteso dalla grafica STATS reale del repository."""
    minute = min(90, max(1, _minute_number(state.minute)))
    progress = minute / 90
    away_possession = 100 - state.possession_home

    home_xg = max(0.0, 0.08 * state.shots_home + 0.16 * state.shots_on_target_home)
    away_xg = max(0.0, 0.08 * state.shots_away + 0.16 * state.shots_on_target_away)

    home_yellows = sum("🟨" in item and "Locatelli" in item for item in state.event_log)
    away_yellows = sum("🟨" in item and "Locatelli" not in item for item in state.event_log)
    home_reds = sum("🟥" in item and "Juventus" in item for item in state.event_log)
    away_reds = sum("🟥" in item and "Inter" in item for item in state.event_log)

    home_saves = max(0, state.shots_on_target_away - state.away_score)
    away_saves = max(0, state.shots_on_target_home - state.home_score)

    home_passes = round((525 * progress) * (state.possession_home / 52))
    away_passes = round((470 * progress) * (away_possession / 48))
    home_accuracy = min(93, 87 + round((state.possession_home - 50) * 0.25))
    away_accuracy = min(93, 86 + round((away_possession - 50) * 0.25))

    home_fouls = max(1, round(11 * progress))
    away_fouls = max(1, round(13 * progress))
    home_offsides = max(0, round(2 * progress))
    away_offsides = max(0, round(3 * progress))

    return [
        ("POSSESSO", f"{state.possession_home}%", f"{away_possession}%"),
        ("xG", f"{home_xg:.2f}", f"{away_xg:.2f}"),
        ("TIRI", str(state.shots_home), str(state.shots_away)),
        ("TIRI IN PORTA", str(state.shots_on_target_home), str(state.shots_on_target_away)),
        ("CORNER", str(state.corners_home), str(state.corners_away)),
        ("FALLI", str(home_fouls), str(away_fouls)),
        ("FUORIGIOCO", str(home_offsides), str(away_offsides)),
        ("AMMONITI", str(home_yellows), str(away_yellows)),
        ("ESPULSI", str(home_reds), str(away_reds)),
        ("PARATE", str(home_saves), str(away_saves)),
        ("PRECISIONE PASSAGGI", f"{home_accuracy}%", f"{away_accuracy}%"),
        ("PASSAGGI", str(home_passes), str(away_passes)),
    ]


def _events_details(state: DemoState) -> str:
    if not state.event_log:
        body = "<p>Nessun evento ancora.</p>"
    else:
        items = "".join(f"<li>{_esc(item)}</li>" for item in state.event_log)
        body = f"<ul>{items}</ul>"
    return f"<details><summary>CRONOLOGIA EVENTI</summary>{body}</details>"


def build_match_center_html(state: DemoState, *, elapsed_seconds: int) -> str:
    """Match Center volutamente sobrio: non sostituisce le grafiche JR."""
    elapsed_seconds = max(0, elapsed_seconds)
    elapsed_min, elapsed_sec = divmod(elapsed_seconds, 60)
    now = datetime.now().strftime("%H:%M:%S")

    if state.status == "PRE MATCH":
        phase = "Calcio d'inizio tra pochi istanti"
    elif state.status == "HALF TIME":
        phase = "INTERVALLO"
    elif state.status == "FULL TIME":
        phase = "FINALE"
    else:
        phase = f"{_esc(state.minute)} • {_esc(state.status)}"

    return (
        "<h3>🇮🇹 SERIE A • MATCH CENTER</h3>"
        f"<h1>{_score(state)}</h1>"
        f"<h3>{phase}</h3>"
        "<hr/>"
        f"<p>{_esc(state.latest_event)}</p>"
        f"{_events_details(state)}"
        "<footer>"
        f"LiveScore JR • demo {elapsed_min:02d}:{elapsed_sec:02d} • aggiornato {now}"
        "</footer>"
    )


def graphic_kind_for_event(event_key: str) -> str | None:
    return {
        "goal_home_1": "goal",
        "goal_home_2": "goal",
        "saved_penalty": "saved",
        "halftime": "stats_ht",
        "fulltime": "stats_ft",
    }.get(event_key)


def build_event_html(state: DemoState, *, include_graphic: bool = False) -> str:
    """Testo della notifica; se presente la grafica resta il blocco dominante."""
    key = state.event_key
    score = _score(state)
    graphic = GRAPHIC_SLOT if include_graphic else ""

    if key == "kickoff":
        return (
            "<h3>▶️ KICK OFF</h3>"
            "<h2>JUVENTUS – INTER</h2>"
            "<p>È iniziata la partita.</p>"
            "<footer>LiveScore JR</footer>"
        )

    if key == "yellow_home":
        return (
            "<h3>🟨 AMMONIZIONE JUVENTUS</h3>"
            "<p><b>Manuel Locatelli</b> • 12'</p>"
            f"<footer>{score}</footer>"
        )

    if key == "goal_home_1":
        return (
            "<h2>⚽️ GOOOOOOL JUVENTUS</h2>"
            f"{graphic}"
            "<p><b>23' • Kenan Yildiz</b><br>Assist: K. Thuram</p>"
            f"<footer>{score}</footer>"
        )

    if key == "saved_penalty":
        return (
            "<h2>🧤 RIGORE PARATO</h2>"
            f"{graphic}"
            "<p><b>34' • Guglielmo Vicario</b></p>"
            f"<footer>{score}</footer>"
        )

    if key == "halftime":
        return (
            "<h2>⏸ HALF TIME</h2>"
            f"{graphic}"
            f"<footer>{score}</footer>"
        )

    if key == "second_half":
        return (
            "<h3>▶️ SECOND HALF</h3>"
            f"<h2>{score}</h2>"
            "<p>Si riparte all’Allianz Stadium.</p>"
            "<footer>LiveScore JR</footer>"
        )

    if key == "substitution":
        return (
            "<h3>🔄 SOSTITUZIONE JUVENTUS</h3>"
            "<p>🔺 <b>Weston McKennie</b><br>🔻 Teun Koopmeiners<br>58'</p>"
            f"<footer>{score}</footer>"
        )

    if key == "goal_away":
        return (
            "<h3>⚽️ GOL INTER</h3>"
            "<p><b>67' • Lautaro Martinez</b></p>"
            f"<footer>{score}</footer>"
        )

    if key == "goal_home_2":
        return (
            "<h2>⚽️ GOOOOOOL JUVENTUS</h2>"
            f"{graphic}"
            "<p><b>78' • Randal Kolo Muani</b><br>Assist: Kenan Yildiz</p>"
            f"<footer>{score}</footer>"
        )

    if key == "fulltime":
        return (
            "<h2>🏁 FULL TIME</h2>"
            f"{graphic}"
            f"<footer>{score}</footer>"
        )

    return (
        "<h3>ℹ️ EVENTO LIVE</h3>"
        f"<p>{_esc(state.latest_event)}</p>"
        f"<footer>{score}</footer>"
    )


class RealGraphicRenderer:
    """Adapter sottile sopra le grafiche già approvate del LiveScore JR."""

    def render_goal(self, state: DemoState) -> bytes:
        import goal_graphics

        if state.event_key == "goal_home_1":
            scorer = "Kenan Yildiz"
            minute = "23"
        elif state.event_key == "goal_home_2":
            scorer = "Randal Kolo Muani"
            minute = "78"
        else:
            raise ValueError(f"Evento GOAL demo non riconosciuto: {state.event_key}")

        rendered = goal_graphics.render_goal_card(
            scorer_name=scorer,
            minute=minute,
            home_name=HOME_NAME,
            away_name=AWAY_NAME,
            home_goals=state.home_score,
            away_goals=state.away_score,
            kit=KIT,
            goal_type="goal",
            home_id=HOME_ID,
            away_id=AWAY_ID,
            event_key=f"rich-demo:{state.event_key}",
            competition=COMPETITION,
        )
        return rendered.png

    def render_saved(self, state: DemoState) -> bytes:
        import goal_graphics

        rendered = goal_graphics.render_saved_card(
            goalkeeper_name="Guglielmo Vicario",
            kit=KIT,
            minute="34",
            home_name=HOME_NAME,
            away_name=AWAY_NAME,
            home_goals=state.home_score,
            away_goals=state.away_score,
            home_id=HOME_ID,
            away_id=AWAY_ID,
            event_key="rich-demo:saved_penalty",
            competition=COMPETITION,
        )
        return rendered.png

    def render_stats(self, state: DemoState, momento: str) -> bytes:
        import stats_graphics

        rich_html = stats_graphics.build_html(
            rows=stats_rows_for_state(state),
            kit=KIT,
            competition=COMPETITION,
            league_name=LEAGUE_NAME,
            momento=momento,
            home_id=HOME_ID,
            away_id=AWAY_ID,
            home_name=HOME_NAME,
            away_name=AWAY_NAME,
        )
        target = Path(stats_graphics.render(rich_html, hd_output=True))
        try:
            return target.read_bytes()
        finally:
            shutil.rmtree(target.parent, ignore_errors=True)


class DryRunGraphicRenderer:
    def render_goal(self, state: DemoState) -> bytes:
        return b"DRY-RUN-GOAL-PNG"

    def render_saved(self, state: DemoState) -> bytes:
        return b"DRY-RUN-SAVED-PNG"

    def render_stats(self, state: DemoState, momento: str) -> bytes:
        return f"DRY-RUN-STATS-{momento}-PNG".encode()


def render_event_graphic(state: DemoState, renderer) -> tuple[bytes, str] | None:
    kind = graphic_kind_for_event(state.event_key)
    if kind == "goal":
        return renderer.render_goal(state), f"{state.event_key}.png"
    if kind == "saved":
        return renderer.render_saved(state), "saved_penalty.png"
    if kind == "stats_ht":
        return renderer.render_stats(state, "HT"), "stats_half_time.png"
    if kind == "stats_ft":
        return renderer.render_stats(state, "FT"), "stats_full_time.png"
    return None


class RequestsTransport:
    def __init__(self, token: str) -> None:
        self.api_root = f"{API_BASE}/bot{token}"
        self.session = requests.Session()

    @staticmethod
    def _multipart_data(payload: dict) -> dict[str, str]:
        result: dict[str, str] = {}
        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                result[key] = json.dumps(value, ensure_ascii=False)
            elif isinstance(value, bool):
                result[key] = "true" if value else "false"
            else:
                result[key] = str(value)
        return result

    def post(
        self,
        method: str,
        payload: dict,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> dict | bool | None:
        last_error = "errore sconosciuto"

        for attempt in range(1, 4):
            try:
                if files:
                    response = self.session.post(
                        f"{self.api_root}/{method}",
                        data=self._multipart_data(payload),
                        files=files,
                        timeout=120,
                    )
                else:
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
                time.sleep(min(delay, 30.0))
                continue

            raise RuntimeError(f"Telegram {method}: {last_error}")

        raise RuntimeError(f"Telegram {method}: {last_error}")


class DryRunTransport:
    def __init__(self) -> None:
        self.next_message_id = 1000

    def post(
        self,
        method: str,
        payload: dict,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> dict | bool | None:
        rich = payload.get("rich_message") or {}
        preview = rich.get("html", "") if isinstance(rich, dict) else str(rich)
        print(f"\n[DRY RUN] {method}")
        print(preview)
        if files:
            print("[DRY RUN] media:", ", ".join(files))
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

    @staticmethod
    def _message_id(result: dict | bool | None, method: str) -> int:
        if not isinstance(result, dict) or result.get("message_id") is None:
            raise RuntimeError(f"{method} non ha restituito message_id")
        return int(result["message_id"])

    def send_rich(self, rich_html: str, *, silent: bool = False) -> int:
        result = self.transport.post(
            "sendRichMessage",
            {
                "chat_id": self.chat_id,
                "rich_message": {"html": rich_html},
                "disable_notification": bool(silent),
            },
        )
        return self._message_id(result, "sendRichMessage")

    def send_rich_photo(
        self,
        rich_html: str,
        photo_bytes: bytes,
        *,
        filename: str = "graphic.png",
        silent: bool = False,
    ) -> int:
        if not photo_bytes:
            raise ValueError("La grafica PNG non può essere vuota.")

        image_tag = f'<img src="tg://photo?id={GRAPHIC_MEDIA_ID}"/>'
        if GRAPHIC_SLOT in rich_html:
            rich_html = rich_html.replace(GRAPHIC_SLOT, image_tag, 1)
        else:
            rich_html += image_tag

        rich_message = {
            "html": rich_html,
            "media": [
                {
                    "id": GRAPHIC_MEDIA_ID,
                    "media": {
                        "type": "photo",
                        "media": f"attach://{GRAPHIC_FILE_FIELD}",
                    },
                }
            ],
        }
        result = self.transport.post(
            "sendRichMessage",
            {
                "chat_id": self.chat_id,
                "rich_message": rich_message,
                "disable_notification": bool(silent),
            },
            files={
                GRAPHIC_FILE_FIELD: (
                    filename,
                    photo_bytes,
                    "image/png",
                )
            },
        )
        return self._message_id(result, "sendRichMessage(media)")

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
    # Eventi principali sonori; il resto resta più discreto nella chat di test.
    return key not in {
        "goal_home_1",
        "saved_penalty",
        "goal_away",
        "goal_home_2",
        "fulltime",
    }


def send_demo_event(
    telegram: TelegramRichClient,
    renderer,
    state: DemoState,
) -> int:
    """Invia la notifica mantenendo la grafica JR dentro il Rich Message."""
    graphic = None
    try:
        graphic = render_event_graphic(state, renderer)
    except Exception as exc:
        print(
            f"[GRAPHICS] {state.event_key}: grafica non disponibile ({exc}); "
            "invio Rich testuale.",
            file=sys.stderr,
        )

    if graphic is not None:
        png, filename = graphic
        return telegram.send_rich_photo(
            build_event_html(state, include_graphic=True),
            png,
            filename=filename,
            silent=_event_is_silent(state.event_key),
        )

    return telegram.send_rich(
        build_event_html(state, include_graphic=False),
        silent=_event_is_silent(state.event_key),
    )


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
    renderer = DryRunGraphicRenderer() if dry_run else RealGraphicRenderer()
    telegram = TelegramRichClient(token, chat_id, transport=transport)
    timeline = demo_timeline(duration)

    print(
        f"Avvio demo Rich LiveScore JR: durata={duration}s, tick={tick}s, "
        f"target={'DRY RUN' if dry_run else 'TELEGRAM_TO_BOT'}"
    )
    print("Grafiche: GOAL + SAVED + STATS reali del repository.")

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
            send_demo_event(telegram, renderer, event_state)
            notified.add(event_state.event_key)
            kind = graphic_kind_for_event(event_state.event_key) or "text"
            print(f"[{elapsed:03d}s] Evento -> {event_state.event_key} ({kind})")

        if elapsed >= duration:
            break

        sleep_for = min(tick, max(0.1, duration - elapsed))
        time.sleep(sleep_for)

    final_state = timeline[-1]
    telegram.edit_rich(
        center_id,
        build_match_center_html(final_state, elapsed_seconds=duration),
    )

    if final_state.event_key not in notified:
        send_demo_event(telegram, renderer, final_state)

    print("Demo terminata. Il Match Center resta in chat nella versione FULL TIME.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Simula 5 minuti di LiveScore JR con Rich Messages e grafiche "
            "GOAL/SAVED/STATS reali del repository."
        )
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
        help="simula anche le grafiche senza inviare nulla a Telegram",
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
