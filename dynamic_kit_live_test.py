#!/usr/bin/env python3
"""
Dynamic Juventus kit live simulator.

SAFE BY DESIGN:
- does NOT import or start juve_bot_espn.py
- does NOT read/write the production Gist
- sends only to TELEGRAM_TO_BOT
- runs for 10 minutes by default
- uses a synthetic event_id in every callback_data
- never sends a replacement message when changing kit: it uses editMessageMedia

The simulator compresses a match into a few seconds:
- publishes a recap with HOME / AWAY / THIRD / AUTO buttons
- publishes representative kit-dependent graphics
- simulates ESPN uniform.type appearing/changing while the job is alive
- polls callback_query via getUpdates without blocking the loop
"""

from __future__ import annotations

import html
import io
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import requests
from PIL import Image, ImageDraw, ImageFont

VALID_KITS = ("home", "away", "third")
VALID_MODES = ("auto", "manual")
DEFAULT_DURATION_SECONDS = int(os.getenv("KIT_TEST_DURATION_SECONDS", "600"))
POLL_SECONDS = float(os.getenv("KIT_TEST_POLL_SECONDS", "1.5"))

# Fake ESPN timeline. None means uniform.type absent.
# Override with KIT_TEST_ESPN_TIMELINE, e.g.:
# [{"at":0,"kit":null},{"at":60,"kit":"third"},{"at":180,"kit":"home"}]
DEFAULT_ESPN_TIMELINE = [
    {"at": 0, "kit": None},
    {"at": 60, "kit": "third"},
    {"at": 180, "kit": "home"},
]

SESSION = requests.Session()


def _log(message: str) -> None:
    print(f"[KIT-TEST {time.strftime('%H:%M:%S')}] {message}", flush=True)


def normalise_kit(value: object) -> Optional[str]:
    raw = str(value or "").strip().lower()
    return raw if raw in VALID_KITS else None


def display_kit(value: Optional[str]) -> str:
    return {"home": "Home", "away": "Away", "third": "Third"}.get(value, "Non disponibile")


@dataclass
class KitState:
    event_id: str
    fallback_kit: str = "away"
    espn_kit: Optional[str] = None
    active_kit: str = "away"
    kit_mode: str = "auto"
    manual_kit: Optional[str] = None
    recap_message_id: Optional[int] = None
    update_offset: Optional[int] = None
    processed_callback_ids: set[str] = field(default_factory=set)
    kit_media: dict[str, dict] = field(default_factory=dict)

    def ensure_compat(self) -> None:
        """Backward-compatible defaults, mirroring how production Gist migration should work."""
        if self.kit_mode not in VALID_MODES:
            self.kit_mode = "auto"
        self.fallback_kit = normalise_kit(self.fallback_kit) or "away"
        self.espn_kit = normalise_kit(self.espn_kit)
        self.manual_kit = normalise_kit(self.manual_kit)
        if self.kit_mode == "manual" and self.manual_kit:
            self.active_kit = self.manual_kit
        else:
            self.kit_mode = "auto"
            self.manual_kit = None
            self.active_kit = self.espn_kit or self.fallback_kit
        if not isinstance(self.kit_media, dict):
            self.kit_media = {}
        if not isinstance(self.processed_callback_ids, set):
            self.processed_callback_ids = set(self.processed_callback_ids or [])


def get_active_kit(state: KitState) -> str:
    if state.kit_mode == "manual" and state.manual_kit in VALID_KITS:
        return state.manual_kit
    return state.espn_kit if state.espn_kit in VALID_KITS else state.fallback_kit


def set_espn_kit(state: KitState, kit: Optional[str]) -> tuple[str, str, bool]:
    """Store latest ESPN value. AUTO follows it, MANUAL only records it."""
    old_active = state.active_kit
    old_espn = state.espn_kit
    state.espn_kit = normalise_kit(kit)
    state.active_kit = get_active_kit(state)
    changed = state.active_kit != old_active
    if old_espn != state.espn_kit:
        _log(f"ESPN uniform: {display_kit(old_espn)} -> {display_kit(state.espn_kit)}")
    if changed:
        _log(f"ACTIVE KIT: {old_active} -> {state.active_kit} | mode={state.kit_mode.upper()}")
    return old_active, state.active_kit, changed


