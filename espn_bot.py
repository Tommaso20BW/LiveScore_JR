import os
import requests
import json
import time
import sys
import base64
from PIL import Image
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

try:
    from nacl import encoding, public
except ImportError:
    print("⚠️ Errore: La libreria 'pynacl' non è installata.")

# ==============================================================================
# CONFIGURAZIONE (DA SECRETS GITHUB)
# ==============================================================================
BOT_TOKEN           = os.getenv('TELEGRAM_TOKEN')
CHAT_ID             = os.getenv('TELEGRAM_TO')
CLIENT_ID           = os.getenv('CANVA_CLIENT_ID')
CLIENT_SECRET       = os.getenv('CANVA_CLIENT_SECRET')
CANVA_REFRESH_TOKEN = os.getenv('CANVA_REFRESH_TOKEN')
GH_PAT              = os.getenv('GH_PAT')
GITHUB_REPOSITORY   = os.getenv('GITHUB_REPOSITORY')
GIST_ID             = os.getenv('GIST_ID')

# ESPN: ID Juventus = "111"
ESPN_JUVE_ID   = "111"
ESPN_JUVE_NAME = "Juventus"

CANVA_DESIGN_ID = "DAHI3ytu6yQ"
PAGINA_TARGET   = 11

JUVE_LOGO_URL = "https://a.espncdn.com/i/teamlogos/soccer/500/111.png"

# Tutte le competizioni in cui può giocare la Juventus
ESPN_SLUGS = [
    ("Serie A",             "ita.1"),
    ("Coppa Italia",        "ita.coppa_italia"),
    ("Champions League",    "uefa.champions"),
    ("Europa League",       "uefa.europa"),
    ("Conference League",   "uefa.europa.conference_league"),
    ("Supercoppa Italiana", "ita.super_cup"),
    ("UEFA Super Cup",      "uefa.super_cup"),
    ("Mondiale per Club",   "fifa.cwc"),
]

ESPN_HEADERS = {"User-Agent": "Mozilla/5.0"}

# ==============================================================================
# EMOJI
# ==============================================================================
E_BOLT   = '⚡️'
E_FLAG   = '🏁'
E_MIC    = '🎙'
E_BALL   = '⚽️'
E_SUB    = '🔄'
E_UP     = '🔼'
E_DOWN   = '🔽'
E_RED    = '🟥'
E_YEL    = '🟨'
E_PEN_OK = '✅'
E_PEN_KO = '❌'

COMP_EMOJIS = {
    "ita.1":                           "🇮🇹",
    "ita.coppa_italia":                "🇮🇹",
    "ita.super_cup":                   "🇮🇹",
    "uefa.champions":                  "🇪🇺",
    "uefa.europa":                     "🇪🇺",
    "uefa.europa.conference_league":   "🇪🇺",
    "uefa.super_cup":                  "🇪🇺",
    "fifa.cwc":                        "🌍",
}

# ==============================================================================
# ESPN API
# ==============================================================================
def espn_get(url):
    try:
        r = requests.get(url, headers=ESPN_HEADERS, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"⚠️ ESPN request error: {e}")
        return None

def find_juve_match():
    """Cerca la partita della Juventus (live o oggi) in tutte le competizioni ESPN."""
    for comp_name, slug in ESPN_SLUGS:
        data = espn_get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard")
        if not data:
            continue
        for event in data.get("events", []):
            comps = event.get("competitions", [{}])[0]
            teams = comps.get("competitors", [])
            for t in teams:
                if t["team"]["id"] == ESPN_JUVE_ID or ESPN_JUVE_NAME in t["team"]["displayName"]:
                    state = event["status"]["type"]["state"]
                    print(f"✅ Juventus trovata in [{comp_name}] - stato: {state}")
                    return event, slug, comp_name
        time.sleep(0.2)
    return None, None, None

def get_summary(event_id, slug):
    """Recupera il summary completo di una partita ESPN."""
    return espn_get(
        f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/summary?event={event_id}"
    )

def parse_event_state(event):
    status  = event["status"]
    state   = status["type"]["state"]
    desc    = status["type"]["description"]
    clock   = status.get("displayClock", "")
    period  = status.get("period", 1)
    return state, desc, clock, period

