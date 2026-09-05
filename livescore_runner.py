import os
from datetime import datetime

from PIL import Image

import juve_bot_espn as bot


_ORIGINAL_TROVA_PARTITA = bot.trova_partita_oggi


def _asset_status(kit: str) -> str:
    root = bot.goal_graphics.DEFAULT_ASSET_DIR
    files = [root / folder / filename for folder, filename in (
        ("backgrounds", f"{kit}.png"), ("backgrounds", "saved.png"),
        ("overlays", "front_goal.png"), ("overlays", "front_saved.png"),
        ("word_textures", f"{kit}.png"), ("word_textures", "saved.png"),
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
    asset_status = _asset_status(kit) if enabled and not friendly and kit in (
        "home", "away", "third") else "non verificati"
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
        f"Kit Juventus: {kit_label}\n\n"
        "🎨 <b>GRAFICHE</b>\n"
        f"GOAL / SAVED: {graphics_status}\n"
        f"Background e scritte: {bot.esc(asset_status)}\n\n"
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


def _notifica_partita_trovata_bot(partita: dict) -> None:
    """Invia al canale Bot JR la conferma che il LiveScore ha agganciato la gara."""
    bot_chat_id = os.getenv("TELEGRAM_TO_BOT")

    if not bot.BOT_TOKEN or not bot_chat_id:
        print(
            f"[{bot.now_it()}] ⚠️  TELEGRAM_TOKEN o TELEGRAM_TO_BOT mancanti "
            "— notifica partita trovata saltata"
        )
        return

    try:
        # Un solo summary per orario, stadio e kit. Se ESPN non risponde,
        # la notifica usa comunque i dati gia' acquisiti dalla discovery.
        try:
            data = bot.fetch_evento(partita["event_id"], partita["league_slug"])
        except Exception:
            data = None
        testo = messaggio_partita_trovata(partita, data)

        r = bot._tg_post(
            "sendMessage",
            payload={
                "chat_id": bot_chat_id,
                "text": testo,
                "parse_mode": "HTML",
            },
        )
        r.raise_for_status()

        print(
            f"[{bot.now_it()}] 🧪 Notifica PARTITA TROVATA inviata a Bot JR "
            f"(event_id={partita.get('event_id', '')})"
        )

    except Exception as e:
        # La notifica di servizio NON deve mai impedire l'avvio del LiveScore.
        print(f"[{bot.now_it()}] ⚠️  Errore notifica Bot JR: {e}")


def trova_partita_con_notifica(team_id: str):
    partita = _ORIGINAL_TROVA_PARTITA(team_id)

    if partita:
        _notifica_partita_trovata_bot(partita)

    return partita


# Il bot originale resta intatto: sostituiamo solo la funzione di discovery
# durante questo run, aggiungendo la notifica sul canale Bot.
if __name__ == "__main__":
    bot.trova_partita_oggi = trova_partita_con_notifica
    bot.main()
