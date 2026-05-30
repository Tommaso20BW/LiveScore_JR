"""
test_bot_replay.py
==================
Simula il ciclo del bot su una partita già finita (o live).
Recupera i dati reali ESPN e stampa ogni messaggio Telegram
che sarebbe stato inviato, nell'ordine corretto.

Uso:
    python test_bot_replay.py <event_id> <league_slug>
    python test_bot_replay.py 401862897 uefa.champions
"""

import sys
import json
import requests

# ---------------------------------------------------------------------------
# Import delle funzioni dal bot (senza eseguire main)
# ---------------------------------------------------------------------------
sys.path.insert(0, ".")

# Patch preventiva: disabilita Telegram, Gist, Canva, sys.exit prima dell'import
import unittest.mock as mock

_exit_called = False

def _fake_exit(code=0):
    global _exit_called
    _exit_called = True
    raise SystemExit(0)

# Patch moduli opzionali che potrebbero non essere installati
import importlib, types

for mod in ["playwright.sync_api", "PIL", "PIL.Image", "nacl", "nacl.encoding", "nacl.public"]:
    if mod not in sys.modules:
        sys.modules[mod] = types.ModuleType(mod)

# Stub sync_playwright
import playwright.sync_api as _pw
_pw.sync_playwright = mock.MagicMock()

# Stub PIL.Image
import PIL.Image as _pil
_pil.open = mock.MagicMock()

# ---------------------------------------------------------------------------
# Import del bot
# ---------------------------------------------------------------------------
import importlib.util, os

BOT_PATH = os.path.join(os.path.dirname(__file__), "juve_bot_alternative.py")
spec = importlib.util.spec_from_file_location("bot", BOT_PATH)
bot  = importlib.util.module_from_spec(spec)

# Inietta env vars fake per evitare crash
os.environ.setdefault("TELEGRAM_TOKEN", "fake")
os.environ.setdefault("TELEGRAM_TO",    "fake")
os.environ.setdefault("GH_PAT",         "fake")
os.environ.setdefault("GITHUB_REPOSITORY", "fake/fake")
os.environ.setdefault("GIST_ID",        "fake")

spec.loader.exec_module(bot)

# ---------------------------------------------------------------------------
# Intercetta i messaggi Telegram
# ---------------------------------------------------------------------------
sent_messages = []

def fake_send_telegram(text: str):
    sent_messages.append(("MSG", text))
    print(f"\n{'='*60}")
    print(f"📨 TELEGRAM MESSAGE:")
    print(text)

def fake_send_telegram_with_photo(text: str, photo_bytes):
    sent_messages.append(("MSG+PHOTO", text))
    print(f"\n{'='*60}")
    print(f"📨 TELEGRAM MESSAGE + FOTO:")
    print(text)

def fake_send_telegram_stats_photo(png_path: str, momento: str, hashtag: str):
    sent_messages.append(("STATS", momento))
    print(f"\n{'='*60}")
    print(f"📊 STATS PHOTO → momento={momento}  {hashtag}")

def fake_recupera_stats(*args, **kwargs):
    return "/tmp/fake_stats.png"

def fake_salva_gist(state):
    pass  # silenzioso

def fake_leggi_gist():
    return None

def fake_get_valid_token():
    return None

def fake_get_canva_image(token):
    return None

# Applica le patch
bot.send_telegram              = fake_send_telegram
bot.send_telegram_with_photo   = fake_send_telegram_with_photo
bot.send_telegram_stats_photo  = fake_send_telegram_stats_photo
bot.recupera_e_genera_stats_html = fake_recupera_stats
bot.salva_stato_su_gist        = fake_salva_gist
bot.leggi_stato_da_gist        = fake_leggi_gist
bot.get_valid_token            = fake_get_valid_token
bot.get_canva_image            = fake_get_canva_image
bot.time                       = mock.MagicMock()  # azzera tutti i sleep
bot.sys.exit                   = _fake_exit

# ---------------------------------------------------------------------------
# Fetch dati ESPN reali
# ---------------------------------------------------------------------------
def fetch_data(event_id: str, league_slug: str) -> dict:
    local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"espn_{event_id}.json")
    if os.path.exists(local_path):
        print(f"📁 Usando dati locali: {local_path}")
        with open(local_path, encoding="utf-8") as f:
            return json.load(f)
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_slug}/summary"
    r = requests.get(url, params={"event": event_id}, timeout=20)
    r.raise_for_status()
    return r.json()