def get_teams_and_scores(event):
    comps = event.get("competitions", [{}])[0]
    teams = comps.get("competitors", [])
    home = next((t for t in teams if t.get("homeAway") == "home"), teams[0])
    away = next((t for t in teams if t.get("homeAway") == "away"), teams[1])
    home_name  = home["team"]["displayName"]
    away_name  = away["team"]["displayName"]
    home_score = int(home.get("score", 0) or 0)
    away_score = int(away.get("score", 0) or 0)
    home_id    = home["team"]["id"]
    away_id    = away["team"]["id"]
    home_logo  = JUVE_LOGO_URL if home_id == ESPN_JUVE_ID else home["team"].get("logo", "")
    away_logo  = JUVE_LOGO_URL if away_id == ESPN_JUVE_ID else away["team"].get("logo", "")
    return (home_name, away_name, home_score, away_score,
            home_id, away_id, home_logo, away_logo)

# ==============================================================================
# TELEGRAM
# ==============================================================================
def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID:
        print(f"[TELEGRAM] {text}")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print(f"Errore invio Telegram: {e}")

def send_telegram_with_photo(text, photo_bytes):
    if not photo_bytes:
        send_telegram(text)
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        res = requests.post(url, data={"chat_id": CHAT_ID, "caption": text, "parse_mode": "HTML"},
                            files={"photo": ("matchday.png", photo_bytes)}, timeout=25)
        if res.status_code != 200:
            send_telegram(text)
    except Exception as e:
        send_telegram(text)

def send_telegram_stats_photo(png_path, momento, hashtag):
    titoli = {
        "HT":     "<b>STATS PRIMO TEMPO</b> 📊",
        "2H_END": "<b>STATS SECONDO TEMPO</b> 📊",
        "FT":     "<b>STATS FINE PARTITA</b> 📊",
    }
    caption = f"{titoli.get(momento, '📊')}\n\n{hashtag}"
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(png_path, "rb") as f:
            requests.post(url, data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "HTML"},
                          files={"photo": ("stats.png", f, "image/png")}, timeout=25)
        print(f"✅ Statistiche ({momento}) inviate su Telegram!")
    except Exception as e:
        print(f"❌ Errore invio foto: {e}")

# ==============================================================================
# GITHUB SECRET + GIST
# ==============================================================================
def update_github_secret(secret_name, new_value):
    if not GH_PAT or not GITHUB_REPOSITORY:
        return False
    headers = {
        "Authorization": f"Bearer {GH_PAT}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    try:
        res_pk = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/secrets/public-key",
            headers=headers, timeout=10)
        if res_pk.status_code != 200:
            return False
        pk_data = res_pk.json()
        pub_key = public.PublicKey(pk_data["key"].encode("utf-8"), encoding.Base64Encoder)
        encrypted = public.SealedBox(pub_key).encrypt(new_value.encode("utf-8"))
        res = requests.put(
            f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/secrets/{secret_name}",
            headers=headers,
            json={"encrypted_value": base64.b64encode(encrypted).decode("utf-8"), "key_id": pk_data["key_id"]},
            timeout=10)
        return res.status_code in [201, 204]
    except Exception as e:
        print(f"❌ Errore update secret: {e}")
        return False