def set_manual_kit(state: KitState, kit: str) -> tuple[str, str, bool]:
    kit = normalise_kit(kit)
    if not kit:
        raise ValueError("kit manuale non valido")
    old = state.active_kit
    state.kit_mode = "manual"
    state.manual_kit = kit
    state.active_kit = kit
    return old, state.active_kit, old != state.active_kit


def set_auto(state: KitState) -> tuple[str, str, bool]:
    old = state.active_kit
    state.kit_mode = "auto"
    state.manual_kit = None
    state.active_kit = get_active_kit(state)
    return old, state.active_kit, old != state.active_kit


def keyboard_for(state: KitState) -> dict:
    selected = state.active_kit if state.kit_mode == "manual" else "auto"

    def label(kit: str) -> str:
        base = kit.upper()
        return f"✅ {base}" if selected == kit else base

    return {
        "inline_keyboard": [[
            {"text": label("home"), "callback_data": f"kit:{state.event_id}:home"},
            {"text": label("away"), "callback_data": f"kit:{state.event_id}:away"},
            {"text": label("third"), "callback_data": f"kit:{state.event_id}:third"},
            {"text": label("auto"), "callback_data": f"kit:{state.event_id}:auto"},
        ]]
    }


def recap_text(state: KitState, remaining: Optional[int] = None) -> str:
    lines = [
        "🧪 <b>TEST KIT DINAMICO JUVENTUS</b>",
        "",
        f"Evento: <code>{html.escape(state.event_id)}</code>",
        f"Kit Juventus: <b>{display_kit(state.active_kit)}</b>",
        f"Modalità kit: <b>{state.kit_mode.upper()}</b>",
    ]
    if state.kit_mode == "manual" or state.espn_kit:
        lines.append(f"ESPN uniform: <b>{display_kit(state.espn_kit)}</b>")
    if state.kit_mode == "auto" and not state.espn_kit:
        lines.append(f"Fallback: <b>{display_kit(state.fallback_kit)}</b>")
    if remaining is not None:
        lines.extend(["", f"Test attivo ancora per ~{max(0, remaining)}s"])
    lines.extend([
        "",
        "Premi i pulsanti: tutte le foto già pubblicate devono cambiare senza creare nuovi messaggi.",
    ])
    return "\n".join(lines)


def parse_callback_data(data: str) -> tuple[Optional[str], Optional[str]]:
    parts = str(data or "").split(":")
    if len(parts) != 3 or parts[0] != "kit":
        return None, None
    return parts[1], parts[2]


def apply_callback(state: KitState, callback_id: str, callback_data: str) -> tuple[bool, bool, str]:
    """
    Returns: (handled, active_changed, message)
    Duplicate callbacks and callbacks for another event are ignored.
    """
    if not callback_id or callback_id in state.processed_callback_ids:
        return False, False, "Callback già elaborato"

    event_id, choice = parse_callback_data(callback_data)
    if event_id != state.event_id:
        return False, False, "Evento non valido"
    if choice not in (*VALID_KITS, "auto"):
        return False, False, "Scelta non valida"

    # Mark only callbacks that actually belong to this event.
    state.processed_callback_ids.add(callback_id)

    if choice == "auto":
        _, _, changed = set_auto(state)
        return True, changed, f"AUTO · {display_kit(state.active_kit)}"

    _, _, changed = set_manual_kit(state, choice)
    return True, changed, f"MANUALE · {display_kit(state.active_kit)}"


