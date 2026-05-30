import sys
import json
import os
import importlib.util
import types
import time
import unittest.mock as mock
import requests

# ---------------------------------------------------------------------------
# Stub moduli opzionali (playwright, PIL, nacl) — non servono nel test
# ---------------------------------------------------------------------------
for mod in ["playwright.sync_api", "PIL", "PIL.Image", "nacl", "nacl.encoding", "nacl.public"]:
    if mod not in sys.modules:
        sys.modules[mod] = types.ModuleType(mod)

import playwright.sync_api as _pw
_pw.sync_playwright = mock.MagicMock()
import PIL.Image as _pil
_pil.open = mock.MagicMock()

# ---------------------------------------------------------------------------
# Import del bot
# ---------------------------------------------------------------------------
BOT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "juve_bot_alternative.py")
spec = importlib.util.spec_from_file_location("bot", BOT_PATH)
bot  = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)

# ---------------------------------------------------------------------------
# Patch e Wrappers
# ---------------------------------------------------------------------------
bot.time = mock.MagicMock()
bot.sys.exit = lambda code=0: (_ for _ in ()).throw(SystemExit(0))

bot.salva_stato_su_gist = lambda state: None
bot.leggi_stato_da_gist = lambda: None
bot.get_valid_token     = lambda: None
bot.get_canva_image     = lambda token: None

# Intercettiamo send_telegram per forzare un delay di 30 secondi tra i messaggi reali
_original_send_telegram = bot.send_telegram
def delayed_send_telegram(text):
    print(f"[Telegram Delay] Attendo 30 secondi prima di inviare...")
    time.sleep(30)
    _original_send_telegram(text)

bot.send_telegram = delayed_send_telegram

def _stats_solo_testo(data_espn, home_id, away_id, home_name, away_name,
                      home_goals, away_goals, momento, league_name=""):
    """Al posto del rendering grafico, manda un messaggio testo con le stats."""
    raw = bot._estrai_stats_espn(data_espn)
    def g(side, *keys):
        for k in keys:
            v = raw[side].get(k.lower())
            if v is not None:
                return v
        return "N/D"
    testo = (
        f"📊 <b>STATS {momento}</b>\n\n"
        f"{home_name} - {away_name}\n"
        f"Possesso: {g('home','possessionPct','possession')}% - {g('away','possessionPct','possession')}%\n"
        f"Tiri: {g('home','totalShots')} - {g('away','totalShots')}\n"
        f"In porta: {g('home','shotsOnTarget')} - {g('away','shotsOnTarget')}\n"
        f"Corner: {g('home','wonCorners','cornerKicks')} - {g('away','wonCorners','cornerKicks')}\n"
        f"Falli: {g('home','foulsCommitted')} - {g('away','foulsCommitted')}"
    )
    bot.send_telegram(testo)
    return "/tmp/fake_stats.png"

bot.recupera_e_genera_stats_html = _stats_solo_testo

def _stats_foto_testo(png_path, momento, hashtag):
    pass  # il testo è già stato inviato dentro _stats_solo_testo

bot.send_telegram_stats_photo = _stats_foto_testo

# ---------------------------------------------------------------------------
# Fetch dati ESPN (locale se disponibile, altrimenti API)
# ---------------------------------------------------------------------------
def fetch_data(event_id: str, league_slug: str) -> dict:
    local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"espn_{event_id}.json")
    if os.path.exists(local_path):
        print(f"📁 Dati locali: {local_path}")
        with open(local_path, encoding="utf-8") as f:
            return json.load(f)
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_slug}/summary"
    r = requests.get(url, params={"event": event_id}, timeout=20)
    r.raise_for_status()
    return r.json()

# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------
def replay(event_id: str, league_slug: str):
    print(f"\n🔄 Fetch ESPN: event={event_id}  slug={league_slug}")
    data = fetch_data(event_id, league_slug)

    # fetch_evento nel bot restituisce sempre questi stessi dati
    bot.fetch_evento = lambda eid, slug: data

    try:
        competitors = data["header"]["competitions"][0]["competitors"]
    except Exception:
        print("❌ Impossibile leggere competitors")
        return

    home_id, away_id, home_name, away_name, g_home, g_away = bot.parse_score(competitors)
    status, elapsed = bot.parse_status(data)
    events = bot.parse_events(data, home_name, away_name, home_id, away_id)

    print(f"⚽  {home_name} {g_home} – {g_away} {away_name}")
    print(f"📊  Status: {status} | elapsed: {elapsed}'")
    print(f"📋  Eventi parsed: {len(events)}")
    print()

    league_name = (data.get("leagues") or [{}])[0].get("name", league_slug)
    hashtag     = bot.build_hashtag(home_name, away_name)
    e_comp      = bot.get_league_emoji(league_slug)
    score_str   = bot.build_score_str(home_name, away_name, g_home, g_away)

    # Stato fresco
    state = {
        "event_id":              event_id,
        "sent_periods":          [],
        "goals_detected":        0,
        "prev_home_goals":       0,
        "prev_away_goals":       0,
        "sent_subs_groups":      [], # Tracciamento ID dei gruppi di cambi inviati
        "sent_cards":            [],
        "penalties_count":       0,
        "sent_stats":            [],
        "sent_failed_penalties": [],
    }

    # -----------------------------------------------------------------------
    # Ciclo principale eventi e periodi di gara
    # -----------------------------------------------------------------------

    # Inizio partita
    if status == "1H" and "1H" not in state["sent_periods"]:
        bot.send_telegram(f"<b>INIZIO PARTITA {bot.E_BOLT}</b>\n\n{home_name} - {away_name}\n\n{e_comp} {hashtag}")
        state["sent_periods"].append("1H")

    # Fine primo tempo
    if status == "HT" and "HT" not in state["sent_periods"]:
        bot.send_telegram(f"<b>FINE PRIMO TEMPO {bot.E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
        state["sent_periods"].append("HT")
        _stats_solo_testo(data, home_id, away_id, home_name, away_name, g_home, g_away, "HT", league_name)
        state["sent_stats"].append("HT")

    # Inizio secondo tempo
    if status == "2H" and "2H" not in state["sent_periods"]:
        bot.send_telegram(f"<b>INIZIO SECONDO TEMPO {bot.E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
        state["sent_periods"].append("2H")

    # Fine regolamentari
    if status in ("ET", "PEN", "AET") and "2H_END" not in state["sent_periods"] and "FT" not in state["sent_periods"]:
        bot.send_telegram(f"<b>FINE REGOLAMENTARI {bot.E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
        state["sent_periods"].append("2H_END")
        if status == "ET":
            _stats_solo_testo(data, home_id, away_id, home_name, away_name, g_home, g_away, "2H_END", league_name)
            state["sent_stats"].append("2H_END")

    # Supplementari
    if status == "ET":
        try:
            comp_status = data["header"]["competitions"][0].get("status", {})
            stype_name  = comp_status.get("type", {}).get("name", "").upper()
            et_period   = comp_status.get("period", 1)
        except Exception:
            stype_name, et_period = "", 1

        is_et_halftime = any(kw in stype_name for kw in ("HALFTIME", "HALF_TIME", "HT_ET", "EXTRA_TIME_HALF"))
        is_second_et   = (et_period >= 4 or (elapsed >= 106 and et_period >= 3))

        if "1ET_START" not in state["sent_periods"] and not is_et_halftime and not is_second_et:
            bot.send_telegram(f"<b>INIZIO 1° TEMPO SUPPLEMENTARE {bot.E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
            state["sent_periods"].append("1ET_START")

        if (is_et_halftime or is_second_et) and "1ET_END" not in state["sent_periods"]:
            bot.send_telegram(f"<b>FINE 1° TEMPO SUPPLEMENTARE {bot.E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
            state["sent_periods"].append("1ET_END")

        if is_second_et and "2ET_START" not in state["sent_periods"]:
            bot.send_telegram(f"<b>INIZIO 2° TEMPO SUPPLEMENTARE {bot.E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
            state["sent_periods"].append("2ET_START")

    # Intervallo supplementari esplicito
    if status == "HT_ET":
        if "1ET_START" not in state["sent_periods"]:
            state["sent_periods"].append("1ET_START")
        if "1ET_END" not in state["sent_periods"]:
            bot.send_telegram(f"<b>FINE 1° TEMPO SUPPLEMENTARE {bot.E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
            state["sent_periods"].append("1ET_END")

    # Lotteria dei Rigori Finale (Aggiornamento interattivo ad ogni tiro)
    if status == "PEN":
        if "ET_END_PENS" not in state["sent_periods"]:
            if "2ET_START" in state["sent_periods"] or "1ET_START" in state["sent_periods"]:
                bot.send_telegram(f"<b>FINE SUPPLEMENTARI {bot.E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
            state["sent_periods"].append("ET_END_PENS")

        shootout_events = [e for e in events if e["type"] in ("shootout goal", "shootout miss", "shootout saved")]
        total_kicks = len(shootout_events)

        if total_kicks > state["penalties_count"]:
            home_pen_icons, away_pen_icons = [], []
            for e in shootout_events:
                icon = bot.E_PEN_OK if e["type"] == "shootout goal" else bot.E_PEN_KO
                if e["team_id"] == home_id:
                    home_pen_icons.append(icon)
                else:
                    away_pen_icons.append(icon)

            bot.send_telegram(
                f"<b>RIGORI 🥅</b>\n\n"
                f"{home_name}: " + "".join(home_pen_icons or ["-"]) + "\n"
                f"{away_name}: " + "".join(away_pen_icons or ["-"])
            )
            state["penalties_count"] = total_kicks

    # Goal (Solo nei tempi regolamentari/supplementari)
    if status != "PEN":
        total_goals_now = g_home + g_away
        if total_goals_now > state["goals_detected"]:
            goal_events = [e for e in events if e["type"] in ("goal", "own goal", "penalty goal")]
            home_goal_count = 0
            away_goal_count = 0
            for e in sorted(goal_events, key=lambda x: x["minute"]):
                is_home = (e["type"] != "own goal" and e["team_id"] == home_id) or \
                          (e["type"] == "own goal" and e["team_id"] == away_id)
                if is_home:
                    home_goal_count += 1
                    gh, ga = home_goal_count, away_goal_count
                    goal_score = f"<b>{home_name} {gh}</b>-{ga} {away_name}"
                else:
                    away_goal_count += 1
                    gh, ga = home_goal_count, away_goal_count
                    goal_score = f"{home_name} {gh}-<b>{ga} {away_name}</b>"

                ps = bot.fmt_player(e["player_name"])
                if e["type"] == "own goal":
                    ps += " (Autogol)"
                elif e["type"] == "penalty goal":
                    ps += " (Rig.)"

                bot.send_telegram(
                    f"<b>GOAL {bot.E_MIC}</b>\n\n{goal_score}\n"
                    f"{bot.E_BALL} <i>{e['minute']}' {ps}</i>\n\n{e_comp} {hashtag}"
                )

            state["goals_detected"]    = total_goals_now
            state["prev_home_goals"]   = g_home
            state["prev_away_goals"]   = g_away

    # Raggruppamento dei cambi (stesso minuto per singola squadra)
    raw_subs = [x for x in events if x["type"] == "substitution"]
    subs_by_team_and_minute = {}
    for s in raw_subs:
        key = (s["team_id"], s["minute"])
        if key not in subs_by_team_and_minute:
            subs_by_team_and_minute[key] = []
        subs_by_team_and_minute[key].append(s)

    for (team_id, minute), group in sorted(subs_by_team_and_minute.items(), key=lambda x: x[0][1]):
        # Identificativo unico del gruppo basato sulle UID dei cambi
        group_id = f"sub_group_{team_id}_{minute}_" + "_".join(sorted([e["uid"] for e in group]))
        if group_id not in state["sent_subs_groups"]:
            team_title = home_name.upper() if team_id == home_id else away_name.upper()
            
            # Costruiamo le linee dei giocatori entrati/usciti per questo specifico minuto
            lines = []
            for e in group:
                lines.append(f"{bot.E_UP} {bot.fmt_player(e['assist_name'])}\n{bot.E_DOWN} {bot.fmt_player(e['player_name'])}")
            
            subs_content = "\n\n".join(lines)
            bot.send_telegram(
                f"<b>CAMBIO {team_title} {bot.E_SUB} ({minute}')</b>\n\n"
                f"{subs_content}\n\n"
                f"{e_comp} {hashtag}"
            )
            state["sent_subs_groups"].append(group_id)

    # Cartellini rossi / doppio giallo
    for e in events:
        if e["type"] in ("red card", "second yellow card"):
            card_id = f"card_{e['minute']}_{e['player_name']}".replace(" ", "_")
            if card_id not in state["sent_cards"]:
                bot.send_telegram(
                    f"<b>CARTELLINO ROSSO {bot.E_RED}</b>\n\n"
                    f"🔚 <i>{e['minute']}' {bot.fmt_player(e['player_name'])}</i>\n\n{e_comp} {hashtag}"
                )
                state["sent_cards"].append(card_id)

    # Rigori sbagliati (Solo nei tempi regolamentari/supplementari)
    for e in events:
        if e["type"] in ("penalty missed", "penalty saved"):
            pen_id = f"failpen_{e['minute']}_{e['player_name']}".replace(" ", "_")
            if pen_id not in state["sent_failed_penalties"]:
                team_name_pen = home_name if e["team_id"] == home_id else away_name
                bot.send_telegram(
                    f"<b>RIGORE SBAGLIATO {team_name_pen.upper()} {bot.E_PEN_KO}</b>\n\n"
                    f"🥅 <i>{e['minute']}' {bot.fmt_player(e['player_name'])}</i>\n\n{e_comp} {hashtag}"
                )
                state["sent_failed_penalties"].append(pen_id)

    # Fine partita definitiva
    comp_state_espn = (
        data.get("header", {}).get("competitions", [{}])[0]
            .get("status", {}).get("type", {}).get("state", "")
    )
    is_finished = status in ("FT", "AET") or (status == "PEN" and comp_state_espn == "post")

    if is_finished and "FT" not in state["sent_periods"]:
        home_scorers, away_scorers = [], []
        for e in events:
            if e["type"] in ("goal", "own goal", "penalty goal"):
                ps = bot.fmt_player(e["player_name"])
                if e["type"] == "own goal":
                    ps += " (Autogol)"
                elif e["type"] == "penalty goal":
                    ps += " (Rig.)"
                tid = e["team_id"]
                if e["type"] == "own goal":
                    tid = away_id if tid == home_id else home_id
                (home_scorers if tid == home_id else away_scorers).append(f"{e['minute']}' {ps}")

        scorers_line = ""
        if home_scorers or away_scorers:
            parts = [", ".join(home_scorers)] if home_scorers else []
            if away_scorers:
                parts.append(", ".join(away_scorers))
            scorers_line = f"{bot.E_BALL} <i>{' // '.join(parts)}</i>\n"

        has_shootout = "ET_END_PENS" in state["sent_periods"] or status == "PEN" or len(data.get("shootout", [])) > 0
        if has_shootout:
            home_pen_goals = sum(1 for e in events if e["type"] == "shootout goal" and e["team_id"] == home_id)
            away_pen_goals = sum(1 for e in events if e["type"] == "shootout goal" and e["team_id"] == away_id)
            if home_pen_goals > 0 or away_pen_goals > 0:
                if home_pen_goals > away_pen_goals:
                    score_str = f"<b>{home_name} {g_home}-{g_away} {away_name}</b>\n(d.c.r. <b>{home_pen_goals}</b>-{away_pen_goals})"
                else:
                    score_str = f"<b>{home_name} {g_home}-{g_away} {away_name}</b>\n(d.c.r. {home_pen_goals}-<b>{away_pen_goals}</b>)"

        msg_finale = f"<b>FINE PARTITA {bot.E_FLAG}</b>\n\n{score_str}\n{scorers_line}\n{e_comp} {hashtag}"
        bot.send_telegram(msg_finale)
        _stats_solo_testo(data, home_id, away_id, home_name, away_name, g_home, g_away, "FT", league_name)
        state["sent_periods"].append("FT")

    print(f"\n✅ Fine replay — sent_periods: {state['sent_periods']}")

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python test_bot_replay.py <event_id> <league_slug>")
        print("Es:  python test_bot_replay.py 401862897 uefa.champions")
        sys.exit(1)
    replay(sys.argv[1], sys.argv[2])
