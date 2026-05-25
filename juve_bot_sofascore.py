import os
import requests
import json
import time
import sys
import base64
import random
from PIL import Image
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

try:
    from nacl import encoding, public
except ImportError:
    print("⚠️ pynacl non installato. Necessario per aggiornare i Secrets di GitHub.")

# ==============================================================================
# CONFIGURAZIONE — secrets GitHub (stessi nomi del progetto originale)
# RIMOSSA: API_KEY — non serve più con Sofascore
# ==============================================================================
BOT_TOKEN           = os.getenv('TELEGRAM_TOKEN')
CHAT_ID             = os.getenv('TELEGRAM_TO')
CLIENT_ID           = os.getenv('CANVA_CLIENT_ID')
CLIENT_SECRET       = os.getenv('CANVA_CLIENT_SECRET')
CANVA_REFRESH_TOKEN = os.getenv('CANVA_REFRESH_TOKEN')
GH_PAT              = os.getenv('GH_PAT')
GITHUB_REPOSITORY   = os.getenv('GITHUB_REPOSITORY')

# ==============================================================================
# SOFASCORE — IDs e configurazione
# ==============================================================================
JUVE_ID        = 2697          # ID Juventus su Sofascore
JUVE_LOGO_URL  = "https://upload.wikimedia.org/wikipedia/commons/9/99/Juventus_FC_2017_squared_icon_%28white%29.png"

SOFASCORE_BASE = "https://www.sofascore.com/api/v1"
SOFASCORE_IMG  = "https://api.sofascore.com/api/v1/team/{}/image"

# Pool di User-Agent reali — viene scelto uno a caso ad ogni sessione
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

def _build_headers():
    """Costruisce headers freschi con UA casuale ad ogni chiamata."""
    ua = random.choice(USER_AGENTS)
    return {
        "User-Agent":                ua,
        "Accept":                    "application/json, text/plain, */*",
        "Accept-Language":           "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding":           "gzip, deflate, br",
        "Referer":                   "https://www.sofascore.com/",
        "Origin":                    "https://www.sofascore.com",
        "DNT":                       "1",
        "Connection":                "keep-alive",
        "Sec-Fetch-Dest":            "empty",
        "Sec-Fetch-Mode":            "cors",
        "Sec-Fetch-Site":            "same-origin",
        "Cache-Control":             "no-cache",
        "Pragma":                    "no-cache",
    }

CANVA_DESIGN_ID = "DAHI3ytu6yQ"
PAGINA_TARGET   = 11

# ==============================================================================
# EMOJI — identici all'originale (branding @Juventus_Reborn)
# ==============================================================================
E_BOLT   = '⚡️'; E_FLAG = '🏁'; E_MIC = '🎙'; E_BALL = '⚽️'
E_SUB    = '🔄'; E_UP   = '🔼'; E_DOWN = '🔽'; E_RED  = '🟥'
E_YEL    = '🟨'; E_PEN_OK = '✅'; E_PEN_KO = '❌'

# Mappa tournament ID Sofascore → emoji competizione
LEAGUE_EMOJIS = {
    23:   '🇮🇹',   # Serie A
    132:  '🇮🇹',   # Coppa Italia
    679:  '🇮🇹',   # Supercoppa Italiana
    7:    '🇪🇺',   # Champions League
    679:  '🇪🇺',   # Europa League  (id reale: 679 — Sofascore usa uniqueTournament)
    17:   '🇪🇺',   # Europa League
    155:  '🇪🇺',   # Conference League
    11:   '🤝',    # Amichevoli
}

MOMENTI_CONFIG = {
    "HT":     {"titolo": "<b>STATS PRIMO TEMPO</b> 📊",   "badge": "FINE PRIMO TEMPO"},
    "2H_END": {"titolo": "<b>STATS SECONDO TEMPO</b> 📊", "badge": "FINE SECONDO TEMPO"},
    "FT":     {"titolo": "<b>STATS FINE PARTITA</b> 📊",  "badge": "FINE PARTITA"},
}

def get_league_emoji(tournament_id):
    return LEAGUE_EMOJIS.get(tournament_id, "⚽️")

def clean_name(name):
    for w in ["AC ", "AS ", " US", " FC", "FC ", "A.C. ", "A.S. "]:
        name = name.replace(w, "").replace(w.strip(), "")
    return " ".join(name.split())