class Telegram:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = str(chat_id)
        self.base = f"https://api.telegram.org/bot{token}"

    def _post(self, method: str, *, data=None, files=None, timeout=20) -> dict:
        response = SESSION.post(
            f"{self.base}/{method}",
            data=data,
            files=files,
            timeout=timeout,
        )
        try:
            payload = response.json()
        except Exception:
            payload = {"ok": False, "description": response.text[:500]}
        if response.status_code != 200 or not payload.get("ok"):
            raise RuntimeError(f"Telegram {method}: HTTP {response.status_code} · {payload}")
        return payload

    def send_recap(self, state: KitState, remaining: int) -> int:
        payload = self._post(
            "sendMessage",
            data={
                "chat_id": self.chat_id,
                "text": recap_text(state, remaining),
                "parse_mode": "HTML",
                "reply_markup": json.dumps(keyboard_for(state), ensure_ascii=False),
            },
        )
        return int(payload["result"]["message_id"])

    def edit_recap(self, state: KitState, remaining: int) -> None:
        if not state.recap_message_id:
            return
        self._post(
            "editMessageText",
            data={
                "chat_id": self.chat_id,
                "message_id": state.recap_message_id,
                "text": recap_text(state, remaining),
                "parse_mode": "HTML",
                "reply_markup": json.dumps(keyboard_for(state), ensure_ascii=False),
            },
        )

    def answer_callback(self, callback_query_id: str, text: str) -> None:
        try:
            self._post(
                "answerCallbackQuery",
                data={
                    "callback_query_id": callback_query_id,
                    "text": text[:180],
                    "show_alert": "false",
                },
                timeout=10,
            )
        except Exception as exc:
            _log(f"answerCallbackQuery fallita: {exc}")

    def send_photo(self, caption: str, png: bytes) -> int:
        payload = self._post(
            "sendPhoto",
            data={
                "chat_id": self.chat_id,
                "caption": caption,
                "parse_mode": "HTML",
            },
            files={"photo": ("kit-test.png", png, "image/png")},
            timeout=30,
        )
        return int(payload["result"]["message_id"])

    def edit_photo(self, message_id: int, caption: str, png: bytes) -> bool:
        media = json.dumps({
            "type": "photo",
            "media": "attach://photo",
            "caption": caption,
            "parse_mode": "HTML",
        })
        try:
            self._post(
                "editMessageMedia",
                data={
                    "chat_id": self.chat_id,
                    "message_id": int(message_id),
                    "media": media,
                },
                files={"photo": ("kit-test.png", png, "image/png")},
                timeout=30,
            )
            return True
        except Exception as exc:
            _log(f"editMessageMedia fallita | message_id={message_id} | {exc}")
            return False

    def get_callback_updates(self, offset: Optional[int], timeout: int = 1) -> list[dict]:
        data = {
            "timeout": str(max(0, timeout)),
            "allowed_updates": json.dumps(["callback_query"]),
        }
        if offset is not None:
            data["offset"] = str(offset)
        try:
            payload = self._post("getUpdates", data=data, timeout=timeout + 5)
            return list(payload.get("result") or [])
        except Exception as exc:
            _log(f"getUpdates fallita: {exc}")
            return []


def _load_timeline() -> list[dict]:
    raw = os.getenv("KIT_TEST_ESPN_TIMELINE", "").strip()
    if not raw:
        return list(DEFAULT_ESPN_TIMELINE)
    parsed = json.loads(raw)
    result = []
    for item in parsed:
        result.append({"at": int(item["at"]), "kit": normalise_kit(item.get("kit"))})
    return sorted(result, key=lambda x: x["at"])


