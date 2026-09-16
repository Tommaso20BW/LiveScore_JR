#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
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
    chat_id = (os.getenv("TELEGRAM_TO_BOT") or "").strip()
    if not chat_id:
        raise RuntimeError("TELEGRAM_TO_BOT mancante. La demo usa solo il Bot JR di test.")
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
    raw = [
        DemoState(0, "PRE MATCH", "-", 0, 0, 50, 0, 0, 0, 0, 0, 0, "Le squadre stanno entrando in campo.", (), ""),
        DemoState(15, "1° TEMPO", "1'", 0, 0, 51, 1, 0, 0, 0, 0, 0, "▶️ Calcio d'inizio.", ("1' ▶️ Calcio d'inizio",), "kickoff"),
        DemoState(45, "1° TEMPO", "12'", 0, 0, 53, 3, 2, 1, 0, 1, 0, "🟨 12' Manuel Locatelli ammonito.", ("1' ▶️ Calcio d'inizio", "12' 🟨 Manuel Locatelli ammonito"), "yellow_home"),
        DemoState(75, "1° TEMPO", "23'", 1, 0, 55, 6, 3, 3, 1, 2, 1, "⚽️ 23' Kenan Yildiz. Assist: K. Thuram.", ("1' ▶️ Calcio d'inizio", "12' 🟨 Manuel Locatelli ammonito", "23' ⚽️ Kenan Yildiz, assist K. Thuram"), "goal_home_1"),
        DemoState(105, "1° TEMPO", "34'", 1, 0, 54, 8, 6, 3, 3, 3, 2, "🧤 34' Guglielmo Vicario para un rigore.", ("12' 🟨 Manuel Locatelli ammonito", "23' ⚽️ Kenan Yildiz, assist K. Thuram", "34' 🧤 Rigore parato da Guglielmo Vicario"), "saved_penalty"),
        DemoState(135, "HALF TIME", "45'", 1, 0, 53, 9, 7, 4, 3, 4, 2, "⏸ Fine primo tempo.", ("23' ⚽️ Kenan Yildiz, assist K. Thuram", "34' 🧤 Rigore parato da Guglielmo Vicario", "45' ⏸ Fine primo tempo"), "halftime"),
        DemoState(160, "2° TEMPO", "46'", 1, 0, 52, 9, 7, 4, 3, 4, 2, "▶️ Inizia il secondo tempo.", ("34' 🧤 Rigore parato da Guglielmo Vicario", "45' ⏸ Fine primo tempo", "46' ▶️ Inizia il secondo tempo"), "second_half"),
        DemoState(195, "2° TEMPO", "58'", 1, 0, 51, 11, 9, 4, 3, 5, 3, "🔄 58' Weston McKennie entra per Koopmeiners.", ("45' ⏸ Fine primo tempo", "46' ▶️ Inizia il secondo tempo", "58' 🔄 McKennie ↔ Koopmeiners"), "substitution"),
        DemoState(225, "2° TEMPO", "67'", 1, 1, 50, 12, 11, 4, 5, 5, 4, "⚽️ 67' Lautaro Martinez pareggia.", ("46' ▶️ Inizia il secondo tempo", "58' 🔄 McKennie ↔ Koopmeiners", "67' ⚽️ Lautaro Martinez"), "goal_away"),
        DemoState(255, "2° TEMPO", "78'", 2, 1, 52, 15, 11, 7, 5, 6, 4, "⚽️ 78' Randal Kolo Muani. Assist: Kenan Yildiz.", ("58' 🔄 McKennie ↔ Koopmeiners", "67' ⚽️ Lautaro Martinez", "78' ⚽️ Randal Kolo Muani, assist Kenan Yildiz"), "goal_home_2"),
        DemoState(300, "FULL TIME", "90'", 2, 1, 51, 17, 12, 7, 5, 7, 4, "🏁 Fine partita.", ("67' ⚽️ Lautaro Martinez", "78' ⚽️ Randal Kolo Muani, assist Kenan Yildiz", "90' 🏁 Fine partita"), "fulltime"),
    ]
    return [DemoState(_scale(item.at_second, duration), item.status, item.minute, item.home_score, item.away_score, item.possession_home, item.shots_home, item.shots_away, item.shots_on_target_home, item.shots_on_target_away, item.corners_home, item.corners_away, item.latest_event, item.event_log, item.event_key) for item in raw]


def _esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def _score_text(state: DemoState) -> str:
    return f"{HOME_NAME} {state.home_score}-{state.away_score} {AWAY_NAME}"


def _phase_text(state: DemoState) -> str:
    if state.status == "PRE MATCH":
        return state.status
    if state.minute and state.minute != "-":
        return f"{state.status} • {state.minute}"
    return state.status


def _event_should_notify(key: str) -> bool:
    return bool(key)


def _event_is_silent(key: str) -> bool:
    return key not in {"goal_home_1", "saved_penalty", "goal_away", "goal_home_2", "fulltime"}


