import json
import os
from datetime import datetime

from PIL import Image

import juve_bot_espn as bot
from dynamic_kit_runtime import DynamicKitRuntime


# Installa gli hook una sola volta. Il cuore juve_bot_espn.py resta invariato.
KIT_RUNTIME = DynamicKitRuntime(bot).install()
if os.getenv('MANUAL_GRAPHICS_BRIDGE') == '1':
    from manual_graphics.live_bridge import install as install_manual_bridge
    install_manual_bridge(bot, KIT_RUNTIME)
_ORIGINAL_TROVA_PARTITA = bot.trova_partita_oggi


def _asset_status(kit: str, competition: str = '') -> str:
    from portrait_graphics import theme
    key = theme(kit, competition)
    saved_key = theme(kit, competition, True)
    root = bot.goal_graphics.DEFAULT_ASSET_DIR
    files = [root / folder / filename for folder, filename in (
        ("portrait", f"{key}_goal_1086x1448.png"),
        ("portrait", f"{saved_key}_clean_1086x1448.png"),
        ("portrait", f"{key}_clean_1086x1448.png"),
        ("overlays", "front_goal.png"), ("overlays", "front_saved.png"),
        ("word_textures", f"{kit}.png"),
    )]
    missing = []
    for path in files:
        try:
            with Image.open(path) as image:
                image.verify()
        except (OSError, ValueError):
            missing.append(f"{path.parent.name}/{path.name}")
    return "disponibili" if not missing else "da controllare: " + ", ".join(missing)


def messaggio_partita_trovata(partita: dict, data: dict | None = None) -> str:
    """Riepilogo di servizio; non cambia i testi delle notifiche partita."""
    data = data or {}
    competitions = (data.get("header") or {}).get("competitions") or []
    competition = {**partita.get("competition", {}),
                   **(competitions[0] if competitions else {})}
    competitors = competition.get("competitors") or partita.get("competitors", [])
    home_id, away_id, home_raw, away_raw, _, _ = bot.parse_score(competitors)
    juventus_match = bot.JUVE_ID in (str(home_id), str(away_id))
    home, away = (bot.esc(bot.translate_team(name)) for name in (home_raw, away_raw))
    league_slug = partita.get("league_slug", "")
    league_name = partita.get("league_name", "")
    kit_data = data if competitions else {**data, "header": {"competitions": [competition]}}
    try:
        kit = bot.rileva_kit_juve(kit_data, home_id, away_id, home_raw, away_raw,
                                 league_slug, league_name)
    except Exception:
        kit = bot.determina_kit(home_id, away_id, league_slug, league_name)
    kit_label = {"home": "Home", "away": "Away", "third": "Third"}.get(kit, "Non disponibile")
    date_raw = competition.get("date") or partita.get("date", "")
    try:
        kickoff = datetime.fromisoformat(date_raw.replace("Z", "+00:00"))
        if kickoff.tzinfo is None:
            raise ValueError("orario senza fuso")
        kickoff_text = kickoff.astimezone(bot.ITALY_TZ).strftime("%d/%m/%Y · %H:%M")
    except (ValueError, TypeError, AttributeError):
        kickoff_text = "Orario non disponibile"
    venue = ((data.get("gameInfo") or {}).get("venue")
             or competition.get("venue") or {})
    venue_name = venue.get("fullName") or "Stadio non disponibile"
    enabled = bot.GOAL_GRAPHICS_ENABLED
    friendly = bot.is_friendly_competition(league_slug, league_name)
    graphics_status = "disabilitate (amichevole)" if friendly else (
        "abilitate" if enabled else "disabilitate")
    asset_status = _asset_status(kit, league_slug) if enabled and not friendly and kit in (
        "home", "away", "third") and juventus_match else None

    mode_label = KIT_RUNTIME.mode_label_for(partita.get("event_id"))
    kit_line = ""
    if juventus_match:
        kit_line = f"Kit Juventus: {kit_label}\n"
        if mode_label:
            kit_line += f"Modalità kit: {mode_label}\n"

    asset_line = f"Background e scritte: {bot.esc(asset_status)}\n" if asset_status else ""
    graphics_section = (
        "🎨 <b>GRAFICHE</b>\n"
        f"GOAL / SAVED: {graphics_status}\n{asset_line}\n"
    ) if juventus_match else ""
    sources = []
    for name, team_id in ((home_raw, home_id), (away_raw, away_id)):
        try:
            _, source = bot.goal_graphics.resolve_team_logo_source(
                name, team_id, bot.goal_graphics.DEFAULT_ASSET_DIR)
        except Exception:
            source = "Non disponibile"
        sources.append(source)
    channel = os.getenv("LIVE_SCORE_CHANNEL_NAME") or (
        "Bot JR" if bot.CHAT_ID and bot.CHAT_ID == os.getenv("TELEGRAM_TO_BOT")
        else "Juventus Reborn")
    delay = bot.STATS_DELAY_SECONDS
    delay_text = f"{delay // 60} minuti" if delay % 60 == 0 else f"{delay} secondi"
    return (
        "✅ <b>PARTITA TROVATA</b>\n\n"
        f"{home} — {away}\n"
        f"{bot.esc(league_name)} · {bot.esc(venue_name)}\n"
        f"{kickoff_text}\n"
        f"{kit_line}\n"
        f"{graphics_section}"
        "🛡 <b>LOGHI</b>\n"
        f"{home}: {sources[0]}\n{away}: {sources[1]}\n\n"
        "⚙️ <b>LIVE SCORE</b>\n"
        f"Canale: {bot.esc(channel)}\n"
        f"Statistiche: +{delay_text} da fine tempo/partita\n\n"
        "📋 <b>ESPN</b>\n"
        f"Evento: <code>{bot.esc(partita.get('event_id', ''))}</code>\n"
        f"Squadre: {home} <code>{bot.esc(home_id)}</code> · "
        f"{away} <code>{bot.esc(away_id)}</code>"
    )