def _font(size: int):
    candidates = [
        Path("assets/goal_graphics/fonts/DharmaGothicEBold.otf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fallback_card(title: str, kit: str, subtitle: str = "") -> bytes:
    """Emergency renderer so the interactive test still works if a production asset is missing."""
    palette = {
        "home": (242, 195, 0),
        "away": (230, 145, 175),
        "third": (190, 160, 75),
    }
    accent = palette.get(kit, palette["home"])
    im = Image.new("RGB", (1086, 1448), (18, 18, 20))
    d = ImageDraw.Draw(im)
    d.rectangle((60, 60, 1026, 1388), outline=accent, width=8)
    d.text((90, 120), "DYNAMIC KIT TEST", font=_font(58), fill=accent)
    d.text((90, 520), title, font=_font(110), fill=(245, 245, 245))
    d.text((90, 680), f"KIT: {kit.upper()}", font=_font(76), fill=accent)
    if subtitle:
        d.text((90, 820), subtitle, font=_font(48), fill=(220, 220, 220))
    stream = io.BytesIO()
    im.save(stream, format="PNG")
    return stream.getvalue()


def _dummy_canva_layers() -> Path:
    root = Path(tempfile.mkdtemp(prefix="jr_kit_test_layers_"))
    bg = Image.new("RGBA", (934, 1296), (22, 22, 24, 255))
    d = ImageDraw.Draw(bg)
    for y in range(bg.height):
        shade = 22 + int(28 * y / bg.height)
        d.line((0, y, bg.width, y), fill=(shade, shade, shade + 2, 255))
    bg.save(root / "background.png")
    Image.new("RGBA", (934, 1296), (0, 0, 0, 0)).save(root / "player.png")
    return root


def render_entry(entry: dict, kit: str, layers: Path) -> bytes:
    """Use production renderers where possible; emergency fallback keeps the test alive."""
    kind = entry["type"]
    try:
        if kind == "kick":
            import portrait_graphics
            return portrait_graphics.phase(
                kind="kick",
                home_name="Juventus",
                away_name="Inter",
                home_id="111",
                away_id="110",
                kit=kit,
                competition="ita.1",
            )

        if kind in ("half", "end_of_90", "full"):
            import portrait_graphics
            return portrait_graphics.phase(
                kind=kind,
                home_name="Juventus",
                away_name="Inter",
                home_id="111",
                away_id="110",
                home_goals=entry.get("home_goals", 1),
                away_goals=entry.get("away_goals", 0),
                kit=kit,
                competition="ita.1",
                layers=layers,
            )

        if kind == "goal":
            import goal_graphics
            try:
                rendered = goal_graphics.render_goal_card(
                    scorer_name="Kenan Yildiz",
                    minute=entry.get("minute", "24"),
                    home_name="Juventus",
                    away_name="Inter",
                    home_goals=1,
                    away_goals=0,
                    home_id="111",
                    away_id="110",
                    kit=kit,
                    event_key="dynamic-kit-test-goal",
                    competition="ita.1",
                )
            except Exception:
                rendered = goal_graphics.render_goal_card(
                    scorer_name="TEST PLAYER",
                    minute=entry.get("minute", "24"),
                    home_name="Juventus",
                    away_name="Inter",
                    home_goals=1,
                    away_goals=0,
                    home_id="111",
                    away_id="110",
                    kit=kit,
                    event_key="dynamic-kit-test-goal",
                    competition="ita.1",
                )
            return rendered.png

        if kind == "saved":
            import goal_graphics
            for keeper in ("Guglielmo Vicario", "Carlo Pinsoglio", "Kamil Grabara"):
                try:
                    return goal_graphics.render_saved_card(
                        goalkeeper_name=keeper,
                        minute=entry.get("minute", "61"),
                        home_name="Juventus",
                        away_name="Inter",
                        home_goals=1,
                        away_goals=0,
                        home_id="111",
                        away_id="110",
                        kit=kit,
                        event_key="dynamic-kit-test-saved",
                        competition="ita.1",
                    ).png
                except Exception:
                    continue
            raise RuntimeError("Nessun asset portiere disponibile")

        if kind == "stats":
            import stats_graphics
            rows = [
                ("POSSESSO", "54%", "46%"),
                ("xG", "1.42", "0.73"),
                ("TIRI", "12", "8"),
                ("TIRI IN PORTA", "5", "3"),
                ("CORNER", "6", "4"),
                ("FALLI", "9", "11"),
                ("FUORIGIOCO", "2", "1"),
                ("AMMONITI", "1", "2"),
                ("ESPULSI", "0", "0"),
                ("PARATE", "3", "4"),
                ("PRECISIONE PASSAGGI", "89%", "85%"),
                ("PASSAGGI", "521", "447"),
            ]
            html_text = stats_graphics.build_html(
                rows=rows,
                kit=kit,
                competition="ita.1",
                league_name="SERIE A · TEST",
                momento="HT",
                home_id="111",
                away_id="110",
                home_name="Juventus",
                away_name="Inter",
            )
            path = stats_graphics.render(html_text, hd_output=False)
            return Path(path).read_bytes()

    except Exception as exc:
        _log(f"Renderer produzione non disponibile per {kind}/{kit}: {exc}; uso fallback test")

    return _fallback_card(entry.get("label", kind.upper()), kit, entry.get("caption", ""))


SIMULATED_MEDIA = [
    {"key": "kickoff", "type": "kick", "label": "INIZIO PARTITA",
     "caption": "⚡️ <b>INIZIO PARTITA · TEST</b>"},
    {"key": "goal_1_0", "type": "goal", "label": "GOAL", "minute": "24",
     "caption": "⚽️ <b>GOAL · 24' · TEST</b>"},
    {"key": "saved_61", "type": "saved", "label": "SAVED", "minute": "61",
     "caption": "🧤 <b>SAVED · 61' · TEST</b>"},
    {"key": "half", "type": "half", "label": "HALF TIME", "home_goals": 1, "away_goals": 0,
     "caption": "🏁 <b>HALF TIME · TEST</b>"},
    {"key": "end90", "type": "end_of_90", "label": "END OF 90'", "home_goals": 1, "away_goals": 1,
     "caption": "🏁 <b>END OF 90' · TEST</b>"},
    {"key": "full", "type": "full", "label": "FULL TIME", "home_goals": 2, "away_goals": 1,
     "caption": "🏁 <b>FULL TIME · TEST</b>"},
    {"key": "stats", "type": "stats", "label": "STATS",
     "caption": "📊 <b>STATS · TEST</b>"},
]


def publish_initial_media(tg: Telegram, state: KitState, layers: Path) -> None:
    for descriptor in SIMULATED_MEDIA:
        png = render_entry(descriptor, state.active_kit, layers)
        msg_id = tg.send_photo(descriptor["caption"], png)
        state.kit_media[descriptor["key"]] = {
            **descriptor,
            "message_id": msg_id,
            "kit": state.active_kit,
            "last_edit_error": None,
        }
        _log(f"Pubblicata {descriptor['key']} | message_id={msg_id} | kit={state.active_kit}")


def refresh_all_media(
    tg: Telegram,
    state: KitState,
    layers: Path,
    render_func: Callable[[dict, str, Path], bytes] = render_entry,
) -> int:
    """Edit only existing messages. Failed edits remain stale and are retryable."""
    edited = 0
    for key, record in state.kit_media.items():
        if record.get("kit") == state.active_kit:
            continue
        png = render_func(record, state.active_kit, layers)
        ok = tg.edit_photo(int(record["message_id"]), record["caption"], png)
        if ok:
            record["kit"] = state.active_kit
            record["last_edit_error"] = None
            edited += 1
            _log(f"MEDIA EDIT {key} | message_id={record['message_id']} | kit={state.active_kit}")
        else:
            record["last_edit_error"] = f"edit fallito verso {state.active_kit}"
    return edited


def _drain_old_callbacks(tg: Telegram) -> Optional[int]:
    updates = tg.get_callback_updates(None, timeout=0)
    if not updates:
        return None
    return max(int(u["update_id"]) for u in updates) + 1


def run() -> int:
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    bot_chat = os.getenv("TELEGRAM_TO_BOT", "").strip()
    if not token or not bot_chat:
        raise SystemExit("Mancano TELEGRAM_TOKEN o TELEGRAM_TO_BOT")

    duration = max(60, DEFAULT_DURATION_SECONDS)
    event_id = f"SIM{int(time.time())}"
    fallback = normalise_kit(os.getenv("KIT_TEST_FALLBACK", "away")) or "away"
    state = KitState(event_id=event_id, fallback_kit=fallback, active_kit=fallback)
    state.ensure_compat()

    tg = Telegram(token, bot_chat)
    layers = _dummy_canva_layers()
    timeline = _load_timeline()

    state.update_offset = _drain_old_callbacks(tg)
    start = time.monotonic()
    deadline = start + duration
    timeline_index = 0

    # Apply t=0 ESPN state before publishing.
    while timeline_index < len(timeline) and timeline[timeline_index]["at"] <= 0:
        set_espn_kit(state, timeline[timeline_index]["kit"])
        timeline_index += 1

    state.recap_message_id = tg.send_recap(state, duration)
    publish_initial_media(tg, state, layers)
    _log(
        f"SIMULAZIONE AVVIATA | event_id={event_id} | durata={duration}s | "
        f"active={state.active_kit} | recap={state.recap_message_id}"
    )

    last_recap_refresh = 0.0
    last_retry = 0.0

    try:
        while time.monotonic() < deadline:
            now = time.monotonic()
            elapsed = int(now - start)
            remaining = int(deadline - now)

            # Simulated ESPN publication/correction.
            while timeline_index < len(timeline) and elapsed >= int(timeline[timeline_index]["at"]):
                new_espn = timeline[timeline_index]["kit"]
                _, _, active_changed = set_espn_kit(state, new_espn)
                if active_changed:
                    refresh_all_media(tg, state, layers)
                tg.edit_recap(state, remaining)
                timeline_index += 1

            # Non-blocking-ish callback polling: Telegram long poll <= 1s.
            updates = tg.get_callback_updates(state.update_offset, timeout=1)
            for update in updates:
                state.update_offset = int(update["update_id"]) + 1
                callback = update.get("callback_query") or {}
                callback_id = str(callback.get("id") or "")
                callback_data = str(callback.get("data") or "")
                handled, active_changed, answer = apply_callback(
                    state, callback_id, callback_data
                )
                if not handled:
                    # Do not answer callbacks for unrelated events. A duplicate
                    # callback id may already have been answered on first handling.
                    continue

                tg.answer_callback(callback_id, answer)
                _log(
                    f"CALLBACK {callback_data} | mode={state.kit_mode} | "
                    f"espn={state.espn_kit} | active={state.active_kit}"
                )

                if active_changed:
                    refresh_all_media(tg, state, layers)
                tg.edit_recap(state, remaining)

            # Retry stale photos after a transient edit error.
            if now - last_retry >= 10:
                if any(rec.get("kit") != state.active_kit for rec in state.kit_media.values()):
                    refresh_all_media(tg, state, layers)
                last_retry = now

            # Keep remaining time reasonably fresh without hammering Telegram.
            if now - last_recap_refresh >= 30:
                try:
                    tg.edit_recap(state, remaining)
                except Exception as exc:
                    # Telegram may answer "message is not modified"; harmless.
                    _log(f"Recap refresh ignorato: {exc}")
                last_recap_refresh = now

            time.sleep(POLL_SECONDS)

    finally:
        try:
            final_text = recap_text(state, 0) + "\n\n✅ <b>TEST TERMINATO</b>"
            tg._post(
                "editMessageText",
                data={
                    "chat_id": tg.chat_id,
                    "message_id": state.recap_message_id,
                    "text": final_text,
                    "parse_mode": "HTML",
                    "reply_markup": json.dumps({"inline_keyboard": []}),
                },
            )
        except Exception as exc:
            _log(f"Chiusura recap fallita: {exc}")

    _log("SIMULAZIONE TERMINATA")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