def leggi_stato_da_gist():
    if not GH_PAT or not GIST_ID:
        return None
    try:
        headers = {"Authorization": f"Bearer {GH_PAT}", "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}
        res = requests.get(f"https://api.github.com/gists/{GIST_ID}", headers=headers, timeout=10)
        if res.status_code != 200:
            return None
        content = res.json()["files"]["match_state.json"]["content"].strip()
        if not content or content == "{}":
            return None
        return json.loads(content)
    except Exception as e:
        print(f"❌ Errore lettura Gist: {e}")
        return None

def salva_stato_su_gist(state):
    if not GH_PAT or not GIST_ID:
        return
    try:
        headers = {"Authorization": f"Bearer {GH_PAT}", "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}
        requests.patch(f"https://api.github.com/gists/{GIST_ID}", headers=headers,
                       json={"files": {"match_state.json": {"content": json.dumps(state, ensure_ascii=False)}}},
                       timeout=10)
    except Exception as e:
        print(f"❌ Errore salvataggio Gist: {e}")

def resetta_gist():
    if not GH_PAT or not GIST_ID:
        return
    try:
        headers = {"Authorization": f"Bearer {GH_PAT}", "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}
        requests.patch(f"https://api.github.com/gists/{GIST_ID}", headers=headers,
                       json={"files": {"match_state.json": {"content": "{}"}}}, timeout=10)
        print("🔄 Gist resettato.")
    except Exception as e:
        print(f"❌ Errore reset Gist: {e}")

# ==============================================================================
# CANVA
# ==============================================================================
def get_valid_token():
    if not CANVA_REFRESH_TOKEN:
        return None
    print("🔄 Richiesta Access Token Canva...")
    try:
        res = requests.post("https://api.canva.com/rest/v1/oauth/token", data={
            "grant_type": "refresh_token",
            "refresh_token": CANVA_REFRESH_TOKEN,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }, timeout=15)
        if res.status_code == 200:
            tokens = res.json()
            if "refresh_token" in tokens and tokens["refresh_token"] != CANVA_REFRESH_TOKEN:
                update_github_secret("CANVA_REFRESH_TOKEN", tokens["refresh_token"])
            return tokens["access_token"]
    except Exception as e:
        print(f"❌ Errore Canva token: {e}")
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
        job_id = (res.json().get("id") or res.json().get("job", {}).get("id"))
        if not job_id:
            return None
        time.sleep(8)
        status_url = f"https://api.canva.com/rest/v1/exports/{job_id}"
        for _ in range(60):
            time.sleep(5)
            check = requests.get(status_url, headers=headers, timeout=15)
            if check.status_code == 200:
                data = check.json()
                status = data.get("status") or data.get("job", {}).get("status")
                if status == "success":
                    urls = data.get("urls") or data.get("job", {}).get("urls")
                    dl_url = urls[0] if urls else None
                    if dl_url:
                        time.sleep(10)
                        return requests.get(dl_url, timeout=30).content
                elif status == "failed":
                    return None
    except Exception as e:
        print(f"❌ Errore Canva image: {e}")
    return None

# ==============================================================================
# STATISTICHE CON PLAYWRIGHT (da ESPN boxscore)
# ==============================================================================
def genera_stats_html(summary, home_name, away_name, home_score, away_score,
                      home_logo, away_logo, momento, comp_name):

    badge_map = {
        "HT":     "FINE PRIMO TEMPO",
        "2H_END": "FINE SECONDO TEMPO",
        "FT":     "FINE PARTITA",
    }
    badge_label = badge_map.get(momento, "LIVE")

    teams_bs = summary.get("boxscore", {}).get("teams", [])
    home_stats = {}
    away_stats = {}
    for t in teams_bs:
        stat_dict = {s["name"]: s.get("displayValue", "0") for s in t.get("statistics", [])}
        if t.get("homeAway") == "home":
            home_stats = stat_dict
        else:
            away_stats = stat_dict

    def pct(h_raw, a_raw):
        try:
            h = float(h_raw or 0)
            a = float(a_raw or 0)
            if h + a == 0:
                return 50
            return int(h / (h + a) * 100)
        except:
            return 50

    pos_h = home_stats.get("possessionPct", "50")
    pos_a = away_stats.get("possessionPct", "50")

    stats_mappate = [
        ("Possesso palla",    f"{float(pos_h):.0f}%",                      f"{float(pos_a):.0f}%",                      pct(pos_h, pos_a)),
        ("Tiri totali",       home_stats.get("totalShots", "0"),            away_stats.get("totalShots", "0"),            pct(home_stats.get("totalShots", 0),    away_stats.get("totalShots", 0))),
        ("Tiri in porta",     home_stats.get("shotsOnTarget", "0"),         away_stats.get("shotsOnTarget", "0"),         pct(home_stats.get("shotsOnTarget", 0), away_stats.get("shotsOnTarget", 0))),
        ("Passaggi riusciti", home_stats.get("accuratePasses", "0"),        away_stats.get("accuratePasses", "0"),        pct(home_stats.get("accuratePasses", 0),away_stats.get("accuratePasses", 0))),
        ("Corner",            home_stats.get("wonCorners", "0"),            away_stats.get("wonCorners", "0"),            pct(home_stats.get("wonCorners", 0),    away_stats.get("wonCorners", 0))),
        ("Falli",             home_stats.get("foulsCommitted", "0"),        away_stats.get("foulsCommitted", "0"),        pct(home_stats.get("foulsCommitted", 0),away_stats.get("foulsCommitted", 0))),
        ("Ammoniti",          home_stats.get("yellowCards", "0"),           away_stats.get("yellowCards", "0"),           pct(home_stats.get("yellowCards", 0),   away_stats.get("yellowCards", 0))),
        ("Espulsi",           home_stats.get("redCards", "0"),              away_stats.get("redCards", "0"),              pct(home_stats.get("redCards", 0),      away_stats.get("redCards", 0))),
        ("Parate",            home_stats.get("saves", "0"),                 away_stats.get("saves", "0"),                 pct(home_stats.get("saves", 0),         away_stats.get("saves", 0))),
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
<html lang="it">
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Barlow+Condensed:wght@700;900&display=swap" rel="stylesheet">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  width: 1620px; height: 1980px;
  background: radial-gradient(circle at top left, #1e3a8a 0%, transparent 40%),
              radial-gradient(circle at bottom right, #7c3aed 0%, transparent 40%), #060816;
  font-family: 'Inter', sans-serif; padding: 50px 60px; overflow: hidden;
}}
.card {{
  width: 1500px; height: 1880px; margin: 0 auto;
  background: linear-gradient(180deg, rgba(17,24,39,0.96), rgba(10,14,28,0.96));
  border-radius: 70px; overflow: hidden;
  border: 3px solid rgba(255,255,255,0.08);
  box-shadow: 0 50px 100px rgba(0,0,0,0.6), inset 0 2px 0 rgba(255,255,255,0.04);
  display: flex; flex-direction: column;
}}
.header {{ position: relative; padding: 75px 80px 55px; border-bottom: 3px solid rgba(255,255,255,0.06); }}
.league-row {{ text-align: center; color: #7c8cb5; font-size: 28px; letter-spacing: 5px; text-transform: uppercase; font-weight: 700; margin-bottom: 35px; }}
.badge {{ width: fit-content; margin: 0 auto 40px; padding: 14px 40px; border-radius: 999px; background: linear-gradient(135deg, #facc15, #f59e0b); color: #111827; font-size: 22px; font-weight: 900; letter-spacing: 3px; text-transform: uppercase; }}
.teams-row {{ display: flex; align-items: center; justify-content: space-between; padding: 0 30px; }}
.team {{ width: 350px; text-align: center; }}
.logo {{ width: 170px; height: 170px; object-fit: contain; display: block; margin: 0 auto 25px; }}
.team-name {{ color: white; font-weight: 800; font-size: 40px; }}
.score-wrap {{ text-align: center; }}
.score {{ font-family: 'Barlow Condensed', sans-serif; font-size: 195px; line-height: 0.85; font-weight: 900; color: white; letter-spacing: -4px; }}
.match-status {{ margin-top: 20px; color: #8fa1c7; font-size: 26px; font-weight: 600; text-transform: uppercase; letter-spacing: 2px; }}
.stats-body {{ padding: 50px 80px 65px; flex: 1; display: flex; flex-direction: column; justify-content: space-between; }}
.stats-title {{ text-align: center; color: #91a4d0; font-size: 26px; font-weight: 800; letter-spacing: 4px; text-transform: uppercase; margin-bottom: 15px; }}
.stat-row {{ padding: 15px 0; border-bottom: 2px solid rgba(255,255,255,0.05); }}
.stat-row:last-child {{ border-bottom: none; }}
.stat-top {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }}
.val {{ width: 120px; color: white; font-weight: 900; font-size: 46px; font-family: 'Barlow Condensed', sans-serif; }}
.home-val {{ text-align: left; }}
.away-val {{ text-align: right; }}
.stat-label {{ color: #b4c0df; font-size: 30px; font-weight: 700; }}
.bar-track {{ position: relative; height: 22px; border-radius: 999px; overflow: hidden; background: rgba(255,255,255,0.06); }}
.bar-home {{ position: absolute; top: 0; left: 0; height: 100%; background: linear-gradient(90deg, #60a5fa, #2563eb); }}
.bar-away {{ position: absolute; top: 0; right: 0; height: 100%; background: linear-gradient(90deg, #ef4444, #dc2626); }}
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <div class="league-row">{comp_name.upper()}</div>
    <div class="badge">{badge_label}</div>
    <div class="teams-row">
      <div class="team"><img src="{home_logo}" class="logo"><div class="team-name">{home_name}</div></div>
      <div class="score-wrap"><div class="score">{home_score}–{away_score}</div><div class="match-status">LIVE STATS</div></div>
      <div class="team"><img src="{away_logo}" class="logo"><div class="team-name">{away_name}</div></div>
    </div>
  </div>
  <div class="stats-body">
    <div class="stats-title">STATISTICHE ANALITICHE</div>
    {rows_html}
  </div>
</div>
</body>
</html>"""

    path_html      = "/tmp/stats.html"
    path_raw_png   = "/tmp/stats_raw.png"
    path_final_png = "/tmp/stats_final.png"

    with open(path_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    print("📸 Rendering con Playwright...")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-web-security"])
        page = browser.new_page(viewport={"width": 1620, "height": 1980})
        page.goto(f"file://{path_html}")
        page.wait_for_timeout(3000)
        page.screenshot(path=path_raw_png)
        browser.close()

    if os.path.exists("texture.png"):
        try:
            base_img    = Image.open(path_raw_png).convert("RGBA")
            texture_img = Image.open("texture.png").convert("RGBA")
            texture_img = texture_img.resize(base_img.size, Image.Resampling.LANCZOS)
            Image.alpha_composite(base_img, texture_img).convert("RGB").save(path_final_png, "PNG")
            return path_final_png
        except Exception as e:
            print(f"Errore texture: {e}")

    return path_raw_png

# ==============================================================================
# FORMATTAZIONE MESSAGGI
# ==============================================================================
def clean_name(name):
    for w in ["AC ", "AS ", " US", " FC", "FC ", "A.C. ", "A.S. "]:
        name = name.replace(w, "")
    return " ".join(name.split())

def fmt_score(home_name, home_score, away_score, away_name, winner_id=None, home_id=None, away_id=None):
    if winner_id == home_id:
        return f"<b>{home_name} {home_score}</b>-{away_score} {away_name}"
    elif winner_id == away_id:
        return f"{home_name} {home_score}-<b>{away_score} {away_name}</b>"
    elif home_score > away_score:
        return f"<b>{home_name} {home_score}</b>-{away_score} {away_name}"
    elif away_score > home_score:
        return f"{home_name} {home_score}-<b>{away_score} {away_name}</b>"
    return f"{home_name} {home_score}-{away_score} {away_name}"

def build_scorers_line(sent_goals):
    if not sent_goals:
        return ""
    lines = [f"{g['minute']}' {g['scorer']}" for g in sent_goals]
    return f"{E_BALL} <i>{', '.join(lines)}</i>\n"

# ==============================================================================
# PARSING KEY EVENTS ESPN
# ==============================================================================
EVENT_TYPE_MAP = {
    "kickoff":         "kickoff",
    "halftime":        "halftime",
    "start-2nd-half":  "second_half_start",
    "goal":            "goal",
    "goal---header":   "goal",
    "goal---penalty":  "goal_penalty",
    "own-goal":        "own_goal",
    "substitution":    "substitution",
    "yellow-card":     "yellow_card",
    "red-card":        "red_card",
    "yellow-red-card": "red_card",
    "end-period":      "end_period",
    "full-time":       "full_time",
    "var":             "var",
    "penalty-missed":  "penalty_missed",
    "penalty-saved":   "penalty_missed",
}

def parse_key_event(ke):
    etype_raw = ke.get("type", {}).get("type", "")
    etype     = EVENT_TYPE_MAP.get(etype_raw, etype_raw)
    parts     = ke.get("participants", [])
    return {
        "id":        ke.get("id", ""),
        "type":      etype,
        "clock":     ke.get("clock", {}).get("displayValue", ""),
        "team_id":   ke.get("team", {}).get("id", ""),
        "team_name": ke.get("team", {}).get("displayName", ""),
        "text":      ke.get("text", ""),
        "period":    ke.get("period", {}).get("number", 1),
        "scoring":   ke.get("scoringPlay", False),
        "p0":        parts[0]["athlete"]["displayName"] if len(parts) > 0 else "",
        "p1":        parts[1]["athlete"]["displayName"] if len(parts) > 1 else "",
    }

# ==============================================================================
# CICLO PRINCIPALE
# ==============================================================================
def avvia_ciclo_partita():
    event, slug, comp_name = None, None, None
    while not event:
        event, slug, comp_name = find_juve_match()
        if not event:
            print("⏳ Nessuna partita Juventus trovata. Ricontrollo tra 60s...")
            time.sleep(60)

    event_id = event["id"]
    e_comp   = COMP_EMOJIS.get(slug, "⚽️")

    (home_name, away_name, home_score, away_score,
     home_id, away_id, home_logo, away_logo) = get_teams_and_scores(event)

    h_short = "Juve" if home_id == ESPN_JUVE_ID else clean_name(home_name).replace(" ", "")
    a_short = "Juve" if away_id == ESPN_JUVE_ID else clean_name(away_name).replace(" ", "")
    hashtag = f"#{h_short}{a_short}"

    print(f"⚽ Partita: {home_name} vs {away_name} [{comp_name}] ID:{event_id}")

    state = leggi_stato_da_gist()
    if state is None:
        state = {
            "event_id":        event_id,
            "sent_periods":    [],
            "sent_key_events": [],
            "sent_goals":      [],
            "goals_home":      0,
            "goals_away":      0,
            "sent_stats":      [],
            "_reset_done":     False,
        }

    while True:
        sleep_time = 90
        try:
            data = espn_get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard")
            if not data:
                time.sleep(30)
                continue

            current_event = next((ev for ev in data.get("events", []) if ev["id"] == event_id), None)
            if not current_event:
                print("⚠️ Evento non più in scoreboard. Partita probabilmente finita.")
                break

            state_str, desc, clock, period = parse_event_state(current_event)
            (home_name, away_name, home_score, away_score,
             home_id, away_id, home_logo, away_logo) = get_teams_and_scores(current_event)

            score_fmt = fmt_score(home_name, home_score, away_score, away_name,
                                  home_id=home_id, away_id=away_id)
            print(f"[{state_str}] {home_name} {home_score}-{away_score} {away_name} | {desc} {clock}")

            summary    = get_summary(event_id, slug)
            key_events = summary.get("keyEvents", []) if summary else []

            for ke in key_events:
                ke_id = ke.get("id", "")
                if ke_id in state["sent_key_events"]:
                    continue

                p = parse_key_event(ke)

                if p["type"] == "kickoff" and "kickoff" not in state["sent_periods"]:
                    send_telegram(f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{home_name} - {away_name}\n\n{e_comp} {comp_name.upper()} | {hashtag}")
                    state["sent_periods"].append("kickoff")
                    state["sent_key_events"].append(ke_id)

                elif p["type"] == "halftime" and "HT" not in state["sent_periods"]:
                    send_telegram(f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{score_fmt}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("HT")
                    state["sent_key_events"].append(ke_id)
                    if summary and "HT" not in state["sent_stats"]:
                        time.sleep(60)
                        sf = get_summary(event_id, slug)
                        if sf:
                            png = genera_stats_html(sf, home_name, away_name, home_score, away_score, home_logo, away_logo, "HT", comp_name)
                            send_telegram_stats_photo(png, "HT", f"{e_comp} {hashtag}")
                            state["sent_stats"].append("HT")

                elif p["type"] == "second_half_start" and "2H" not in state["sent_periods"]:
                    send_telegram(f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n{score_fmt}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("2H")
                    state["sent_key_events"].append(ke_id)

                elif p["type"] in ("goal", "goal_penalty", "own_goal"):
                    scorer = p["p0"] or "?"
                    assist = p["p1"]
                    is_pen = p["type"] == "goal_penalty"
                    is_own = p["type"] == "own_goal"
                    scoring_team = (away_id if p["team_id"] == home_id else home_id) if is_own else p["team_id"]
                    note = " (Rig.)" if is_pen else (" (Autogol)" if is_own else "")
                    assist_line = f"\n🎯 <i>Assist: {assist}</i>" if assist else ""
                    score_goal = fmt_score(home_name, home_score, away_score, away_name,
                                           winner_id=scoring_team, home_id=home_id, away_id=away_id)
                    send_telegram(f"<b>GOAL {E_MIC}</b>\n\n{score_goal}\n{E_BALL} <i>{p['clock']}' {scorer}{note}</i>{assist_line}\n\n{e_comp} {hashtag}")
                    state["sent_goals"].append({"minute": p["clock"], "scorer": scorer + note})
                    state["goals_home"] = home_score
                    state["goals_away"] = away_score
                    state["sent_key_events"].append(ke_id)

                elif p["type"] == "substitution":
                    send_telegram(f"<b>CAMBIO {p['team_name'].upper()} {E_SUB}</b>\n\n{E_UP} {p['p0']}\n{E_DOWN} {p['p1']}\n\n{e_comp} {hashtag}")
                    state["sent_key_events"].append(ke_id)

                elif p["type"] == "yellow_card":
                    send_telegram(f"<b>CARTELLINO GIALLO {E_YEL}</b>\n\n{E_FLAG} <i>{p['clock']}' {p['p0']} ({p['team_name']})</i>\n\n{e_comp} {hashtag}")
                    state["sent_key_events"].append(ke_id)

                elif p["type"] == "red_card":
                    send_telegram(f"<b>CARTELLINO ROSSO {E_RED}</b>\n\n🔚 <i>{p['clock']}' {p['p0']} ({p['team_name']})</i>\n\n{e_comp} {hashtag}")
                    state["sent_key_events"].append(ke_id)

                elif p["type"] == "penalty_missed":
                    send_telegram(f"<b>RIGORE SBAGLIATO {E_PEN_KO}</b>\n\n<i>{p['clock']}' {p['p0']} ({p['team_name']})</i>\n\n{e_comp} {hashtag}")
                    state["sent_key_events"].append(ke_id)

            # Gol annullato (VAR)
            if home_score + away_score < state["goals_home"] + state["goals_away"]:
                send_telegram(f"<b>GOAL ANNULLATO 📺</b>\n\n{home_name} {home_score}-{away_score} {away_name}\n\n{e_comp} {hashtag}")
                state["goals_home"] = home_score
                state["goals_away"] = away_score

            # Fine partita
            if state_str == "post" and "FT" not in state["sent_periods"]:
                scorers_line = build_scorers_line(state["sent_goals"])
                p_home_score = p_away_score = None
                for t in current_event.get("competitions", [{}])[0].get("competitors", []):
                    pen = t.get("shootoutScore")
                    if pen is not None:
                        if t.get("homeAway") == "home": p_home_score = pen
                        else: p_away_score = pen

                if p_home_score is not None:
                    final_score = f"{home_name} {home_score} ({p_home_score})-({p_away_score}) {away_score} {away_name}"
                else:
                    final_score = fmt_score(home_name, home_score, away_score, away_name, home_id=home_id, away_id=away_id)

                msg_finale = f"<b>FINE PARTITA {E_FLAG}</b>\n\n{final_score}\n{scorers_line}\n{e_comp} {hashtag}"
                canva_token = get_valid_token()
                if canva_token:
                    send_telegram_with_photo(msg_finale, get_canva_image(canva_token))
                else:
                    send_telegram(msg_finale)

                state["sent_periods"].append("FT")
                time.sleep(120)
                sf = get_summary(event_id, slug)
                if sf and "FT" not in state["sent_stats"]:
                    png = genera_stats_html(sf, home_name, away_name, home_score, away_score, home_logo, away_logo, "FT", comp_name)
                    send_telegram_stats_photo(png, "FT", f"{e_comp} {hashtag}")
                    state["sent_stats"].append("FT")

                state["_reset_done"] = True
                resetta_gist()
                print("🏁 Bot terminato.")
                sys.exit(0)

            sleep_time = 60 if state_str == "pre" else (120 if desc == "Halftime" else 90)

        except Exception as e:
            print(f"❌ Errore ciclo: {e}")
            sleep_time = 30
        finally:
            if isinstance(state, dict) and not state.get("_reset_done"):
                salva_stato_su_gist(state)

        time.sleep(sleep_time)

# ==============================================================================
# MAIN
# ==============================================================================
def main():
    print("🚀 Avvio Juventus Live Score Bot (ESPN - no API key)")
    if str(os.getenv('ONLY_REFRESH_TOKEN', '')).strip().lower() == "true":
        print("🔒 Modalità Keep-Alive: rinnovo token Canva...")
        get_valid_token()
        return
    avvia_ciclo_partita()

if __name__ == "__main__":
    main()