# ---------------------------------------------------------------------------
# Replay del ciclo
# ---------------------------------------------------------------------------
def replay(event_id: str, league_slug: str):
    global _exit_called
    _exit_called = False

    print(f"\n{'='*60}")
    print(f"🔄 Fetch ESPN: event={event_id}  slug={league_slug}")
    data = fetch_data(event_id, league_slug)

    # Patch fetch_evento per restituire sempre gli stessi dati (già scaricati)
    bot.fetch_evento = lambda eid, slug: data

    # Stato iniziale vuoto (come bot avviato da zero)
    state = {
        "event_id":              event_id,
        "sent_periods":          [],
        "goals_detected":        0,
        "prev_home_goals":       0,
        "prev_away_goals":       0,
        "sent_subs":             [],
        "sent_cards":            [],
        "penalties_count":       0,
        "sent_stats":            [],
        "sent_failed_penalties": [],
    }

    # Info partita
    try:
        competitors = data["header"]["competitions"][0]["competitors"]
    except Exception:
        print("❌ Impossibile leggere competitors")
        return

    home_id, away_id, home_name, away_name, g_home, g_away = bot.parse_score(competitors)
    status, elapsed = bot.parse_status(data)
    events = bot.parse_events(data, home_name, away_name, home_id, away_id)
    hashtag = bot.build_hashtag(home_name, away_name)
    e_comp  = bot.get_league_emoji(league_slug)
    score_str = bot.build_score_str(home_name, away_name, g_home, g_away)

    print(f"⚽  {home_name} {g_home} – {g_away} {away_name}")
    print(f"📊  Status: {status}  |  elapsed: {elapsed}'")
    print(f"📋  Eventi parsed: {len(events)}")

    # Stampa tutti gli eventi trovati
    print(f"\n--- EVENTI TROVATI ---")
    for e in events:
        print(f"  [{e['type']:20s}] min={e['minute']:3d}  player={e['player_name']}  team={e['team_id']}  uid={e['uid']}")

    print(f"\n--- SIMULAZIONE MESSAGGI ---")

    league_name = data.get("leagues", [{}])[0].get("name", league_slug) if data.get("leagues") else league_slug

    # -----------------------------------------------------------------------
    # Riproduce esattamente la logica del ciclo del bot (un solo giro)
    # -----------------------------------------------------------------------

    # Inizio primo tempo
    if status == "1H" and "1H" not in state["sent_periods"]:
        fake_send_telegram(f"<b>INIZIO PARTITA {bot.E_BOLT}</b>\n\n{home_name} - {away_name}\n\n{e_comp} {hashtag}")
        state["sent_periods"].append("1H")

    # Fine primo tempo
    if status == "HT" and "HT" not in state["sent_periods"]:
        fake_send_telegram(f"<b>FINE PRIMO TEMPO {bot.E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
        state["sent_periods"].append("HT")
        fake_send_telegram_stats_photo("/tmp/fake.png", "HT", f"{e_comp} {hashtag}")
        state["sent_stats"].append("HT")

    # Inizio secondo tempo
    if status == "2H" and "2H" not in state["sent_periods"]:
        fake_send_telegram(f"<b>INIZIO SECONDO TEMPO {bot.E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
        state["sent_periods"].append("2H")

    # Fine regolamentari
    if status in ("ET", "PEN", "AET") and "2H_END" not in state["sent_periods"] and "FT" not in state["sent_periods"]:
        fake_send_telegram(f"<b>FINE REGOLAMENTARI {bot.E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
        state["sent_periods"].append("2H_END")
        if status == "ET":
            fake_send_telegram_stats_photo("/tmp/fake.png", "2H_END", f"{e_comp} {hashtag}")
            state["sent_stats"].append("2H_END")

    # Supplementari
    if status == "ET":
        try:
            comp_status = data["header"]["competitions"][0].get("status", {})
            stype_name  = comp_status.get("type", {}).get("name", "").upper()
            et_period   = comp_status.get("period", 1)
        except Exception:
            stype_name = ""
            et_period  = 1

        is_et_halftime = any(kw in stype_name for kw in ("HALFTIME", "HALF_TIME", "HT_ET", "EXTRA_TIME_HALF"))
        is_second_et   = (et_period >= 4 or (elapsed >= 106 and et_period >= 3))

        if "1ET_START" not in state["sent_periods"] and not is_et_halftime and not is_second_et:
            fake_send_telegram(f"<b>INIZIO 1° TEMPO SUPPLEMENTARE {bot.E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
            state["sent_periods"].append("1ET_START")

        if (is_et_halftime or is_second_et) and "1ET_END" not in state["sent_periods"]:
            fake_send_telegram(f"<b>FINE 1° TEMPO SUPPLEMENTARE {bot.E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
            state["sent_periods"].append("1ET_END")

        if is_second_et and "2ET_START" not in state["sent_periods"]:
            fake_send_telegram(f"<b>INIZIO 2° TEMPO SUPPLEMENTARE {bot.E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
            state["sent_periods"].append("2ET_START")

    # Intervallo supplementari esplicito
    if status == "HT_ET":
        if "1ET_START" not in state["sent_periods"]:
            state["sent_periods"].append("1ET_START")
        if "1ET_END" not in state["sent_periods"]:
            fake_send_telegram(f"<b>FINE 1° TEMPO SUPPLEMENTARE {bot.E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
            state["sent_periods"].append("1ET_END")

    # Rigori
    if status == "PEN":
        if "ET_END_PENS" not in state["sent_periods"]:
            if "2ET_START" in state["sent_periods"] or "1ET_START" in state["sent_periods"]:
                fake_send_telegram(f"<b>FINE SUPPLEMENTARI {bot.E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
            state["sent_periods"].append("ET_END_PENS")

        home_pen_icons, away_pen_icons = [], []
        for e in events:
            if e["type"] in ("shootout goal", "shootout miss", "shootout saved"):
                icon = bot.E_PEN_OK if e["type"] == "shootout goal" else bot.E_PEN_KO
                (home_pen_icons if e["team_id"] == home_id else away_pen_icons).append(icon)

        total_kicks = len(home_pen_icons) + len(away_pen_icons)
        if total_kicks > state["penalties_count"]:
            fake_send_telegram(
                f"<b>RIGORI {bot.E_MIC}</b>\n\n"
                f"{home_name}: " + "".join(home_pen_icons or ["-"]) + "\n"
                f"{away_name}: " + "".join(away_pen_icons or ["-"]) + f"\n\n{e_comp} {hashtag}"
            )
            state["penalties_count"] = total_kicks

    # Goal
    total_goals_now = g_home + g_away
    if total_goals_now > state["goals_detected"]:
        goal_events = [e for e in events if e["type"] in ("goal", "own goal", "penalty goal")]

        # Simula ogni goal in ordine
        for goal_idx in range(state["goals_detected"], total_goals_now):
            # Determina quale squadra ha segnato questo goal (per ordine)
            # Ricostruisce il punteggio progressivo
            home_goals_at = sum(
                1 for e in goal_events
                if (e["type"] != "own goal" and e["team_id"] == home_id) or
                   (e["type"] == "own goal" and e["team_id"] == away_id)
            )
            away_goals_at = sum(
                1 for e in goal_events
                if (e["type"] != "own goal" and e["team_id"] == away_id) or
                   (e["type"] == "own goal" and e["team_id"] == home_id)
            )

        # Invia un messaggio per ogni goal non ancora inviato
        home_goal_count = 0
        away_goal_count = 0
        for e in sorted(goal_events, key=lambda x: x["minute"]):
            is_home_goal = (e["type"] != "own goal" and e["team_id"] == home_id) or \
                           (e["type"] == "own goal" and e["team_id"] == away_id)
            if is_home_goal:
                home_goal_count += 1
                gh = home_goal_count
                ga = away_goal_count
            else:
                away_goal_count += 1
                gh = home_goal_count
                ga = away_goal_count

            ps = bot.fmt_player(e["player_name"])
            if e["type"] == "own goal":
                ps += " (Autogol)"
            elif e["type"] == "penalty goal":
                ps += " (Rig.)"

            if is_home_goal:
                goal_score = f"<b>{home_name} {gh}</b>-{ga} {away_name}"
            else:
                goal_score = f"{home_name} {gh}-<b>{ga} {away_name}</b>"

            fake_send_telegram(
                f"<b>GOAL {bot.E_MIC}</b>\n\n{goal_score}\n"
                f"{bot.E_BALL} <i>{e['minute']}' {ps}</i>\n\n{e_comp} {hashtag}"
            )

        state["goals_detected"] = total_goals_now
        state["prev_home_goals"] = g_home
        state["prev_away_goals"] = g_away

    # Cambi
    for e in sorted([x for x in events if x["type"] == "substitution"], key=lambda x: x["minute"]):
        sub_id = e["uid"]
        if sub_id not in state["sent_subs"]:
            team_title = home_name.upper() if e["team_id"] == home_id else away_name.upper()
            ins  = bot.fmt_player(e["assist_name"])
            outs = bot.fmt_player(e["player_name"])
            fake_send_telegram(
                f"<b>CAMBIO {team_title} {bot.E_SUB}</b>\n\n"
                f"{bot.E_UP} {ins}\n"
                f"{bot.E_DOWN} {outs}\n\n"
                f"{e_comp} {hashtag}"
            )
            state["sent_subs"].append(sub_id)

    # Cartellini rossi / doppio giallo
    for e in events:
        if e["type"] in ("red card", "second yellow card"):
            p_name  = bot.fmt_player(e["player_name"])
            card_id = f"card_{e['minute']}_{e['player_name']}".replace(" ", "_")
            if card_id not in state["sent_cards"]:
                fake_send_telegram(
                    f"<b>CARTELLINO ROSSO {bot.E_RED}</b>\n\n"
                    f"🔚 <i>{e['minute']}' {p_name}</i>\n\n{e_comp} {hashtag}"
                )
                state["sent_cards"].append(card_id)

    # Rigori sbagliati (tempo regolamentare)
    for e in events:
        if e["type"] in ("penalty missed", "penalty saved"):
            p_name = bot.fmt_player(e["player_name"])
            pen_id = f"failpen_{e['minute']}_{e['player_name']}".replace(" ", "_")
            if pen_id not in state["sent_failed_penalties"]:
                team_name_pen = home_name if e["team_id"] == home_id else away_name
                fake_send_telegram(
                    f"<b>RIGORE SBAGLIATO {team_name_pen.upper()} {bot.E_PEN_KO}</b>\n\n"
                    f"🥅 <i>{e['minute']}' {p_name}</i>\n\n{e_comp} {hashtag}"
                )
                state["sent_failed_penalties"].append(pen_id)

    # Fine partita
    comp_state_espn = (
        data.get("header", {}).get("competitions", [{}])[0]
            .get("status", {}).get("type", {}).get("state", "")
    )
    is_finished = (
        status in ("FT", "AET") or
        (status == "PEN" and comp_state_espn == "post")
    )

    if is_finished and "FT" not in state["sent_periods"]:
        home_scorers, away_scorers = [], []
        for e in events:
            if e["type"] in ("goal", "own goal", "penalty goal"):
                ps = bot.fmt_player(e["player_name"])
                if e["type"] == "own goal":
                    ps += " (Autogol)"
                elif e["type"] == "penalty goal":
                    ps += " (Rig.)"
                entry = f"{e['minute']}' {ps}"
                tid = e["team_id"]
                if e["type"] == "own goal":
                    tid = away_id if tid == home_id else home_id
                (home_scorers if tid == home_id else away_scorers).append(entry)

        if home_scorers or away_scorers:
            parts = []
            if home_scorers:
                parts.append(", ".join(home_scorers))
            if away_scorers:
                parts.append(", ".join(away_scorers))
            scorers_line = f"{bot.E_BALL} <i>{' // '.join(parts)}</i>\n"
        else:
            scorers_line = ""

        has_shootout = (
            "ET_END_PENS" in state["sent_periods"] or
            status == "PEN" or
            len(data.get("shootout", [])) > 0
        )
        if has_shootout:
            home_pen_goals = sum(1 for e in events if e["type"] == "shootout goal" and e["team_id"] == home_id)
            away_pen_goals = sum(1 for e in events if e["type"] == "shootout goal" and e["team_id"] == away_id)
            if home_pen_goals > 0 or away_pen_goals > 0:
                if home_pen_goals > away_pen_goals:
                    score_str = (
                        f"<b>{home_name} {g_home}-{g_away} {away_name}</b>\n"
                        f"(d.c.r. <b>{home_pen_goals}</b>-{away_pen_goals})"
                    )
                else:
                    score_str = (
                        f"<b>{home_name} {g_home}-{g_away} {away_name}</b>\n"
                        f"(d.c.r. {home_pen_goals}-<b>{away_pen_goals}</b>)"
                    )

        msg_finale = f"<b>FINE PARTITA {bot.E_FLAG}</b>\n\n{score_str}\n{scorers_line}\n{e_comp} {hashtag}"
        fake_send_telegram_with_photo(msg_finale, None)
        fake_send_telegram_stats_photo("/tmp/fake.png", "FT", f"{e_comp} {hashtag}")
        state["sent_periods"].append("FT")

    # -----------------------------------------------------------------------
    # Riepilogo finale
    # -----------------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"📋 RIEPILOGO: {len(sent_messages)} messaggi che sarebbero stati inviati")
    print(f"   sent_periods: {state['sent_periods']}")
    print(f"   goals_detected: {state['goals_detected']}")
    print(f"   cambi inviati: {len(state['sent_subs'])}")
    print(f"   penalties_count: {state['penalties_count']}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python test_bot_replay.py <event_id> <league_slug>")
        print("Es:  python test_bot_replay.py 401862897 uefa.champions")
        sys.exit(1)

    event_id    = sys.argv[1]
    league_slug = sys.argv[2]
    replay(event_id, league_slug)
