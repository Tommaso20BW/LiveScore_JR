import os
import requests
import json
import time
import sys
import base64
from PIL import Image
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

# NaCl per GitHub Secrets
try:
    from nacl import encoding, public
except ImportError:
    print("⚠️ pynacl non installato. Necessario per aggiornare i Secrets di GitHub.")

# ==============================================================================
# CONFIGURAZIONE — adatta i secrets GitHub di conseguenza
# ==============================================================================
API_KEY             = os.getenv('API_KEY')           # X-Auth-Token di football-data.org
BOT_TOKEN           = os.getenv('TELEGRAM_TOKEN')
CHAT_ID             = os.getenv('TELEGRAM_TO')
CLIENT_ID           = os.getenv('CANVA_CLIENT_ID')
CLIENT_SECRET       = os.getenv('CANVA_CLIENT_SECRET')
CANVA_REFRESH_TOKEN = os.getenv('CANVA_REFRESH_TOKEN')
GH_PAT              = os.getenv('GH_PAT')
GITHUB_REPOSITORY   = os.getenv('GITHUB_REPOSITORY')

# football-data.org IDs
JUVE_ID         = 109          # Juventus FC
SERIE_A_CODE    = "SA"         # Codice competizione Serie A
COMPETITION_ID  = 2019         # Serie A numeric ID

CANVA_DESIGN_ID  = "DAHI3ytu6yQ"
PAGINA_TARGET    = 11

JUVE_LOGO_URL = "https://upload.wikimedia.org/wikipedia/commons/9/99/Juventus_FC_2017_squared_icon_%28white%29.png"

# ==============================================================================
# EMOJI
# ==============================================================================
E_BOLT = '⚡️'; E_FLAG = '🏁'; E_MIC = '🎙'; E_BALL = '⚽️'
E_SUB = '🔄';  E_UP = '🔼';   E_DOWN = '🔽'; E_RED = '🟥'
E_PEN_OK = '✅'; E_PEN_KO = '❌'

MOMENTI_CONFIG = {
    "HT":     {"titolo": "<b>STATS PRIMO TEMPO</b> 📊",   "badge": "FINE PRIMO TEMPO"},
    "2H_END": {"titolo": "<b>STATS SECONDO TEMPO</b> 📊", "badge": "FINE SECONDO TEMPO"},
    "FT":     {"titolo": "<b>STATS FINE PARTITA</b> 📊",  "badge": "FINE PARTITA"}
}

# ==============================================================================
# HELPERS
# ==============================================================================
def clean_name(name):
    for w in ["AC ", "AS ", " US", " FC", "FC ", "A.C. ", "A.S. "]:
        name = name.replace(w, "").replace(w.strip(), "")
    return " ".join(name.split())

def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("Errore: BOT_TOKEN o CHAT_ID mancanti.")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print(f"Errore Telegram: {e}")

def send_telegram_with_photo(text, photo_bytes):
    if not photo_bytes:
        send_telegram(text)
        return
    print("📤 Invio post con grafica Canva su Telegram...")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        res = requests.post(url, data={"chat_id": CHAT_ID, "caption": text, "parse_mode": "HTML"},
                            files={"photo": ("matchday.png", photo_bytes)}, timeout=25)
        if res.status_code != 200:
            send_telegram(text)
    except Exception:
        send_telegram(text)

def send_telegram_stats_photo(png_path, momento, hashtag):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    caption = f"{MOMENTI_CONFIG[momento]['titolo']}\n\n{hashtag}"
    try:
        with open(png_path, "rb") as f:
            requests.post(url, data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "HTML"},
                          files={"photo": ("stats.png", f, "image/png")}, timeout=25)
        print(f"✅ Stats ({momento}) inviate su Telegram!")
    except Exception as e:
        print(f"❌ Errore invio stats: {e}")