def _paragraph(text: str, *, bold: bool = False) -> str:
    content = _esc(text)
    if bold:
        content = f"<b>{content}</b>"
    return f"<p>{content}</p>"


def build_match_center_html(state: DemoState, *, elapsed_seconds: int) -> str:
    elapsed_seconds = max(0, elapsed_seconds)
    elapsed_min, elapsed_sec = divmod(elapsed_seconds, 60)
    updated_at = datetime.now().strftime("%H:%M:%S")
    parts: list[str] = []
    parts.append(_paragraph(_score_text(state), bold=True))
    parts.append(_paragraph(_phase_text(state)))
    parts.append(_paragraph(state.latest_event))
    if state.event_log:
        parts.append("<blockquote>")
        for idx, row in enumerate(state.event_log[-3:]):
            if idx:
                parts.append("<br/>")
            parts.append(_esc(row))
        parts.append("</blockquote>")
    parts.append(f"<footer>LiveScore JR • demo {elapsed_min:02d}:{elapsed_sec:02d} • aggiornato {updated_at}</footer>")
    return "".join(parts)


def build_event_html(state: DemoState, *, include_graphic: bool = False) -> str:
    parts: list[str] = []
    if include_graphic:
        parts.append(GRAPHIC_SLOT)
    parts.append(_paragraph(state.latest_event, bold=True))
    parts.append(_paragraph(_score_text(state)))
    parts.append(_paragraph(_phase_text(state)))
    return "".join(parts)


class RealGraphicRenderer:
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

    def render_stats(self, state: DemoState, phase: str) -> bytes:
        import stats_graphics
        rows = [
            ("POSSESSO", f"{state.possession_home}%", f"{100 - state.possession_home}%"),
            ("xG", "1.32" if phase == "HT" else "2.11", "0.58" if phase == "HT" else "0.96"),
            ("TIRI", str(state.shots_home), str(state.shots_away)),
            ("TIRI IN PORTA", str(state.shots_on_target_home), str(state.shots_on_target_away)),
            ("CORNER", str(state.corners_home), str(state.corners_away)),
            ("FALLI", "6" if phase == "HT" else "11", "5" if phase == "HT" else "9"),
            ("FUORIGIOCO", "1", "0"),
            ("AMMONITI", "1", "0"),
            ("ESPULSI", "0", "0"),
            ("PARATE", "3" if phase == "HT" else "4", "5" if phase == "HT" else "6"),
            ("PRECISIONE PASSAGGI", "88%", "84%"),
            ("PASSAGGI", "271" if phase == "HT" else "463", "249" if phase == "HT" else "401"),
        ]
        html_doc = stats_graphics.build_html(
            rows=rows,
            kit=KIT,
            competition=COMPETITION,
            league_name=LEAGUE_NAME,
            momento=phase,
            home_id=HOME_ID,
            away_id=AWAY_ID,
            home_name=HOME_NAME,
            away_name=AWAY_NAME,
        )
        path = stats_graphics.render(html_doc, hd_output=True)
        return Path(path).read_bytes()


class DryRunGraphicRenderer:
    def render_goal(self, state: DemoState) -> bytes:
        return f"PNG DEMO GOAL {state.event_key}".encode("utf-8")

    def render_saved(self, state: DemoState) -> bytes:
        return b"PNG DEMO SAVED"

    def render_stats(self, state: DemoState, phase: str) -> bytes:
        return f"PNG DEMO STATS {phase}".encode("utf-8")


def graphic_kind_for_event(event_key: str) -> str | None:
    return {
        "goal_home_1": "goal",
        "goal_home_2": "goal",
        "saved_penalty": "saved",
        "halftime": "stats_ht",
        "fulltime": "stats_ft",
    }.get(event_key)


def render_event_graphic(state: DemoState, renderer) -> tuple[bytes, str] | None:
    kind = graphic_kind_for_event(state.event_key)
    if kind is None:
        return None
    if kind == "goal":
        return renderer.render_goal(state), f"{state.event_key}.png"
    if kind == "saved":
        return renderer.render_saved(state), f"{state.event_key}.png"
    if kind == "stats_ht":
        return renderer.render_stats(state, "HT"), "halftime_stats.png"
    if kind == "stats_ft":
        return renderer.render_stats(state, "FT"), "fulltime_stats.png"
    return None


