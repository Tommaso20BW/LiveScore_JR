import os

import juve_bot_espn as bot


_ORIGINAL_TROVA_PARTITA = bot.trova_partita_oggi


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
        competitors = partita.get("competitors", [])
        _, _, home_raw, away_raw, _, _ = bot.parse_score(competitors)

        home_name = bot.esc(bot.translate_team(home_raw))
        away_name = bot.esc(bot.translate_team(away_raw))
        league_name = bot.esc(partita.get("league_name", ""))
        event_id = bot.esc(partita.get("event_id", ""))

        testo = (
            "<b>✅ PARTITA TROVATA DAL LIVE SCORE</b>\n\n"
            f"⚽️ {home_name} - {away_name}\n"
            f"🏆 {league_name}\n"
            f"🆔 <code>{event_id}</code>"
        )

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
bot.trova_partita_oggi = trova_partita_con_notifica


if __name__ == "__main__":
    bot.main()