# ==============================================================================
# GITHUB SECRETS
# ==============================================================================
def update_github_secret(secret_name, new_value):
    if not GH_PAT or not GITHUB_REPOSITORY:
        return False
    headers = {"Authorization": f"Bearer {GH_PAT}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    try:
        pk = requests.get(f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/secrets/public-key",
                          headers=headers, timeout=10).json()
        pub_key = public.PublicKey(pk["key"].encode(), encoding.Base64Encoder)
        encrypted = base64.b64encode(public.SealedBox(pub_key).encrypt(new_value.encode())).decode()
        res = requests.put(f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/secrets/{secret_name}",
                           headers=headers, json={"encrypted_value": encrypted, "key_id": pk["key_id"]}, timeout=10)
        return res.status_code in [201, 204]
    except Exception as e:
        print(f"❌ Errore aggiornamento secret: {e}")
        return False

# ==============================================================================
# CANVA API
# ==============================================================================
def get_valid_token():
    if not CANVA_REFRESH_TOKEN:
        return None
    print("🔄 Richiesta Access Token a Canva...")
    try:
        res = requests.post("https://api.canva.com/rest/v1/oauth/token",
                            data={"grant_type": "refresh_token", "refresh_token": CANVA_REFRESH_TOKEN,
                                  "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}, timeout=15)
        if res.status_code == 200:
            data = res.json()
            if "refresh_token" in data and data["refresh_token"] != CANVA_REFRESH_TOKEN:
                update_github_secret("CANVA_REFRESH_TOKEN", data["refresh_token"])
            return data["access_token"]
    except Exception as e:
        print(f"Errore Canva OAuth: {e}")
    return None

def get_canva_image(access_token):
    if not access_token:
        return None
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    try:
        res = requests.post("https://api.canva.com/rest/v1/exports", headers=headers,
                            json={"design_id": CANVA_DESIGN_ID, "format": {"type": "png", "pages": [PAGINA_TARGET]}},
                            timeout=15)
        if res.status_code not in [200, 201]:
            return None
        job_id = res.json().get("id") or res.json().get("job", {}).get("id")
        if not job_id:
            return None
        status_url = f"https://api.canva.com/rest/v1/exports/{job_id}"
        for _ in range(40):
            time.sleep(4)
            check = requests.get(status_url, headers=headers, timeout=15).json()
            stato = check.get("status") or check.get("job", {}).get("status")
            if stato == "success":
                urls = check.get("urls") or check.get("job", {}).get("urls")
                dl_url = urls[0] if urls else check.get("url")
                if dl_url:
                    return requests.get(dl_url, timeout=20).content
            elif stato == "failed":
                return None
    except Exception as e:
        print(f"❌ Errore Canva: {e}")
    return None

# ==============================================================================
# STATS GRAFICHE — football-data.org include stats base nel match response
# (ball_possession, shots, shots_on_goal, corner_kicks, fouls, yellow_cards, red_cards)
# xG e passaggi NON disponibili nel free tier → mostrati come N/D
# ==============================================================================
def genera_stats_html(match_data, home_name, away_name, home_goals, away_goals, momento, league_name="SERIE A"):
    home_stats = match_data.get("homeTeam", {}).get("statistics") or {}
    away_stats = match_data.get("awayTeam", {}).get("statistics") or {}

    h_logo = JUVE_LOGO_URL if "juventus" in home_name.lower() else match_data.get("homeTeam", {}).get("crest", "")
    a_logo = JUVE_LOGO_URL if "juventus" in away_name.lower() else match_data.get("awayTeam", {}).get("crest", "")
    badge_label = MOMENTI_CONFIG[momento]["badge"]

    def val(d, key):
        v = d.get(key)
        return str(v) if v is not None else "0"

    def perc(h, a):
        try:
            hv, av = int(h), int(a)
            return 50 if (hv + av) == 0 else int(hv / (hv + av) * 100)
        except:
            return 50

    # Possesso: già in percentuale nell'API (es. 45)
    pos_h_raw = home_stats.get("ball_possession", 50)
    pos_a_raw = away_stats.get("ball_possession", 50)
    pos_h = f"{pos_h_raw}%" if pos_h_raw is not None else "50%"
    pos_a = f"{pos_a_raw}%" if pos_a_raw is not None else "50%"
    try:
        bp_perc = int(pos_h_raw)
    except:
        bp_perc = 50

    sh_h   = val(home_stats, "shots");          sh_a   = val(away_stats, "shots")
    shg_h  = val(home_stats, "shots_on_goal");  shg_a  = val(away_stats, "shots_on_goal")
    cor_h  = val(home_stats, "corner_kicks");   cor_a  = val(away_stats, "corner_kicks")
    foul_h = val(home_stats, "fouls");          foul_a = val(away_stats, "fouls")
    yc_h   = val(home_stats, "yellow_cards");   yc_a   = val(away_stats, "yellow_cards")
    rc_h   = val(home_stats, "red_cards");      rc_a   = val(away_stats, "red_cards")

    stats_mappate = [
        ("Possesso palla",  pos_h,  pos_a,  bp_perc),
        ("Tiri totali",     sh_h,   sh_a,   perc(sh_h,   sh_a)),
        ("Tiri in porta",   shg_h,  shg_a,  perc(shg_h,  shg_a)),
        ("Corner",          cor_h,  cor_a,  perc(cor_h,  cor_a)),
        ("Falli",           foul_h, foul_a, perc(foul_h, foul_a)),
        ("Ammoniti",        yc_h,   yc_a,   perc(yc_h,   yc_a)),
        ("Espulsi",         rc_h,   rc_a,   perc(rc_h,   rc_a)),
    ]

    rows_html = "".join([f'''
<div class="stat-row">
  <div class="stat-top">
    <div class="val home-val">{h}</div>
    <div class="stat-label">{label}</div>
    <div class="val away-val">{a}</div>
  </div>
  <div class="bar-track">
    <div class="bar-home" style="width:{hp}%"></div>
    <div class="bar-away" style="width:{100-hp}%"></div>
  </div>
</div>
''' for label, h, a, hp in stats_mappate])

    html_content = f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;800;900&family=Barlow+Condensed:wght@700;900&display=swap" rel="stylesheet">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:1620px; height:1980px; background: radial-gradient(circle at top left,#1e3a8a 0%,transparent 40%), radial-gradient(circle at bottom right,#7c3aed 0%,transparent 40%), #060816; font-family:'Inter',sans-serif; padding:50px 60px; overflow:hidden; }}
.card {{ width:1500px; height:1880px; margin:0 auto; background:linear-gradient(180deg,rgba(17,24,39,.96),rgba(10,14,28,.96)); border-radius:70px; overflow:hidden; border:3px solid rgba(255,255,255,.08); display:flex; flex-direction:column; }}
.header {{ padding:75px 80px 55px; border-bottom:3px solid rgba(255,255,255,.06); }}
.league-row {{ text-align:center; color:#7c8cb5; font-size:28px; letter-spacing:5px; text-transform:uppercase; font-weight:700; margin-bottom:35px; }}
.badge {{ width:fit-content; margin:0 auto 40px; padding:14px 40px; border-radius:999px; background:linear-gradient(135deg,#facc15,#f59e0b); color:#111827; font-size:22px; font-weight:900; letter-spacing:3px; text-transform:uppercase; }}
.teams-row {{ display:flex; align-items:center; justify-content:space-between; padding:0 30px; }}
.team {{ width:350px; text-align:center; }}
.logo {{ width:170px; height:170px; object-fit:contain; display:block; margin:0 auto 25px; }}
.team-name {{ color:white; font-weight:800; font-size:40px; }}
.score-wrap {{ text-align:center; }}
.score {{ font-family:'Barlow Condensed',sans-serif; font-size:195px; line-height:.85; font-weight:900; color:white; }}
.match-status {{ margin-top:20px; color:#8fa1c7; font-size:26px; font-weight:600; text-transform:uppercase; letter-spacing:2px; }}
.stats-body {{ padding:50px 80px 65px; flex:1; display:flex; flex-direction:column; justify-content:space-between; }}
.stats-title {{ text-align:center; color:#91a4d0; font-size:26px; font-weight:800; letter-spacing:4px; text-transform:uppercase; margin-bottom:15px; }}
.stat-row {{ padding:15px 0; border-bottom:2px solid rgba(255,255,255,.05); }}
.stat-row:last-child {{ border-bottom:none; }}
.stat-top {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; }}
.val {{ width:120px; color:white; font-weight:900; font-size:46px; font-family:'Barlow Condensed',sans-serif; }}
.home-val {{ text-align:left; }} .away-val {{ text-align:right; }}
.stat-label {{ color:#b4c0df; font-size:30px; font-weight:700; }}
.bar-track {{ position:relative; height:22px; border-radius:999px; overflow:hidden; background:rgba(255,255,255,.06); }}
.bar-home {{ position:absolute; top:0; left:0; height:100%; background:linear-gradient(90deg,#60a5fa,#2563eb); }}
.bar-away {{ position:absolute; top:0; right:0; height:100%; background:linear-gradient(90deg,#ef4444,#dc2626); }}
</style></head><body>
<div class="card">
  <div class="header">
    <div class="league-row">{league_name.upper()}</div>
    <div class="badge">{badge_label}</div>
    <div class="teams-row">
      <div class="team"><img src="{h_logo}" class="logo"><div class="team-name">{home_name}</div></div>
      <div class="score-wrap"><div class="score">{home_goals}–{away_goals}</div><div class="match-status">LIVE STATS</div></div>
      <div class="team"><img src="{a_logo}" class="logo"><div class="team-name">{away_name}</div></div>
    </div>
  </div>
  <div class="stats-body">
    <div class="stats-title">STATISTICHE ANALITICHE</div>
    {rows_html}
  </div>
</div></body></html>"""

    path_html     = "/tmp/stats.html"
    path_raw_png  = "/tmp/stats_raw.png"
    path_final_png = "/tmp/stats_final.png"
    with open(path_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    print("📸 Rendering Playwright 1620x1980...")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-web-security"])
        page = browser.new_page(viewport={"width": 1620, "height": 1980})
        page.goto(f"file://{path_html}")
        page.wait_for_timeout(3000)
        page.screenshot(path=path_raw_png)
        browser.close()

    if os.path.exists("texture.png"):
        try:
            base_img = Image.open(path_raw_png).convert("RGBA")
            tex      = Image.open("texture.png").convert("RGBA").resize(base_img.size, Image.Resampling.LANCZOS)
            Image.alpha_composite(base_img, tex).convert("RGB").save(path_final_png, "PNG")
            return path_final_png
        except Exception as e:
            print(f"Errore texture: {e}")
    return path_raw_png

# ==============================================================================
# PARSING EVENTI — football-data.org v4
# Struttura evento: {"id","minute","injuryTime","type","team","player","assist","detail"}
# type: GOAL | CARD | SUBSTITUTION | PENALTY | VAR
# detail per GOAL: Regular Play | Own Goal | Penalty | Missed Penalty
# detail per CARD: Yellow Card | Yellow-Red Card | Red Card
# ==============================================================================
def parse_scorers_text(goals, home_id, away_id):
    home_list, away_list = [], []
    for g in goals:
        mn = g.get("minute", "?")
        inj = g.get("injuryTime")
        min_str = f"{mn}+{inj}" if inj else str(mn)
        p = g.get("player", {}).get("name", "Giocatore")
        detail = (g.get("detail") or "").lower()
        if "own goal" in detail:    p += " (Autogol)"
        elif "penalty" in detail:   p += " (Rig.)"
        entry = f"{min_str}' {p}"
        if g.get("team", {}).get("id") == home_id:
            home_list.append(entry)
        else:
            away_list.append(entry)
    if home_list and away_list:
        return f"{E_BALL} <i>" + ", ".join(home_list) + " // " + ", ".join(away_list) + "</i>\n"
    elif home_list:
        return f"{E_BALL} <i>" + ", ".join(home_list) + "</i>\n"
    elif away_list:
        return f"{E_BALL} <i>" + ", ".join(away_list) + "</i>\n"
    return ""

# ==============================================================================
# CICLO PRINCIPALE
# ==============================================================================
def avvia_ciclo_partita():
    if not API_KEY:
        print("❌ API_KEY mancante.")
        return

    # football-data.org usa X-Auth-Token
    headers = {"X-Auth-Token": API_KEY}
    BASE    = "https://api.football-data.org/v4"

    # ── Trova il match della Juventus ──────────────────────────────────────────
    match_id = None
    while not match_id:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        print(f"🔄 Cerco partita Juventus ({today})...")
        try:
            # 1. Match live
            live = requests.get(f"{BASE}/matches?status=LIVE&competitions={COMPETITION_ID}",
                                headers=headers, timeout=10).json()
            for m in live.get("matches", []):
                if m.get("homeTeam", {}).get("id") == JUVE_ID or m.get("awayTeam", {}).get("id") == JUVE_ID:
                    match_id = m["id"]
                    print(f"🔥 Match LIVE trovato! ID: {match_id}")
                    break

            # 2. Match di oggi
            if not match_id:
                today_res = requests.get(f"{BASE}/teams/{JUVE_ID}/matches?dateFrom={today}&dateTo={today}",
                                         headers=headers, timeout=10).json()
                matches = today_res.get("matches", [])
                if matches:
                    match_id = matches[0]["id"]
                    print(f"📅 Match trovato oggi! ID: {match_id}")

            # 3. Prossimo match
            if not match_id:
                next_res = requests.get(f"{BASE}/teams/{JUVE_ID}/matches?status=SCHEDULED&limit=1",
                                        headers=headers, timeout=10).json()
                matches = next_res.get("matches", [])
                if matches:
                    match_id = matches[0]["id"]
                    print(f"📌 Prossimo match agganciato. ID: {match_id} ({matches[0].get('utcDate','')})")
        except Exception as e:
            print(f"⚠️ Errore API: {e}")

        if not match_id:
            print("❌ Nessun match trovato. Riprovo tra 30s...")
            time.sleep(30)

    print(f"⏳ Aggancio completato ID={match_id}. Inizio monitoraggio...")

    state = {
        "match_id": match_id,
        "sent_periods": [], "goals_count": 0, "sent_subs": [],
        "sent_cards": [], "pen_count": 0, "sent_stats": []
    }

    while True:
        sleep_time = 75  # default polling

        # Carica stato da file se esiste
        if os.path.exists("match_state.json"):
            with open("match_state.json") as f:
                state = json.load(f)

        try:
            res = requests.get(f"{BASE}/matches/{match_id}", headers=headers, timeout=15).json()

            status  = res.get("status", "SCHEDULED")   # SCHEDULED|IN_PLAY|PAUSED|FINISHED|SUSPENDED|POSTPONED|CANCELLED|AWARDED
            minute  = res.get("minute") or 0
            injury  = res.get("injuryTime") or 0

            score   = res.get("score", {})
            ft      = score.get("fullTime", {})
            ht      = score.get("halfTime", {})
            g_home  = ft.get("home") or 0
            g_away  = ft.get("away") or 0

            home    = res.get("homeTeam", {})
            away    = res.get("awayTeam", {})
            home_id = home.get("id")
            away_id = away.get("id")

            home_name = "Juventus" if home_id == JUVE_ID else clean_name(home.get("shortName") or home.get("name", "Home"))
            away_name = "Juventus" if away_id == JUVE_ID else clean_name(away.get("shortName") or away.get("name", "Away"))

            comp      = res.get("competition", {})
            league_name = comp.get("name", "Serie A")

            h_short = "Juve" if home_id == JUVE_ID else home_name.replace(" ", "")
            a_short = "Juve" if away_id == JUVE_ID else away_name.replace(" ", "")
            hashtag = f"#{h_short}{a_short}"

            def punteggio(bold_home=False, bold_away=False):
                hn = f"<b>{home_name}</b>" if bold_home else home_name
                an = f"<b>{away_name}</b>" if bold_away else away_name
                gh = f"<b>{g_home}</b>" if bold_home else str(g_home)
                ga = f"<b>{g_away}</b>" if bold_away else str(g_away)
                return f"{hn} {gh}-{ga} {an}"

            def bold_score():
                if g_home > g_away:  return punteggio(bold_home=True)
                elif g_away > g_home: return punteggio(bold_away=True)
                return punteggio()

            min_str = f"{minute}+{injury}" if injury else str(minute)
            print(f"[LIVE] {home_name} {g_home}-{g_away} {away_name} | {status} {min_str}'")

            # Gestione stati
            if status in ["SCHEDULED", "TIMED"] and minute == 0:
                print("💤 Match non ancora iniziato. Attendo 30s...")
                time.sleep(30)
                continue

            # ── INIZIO PARTITA ──────────────────────────────────────────────
            if status == "IN_PLAY" and "1H" not in state["sent_periods"]:
                send_telegram(f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{home_name} - {away_name}\n\n🇮🇹 {hashtag}")
                state["sent_periods"].append("1H")

            # ── FINE PRIMO TEMPO ────────────────────────────────────────────
            elif status == "PAUSED" and "HT" not in state["sent_periods"]:
                send_telegram(f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{bold_score()}\n\n🇮🇹 {hashtag}")
                state["sent_periods"].append("HT")
                print("⏳ Attesa 2 min per consolidamento dati HT...")
                time.sleep(120)
                png = genera_stats_html(res, home_name, away_name, g_home, g_away, "HT", league_name)
                send_telegram_stats_photo(png, "HT", f"🇮🇹 {hashtag}")
                state["sent_stats"].append("HT")
                sleep_time = 30

            # ── INIZIO SECONDO TEMPO ────────────────────────────────────────
            elif status == "IN_PLAY" and "HT" in state["sent_periods"] and "2H" not in state["sent_periods"]:
                send_telegram(f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n{bold_score()}\n\n🇮🇹 {hashtag}")
                state["sent_periods"].append("2H")

            # ── FINE PARTITA ────────────────────────────────────────────────
            if status in ["FINISHED", "AWARDED"]:
                events = res.get("goals", []) or []
                scorers_line = parse_scorers_text(events, home_id, away_id)

                pen = score.get("penalties", {})
                p_h, p_a = pen.get("home"), pen.get("away")
                if p_h is not None:
                    vincitore_home = p_h > p_a
                    msg_fin = (f"<b>FINE PARTITA {E_FLAG}</b>\n\n"
                               f"{'<b>' if vincitore_home else ''}{home_name} {g_home} ({p_h}){'</b>' if vincitore_home else ''}"
                               f"-"
                               f"{'<b>' if not vincitore_home else ''}({p_a}) {g_away} {away_name}{'</b>' if not vincitore_home else ''}\n"
                               f"{scorers_line}\n🇮🇹 {hashtag}")
                else:
                    msg_fin = f"<b>FINE PARTITA {E_FLAG}</b>\n\n{bold_score()}\n{scorers_line}\n🇮🇹 {hashtag}"

                token = get_valid_token()
                foto  = get_canva_image(token) if token else None
                send_telegram_with_photo(msg_fin, foto)

                print("⏳ Attesa 2 min per stats FT...")
                time.sleep(120)
                png = genera_stats_html(res, home_name, away_name, g_home, g_away, "FT", league_name)
                send_telegram_stats_photo(png, "FT", f"🇮🇹 {hashtag}")

                if os.path.exists("match_state.json"):
                    os.remove("match_state.json")
                print("🏁 Bot terminato con successo.")
                sys.exit(0)

            # ── GOAL / GOAL ANNULLATO ───────────────────────────────────────
            total_goals = g_home + g_away
            if total_goals > state["goals_count"]:
                goals_list = res.get("goals", []) or []
                last_g_msg = ""
                if goals_list:
                    last = sorted(goals_list, key=lambda x: (x.get("minute",0), x.get("injuryTime") or 0))[-1]
                    mn_g  = last.get("minute", "?")
                    inj_g = last.get("injuryTime")
                    mn_str = f"{mn_g}+{inj_g}" if inj_g else str(mn_g)
                    p_name = last.get("scorer", {}).get("name") or last.get("player", {}).get("name", "Giocatore")
                    det    = (last.get("detail") or "").lower()
                    if "own goal" in det:  p_name += " (Autogol)"
                    elif "penalty" in det: p_name += " (Rig.)"
                    last_g_msg = f"{E_BALL} <i>{mn_str}' {p_name}</i>\n"

                send_telegram(f"<b>GOAL {E_MIC}</b>\n\n{bold_score()}\n{last_g_msg}\n🇮🇹 {hashtag}")
                state["goals_count"] = total_goals

            elif total_goals < state["goals_count"]:
                send_telegram(f"<b>GOAL ANNULLATO 📺</b>\n\n{punteggio()}\n\n🇮🇹 {hashtag}")
                state["goals_count"] = total_goals

            # ── CARTELLINI ROSSI / CAMBI ────────────────────────────────────
            bookings = res.get("bookings", []) or []
            for b in bookings:
                card_type = (b.get("card") or "").lower()
                if "red" in card_type:
                    p_name  = b.get("player", {}).get("name", "Giocatore")
                    mn_b    = b.get("minute", "?")
                    card_id = f"card_{mn_b}_{p_name}".replace(" ", "_")
                    if card_id not in state["sent_cards"]:
                        send_telegram(f"<b>CARTELLINO ROSSO {E_RED}</b>\n\n🔚 <i>{mn_b}' {p_name}</i>\n\n🇮🇹 {hashtag}")
                        state["sent_cards"].append(card_id)

            # Sostituzioni — football-data.org le riporta in homeTeam.bench / lineup
            # ma più facilmente nell'array "substitutions" se disponibile
            subs_raw = res.get("substitutions", []) or []
            subs_by_key = {}
            for s in subs_raw:
                mn_s     = s.get("minute", "?")
                team_id  = s.get("team", {}).get("id")
                p_in     = s.get("playerIn", {}).get("name", "Entrante")
                p_out    = s.get("playerOut", {}).get("name", "Uscente")
                sub_id   = f"sub_{mn_s}_{p_out}_{p_in}".replace(" ", "_")
                if sub_id not in state["sent_subs"]:
                    key = f"{mn_s}_{team_id}"
                    if key not in subs_by_key:
                        subs_by_key[key] = {"minute": mn_s, "team_id": team_id, "in": [], "out": [], "ids": []}
                    subs_by_key[key]["in"].append(p_in)
                    subs_by_key[key]["out"].append(p_out)
                    subs_by_key[key]["ids"].append(sub_id)

            for key, s in subs_by_key.items():
                team_title = "JUVENTUS" if s["team_id"] == JUVE_ID else (home_name.upper() if s["team_id"] == home_id else away_name.upper())
                send_telegram(f"<b>CAMBIO {team_title} {E_SUB}</b>\n\n{E_UP} {', '.join(s['in'])}\n{E_DOWN} {', '.join(s['out'])}\n\n🇮🇹 {hashtag}")
                state["sent_subs"].extend(s["ids"])

            with open("match_state.json", "w") as f:
                json.dump(state, f)

        except Exception as e:
            print(f"⚠️ Errore ciclo: {e}")
            sleep_time = 30

        time.sleep(sleep_time)

# ==============================================================================
# MAIN
# ==============================================================================
def main():
    print("🚀 Avvio Live Score Bot (football-data.org)...")
    if str(os.getenv("ONLY_REFRESH_TOKEN", "")).strip().lower() == "true":
        print("🔒 Modalità Keep-Alive: rinnovo token Canva...")
        get_valid_token()
        return
    avvia_ciclo_partita()

if __name__ == "__main__":
    main()