class RequestsTransport:
    def __init__(self, token: str) -> None:
        self.base = f"{API_BASE}/bot{token}"

    def post(self, method: str, payload: dict, files: dict[str, tuple[str, bytes, str]] | None = None) -> dict | bool | None:
        url = f"{self.base}/{method}"
        data = payload.copy()
        if "rich_message" in data and isinstance(data["rich_message"], dict):
            data["rich_message"] = json.dumps(data["rich_message"], ensure_ascii=False)
        last_error = "Errore sconosciuto"
        for attempt in range(1, 4):
            response = requests.post(url, data=data, files=files, timeout=60)
            try:
                payload_json = response.json()
            except ValueError:
                payload_json = {"ok": False, "description": response.text}
            if payload_json.get("ok"):
                return payload_json.get("result")
            description = payload_json.get("description", f"HTTP {response.status_code}")
            last_error = description
            if method == "editMessageText" and "message is not modified" in description.lower():
                return {"message_id": payload.get("message_id")}
            retry_after = payload_json.get("parameters", {}).get("retry_after")
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

    def post(self, method: str, payload: dict, files: dict[str, tuple[str, bytes, str]] | None = None) -> dict | bool | None:
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
    def __init__(self, token: str, chat_id: str, *, transport: Transport | None = None) -> None:
        self.chat_id = str(chat_id)
        self.transport = transport or RequestsTransport(token)

    @staticmethod
    def _message_id(result: dict | bool | None, method: str) -> int:
        if not isinstance(result, dict) or result.get("message_id") is None:
            raise RuntimeError(f"{method} non ha restituito message_id")
        return int(result["message_id"])

    def send_rich(self, rich_html: str, *, silent: bool = False) -> int:
        result = self.transport.post("sendRichMessage", {"chat_id": self.chat_id, "rich_message": {"html": rich_html}, "disable_notification": bool(silent)})
        return self._message_id(result, "sendRichMessage")

    def send_rich_photo(self, rich_html: str, photo_bytes: bytes, *, filename: str = "graphic.png", silent: bool = False) -> int:
        if not photo_bytes:
            raise ValueError("La grafica PNG non può essere vuota.")
        image_tag = f'<img src="tg://photo?id={GRAPHIC_MEDIA_ID}"/>'
        if GRAPHIC_SLOT in rich_html:
            rich_html = rich_html.replace(GRAPHIC_SLOT, image_tag, 1)
        else:
            rich_html += image_tag
        rich_message = {
            "html": rich_html,
            "media": [{"id": GRAPHIC_MEDIA_ID, "media": {"type": "photo", "media": f"attach://{GRAPHIC_FILE_FIELD}"}}],
        }
        result = self.transport.post(
            "sendRichMessage",
            {"chat_id": self.chat_id, "rich_message": rich_message, "disable_notification": bool(silent)},
            files={GRAPHIC_FILE_FIELD: (filename, photo_bytes, "image/png")},
        )
        return self._message_id(result, "sendRichMessage(media)")

    def edit_rich(self, message_id: int, rich_html: str) -> int:
        result = self.transport.post("editMessageText", {"chat_id": self.chat_id, "message_id": int(message_id), "rich_message": {"html": rich_html}})
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


def send_demo_event(telegram: TelegramRichClient, renderer, state: DemoState) -> int:
    graphic = None
    try:
        graphic = render_event_graphic(state, renderer)
    except Exception as exc:
        print(f"[GRAPHICS] {state.event_key}: grafica non disponibile ({exc}); invio solo testo.", file=sys.stderr)
    if graphic is not None:
        png, filename = graphic
        return telegram.send_rich_photo(build_event_html(state, include_graphic=True), png, filename=filename, silent=_event_is_silent(state.event_key))
    return telegram.send_rich(build_event_html(state, include_graphic=False), silent=_event_is_silent(state.event_key))


def run_demo(*, duration: int = DEFAULT_DURATION_SECONDS, tick: int = DEFAULT_TICK_SECONDS, dry_run: bool = False) -> None:
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
    print(f"Avvio demo Rich LiveScore JR: durata={duration}s tick={tick}s dry_run={dry_run}", file=sys.stderr)
    start = time.monotonic()
    state = _current_state(timeline, 0)
    match_center_id = telegram.send_rich(build_match_center_html(state, elapsed_seconds=0), silent=True)
    print(f"Match Center creato: message_id={match_center_id}", file=sys.stderr)
    sent_events: set[str] = set()
    while True:
        elapsed = min(duration, int(time.monotonic() - start))
        state = _current_state(timeline, elapsed)
        telegram.edit_rich(match_center_id, build_match_center_html(state, elapsed_seconds=elapsed))
        if state.event_key and state.event_key not in sent_events and _event_should_notify(state.event_key):
            send_demo_event(telegram, renderer, state)
            sent_events.add(state.event_key)
        if elapsed >= duration:
            break
        sleep_for = tick - ((int(time.monotonic() - start)) % tick)
        if sleep_for <= 0 or sleep_for > tick:
            sleep_for = tick
        time.sleep(sleep_for)
    print("Demo completata.", file=sys.stderr)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Demo LiveScore JR con Rich Messages.")
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION_SECONDS, help="Durata totale della demo in secondi.")
    parser.add_argument("--tick", type=int, default=DEFAULT_TICK_SECONDS, help="Intervallo di aggiornamento Match Center.")
    parser.add_argument("--dry-run", action="store_true", help="Non invia a Telegram; stampa solo i payload.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_demo(duration=args.duration, tick=args.tick, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