# ==============================================================================
# SOFASCORE API — wrapper
# ==============================================================================
# SOFASCORE API — wrapper anti-Cloudflare
# ==============================================================================
_session = None

def _get_session():
    """Sessione persistente con cookie — simula un browser che naviga il sito."""
    global _session
    if _session is None:
        _session = requests.Session()
        # Prima visita alla homepage per ottenere i cookie Cloudflare
        try:
            print("🌐 Inizializzazione sessione Sofascore...")
            _session.get(
                "https://www.sofascore.com/",
                headers=_build_headers(),
                timeout=15
            )
            time.sleep(random.uniform(2, 4))  # pausa umana dopo la homepage
            print("✅ Sessione inizializzata.")
        except Exception as e:
            print(f"⚠️ Errore init sessione: {e}")
    return _session

def sf_get(path, retries=4, base_delay=15):
    """Chiama Sofascore con retry, sessione persistente e delay casuale."""
    url = f"{SOFASCORE_BASE}{path}"
    session = _get_session()

    for attempt in range(retries):
        try:
            # Delay casuale tra chiamate (simula comportamento umano)
            if attempt > 0:
                wait = base_delay * (attempt) + random.uniform(3, 8)
                print(f"   ⏳ Attendo {wait:.0f}s prima del tentativo {attempt+1}/{retries}...")
                time.sleep(wait)

            r = session.get(url, headers=_build_headers(), timeout=15)

            if r.status_code == 200:
                return r.json()
            elif r.status_code == 403:
                print(f"⚠️ Sofascore 403 (tentativo {attempt+1}/{retries}) — reinizializzo sessione...")
                # Reinizializza la sessione con nuovi cookie
                global _session
                _session = None
                _get_session()
            elif r.status_code == 429:
                wait = base_delay * 2 + random.uniform(5, 15)
                print(f"⚠️ Sofascore 429 Too Many Requests. Attendo {wait:.0f}s...")
                time.sleep(wait)
            else:
                print(f"⚠️ Sofascore HTTP {r.status_code} su {path}")
                time.sleep(5)

        except requests.exceptions.Timeout:
            print(f"⚠️ Timeout Sofascore (tentativo {attempt+1}/{retries}).")
        except Exception as e:
            print(f"⚠️ Errore Sofascore: {e}")
            time.sleep(5)

    print(f"❌ Sofascore non raggiungibile dopo {retries} tentativi su {path}")
    return None

def trova_partita_juve_live():
    """Cerca la Juventus tra le partite di calcio live."""
    data = sf_get("/sport/football/events/live")
    if not data:
        return None
    for ev in data.get("events", []):
        if ev.get("homeTeam", {}).get("id") == JUVE_ID or \
           ev.get("awayTeam", {}).get("id") == JUVE_ID:
            return ev
    return None