def _response_message_id(response) -> int | None:
    try:
        payload = response.json()
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    try:
        value = (payload.get("result") or {}).get("message_id")
        return int(value) if value is not None else None
    except (TypeError, ValueError, AttributeError):
        return None


def _notifica_partita_trovata_bot(partita: dict) -> None:
    """Invia al canale Bot JR la conferma che il LiveScore ha agganciato la gara."""
    bot_chat_id = os.getenv("TELEGRAM_TO_BOT")

    if not bot.BOT_TOKEN or not bot_chat_id:
        bot.log_line(
            "WARN",
            "TELEGRAM",
            "TELEGRAM_TOKEN o TELEGRAM_TO_BOT mancanti; notifica di servizio saltata",
        )
        return

    try:
        # Un solo summary per orario, stadio e kit. Il runtime non aggiunge
        # richieste ESPN: da qui in poi controllerà uniform.type dentro ogni
        # normale fetch_evento già eseguito dal LiveScore.
        try:
            data = bot.fetch_evento(partita["event_id"], partita["league_slug"])
        except Exception:
            data = None

        KIT_RUNTIME.prepare_match(partita, data)
        testo = messaggio_partita_trovata(partita, data)

        payload = {
            "chat_id": bot_chat_id,
            "text": testo,
            "parse_mode": "HTML",
        }
        keyboard = KIT_RUNTIME.keyboard_for_current()
        if keyboard:
            payload["reply_markup"] = json.dumps(
                keyboard,
                ensure_ascii=False,
            )

        r = bot._tg_post("sendMessage", payload=payload)
        r.raise_for_status()

        message_id = _response_message_id(r)
        if message_id:
            KIT_RUNTIME.attach_recap(
                message_id,
                bot_chat_id,
                lambda: messaggio_partita_trovata(
                    partita,
                    KIT_RUNTIME.latest_summary or data,
                ),
            )

        bot.log_line(
            "DEBUG",
            "TELEGRAM",
            f"Notifica di servizio inviata | event_id={partita.get('event_id', '')}",
        )

    except Exception as e:
        # La notifica di servizio NON deve mai impedire l'avvio del LiveScore.
        bot.log_line("WARN", "TELEGRAM", f"Notifica di servizio non inviata: {e}")


def trova_partita_con_notifica(team_id: str):
    partita = _ORIGINAL_TROVA_PARTITA(team_id)

    if partita:
        _notifica_partita_trovata_bot(partita)

    return partita


# Il bot originale resta intatto: sostituiamo solo la funzione di discovery
# durante questo run, aggiungendo notifica e controllo kit dinamico.
if __name__ == "__main__":
    bot.trova_partita_oggi = trova_partita_con_notifica
    bot.main()
