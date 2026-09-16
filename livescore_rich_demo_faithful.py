#!/usr/bin/env python3
"""Demo LiveScore JR con Rich Messages.

Obiettivo:
- replicare i MESSAGGI attuali del bot;
- NON cambiare il testo;
- migliorare solo la resa grafica con Rich:
  titolo più forte, eventuale immagine sotto, testo originale sotto.

Ordine visuale:
1) titolo (prima riga del messaggio originale, resa più grande)
2) immagine, se disponibile
3) corpo originale del messaggio

Per i goal prova a usare goal_graphics.py se presente.
Per le stats usa stats_graphics.py se presente.
Per il full time prova un'immagine semplice di fallback se manca Canva.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Protocol

import requests

API_BASE = "https://api.telegram.org"
DEFAULT_DURATION_SECONDS = 300

HOME_NAME = "Juventus"
AWAY_NAME = "Inter"
HOME_ID = "111"
AWAY_ID = "110"
LEAGUE_SLUG = "ita.1"
LEAGUE_EMOJI = "🇮🇹"
HASHTAG = "#JuveInter"
KIT = "home"

E_BOLT   = '⚡️'
E_FLAG   = '🏁'
E_MIC    = '🎙'
E_BALL   = '⚽️'
E_SUB    = '🔄'
E_UP     = '🔺'
E_DOWN   = '🔻'
E_RED    = '🟥'
E_PEN_OK = '✅'
E_PEN_KO = '❌'
E_ASSIST = '🅰️'
E_KICK   = '🥅'
E_EXIT   = '🔚'
E_STATS  = '📊'
E_CANCEL = '📺'

GRAPHIC_SLOT = "__JR_GRAPHIC__"
GRAPHIC_MEDIA_ID = "jr_graphic"
GRAPHIC_FILE_FIELD = "jr_graphic_file"


class Transport(Protocol):
    def post(
        self,
        method: str,
        payload: dict,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> dict | bool | None:
        ...


class RequestsTransport:
    def __init__(self, token: str) -> None:
        self.base = f"{API_BASE}/bot{token}"

    def post(
        self,
        method: str,
        payload: dict,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> dict | bool | None:
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
        self.next_message_id += 1
        return {"message_id": self.next_message_id}


def strip_html_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def split_original_message(text: str) -> tuple[str, list[str]]:
    lines = (text or "").split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    title = lines[0] if lines else ""
    body = lines[1:] if len(lines) > 1 else []
    return title, body


def build_rich_html_from_original(text: str, *, include_graphic: bool = False) -> str:
    title_line, body_lines = split_original_message(text)
    title_plain = strip_html_tags(title_line)

    parts: list[str] = []
    if title_plain:
        parts.append(f"<h3>{html.escape(title_plain, quote=False)}</h3>")

    if include_graphic:
        parts.append(GRAPHIC_SLOT)

    pending: list[str] = []
    for line in body_lines:
        if line == "":
            if pending:
                parts.append("<p>" + "<br/>".join(pending) + "</p>")
                pending = []
            else:
                parts.append("<br/>")
        else:
            pending.append(line)
    if pending:
        parts.append("<p>" + "<br/>".join(pending) + "</p>")

    return "".join(parts)


class TelegramRichClient:
    def __init__(self, token: str, chat_id: str, *, transport: Transport | None = None) -> None:
        self.chat_id = str(chat_id)
        self.transport = transport or RequestsTransport(token)

    @staticmethod
    def _message_id(result: dict | bool | None, method: str) -> int:
        if not isinstance(result, dict) or result.get("message_id") is None:
            raise RuntimeError(f"{method} non ha restituito message_id")
        return int(result["message_id"])

    def send_rich_text(self, original_text: str, *, silent: bool = False) -> int:
        result = self.transport.post(
            "sendRichMessage",
            {
                "chat_id": self.chat_id,
                "rich_message": {"html": build_rich_html_from_original(original_text, include_graphic=False)},
                "disable_notification": bool(silent),
            },
        )
        return self._message_id(result, "sendRichMessage")

    def send_rich_photo(
        self,
        original_text: str,
        photo_bytes: bytes,
        *,
        filename: str,
        silent: bool = False,
    ) -> int:
        rich_html = build_rich_html_from_original(original_text, include_graphic=True)
        image_tag = f'<img src="tg://photo?id={GRAPHIC_MEDIA_ID}"/>'
        rich_html = rich_html.replace(GRAPHIC_SLOT, image_tag, 1)

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


def ecomp() -> str:
    return LEAGUE_EMOJI


def build_score_str(home_goals: int, away_goals: int) -> str:
    return f"{HOME_NAME} {home_goals}-{away_goals} {AWAY_NAME}"


def build_goal_text(
    *,
    minute: str,
    home_goals: int,
    away_goals: int,
    scoring_team: str,
    scorer: str,
    assist: str = "",
    goal_type: str = "goal",
) -> str:
    if scoring_team == "home":
        goal_score = f"<b>{HOME_NAME} {home_goals}</b>-{away_goals} {AWAY_NAME}"
    else:
        goal_score = f"{HOME_NAME} {home_goals}-<b>{away_goals} {AWAY_NAME}</b>"

    scorer_label = scorer
    if goal_type == "own goal":
        scorer_label += " (Autogol)"
    elif goal_type == "penalty goal":
        scorer_label += " (Rig.)"

    scorer_line = f"{E_BALL} <i>{scorer_label}</i>\n"
    assist_line = f"{E_ASSIST} <i>{assist}</i>\n" if assist and assist != scorer else ""
    return f"<b>GOAL · {minute}' {E_MIC}</b>\n\n{goal_score}\n{scorer_line}{assist_line}\n{ecomp()} {HASHTAG}"


def build_start_text() -> str:
    return f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{HOME_NAME} - {AWAY_NAME}\n\n{ecomp()} {HASHTAG}"


def build_ht_text(home_goals: int, away_goals: int) -> str:
    return f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{build_score_str(home_goals, away_goals)}\n\n{ecomp()} {HASHTAG}"


def build_second_half_text(home_goals: int, away_goals: int) -> str:
    return f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n{build_score_str(home_goals, away_goals)}\n\n{ecomp()} {HASHTAG}"


def build_sub_text(minute: str, team_title: str, ins: str, outs: str) -> str:
    return (
        f"<b>CAMBIO {team_title} · {minute}' {E_SUB}</b>\n\n"
        f"{E_UP} {ins}\n"
        f"{E_DOWN} {outs}\n\n"
        f"{ecomp()} {HASHTAG}"
    )


def build_red_text(minute: str, team_name: str, player: str) -> str:
    label = f"ROSSO {team_name.upper()}"
    return (
        f"<b>{label} · {minute}' {E_RED}</b>\n\n"
        f"{E_EXIT} <i>{player}</i>\n\n"
        f"{ecomp()} {HASHTAG}"
    )


def build_fail_pen_text(minute: str, team_name: str, player: str) -> str:
    return (
        f"<b>RIGORE SBAGLIATO {team_name.upper()} · {minute}' {E_KICK}</b>\n\n"
        f"{E_PEN_KO} <i>{player}</i>\n\n"
        f"{ecomp()} {HASHTAG}"
    )


def build_ft_text(home_goals: int, away_goals: int) -> str:
    score_str = build_score_str(home_goals, away_goals)
    scorers_line = f"{E_BALL} <i>23' K. Yildiz // 67' Lautaro Martinez // 78' R. Kolo Muani</i>\n"
    return f"<b>FINE PARTITA {E_FLAG}</b>\n\n{score_str}\n{scorers_line}\n{ecomp()} {HASHTAG}"


def build_stats_caption(momento: str) -> str:
    titles = {
        "HT": f"<b>STATS PRIMO TEMPO</b> {E_STATS}",
        "FT": f"<b>STATS FINE PARTITA</b> {E_STATS}",
    }
    return f"{titles[momento]}\n\n{ecomp()} {HASHTAG}"


def render_goal_graphic(
    *,
    scorer_name: str,
    minute: str,
    home_goals: int,
    away_goals: int,
    goal_type: str = "goal",
) -> bytes | None:
    try:
        import goal_graphics
        rendered = goal_graphics.render_goal_card(
            scorer_name=scorer_name,
            minute=minute,
            home_name=HOME_NAME,
            away_name=AWAY_NAME,
            home_goals=home_goals,
            away_goals=away_goals,
            kit=KIT,
            goal_type=goal_type,
            home_id=HOME_ID,
            away_id=AWAY_ID,
            event_key=f"rich-demo:{scorer_name}:{minute}",
            competition=LEAGUE_SLUG,
        )
        return rendered.png
    except Exception as exc:
        print(f"[WARN] goal_graphics non disponibile: {exc}", file=sys.stderr)
        return None


def render_stats_graphic(
    *,
    home_goals: int,
    away_goals: int,
    momento: str,
) -> bytes | None:
    try:
        import stats_graphics

        if momento == "HT":
            rows = [
                ("POSSESSO", "53%", "47%"),
                ("xG", "1.32", "0.58"),
                ("TIRI", "9", "7"),
                ("TIRI IN PORTA", "4", "3"),
                ("CORNER", "4", "2"),
                ("FALLI", "6", "5"),
                ("FUORIGIOCO", "1", "0"),
                ("AMMONITI", "1", "0"),
                ("ESPULSI", "0", "0"),
                ("PARATE", "3", "5"),
                ("PRECISIONE PASSAGGI", "88%", "84%"),
                ("PASSAGGI", "271", "249"),
            ]
        else:
            rows = [
                ("POSSESSO", "51%", "49%"),
                ("xG", "2.11", "0.96"),
                ("TIRI", "17", "12"),
                ("TIRI IN PORTA", "7", "5"),
                ("CORNER", "7", "4"),
                ("FALLI", "11", "9"),
                ("FUORIGIOCO", "1", "0"),
                ("AMMONITI", "1", "0"),
                ("ESPULSI", "0", "0"),
                ("PARATE", "4", "6"),
                ("PRECISIONE PASSAGGI", "88%", "84%"),
                ("PASSAGGI", "463", "401"),
            ]

        html_doc = stats_graphics.build_html(
            rows=rows,
            kit=KIT,
            competition=LEAGUE_SLUG,
            league_name="Serie A",
            momento=momento,
            home_id=HOME_ID,
            away_id=AWAY_ID,
            home_name=HOME_NAME,
            away_name=AWAY_NAME,
        )
        path = stats_graphics.render(html_doc, hd_output=True)
        return Path(path).read_bytes()
    except Exception as exc:
        print(f"[WARN] stats_graphics non disponibile: {exc}", file=sys.stderr)
        return None


def render_simple_ft_graphic(home_goals: int, away_goals: int) -> bytes | None:
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (1400, 900), "white")
        draw = ImageDraw.Draw(img)
        try:
            font_big = ImageFont.truetype("DejaVuSans-Bold.ttf", 110)
            font_mid = ImageFont.truetype("DejaVuSans-Bold.ttf", 60)
            font_small = ImageFont.truetype("DejaVuSans.ttf", 36)
        except Exception:
            font_big = ImageFont.load_default()
            font_mid = ImageFont.load_default()
            font_small = ImageFont.load_default()

        draw.text((100, 90), "FULL TIME", fill="black", font=font_mid)
        draw.text((100, 250), HOME_NAME, fill="black", font=font_mid)
        draw.text((1000, 250), AWAY_NAME, fill="black", font=font_mid)
        draw.text((575, 220), f"{home_goals}-{away_goals}", fill="black", font=font_big)
        draw.text((100, 420), "23' K. Yildiz", fill="black", font=font_small)
        draw.text((100, 470), "67' Lautaro Martinez", fill="black", font=font_small)
        draw.text((100, 520), "78' R. Kolo Muani", fill="black", font=font_small)
        draw.text((100, 760), f"{ecomp()} {HASHTAG}", fill="black", font=font_small)

        from io import BytesIO
        bio = BytesIO()
        img.save(bio, format="PNG")
        return bio.getvalue()
    except Exception as exc:
        print(f"[WARN] fallback FT graphic non disponibile: {exc}", file=sys.stderr)
        return None


def resolve_chat_id() -> str:
    chat_id = (os.getenv("TELEGRAM_TO_BOT") or "").strip()
    if not chat_id:
        raise RuntimeError("TELEGRAM_TO_BOT mancante.")
    return chat_id


def resolve_token() -> str:
    token = (os.getenv("TELEGRAM_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_TOKEN mancante.")
    return token


def timeline(duration: int) -> list[tuple[int, str, dict]]:
    def scale(second: int) -> int:
        return min(duration, max(0, round(second * duration / DEFAULT_DURATION_SECONDS)))

    return [
        (scale(0), "text", {"text": build_start_text(), "silent": True}),
        (scale(60), "photo_text", {
            "text": build_goal_text(
                minute="23",
                home_goals=1,
                away_goals=0,
                scoring_team="home",
                scorer="K. Yildiz",
                assist="K. Thuram",
            ),
            "graphic": ("goal", {"scorer_name": "Kenan Yildiz", "minute": "23", "home_goals": 1, "away_goals": 0, "goal_type": "goal"}),
            "filename": "goal_23.png",
        }),
        (scale(135), "text", {"text": build_ht_text(1, 0), "silent": False}),
        (scale(145), "photo_text", {
            "text": build_stats_caption("HT"),
            "graphic": ("stats", {"home_goals": 1, "away_goals": 0, "momento": "HT"}),
            "filename": "stats_ht.png",
            "silent": True,
        }),
        (scale(170), "text", {"text": build_second_half_text(1, 0), "silent": True}),
        (scale(200), "text", {
            "text": build_sub_text("58", HOME_NAME.upper(), "W. McKennie", "T. Koopmeiners"),
            "silent": True,
        }),
        (scale(225), "photo_text", {
            "text": build_goal_text(
                minute="67",
                home_goals=1,
                away_goals=1,
                scoring_team="away",
                scorer="Lautaro Martinez",
                assist="F. Dimarco",
            ),
            "graphic": ("goal", {"scorer_name": "Lautaro Martinez", "minute": "67", "home_goals": 1, "away_goals": 1, "goal_type": "goal"}),
            "filename": "goal_67.png",
        }),
        (scale(255), "photo_text", {
            "text": build_goal_text(
                minute="78",
                home_goals=2,
                away_goals=1,
                scoring_team="home",
                scorer="R. Kolo Muani",
                assist="K. Yildiz",
            ),
            "graphic": ("goal", {"scorer_name": "Randal Kolo Muani", "minute": "78", "home_goals": 2, "away_goals": 1, "goal_type": "goal"}),
            "filename": "goal_78.png",
        }),
        (scale(290), "photo_text", {
            "text": build_ft_text(2, 1),
            "graphic": ("ft", {"home_goals": 2, "away_goals": 1}),
            "filename": "ft.png",
            "silent": False,
        }),
        (scale(300), "photo_text", {
            "text": build_stats_caption("FT"),
            "graphic": ("stats", {"home_goals": 2, "away_goals": 1, "momento": "FT"}),
            "filename": "stats_ft.png",
            "silent": True,
        }),
    ]


def render_graphic(kind: str, params: dict) -> bytes | None:
    if kind == "goal":
        return render_goal_graphic(**params)
    if kind == "stats":
        return render_stats_graphic(**params)
    if kind == "ft":
        return render_simple_ft_graphic(**params)
    return None


def run_demo(*, duration: int, dry_run: bool = False) -> None:
    if duration < 30:
        raise ValueError("Durata minima 30 secondi.")

    token = "dry-run-token" if dry_run else resolve_token()
    chat_id = "dry-run-bot-jr" if dry_run else resolve_chat_id()
    transport: Transport = DryRunTransport() if dry_run else RequestsTransport(token)
    tg = TelegramRichClient(token, chat_id, transport=transport)

    events = timeline(duration)
    sent = set()
    start = time.monotonic()

    print(f"Avvio demo: duration={duration}s dry_run={dry_run}", file=sys.stderr)

    while True:
        elapsed = min(duration, int(time.monotonic() - start))
        for idx, (at_sec, kind, payload) in enumerate(events):
            if idx in sent or elapsed < at_sec:
                continue

            text = payload["text"]
            silent = bool(payload.get("silent", False))

            if kind == "text":
                tg.send_rich_text(text, silent=silent)
            else:
                graphic_kind, params = payload["graphic"]
                graphic = render_graphic(graphic_kind, params)
                if graphic:
                    tg.send_rich_photo(text, graphic, filename=payload.get("filename", "graphic.png"), silent=silent)
                else:
                    tg.send_rich_text(text, silent=silent)

            sent.add(idx)

        if elapsed >= duration:
            break
        time.sleep(1)

    print("Demo completata.", file=sys.stderr)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Demo Rich LiveScore JR.")
    parser.add_argument("--duration", type=int, default=300, help="Durata demo in secondi.")
    parser.add_argument("--dry-run", action="store_true", help="Non invia a Telegram.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_demo(duration=args.duration, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
