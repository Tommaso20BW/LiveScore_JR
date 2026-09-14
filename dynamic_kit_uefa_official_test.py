#!/usr/bin/env python3
"""
Interactive UEFA dynamic-kit test using ONLY the repository's official graphics.

Important:
- does not start juve_bot_espn.main()
- does not read/write the production match Gist
- sends only to TELEGRAM_TO_BOT
- uses official goal_graphics / portrait_graphics / stats_graphics assets
- uses a REAL fresh Canva page-1 PRO export for phase graphics
- has NO synthetic graphic fallback
- if an official renderer/asset/Canva export fails, the test fails loudly
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import time
from pathlib import Path

from PIL import Image

import dynamic_kit_live_test as base

DURATION = max(60, int(os.getenv("KIT_TEST_DURATION_SECONDS", "600")))
COMPETITION = os.getenv("KIT_TEST_COMPETITION", "uefa.champions").strip()
LEAGUE_NAME = os.getenv("KIT_TEST_LEAGUE_NAME", "UEFA CHAMPIONS LEAGUE").strip()
FALLBACK = base.normalise_kit(os.getenv("KIT_TEST_FALLBACK", "away")) or "away"

HOME_NAME = "Juventus"
HOME_ID = "111"
AWAY_NAME = "Real Madrid"
AWAY_ID = "86"

ROWS = [
    ("POSSESSO", "52%", "48%"),
    ("xG", "1.21", "0.88"),
    ("TIRI", "11", "9"),
    ("TIRI IN PORTA", "5", "4"),
    ("CORNER", "5", "3"),
    ("FALLI", "10", "12"),
    ("FUORIGIOCO", "1", "2"),
    ("AMMONITI", "2", "1"),
    ("ESPULSI", "0", "0"),
    ("PARATE", "4", "4"),
    ("PRECISIONE PASSAGGI", "88%", "87%"),
    ("PASSAGGI", "493", "471"),
]


def visual_hash(png: bytes) -> str:
    """Hash pixels, not PNG metadata."""
    with Image.open(io.BytesIO(png)) as im:
        rgba = im.convert("RGBA")
        payload = (
            f"{rgba.width}x{rgba.height}:".encode()
            + rgba.tobytes()
        )
    return hashlib.sha256(payload).hexdigest()


def export_real_canva_layers() -> Path:
    """
    Same official path used by the production LiveScore:
      get_valid_token()
      -> canva_page_one.export_page_one(...)
      -> background.png + player.png extracted from Canva page 1.
    """
    import juve_bot_espn as bot
    from canva_page_one import export_page_one

    token = bot.get_valid_token()
    if not token:
        raise RuntimeError("Token Canva non disponibile")

    base._log("CANVA UFFICIALE: richiedo export PRO reale della pagina 1")
    return export_page_one(
        bot.SESSION,
        token,
        bot.CANVA_DESIGN_ID,
        Path("canva_page1_cache_uefa_test"),
    )


def render_official(entry: dict, kit: str, layers: Path) -> bytes:
    """
    No fallback. These are the same production compositors/assets.
    In UEFA, portrait_graphics.theme() keeps the UEFA theme fixed while
    GOAL/SAVED still resolve the player's kit-specific PNG.
    """
    kind = entry["type"]

    if kind == "kick":
        import portrait_graphics
        return portrait_graphics.phase(
            kind="kick",
            home_name=HOME_NAME,
            away_name=AWAY_NAME,
            home_id=HOME_ID,
            away_id=AWAY_ID,
            kit=kit,
            competition=COMPETITION,
        )

    if kind in ("half", "end_of_90", "full"):
        import portrait_graphics
        return portrait_graphics.phase(
            kind=kind,
            home_name=HOME_NAME,
            away_name=AWAY_NAME,
            home_id=HOME_ID,
            away_id=AWAY_ID,
            home_goals=entry.get("home_goals", 1),
            away_goals=entry.get("away_goals", 0),
            kit=kit,
            competition=COMPETITION,
            layers=layers,
        )

    if kind == "goal":
        import goal_graphics
        return goal_graphics.render_goal_card(
            scorer_name="Kenan Yildiz",
            minute=entry.get("minute", "24"),
            home_name=HOME_NAME,
            away_name=AWAY_NAME,
            home_goals=1,
            away_goals=0,
            home_id=HOME_ID,
            away_id=AWAY_ID,
            kit=kit,
            event_key="dynamic-kit-uefa-official-goal",
            competition=COMPETITION,
        ).png

    if kind == "saved":
        import goal_graphics
        return goal_graphics.render_saved_card(
            goalkeeper_name="Guglielmo Vicario",
            minute=entry.get("minute", "61"),
            home_name=HOME_NAME,
            away_name=AWAY_NAME,
            home_goals=1,
            away_goals=0,
            home_id=HOME_ID,
            away_id=AWAY_ID,
            kit=kit,
            event_key="dynamic-kit-uefa-official-saved",
            competition=COMPETITION,
        ).png

    if kind == "stats":
        import stats_graphics
        html = stats_graphics.build_html(
            rows=ROWS,
            kit=kit,
            competition=COMPETITION,
            league_name=LEAGUE_NAME,
            momento="HT",
            home_id=HOME_ID,
            away_id=AWAY_ID,
            home_name=HOME_NAME,
            away_name=AWAY_NAME,
        )
        path = stats_graphics.render(html, hd_output=True)
        return Path(path).read_bytes()

    raise ValueError(f"Tipo grafica non supportato: {kind}")


MEDIA = [
    {
        "key": "kickoff",
        "type": "kick",
        "caption": "⚡️ <b>INIZIO PARTITA · UEFA TEST UFFICIALE</b>",
    },
    {
        "key": "goal_1_0",
        "type": "goal",
        "minute": "24",
        "caption": "⚽️ <b>GOAL · 24' · UEFA TEST UFFICIALE</b>",
    },
    {
        "key": "saved_61",
        "type": "saved",
        "minute": "61",
        "caption": "🧤 <b>SAVED · 61' · UEFA TEST UFFICIALE</b>",
    },
    {
        "key": "half",
        "type": "half",
        "home_goals": 1,
        "away_goals": 0,
        "caption": "🏁 <b>HALF TIME · UEFA TEST UFFICIALE</b>",
    },
    {
        "key": "end90",
        "type": "end_of_90",
        "home_goals": 1,
        "away_goals": 1,
        "caption": "🏁 <b>END OF 90' · UEFA TEST UFFICIALE</b>",
    },
    {
        "key": "full",
        "type": "full",
        "home_goals": 2,
        "away_goals": 1,
        "caption": "🏁 <b>FULL TIME · UEFA TEST UFFICIALE</b>",
    },
    {
        "key": "stats",
        "type": "stats",
        "caption": "📊 <b>STATS · UEFA TEST UFFICIALE</b>",
    },
]


def recap_text(state: base.KitState, remaining: int) -> str:
    return "\n".join([
        "🧪 <b>TEST KIT DINAMICO UEFA · GRAFICHE UFFICIALI</b>",
        "",
        f"Competizione: <b>{LEAGUE_NAME}</b>",
        "Render: <b>asset ufficiali LiveScore + Canva reale</b>",
        f"Kit Juventus: <b>{base.display_kit(state.active_kit)}</b>",
        f"Modalità: <b>{state.kit_mode.upper()}</b>",
        f"ESPN uniform simulata: <b>{base.display_kit(state.espn_kit)}</b>",
        "",
        "In UEFA il tema deve restare fisso.",
        "GOAL/SAVED devono cambiare soltanto la maglia del giocatore.",
        "Le grafiche visivamente identiche non vengono ri-editate.",
        "",
        f"Test attivo ancora per ~{max(0, remaining)}s",
    ])


def send_recap(tg: base.Telegram, state: base.KitState, remaining: int) -> int:
    payload = tg._post(
        "sendMessage",
        data={
            "chat_id": tg.chat_id,
            "text": recap_text(state, remaining),
            "parse_mode": "HTML",
            "reply_markup": json.dumps(base.keyboard_for(state), ensure_ascii=False),
        },
    )
    return int(payload["result"]["message_id"])


def edit_recap(tg: base.Telegram, state: base.KitState, remaining: int) -> None:
    tg._post(
        "editMessageText",
        data={
            "chat_id": tg.chat_id,
            "message_id": state.recap_message_id,
            "text": recap_text(state, remaining),
            "parse_mode": "HTML",
            "reply_markup": json.dumps(base.keyboard_for(state), ensure_ascii=False),
        },
    )


def publish_initial(tg: base.Telegram, state: base.KitState, layers: Path) -> None:
    for descriptor in MEDIA:
        png = render_official(descriptor, state.active_kit, layers)
        msg_id = tg.send_photo(descriptor["caption"], png)
        state.kit_media[descriptor["key"]] = {
            **descriptor,
            "message_id": msg_id,
            "kit": state.active_kit,
            "visual_hash": visual_hash(png),
            "last_edit_error": None,
        }
        base._log(
            f"UFFICIALE PUBBLICATA {descriptor['key']} | "
            f"message_id={msg_id} | kit={state.active_kit}"
        )


def refresh_all(tg: base.Telegram, state: base.KitState, layers: Path) -> tuple[int, int]:
    """
    Re-render every stale media item with official production renderers.
    editMessageMedia is called only if the actual pixels changed.
    """
    edited = 0
    identical = 0

    for key, record in state.kit_media.items():
        if record.get("kit") == state.active_kit:
            continue

        png = render_official(record, state.active_kit, layers)
        new_hash = visual_hash(png)

        if new_hash == record.get("visual_hash"):
            record["kit"] = state.active_kit
            record["last_edit_error"] = None
            identical += 1
            base._log(
                f"INVARIATA {key} | tema UEFA fisso | "
                f"nessun editMessageMedia"
            )
            continue

        if tg.edit_photo(int(record["message_id"]), record["caption"], png):
            record["kit"] = state.active_kit
            record["visual_hash"] = new_hash
            record["last_edit_error"] = None
            edited += 1
            base._log(
                f"MEDIA EDIT UFFICIALE {key} | "
                f"message_id={record['message_id']} | kit={state.active_kit}"
            )
        else:
            record["last_edit_error"] = f"edit fallito verso {state.active_kit}"

    return edited, identical


def run() -> int:
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_TO_BOT", "").strip()
    if not token or not chat_id:
        raise SystemExit("Mancano TELEGRAM_TOKEN o TELEGRAM_TO_BOT")

    # Fail BEFORE sending Telegram messages if real Canva/official assets are not available.
    layers = export_real_canva_layers()

    state = base.KitState(
        event_id=f"UEFAOFFICIAL{int(time.time())}",
        fallback_kit=FALLBACK,
        active_kit=FALLBACK,
    )
    state.ensure_compat()

    tg = base.Telegram(token, chat_id)
    timeline = base._load_timeline()
    state.update_offset = base._drain_old_callbacks(tg)

    start = time.monotonic()
    deadline = start + DURATION
    timeline_index = 0

    while timeline_index < len(timeline) and timeline[timeline_index]["at"] <= 0:
        base.set_espn_kit(state, timeline[timeline_index]["kit"])
        timeline_index += 1

    state.recap_message_id = send_recap(tg, state, DURATION)
    publish_initial(tg, state, layers)

    base._log(
        f"UEFA UFFICIALE AVVIATO | event={state.event_id} | "
        f"competition={COMPETITION} | active={state.active_kit}"
    )

    last_retry = 0.0

    try:
        while time.monotonic() < deadline:
            now = time.monotonic()
            elapsed = int(now - start)
            remaining = int(deadline - now)

            while (
                timeline_index < len(timeline)
                and elapsed >= int(timeline[timeline_index]["at"])
            ):
                new_espn = timeline[timeline_index]["kit"]
                _, _, changed = base.set_espn_kit(state, new_espn)
                if changed:
                    edited, identical = refresh_all(tg, state, layers)
                    base._log(
                        f"ESPN -> propagazione | edit={edited} | invariata={identical}"
                    )
                edit_recap(tg, state, remaining)
                timeline_index += 1

            for update in tg.get_callback_updates(state.update_offset, timeout=1):
                state.update_offset = int(update["update_id"]) + 1
                cb = update.get("callback_query") or {}
                cb_id = str(cb.get("id") or "")
                cb_data = str(cb.get("data") or "")

                handled, changed, answer = base.apply_callback(
                    state, cb_id, cb_data
                )
                if not handled:
                    continue

                tg.answer_callback(cb_id, answer)

                if changed:
                    edited, identical = refresh_all(tg, state, layers)
                    base._log(
                        f"PULSANTE -> propagazione | edit={edited} | "
                        f"invariata={identical}"
                    )

                edit_recap(tg, state, remaining)

            if now - last_retry >= 10:
                if any(
                    item.get("kit") != state.active_kit
                    for item in state.kit_media.values()
                ):
                    refresh_all(tg, state, layers)
                last_retry = now

            time.sleep(base.POLL_SECONDS)

    finally:
        try:
            tg._post(
                "editMessageText",
                data={
                    "chat_id": tg.chat_id,
                    "message_id": state.recap_message_id,
                    "text": recap_text(state, 0)
                    + "\n\n✅ <b>TEST UEFA UFFICIALE TERMINATO</b>",
                    "parse_mode": "HTML",
                    "reply_markup": json.dumps({"inline_keyboard": []}),
                },
            )
        except Exception as exc:
            base._log(f"Chiusura recap fallita: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
