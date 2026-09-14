"""
Manual GOAL graphics for LiveScore_JR.

This script DOES NOT use Canva for the player poses.
It uses the exact PNG poses already stored in:
    assets/goal_graphics/players/<player_slug>/

The actual filename is resolved by goal_graphics.py from:
- player
- kit: home / away / third
- pose: arms_crossed / pointing

Batch extras:
- kit="all"  -> creates home + away + third
- pose="both" -> creates arms_crossed + pointing
So one player can generate up to 6 variants in one run.
"""

from __future__ import annotations

import io
import json
import os
import re
from pathlib import Path

import goal_graphics as gg


VALID_KITS = ("home", "away", "third")
VALID_POSES = ("arms_crossed", "pointing")
VALID_GOAL_TYPES = ("goal", "penalty goal", "own goal")

OUTPUT_DIR = Path("manual_goal_output")


def env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None else value.strip()


def env_int(name: str, default: int = 0) -> int:
    raw = env(name, str(default))
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} deve essere un numero intero, ricevuto: {raw!r}") from exc


def truthy(value: str, default: bool = False) -> bool:
    if value == "":
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def safe_name(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip())
    return value.strip("_") or "goal"


def available_players() -> str:
    try:
        return ", ".join(player.name for player in gg.load_players())
    except Exception:
        return "(impossibile leggere goal_players.json)"


def parse_items(raw: str) -> list[dict]:
    if not raw:
        raise ValueError("GOAL_ITEMS_JSON è vuoto")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"GOAL_ITEMS_JSON non è JSON valido: {exc}") from exc

    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list) or not payload:
        raise ValueError("GOAL_ITEMS_JSON deve essere un oggetto oppure una lista non vuota")

    items: list[dict] = []
    for i, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Elemento #{i}: deve essere un oggetto JSON")

        player = str(item.get("player", "")).strip()
        if not player:
            raise ValueError(f"Elemento #{i}: manca 'player'")

        kit = str(item.get("kit", "home")).strip().lower()
        pose = str(item.get("pose", "arms_crossed")).strip().lower()
        goal_type = str(item.get("goal_type", "goal")).strip().lower()

        if kit not in {*VALID_KITS, "all"}:
            raise ValueError(
                f"Elemento #{i}: kit {kit!r} non valido. "
                "Usa home, away, third oppure all."
            )
        if pose not in {*VALID_POSES, "both"}:
            raise ValueError(
                f"Elemento #{i}: pose {pose!r} non valida. "
                "Usa arms_crossed, pointing oppure both."
            )
        if goal_type not in VALID_GOAL_TYPES:
            raise ValueError(
                f"Elemento #{i}: goal_type {goal_type!r} non valido. "
                "Usa goal, penalty goal oppure own goal."
            )

        minute = str(item.get("minute", "1")).strip() or "1"

        items.append(
            {
                "player": player,
                "kit": kit,
                "pose": pose,
                "minute": minute,
                "goal_type": goal_type,
                "competition": str(item.get("competition", "")).strip(),
            }
        )

    return items


def expand_items(items: list[dict]) -> list[dict]:
    expanded: list[dict] = []

    for item in items:
        kits = VALID_KITS if item["kit"] == "all" else (item["kit"],)
        poses = VALID_POSES if item["pose"] == "both" else (item["pose"],)

        # Own goal intentionally has no player silhouette in the approved renderer.
        if item["goal_type"] == "own goal":
            poses = (poses[0],)

        for kit in kits:
            for pose in poses:
                expanded.append({**item, "kit": kit, "pose": pose})

    return expanded


def validate_player_asset(player_name: str, kit: str, pose: str, goal_type: str) -> gg.Player | None:
    player = gg.find_player(player_name)

    if player is None:
        raise ValueError(
            f"Giocatore non trovato nel registro: {player_name!r}\n"
            f"Giocatori disponibili: {available_players()}"
        )

    if goal_type == "own goal":
        return player

    player_path = gg.resolve_player_path(player, kit, pose)
    if not player_path.is_file():
        raise FileNotFoundError(
            "Posa non trovata nel repository:\n"
            f"  giocatore: {player.name}\n"
            f"  kit: {kit}\n"
            f"  posa: {pose}\n"
            f"  file atteso: {player_path}"
        )

    return player


def render_one(
    *,
    player_name: str,
    kit: str,
    pose: str,
    minute: str,
    goal_type: str,
    competition: str,
    home_name: str,
    away_name: str,
    home_id: str,
    away_id: str,
    home_goals: int,
    away_goals: int,
) -> tuple[bytes, gg.RenderedGoal]:
    validate_player_asset(player_name, kit, pose, goal_type)

    rendered = gg.render_goal_card(
        scorer_name=player_name,
        minute=minute,
        home_name=home_name,
        away_name=away_name,
        home_goals=home_goals,
        away_goals=away_goals,
        kit=kit,
        goal_type=goal_type,
        home_id=home_id,
        away_id=away_id,
        pose=pose,
        event_key=f"manual:{player_name}:{kit}:{pose}:{minute}:{goal_type}",
        competition=competition,
    )

    if not rendered.png:
        raise RuntimeError(f"Renderer GOAL non ha restituito il PNG per {player_name}")

    return rendered.png, rendered


