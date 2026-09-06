"""Genera una grafica stats ESPN e la invia esclusivamente a Bot JR."""

import argparse
import os

import juve_bot_espn as bot


ESPN_WEB_BASE = "https://site.web.api.espn.com/apis/site/v2/sports/soccer"


def fetch_event(event_id: str, league_slug: str) -> dict | None:
    data = bot.fetch_evento(event_id, league_slug)
    if data:
        return data

    # Alcune reti ricevono un 403 dal dominio storico site.api. Il dominio
    # web espone lo stesso summary e rende affidabile anche il test manuale.
    try:
        response = bot.SESSION.get(
            f"{ESPN_WEB_BASE}/{league_slug}/summary",
            params={
                "region": "us",
                "lang": "en",
                "contentorigin": "espn",
                "event": event_id,
            },
            headers={
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://www.espn.com",
                "Referer": "https://www.espn.com/",
                "User-Agent": "Mozilla/5.0 (compatible; LiveScore_JR/1.0)",
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        return data if (data.get("header") or {}).get("competitions") else None
    except Exception as exc:
        print(f"[{bot.now_it()}] ❌ Evento ESPN {event_id} non disponibile: {exc}")
        return None


def send_preview(event_id: str, league_slug: str, momento: str = "FT") -> bool:
    target = os.getenv("TELEGRAM_TO_BOT")
    if not bot.BOT_TOKEN or not target:
        raise RuntimeError("TELEGRAM_TOKEN o TELEGRAM_TO_BOT mancante")

    data = fetch_event(event_id, league_slug)
    if data is None:
        raise RuntimeError(f"Evento ESPN {event_id} non trovato in {league_slug}")

    competition = data["header"]["competitions"][0]
    competitors = competition.get("competitors") or []
    if len(competitors) < 2:
        raise RuntimeError("Evento ESPN senza due squadre")

    home_id, away_id, home_raw, away_raw, home_goals, away_goals = bot.parse_score(
        competitors
    )
    home_name = bot.esc(bot.translate_team(home_raw))
    away_name = bot.esc(bot.translate_team(away_raw))
    league_name = (data.get("header") or {}).get("league", {}).get(
        "name", league_slug
    )
    hashtag = f"{bot.get_league_emoji(league_slug)} {bot.build_hashtag(home_raw, away_raw)}"

    print(
        f"[{bot.now_it()}] 🧪 Preview stats {momento}: "
        f"{home_name} {home_goals}-{away_goals} {away_name}"
    )
    png_path = bot.recupera_e_genera_stats_html(
        data,
        home_id,
        away_id,
        home_name,
        away_name,
        home_goals,
        away_goals,
        momento,
        league_name,
        league_slug=league_slug,
        event_id=event_id,
    )

    # Impedisce a questo comando di usare per errore il canale principale.
    bot.CHAT_ID = target
    sent = bot.send_telegram_stats_photo(png_path, momento, hashtag)
    if sent:
        print(f"[{bot.now_it()}] ✅ Preview stats inviata esclusivamente a Bot JR")
    return sent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--league-slug", default="ita.1")
    parser.add_argument("--momento", choices=tuple(bot.MOMENTI_CONFIG), default="FT")
    args = parser.parse_args()
    return 0 if send_preview(args.event_id, args.league_slug, args.momento) else 1


if __name__ == "__main__":
    raise SystemExit(main())