def trova_partita_juve_oggi():
    """Cerca la Juventus nelle partite programmate per oggi."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    data  = sf_get(f"/team/{JUVE_ID}/events/next/0")  # prossimi eventi
    if not data:
        return None
    for ev in data.get("events", []):
        ev_date = datetime.utcfromtimestamp(ev.get("startTimestamp", 0)).strftime("%Y-%m-%d")
        if ev_date == today:
            return ev
    return None

def get_match_detail(event_id):
    """Aggiorna i dati di una partita in corso."""
    data = sf_get(f"/event/{event_id}")
    return data.get("event") if data else None

def get_incidents(event_id):
    """Recupera gol, cartellini, cambi di un evento."""
    data = sf_get(f"/event/{event_id}/incidents")
    return data.get("incidents", []) if data else []

def get_statistics(event_id):
    """Recupera le statistiche di una partita (possesso, tiri, ecc.)."""
    data = sf_get(f"/event/{event_id}/statistics")
    return data.get("statistics", []) if data else []

def logo_url(team_id, is_juve=False):
    if is_juve:
        return JUVE_LOGO_URL
    return SOFASCORE_IMG.format(team_id)

# ==============================================================================
# TELEGRAM
# ==============================================================================
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
        res = requests.post(url,
                            data={"chat_id": CHAT_ID, "caption": text, "parse_mode": "HTML"},
                            files={"photo": ("matchday.png", photo_bytes)}, timeout=25)
        if res.status_code != 200:
            send_telegram(text)
    except Exception:
        send_telegram(text)

def send_telegram_stats_photo(png_path, momento, hashtag):
    url     = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    caption = f"{MOMENTI_CONFIG[momento]['titolo']}\n\n{hashtag}"
    try:
        with open(png_path, "rb") as f:
            requests.post(url,
                          data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "HTML"},
                          files={"photo": ("stats.png", f, "image/png")}, timeout=25)
        print(f"✅ Stats ({momento}) inviate su Telegram!")
    except Exception as e:
        print(f"❌ Errore invio stats: {e}")

# ==============================================================================
# GITHUB SECRETS — identico all'originale
# ==============================================================================
def update_github_secret(secret_name, new_value):
    if not GH_PAT or not GITHUB_REPOSITORY:
        return False
    headers = {"Authorization": f"Bearer {GH_PAT}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    try:
        pk = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/secrets/public-key",
            headers=headers, timeout=10).json()
        pub_key   = public.PublicKey(pk["key"].encode(), encoding.Base64Encoder)
        encrypted = base64.b64encode(public.SealedBox(pub_key).encrypt(new_value.encode())).decode()
        res = requests.put(
            f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/secrets/{secret_name}",
            headers=headers,
            json={"encrypted_value": encrypted, "key_id": pk["key_id"]}, timeout=10)
        return res.status_code in [201, 204]
    except Exception as e:
        print(f"❌ Errore aggiornamento secret: {e}")
        return False

# ==============================================================================
# CANVA API — identico all'originale
# ==============================================================================
def get_valid_token():
    if not CANVA_REFRESH_TOKEN:
        return None
    print("🔄 Richiesta Access Token a Canva...")
    try:
        res = requests.post("https://api.canva.com/rest/v1/oauth/token",
                            data={"grant_type": "refresh_token",
                                  "refresh_token": CANVA_REFRESH_TOKEN,
                                  "client_id": CLIENT_ID,
                                  "client_secret": CLIENT_SECRET}, timeout=15)
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
                            json={"design_id": CANVA_DESIGN_ID,
                                  "format": {"type": "png", "pages": [PAGINA_TARGET]}}, timeout=15)
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
                urls   = check.get("urls") or check.get("job", {}).get("urls")
                dl_url = urls[0] if urls else check.get("url")
                if dl_url:
                    return requests.get(dl_url, timeout=20).content
            elif stato == "failed":
                return None
    except Exception as e:
        print(f"❌ Errore Canva: {e}")
    return None

# ==============================================================================
# GRAFICHE STATISTICHE — adattato a struttura Sofascore
# Sofascore restituisce statistics[] con groups[] → items[] → statisticsType + homeValue/awayValue
# ==============================================================================
def parse_sofascore_stats(statistics):
    """Appiattisce la struttura a gruppi di Sofascore in un dict chiave→(home,away)."""
    result = {}
    for group in statistics:
        for item in group.get("statisticsItems", []):
            key      = item.get("statisticsType", "")
            home_val = item.get("homeValue")
            away_val = item.get("awayValue")
            result[key] = (home_val, away_val)
    return result

def recupera_e_genera_stats_html(event_id, home_id, away_id, home_name, away_name,
                                  home_goals, away_goals, momento, league_name="SERIE A"):
    print(f"📊 Recupero statistiche Sofascore per {momento}...")

    statistics = get_statistics(event_id)
    stats      = parse_sofascore_stats(statistics)

    h_logo = logo_url(home_id, "juventus" in home_name.lower())
    a_logo = logo_url(away_id, "juventus" in away_name.lower())
    badge_label = MOMENTI_CONFIG[momento]["badge"]

    def sv(key, idx):
        """Safe value: ritorna stringa, default '0'."""
        v = stats.get(key, (0, 0))[idx]
        return str(v) if v is not None else "0"

    def perc(h_raw, a_raw, is_pct=False):
        """Calcola la % per la barra home."""
        try:
            h = float(str(h_raw).replace("%", "")) if h_raw is not None else 0
            a = float(str(a_raw).replace("%", "")) if a_raw is not None else 0
            if is_pct:
                return int(h)           # già percentuale (es. possesso)
            return 50 if (h + a) == 0 else int(h / (h + a) * 100)
        except:
            return 50

    # Chiavi usate da Sofascore
    pos_h_raw = stats.get("ballPossession", ("50%", "50%"))[0]
    pos_a_raw = stats.get("ballPossession", ("50%", "50%"))[1]
    pos_h = str(pos_h_raw) if pos_h_raw else "50%"
    pos_a = str(pos_a_raw) if pos_a_raw else "50%"

    xg_h = sv("expectedGoals", 0); xg_a = sv("expectedGoals", 1)

    stats_mappate = [
        ("xG",               xg_h,                          xg_a,                          perc(xg_h, xg_a)),
        ("Possesso palla",   pos_h,                         pos_a,                         perc(pos_h_raw, pos_a_raw, is_pct=True)),
        ("Tiri totali",      sv("totalShotsOnGoal", 0),     sv("totalShotsOnGoal", 1),     perc(sv("totalShotsOnGoal",0), sv("totalShotsOnGoal",1))),
        ("Tiri in porta",    sv("shotsOnTarget", 0),        sv("shotsOnTarget", 1),        perc(sv("shotsOnTarget",0), sv("shotsOnTarget",1))),
        ("Passaggi riusciti",sv("accuratePasses", 0),       sv("accuratePasses", 1),       perc(sv("accuratePasses",0), sv("accuratePasses",1))),
        ("Corner",           sv("cornerKicks", 0),          sv("cornerKicks", 1),          perc(sv("cornerKicks",0), sv("cornerKicks",1))),
        ("Falli",            sv("fouls", 0),                sv("fouls", 1),                perc(sv("fouls",0), sv("fouls",1))),
        ("Ammoniti",         sv("yellowCards", 0),          sv("yellowCards", 1),          perc(sv("yellowCards",0), sv("yellowCards",1))),
        ("Espulsi",          sv("redCards", 0),             sv("redCards", 1),             perc(sv("redCards",0), sv("redCards",1))),
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
body {{ width:1620px; height:1980px;
  background: radial-gradient(circle at top left,#1e3a8a 0%,transparent 40%),
              radial-gradient(circle at bottom right,#7c3aed 0%,transparent 40%), #060816;
  font-family:'Inter',sans-serif; padding:50px 60px; overflow:hidden; }}
.card {{ width:1500px; height:1880px; margin:0 auto;
  background:linear-gradient(180deg,rgba(17,24,39,.96),rgba(10,14,28,.96));
  border-radius:70px; overflow:hidden; border:3px solid rgba(255,255,255,.08);
  display:flex; flex-direction:column; }}
.header {{ padding:75px 80px 55px; border-bottom:3px solid rgba(255,255,255,.06); }}
.league-row {{ text-align:center; color:#7c8cb5; font-size:28px; letter-spacing:5px;
  text-transform:uppercase; font-weight:700; margin-bottom:35px; }}
.badge {{ width:fit-content; margin:0 auto 40px; padding:14px 40px; border-radius:999px;
  background:linear-gradient(135deg,#facc15,#f59e0b); color:#111827;
  font-size:22px; font-weight:900; letter-spacing:3px; text-transform:uppercase; }}
.teams-row {{ display:flex; align-items:center; justify-content:space-between; padding:0 30px; }}
.team {{ width:350px; text-align:center; }}
.logo {{ width:170px; height:170px; object-fit:contain; display:block; margin:0 auto 25px; }}
.team-name {{ color:white; font-weight:800; font-size:40px; }}
.score-wrap {{ text-align:center; }}
.score {{ font-family:'Barlow Condensed',sans-serif; font-size:195px; line-height:.85; font-weight:900; color:white; }}
.match-status {{ margin-top:20px; color:#8fa1c7; font-size:26px; font-weight:600;
  text-transform:uppercase; letter-spacing:2px; }}
.stats-body {{ padding:50px 80px 65px; flex:1; display:flex; flex-direction:column; justify-content:space-between; }}
.stats-title {{ text-align:center; color:#91a4d0; font-size:26px; font-weight:800;
  letter-spacing:4px; text-transform:uppercase; margin-bottom:15px; }}
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

    path_html      = "/tmp/stats.html"
    path_raw_png   = "/tmp/stats_raw.png"
    path_final_png = "/tmp/stats_final.png"

    with open(path_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    print("📸 Rendering Playwright 1620x1980...")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-web-security", "--allow-running-insecure-content"])
        page    = browser.new_page(viewport={"width": 1620, "height": 1980})
        page.goto(f"file://{path_html}")
        page.wait_for_timeout(3000)
        page.screenshot(path=path_raw_png, omit_background=False)
        browser.close()

    if os.path.exists("texture.png"):
        try:
            base_img = Image.open(path_raw_png).convert("RGBA")
            tex      = Image.open("texture.png").convert("RGBA").resize(base_img.size, Image.Resampling.LANCZOS)
            Image.alpha_composite(base_img, tex).convert("RGB").save(path_final_png, "PNG")
            print("🎨 Texture applicata con successo!")
            return path_final_png
        except Exception as e:
            print(f"Errore texture: {e}")
    return path_raw_png

# ==============================================================================
# PARSING INCIDENTS — struttura Sofascore
# incidentType: goal | card | substitution | inGamePenalty | varDecision | period
# ==============================================================================
def build_scorers_text(incidents, home_id, away_id):
    home_list, away_list = [], []
    for inc in incidents:
        if inc.get("incidentType") != "goal":
            continue
        if "shootout" in str(inc.get("incidentClass", "")).lower():
            continue
        mn  = inc.get("time", "?")
        inj = inc.get("addedTime")
        mn_str  = f"{mn}+{inj}" if inj else str(mn)
        p_name  = inc.get("player", {}).get("name", "Giocatore")
        cls     = str(inc.get("incidentClass", "")).lower()
        if "penalty"  in cls: p_name += " (Rig.)"
        elif "own"    in cls: p_name += " (Autogol)"
        entry = f"{mn_str}' {p_name}"
        if inc.get("isHome"):
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
    print("✅ Avvio monitoraggio Sofascore...")

    event_id = None

    # ── Trova il match ────────────────────────────────────────────────────────
    while not event_id:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        print(f"🔄 Cerco partita Juventus ({today})...")

        # 1. Live
        ev = trova_partita_juve_live()
        if ev:
            event_id = ev["id"]
            print(f"🔥 Match LIVE trovato! ID: {event_id}")

        # 2. Oggi (non ancora iniziata)
        if not event_id:
            ev = trova_partita_juve_oggi()
            if ev:
                event_id = ev["id"]
                print(f"📅 Match trovato oggi! ID: {event_id}")

        if not event_id:
            print("❌ Nessun match trovato. Riprovo tra 30s...")
            time.sleep(30)

    print(f"⏳ Aggancio completato ID={event_id}. Inizio monitoraggio...")

    state = {
        "event_id":        event_id,
        "sent_periods":    [],
        "goals_detected":  0,
        "sent_subs":       [],
        "sent_cards":      [],
        "pen_count":       0,
        "sent_stats":      [],
        "incidents_visti": [],
    }

    while True:
        sleep_time = 60  # default

        if os.path.exists("match_state.json"):
            with open("match_state.json") as f:
                state = json.load(f)

        try:
            ev = get_match_detail(event_id)
            if not ev:
                print("⚠️ Dati partita non disponibili. Riprovo...")
                time.sleep(30)
                continue

            status_obj = ev.get("status", {})
            status_type = status_obj.get("type", "notstarted")   # notstarted|inprogress|halftime|finished
            status_desc = status_obj.get("description", "")

            home_score = ev.get("homeScore", {}).get("current", 0) or 0
            away_score = ev.get("awayScore", {}).get("current", 0) or 0

            home_team = ev.get("homeTeam", {})
            away_team = ev.get("awayTeam", {})
            home_id   = home_team.get("id")
            away_id   = away_team.get("id")

            home_name = "Juventus" if home_id == JUVE_ID else clean_name(home_team.get("shortName") or home_team.get("name", "Home"))
            away_name = "Juventus" if away_id == JUVE_ID else clean_name(away_team.get("shortName") or away_team.get("name", "Away"))

            tournament    = ev.get("tournament", {})
            league_name   = tournament.get("name", "Serie A")
            unique_tourn  = ev.get("uniqueTournament", {})
            tournament_id = unique_tourn.get("id", 0)
            e_comp        = get_league_emoji(tournament_id)

            h_short = "Juve" if home_id == JUVE_ID else home_name.replace(" ", "")
            a_short = "Juve" if away_id == JUVE_ID else away_name.replace(" ", "")
            hashtag = f"#{h_short}{a_short}"

            def bold_score():
                if home_score > away_score:
                    return f"<b>{home_name} {home_score}</b>-{away_score} {away_name}"
                elif away_score > home_score:
                    return f"{home_name} {home_score}-<b>{away_score} {away_name}</b>"
                return f"{home_name} {home_score}-{away_score} {away_name}"

            print(f"[LIVE] {home_name} {home_score}-{away_score} {away_name} | {status_desc}")

            # Aspetta inizio
            if status_type == "notstarted":
                print("💤 Partita non ancora iniziata. Attendo 30s...")
                time.sleep(30)
                continue

            # ── INIZIO 1° TEMPO ───────────────────────────────────────────────
            if status_type == "inprogress" and "1H" not in state["sent_periods"]:
                send_telegram(f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{home_name} - {away_name}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("1H")

            # ── FINE 1° TEMPO ─────────────────────────────────────────────────
            elif status_type == "halftime" and "HT" not in state["sent_periods"]:
                send_telegram(f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{bold_score()}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("HT")
                print("⏳ Attesa 2 min per consolidamento dati HT...")
                time.sleep(120)
                png = recupera_e_genera_stats_html(event_id, home_id, away_id,
                                                   home_name, away_name,
                                                   home_score, away_score, "HT", league_name)
                send_telegram_stats_photo(png, "HT", f"{e_comp} {hashtag}")
                state["sent_stats"].append("HT")
                sleep_time = 30

            # ── INIZIO 2° TEMPO ───────────────────────────────────────────────
            elif (status_type == "inprogress" and "HT" in state["sent_periods"]
                  and "2H" not in state["sent_periods"]):
                send_telegram(f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n{bold_score()}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("2H")

            # ── SUPPLEMENTARI ─────────────────────────────────────────────────
            elif status_type == "extra_time" and "ET" not in state["sent_periods"]:
                send_telegram(f"<b>TEMPI SUPPLEMENTARI {E_BOLT}</b>\n\n{bold_score()}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("ET")
                time.sleep(120)
                png = recupera_e_genera_stats_html(event_id, home_id, away_id,
                                                   home_name, away_name,
                                                   home_score, away_score, "2H_END", league_name)
                send_telegram_stats_photo(png, "2H_END", f"{e_comp} {hashtag}")
                state["sent_stats"].append("2H_END")

            # ── FINE PARTITA ──────────────────────────────────────────────────
            if status_type == "finished" and "FT" not in state["sent_periods"]:
                incidents = get_incidents(event_id)
                scorers_line = build_scorers_text(incidents, home_id, away_id)

                # Rigori
                pen_home = ev.get("homeScore", {}).get("penalties")
                pen_away = ev.get("awayScore", {}).get("penalties")
                if pen_home is not None:
                    vincitore_home = pen_home > pen_away
                    msg_fin = (f"<b>FINE PARTITA {E_FLAG}</b>\n\n"
                               f"{'<b>' if vincitore_home else ''}{home_name} {home_score} ({pen_home}){'</b>' if vincitore_home else ''}"
                               f"-"
                               f"{'<b>' if not vincitore_home else ''}({pen_away}) {away_score} {away_name}{'</b>' if not vincitore_home else ''}\n"
                               f"{scorers_line}\n{e_comp} {hashtag}")
                else:
                    msg_fin = f"<b>FINE PARTITA {E_FLAG}</b>\n\n{bold_score()}\n{scorers_line}\n{e_comp} {hashtag}"

                token = get_valid_token()
                foto  = get_canva_image(token) if token else None
                send_telegram_with_photo(msg_fin, foto)

                state["sent_periods"].append("FT")
                print("⏳ Attesa 2 min per stats FT...")
                time.sleep(120)
                png = recupera_e_genera_stats_html(event_id, home_id, away_id,
                                                   home_name, away_name,
                                                   home_score, away_score, "FT", league_name)
                send_telegram_stats_photo(png, "FT", f"{e_comp} {hashtag}")

                if os.path.exists("match_state.json"):
                    os.remove("match_state.json")
                print("🏁 Bot terminato con successo.")
                sys.exit(0)

            # ── INCIDENTS: GOAL, CARTELLINI, CAMBI ────────────────────────────
            incidents = get_incidents(event_id)
            total_goals = home_score + away_score

            # GOAL
            if total_goals > state["goals_detected"]:
                goals = [i for i in incidents
                         if i.get("incidentType") == "goal"
                         and "shootout" not in str(i.get("incidentClass", "")).lower()]
                last_g_msg = ""
                if goals:
                    goals.sort(key=lambda x: (x.get("time", 0), x.get("addedTime") or 0))
                    last = goals[-1]
                    p_name = last.get("player", {}).get("name")
                    if not p_name:
                        print("⏳ Marcatore non ancora disponibile. Attendo prossimo ciclo...")
                        with open("match_state.json", "w") as f: json.dump(state, f)
                        time.sleep(sleep_time)
                        continue
                    mn  = last.get("time", "?")
                    inj = last.get("addedTime")
                    mn_str = f"{mn}+{inj}" if inj else str(mn)
                    cls    = str(last.get("incidentClass", "")).lower()
                    if "penalty" in cls: p_name += " (Rig.)"
                    elif "own"   in cls: p_name += " (Autogol)"
                    last_g_msg = f"{E_BALL} <i>{mn_str}' {p_name}</i>\n"
                send_telegram(f"<b>GOAL {E_MIC}</b>\n\n{bold_score()}\n{last_g_msg}\n{e_comp} {hashtag}")
                state["goals_detected"] = total_goals

            elif total_goals < state["goals_detected"]:
                send_telegram(f"<b>GOAL ANNULLATO 📺</b>\n\n{home_name} {home_score}-{away_score} {away_name}\n\n{e_comp} {hashtag}")
                state["goals_detected"] = total_goals

            # CARTELLINI
            for inc in incidents:
                if inc.get("incidentType") != "card":
                    continue
                inc_id = str(inc.get("id", ""))
                if inc_id in state["incidents_visti"]:
                    continue
                cls    = str(inc.get("incidentClass", "")).lower()
                p_name = inc.get("player", {}).get("name", "Giocatore")
                mn     = inc.get("time", "?")
                if "red" in cls:
                    send_telegram(f"<b>CARTELLINO ROSSO {E_RED}</b>\n\n🔚 <i>{mn}' {p_name}</i>\n\n{e_comp} {hashtag}")
                    state["incidents_visti"].append(inc_id)
                elif "yellow" in cls and "red" not in cls:
                    # Solo cartellini gialli della Juve
                    is_juve_card = (inc.get("isHome") and home_id == JUVE_ID) or \
                                   (not inc.get("isHome") and away_id == JUVE_ID)
                    if is_juve_card:
                        send_telegram(f"<b>AMMONIZIONE {E_YEL}</b>\n\n<i>{mn}' {p_name}</i>\n\n{e_comp} {hashtag}")
                        state["incidents_visti"].append(inc_id)

            # CAMBI — raggruppati per squadra nella stessa finestra di 2 minuti
            subs_by_key = {}
            for inc in incidents:
                if inc.get("incidentType") != "substitution":
                    continue
                inc_id = str(inc.get("id", ""))
                if inc_id in state["sent_subs"]:
                    continue
                mn      = inc.get("time", 0) or 0
                is_home = inc.get("isHome", True)
                t_id    = home_id if is_home else away_id
                p_in    = inc.get("playerIn",  {}).get("name", "Entrante")
                p_out   = inc.get("playerOut", {}).get("name", "Uscente")
                key     = f"{t_id}_{mn // 2}"
                if key not in subs_by_key:
                    subs_by_key[key] = {"minute": mn, "team_id": t_id, "in": [], "out": [], "ids": []}
                subs_by_key[key]["in"].append(p_in)
                subs_by_key[key]["out"].append(p_out)
                subs_by_key[key]["ids"].append(inc_id)

            for key, s in subs_by_key.items():
                team_title = "JUVENTUS" if s["team_id"] == JUVE_ID else \
                             (home_name.upper() if s["team_id"] == home_id else away_name.upper())
                send_telegram(
                    f"<b>CAMBIO {team_title} {E_SUB}</b>\n\n"
                    f"{E_UP} {', '.join(s['in'])}\n"
                    f"{E_DOWN} {', '.join(s['out'])}\n\n"
                    f"{e_comp} {hashtag}"
                )
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
    print("🚀 Avvio Juventus Live Bot (Sofascore — no API key) ...")
    if str(os.getenv("ONLY_REFRESH_TOKEN", "")).strip().lower() == "true":
        print("🔒 Modalità Keep-Alive: rinnovo token Canva...")
        get_valid_token()
        return
    avvia_ciclo_partita()

if __name__ == "__main__":
    main()