def send_single_to_bot(bot, caption: str, png_bytes: bytes) -> None:
    response = bot._tg_post(
        "sendPhoto",
        data={
            "chat_id": bot.CHAT_ID,
            "caption": caption,
            "parse_mode": "HTML",
        },
        files={"photo": ("goal.png", png_bytes, "image/png")},
        timeout=30,
    )
    if response is None:
        raise RuntimeError("Telegram sendPhoto: nessuna risposta")
    response.raise_for_status()


def send_album_to_bot(bot, entries: list[tuple[str, str, bytes]]) -> None:
    """Send in Telegram albums of max 10 images."""
    for start in range(0, len(entries), 10):
        chunk = entries[start:start + 10]
        media = []
        files = {}

        for idx, (filename, caption, png_bytes) in enumerate(chunk):
            attach = f"photo{idx}"
            media.append(
                {
                    "type": "photo",
                    "media": f"attach://{attach}",
                    "caption": caption,
                    "parse_mode": "HTML",
                }
            )
            files[attach] = (filename, png_bytes, "image/png")

        response = bot._tg_post(
            "sendMediaGroup",
            data={
                "chat_id": bot.CHAT_ID,
                "media": json.dumps(media, ensure_ascii=False),
            },
            files=files,
            timeout=45,
        )
        if response is None:
            raise RuntimeError("Telegram sendMediaGroup: nessuna risposta")
        response.raise_for_status()


def caption_for(player: str, kit: str, pose: str, minute: str) -> str:
    pose_label = {
        "arms_crossed": "BRACCIA INCROCIATE",
        "pointing": "INDICA",
    }[pose]
    return (
        f"<b>GOAL GRAPHIC</b>\n\n"
        f"{player}\n"
        f"{kit.upper()} • {pose_label} • {minute.rstrip(chr(39) + '’')}’"
    )


def main() -> None:
    home_name = env("HOME_NAME", "Juventus")
    away_name = env("AWAY_NAME", "Sassuolo")
    home_id = env("HOME_ID", "111")
    away_id = env("AWAY_ID", "3997")
    home_goals = env_int("HOME_GOALS", 0)
    away_goals = env_int("AWAY_GOALS", 0)
    default_competition = env("COMPETITION", "Serie A")

    send_to_bot_jr = truthy(env("SEND_TO_BOT_JR", "true"), True)
    send_as_album = truthy(env("SEND_AS_ALBUM", "true"), True)

    items = expand_items(parse_items(env("GOAL_ITEMS_JSON")))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    telegram_entries: list[tuple[str, str, bytes]] = []

    print(f"Varianti da generare: {len(items)}", flush=True)

    for index, item in enumerate(items, start=1):
        competition = item["competition"] or default_competition

        print(
            f"[{index}/{len(items)}] "
            f"{item['player']} | {item['kit']} | {item['pose']} | "
            f"{item['minute']} | {item['goal_type']}",
            flush=True,
        )

        png_bytes, rendered = render_one(
            player_name=item["player"],
            kit=item["kit"],
            pose=item["pose"],
            minute=item["minute"],
            goal_type=item["goal_type"],
            competition=competition,
            home_name=home_name,
            away_name=away_name,
            home_id=home_id,
            away_id=away_id,
            home_goals=home_goals,
            away_goals=away_goals,
        )

        filename = (
            f"{index:02d}_"
            f"{safe_name(item['player'])}_"
            f"{item['kit']}_"
            f"{item['pose']}.png"
        )
        output_path = OUTPUT_DIR / filename
        output_path.write_bytes(png_bytes)

        print(
            f"OK: {output_path} | player asset: {rendered.player_path}",
            flush=True,
        )

        caption = caption_for(
            item["player"], item["kit"], item["pose"], item["minute"]
        )
        telegram_entries.append((filename, caption, png_bytes))

    if send_to_bot_jr:
        import juve_bot_espn as bot

        if not bot.BOT_TOKEN or not bot.CHAT_ID:
            raise RuntimeError(
                "Per Bot JR servono TELEGRAM_TOKEN e TELEGRAM_TO "
                "(nel workflow TELEGRAM_TO viene impostato su TELEGRAM_TO_BOT)."
            )

        if send_as_album and len(telegram_entries) > 1:
            send_album_to_bot(bot, telegram_entries)
            print("Bot JR: immagini inviate come album.", flush=True)
        else:
            for filename, caption, png_bytes in telegram_entries:
                send_single_to_bot(bot, caption, png_bytes)
                print(f"Bot JR: inviato {filename}", flush=True)

    print(f"Fatto. Generate {len(telegram_entries)} immagini.", flush=True)


if __name__ == "__main__":
    main()
