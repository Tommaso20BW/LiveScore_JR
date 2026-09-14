#!/usr/bin/env python3
"""
UEFA dynamic-kit interactive simulator.

Requires dynamic_kit_live_test.py in the same directory.
It does NOT start or modify the production LiveScore.

Purpose:
- keep UEFA visual theme fixed (UCL by default)
- allow HOME/AWAY/THIRD/AUTO callbacks for 10 minutes
- verify that only truly kit-sensitive rendered media are edited
- avoid editMessageMedia when re-rendered bytes are identical
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw

import dynamic_kit_live_test as base

COMPETITION = os.getenv("KIT_TEST_COMPETITION", "uefa.champions").strip()
LEAGUE_NAME = os.getenv("KIT_TEST_LEAGUE_NAME", "UEFA CHAMPIONS LEAGUE").strip()
DURATION = max(60, int(os.getenv("KIT_TEST_DURATION_SECONDS", "600")))
FALLBACK = base.normalise_kit(os.getenv("KIT_TEST_FALLBACK", "away")) or "away"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dummy_layers() -> Path:
    root = Path(tempfile.mkdtemp(prefix="jr_uefa_test_layers_"))
    bg = Image.new("RGBA", (934, 1296), (5, 20, 38, 255))
    d = ImageDraw.Draw(bg)
    for y in range(bg.height):
        value = int(20 + 25 * y / bg.height)
        d.line((0, y, bg.width, y), fill=(4, value, min(90, value + 35), 255))
    bg.save(root / "background.png")
    Image.new("RGBA", (934, 1296), (0, 0, 0, 0)).save(root / "player.png")
    return root


def render_entry(entry: dict, kit: str, layers: Path) -> bytes:
    kind = entry["type"]
    try:
        if kind == "kick":
            import portrait_graphics
            return portrait_graphics.phase(
                kind="kick",
                home_name="Juventus",
                away_name="Real Madrid",
                home_id="111",
                away_id="86",
                kit=kit,
                competition=COMPETITION,
            )

        if kind in ("half", "end_of_90", "full"):
            import portrait_graphics
            return portrait_graphics.phase(
                kind=kind,
                home_name="Juventus",
                away_name="Real Madrid",
                home_id="111",
                away_id="86",
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
                home_name="Juventus",
                away_name="Real Madrid",
                home_goals=1,
                away_goals=0,
                home_id="111",
                away_id="86",
                kit=kit,
                event_key="dynamic-kit-uefa-test-goal",
                competition=COMPETITION,
            ).png

        if kind == "saved":
            import goal_graphics
            for keeper in ("Guglielmo Vicario", "Carlo Pinsoglio", "Kamil Grabara"):
                try:
                    return goal_graphics.render_saved_card(
                        goalkeeper_name=keeper,
                        minute=entry.get("minute", "61"),
                        home_name="Juventus",
                        away_name="Real Madrid",
                        home_goals=1,
                        away_goals=0,
                        home_id="111",
                        away_id="86",
                        kit=kit,
                        event_key="dynamic-kit-uefa-test-saved",
                        competition=COMPETITION,
                    ).png
                except Exception:
                    continue
            raise RuntimeError("Nessun asset portiere disponibile")

        if kind == "stats":
            import stats_graphics
            rows = [
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
            html_text = stats_graphics.build_html(
                rows=rows,
                kit=kit,
                competition=COMPETITION,
                league_name=LEAGUE_NAME,
                momento="HT",
                home_id="111",
                away_id="86",
                home_name="Juventus",
                away_name="Real Madrid",
            )
            path = stats_graphics.render(html_text, hd_output=False)
            return Path(path).read_bytes()

    except Exception as exc:
        base._log(f"Renderer UEFA non disponibile {kind}/{kit}: {exc}; fallback test")
        return base._fallback_card(
            f"{entry.get('label', kind.upper())} · UEFA",
            kit,
            "fallback visuale test",
        )

    return base._fallback_card(entry.get("label", kind.upper()), kit)


def recap_text(state: base.KitState, remaining: int | None = None) -> str:
    theme = "UCL" if "champions" in COMPETITION.lower() else (
        "UEL" if "europa" in COMPETITION.lower() and "conference" not in COMPETITION.lower()
        else "CONFERENCE" if "conference" in COMPETITION.lower() else COMPETITION
    )
    lines = [
        "🧪 <b>TEST KIT DINAMICO · UEFA</b>",
        "",
        f"Competizione: <b>{LEAGUE_NAME}</b>",
        f"Tema grafico: <b>{theme} fisso</b>",
        f"Kit Juventus: <b>{base.display_kit(state.active_kit)}</b>",
        f"Modalità kit: <b>{state.kit_mode.upper()}</b>",
    ]
    if state.kit_mode == "manual" or state.espn_kit:
        lines.append(f"ESPN uniform: <b>{base.display_kit(state.espn_kit)}</b>")
    if state.kit_mode == "auto" and not state.espn_kit:
        lines.append(f"Fallback: <b>{base.display_kit(state.fallback_kit)}</b>")
    lines.extend([
        "",
        "GOAL/SAVED: deve cambiare la maglia, mantenendo il tema UEFA.",
        "KICK/PHASE/STATS: se il render è identico, non viene fatto alcun edit inutile.",
    ])
    if remaining is not None:
        lines.extend(["", f"Test attivo ancora per ~{max(0, remaining)}s"])
    return "\n".join(lines)


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
    for descriptor in base.SIMULATED_MEDIA:
        png = render_entry(descriptor, state.active_kit, layers)
        msg_id = tg.send_photo(descriptor["caption"] + "\n\n🏆 UEFA TEST", png)
        state.kit_media[descriptor["key"]] = {
            **descriptor,
            "caption": descriptor["caption"] + "\n\n🏆 UEFA TEST",
            "message_id": msg_id,
            "kit": state.active_kit,
            "render_hash": sha(png),
            "last_edit_error": None,
        }
        base._log(
            f"PUBBLICATA {descriptor['key']} | message_id={msg_id} | "
            f"kit={state.active_kit} | hash={sha(png)[:10]}"
        )


def refresh_all(tg: base.Telegram, state: base.KitState, layers: Path) -> tuple[int, int]:
    """
    Returns (edited, visually_unchanged).
    All media are re-rendered with the new active kit. If bytes are identical,
    no Telegram edit is performed.
    """
    edited = 0
    unchanged = 0

    for key, record in state.kit_media.items():
        if record.get("kit") == state.active_kit:
            continue

        png = render_entry(record, state.active_kit, layers)
        new_hash = sha(png)
        old_hash = record.get("render_hash")

        if new_hash == old_hash:
            record["kit"] = state.active_kit
            record["last_edit_error"] = None
            unchanged += 1
            base._log(
                f"NESSUN CAMBIO VISIVO {key} | tema UEFA invariato | "
                f"kit logico={state.active_kit}"
            )
            continue

        if tg.edit_photo(int(record["message_id"]), record["caption"], png):
            record["kit"] = state.active_kit
            record["render_hash"] = new_hash
            record["last_edit_error"] = None
            edited += 1
            base._log(
                f"MEDIA EDIT {key} | message_id={record['message_id']} | "
                f"kit={state.active_kit}"
            )
        else:
            record["last_edit_error"] = f"edit fallito verso {state.active_kit}"

    return edited, unchanged


def run() -> int:
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_TO_BOT", "").strip()
    if not token or not chat_id:
        raise SystemExit("Mancano TELEGRAM_TOKEN o TELEGRAM_TO_BOT")

    state = base.KitState(
        event_id=f"UEFA_SIM{int(time.time())}",
        fallback_kit=FALLBACK,
        active_kit=FALLBACK,
    )
    state.ensure_compat()

    tg = base.Telegram(token, chat_id)
    layers = _dummy_layers()
    timeline = base._load_timeline()

    state.update_offset = base._drain_old_callbacks(tg)
    start = time.monotonic()
    deadline = start + DURATION
    idx = 0

    while idx < len(timeline) and timeline[idx]["at"] <= 0:
        base.set_espn_kit(state, timeline[idx]["kit"])
        idx += 1

    state.recap_message_id = send_recap(tg, state, DURATION)
    publish_initial(tg, state, layers)
    base._log(
        f"UEFA TEST AVVIATO | {LEAGUE_NAME} | event_id={state.event_id} | "
        f"active={state.active_kit}"
    )

    last_retry = 0.0

    try:
        while time.monotonic() < deadline:
            now = time.monotonic()
            elapsed = int(now - start)
            remaining = int(deadline - now)

            while idx < len(timeline) and elapsed >= int(timeline[idx]["at"]):
                _, _, changed = base.set_espn_kit(state, timeline[idx]["kit"])
                if changed:
                    refresh_all(tg, state, layers)
                edit_recap(tg, state, remaining)
                idx += 1

            for update in tg.get_callback_updates(state.update_offset, timeout=1):
                state.update_offset = int(update["update_id"]) + 1
                cb = update.get("callback_query") or {}
                callback_id = str(cb.get("id") or "")
                callback_data = str(cb.get("data") or "")

                handled, changed, answer = base.apply_callback(
                    state, callback_id, callback_data
                )
                if not handled:
                    continue

                tg.answer_callback(callback_id, answer)
                base._log(
                    f"CALLBACK {callback_data} | mode={state.kit_mode} | "
                    f"espn={state.espn_kit} | active={state.active_kit}"
                )
                if changed:
                    edited, unchanged = refresh_all(tg, state, layers)
                    base._log(
                        f"PROPAGAZIONE KIT | edit={edited} | invariati={unchanged}"
                    )
                edit_recap(tg, state, remaining)

            if now - last_retry >= 10:
                if any(rec.get("kit") != state.active_kit for rec in state.kit_media.values()):
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
                    "text": recap_text(state, 0) + "\n\n✅ <b>TEST UEFA TERMINATO</b>",
                    "parse_mode": "HTML",
                    "reply_markup": json.dumps({"inline_keyboard": []}),
                },
            )
        except Exception as exc:
            base._log(f"Chiusura recap UEFA fallita: {exc}")

    base._log("UEFA TEST TERMINATO")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
