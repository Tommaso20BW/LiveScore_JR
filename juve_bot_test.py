import os
import requests
import json
import time
import sys
import base64
from PIL import Image
from datetime import datetime
from playwright.sync_api import sync_playwright

# Usiamo NaCl (Libsodium) per criptare il secret come richiesto dalle API di GitHub
try:
    from nacl import encoding, public
except ImportError:
    print("⚠️ Errore: La libreria 'pynacl' non è installata. Necessaria per aggiornare i Secrets di GitHub.")

# ==============================================================================
# CONFIGURAZIONE CHIAVI E DATI REQUISITI (DA SECRETS GITHUB)
# ==============================================================================
API_KEY = os.getenv('API_KEY')
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')
CLIENT_ID = os.getenv('CANVA_CLIENT_ID')
CLIENT_SECRET = os.getenv('CANVA_CLIENT_SECRET')
CANVA_REFRESH_TOKEN = os.getenv('CANVA_REFRESH_TOKEN')
GH_PAT = os.getenv('GH_PAT')                 # Il tuo Personal Access Token di GitHub
GITHUB_REPOSITORY = os.getenv('GITHUB_REPOSITORY') # Es: "tuo-utente/tuo-repo"

JUVE_ID = 5499
CANVA_DESIGN_ID = "DAHI3ytu6yQ"
PAGINA_TARGET = 11

JUVE_LOGO_URL = "https://upload.wikimedia.org/wikipedia/commons/9/99/Juventus_FC_2017_squared_icon_%28white%29.png"
API_LOGO_URL = "https://media.api-sports.io/football/teams/{}.png"

# ==============================================================================
# SET EMOJI STANDARD (BRANDING @Juventus_Reborn)
# ==============================================================================
E_BOLT = '⚡️'
E_FLAG = '🏁'
E_MIC = '🎙'
E_BALL = '⚽️'
E_SUB = '🔄'
E_UP = '🔼'
E_DOWN = '🔽'
E_RED = '🟥'
E_PEN_OK = '✅'
E_PEN_KO = '❌'

LEAGUE_EMOJIS = {
    135: '🇮🇹',   # Serie A
    137: '🇮🇹',   # Coppa Italia
    547: '🇮🇹',   # Supercoppa Italiana
    2:   '🇪🇺',   # Champions League
    3:   '🇪🇺',   # Europa League
    848: '🇪🇺',   # Conference League
    667: '🤝'   # Amichevoli Club
}

MOMENTI_CONFIG = {
    "HT": {"titolo": "<b>STATS PRIMO TEMPO</b> 📊", "badge": "FINE PRIMO TEMPO"},
    "2H_END": {"titolo": "<b>STATS SECONDO TEMPO</b> 📊", "badge": "FINE SECONDO TEMPO"},
    "FT": {"titolo": "<b>STATS FINE PARTITA</b> 📊", "badge": "FINE PARTITA"}
}

def get_league_emoji(league_id):
    return LEAGUE_EMOJIS.get(league_id, "⚽️")

def clean_name(name):
    annoying_words = ["AC ", "AS ", " US", " FC", "FC ", "A.C. ", "A.S. "]
    for word in annoying_words:
        name = name.replace(word, "")
        name = name.replace(word.strip(), "")
    return " ".join(name.split())

def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("Errore: BOT_TOKEN o CHAT_ID non configurati.")
        return
        
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"Errore invio Telegram: {e}")

def send_telegram_with_photo(text, photo_bytes):
    if not photo_bytes:
        print("⚠️ Immagine Canva mancante. Invio il solo testo...")
        send_telegram(text)
        return

    print("📤 Spedisco il post con grafica Canva su Telegram...")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    payload = {"chat_id": CHAT_ID, "caption": text, "parse_mode": "HTML"}
    files = {"photo": ("matchday.png", photo_bytes)}
    
    try:
        res = requests.post(url, data=payload, files=files, timeout=25)
        if res.status_code == 200:
            print("🏁 Grafica fine partita pubblicata!")
        else:
            send_telegram(text)
    except Exception as e:
        send_telegram(text)

def send_telegram_stats_photo(png_path, momento, hashtag):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    caption = f"{MOMENTI_CONFIG[momento]['titolo']}\n\n{hashtag}"
    try:
        with open(png_path, "rb") as f:
            requests.post(url, data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "HTML"}, 
                          files={"photo": ("stats.png", f, "image/png")}, timeout=25)
        print(f"✅ Statistiche ({momento}) inviate su Telegram!")
    except Exception as e:
        print(f"❌ Errore invio foto statistiche Telegram: {e}")

# ==============================================================================
# FUNZIONE AGGIORNAMENTO SECRET GITHUB
# ==============================================================================
def update_github_secret(secret_name, new_value):
    """Aggiorna programmaticamente un secret nella repository GitHub corrente."""
    if not GH_PAT or not GITHUB_REPOSITORY:
        print("⚠️ Impossibile aggiornare il secret: GH_PAT o GITHUB_REPOSITORY non presenti nell'ambiente.")
        return False

    headers = {
        "Authorization": f"Bearer {GH_PAT}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    pk_url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/secrets/public-key"
    try:
        res_pk = requests.get(pk_url, headers=headers, timeout=10)
        if res_pk.status_code != 200:
            print(f"❌ Impossibile ottenere la public key di GitHub: {res_pk.text}")
            return False
        
        pk_data = res_pk.json()
        key_id = pk_data["key_id"]
        public_key_b64 = pk_data["key"]

        public_key = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder)
        sealed_box = public.SealedBox(public_key)
        encrypted_value = sealed_box.encrypt(new_value.encode("utf-8"))
        encrypted_b64 = base64.b64encode(encrypted_value).decode("utf-8")

        secret_url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/secrets/{secret_name}"
        payload = {
            "encrypted_value": encrypted_b64,
            "key_id": key_id
        }
        
        res_secret = requests.put(secret_url, headers=headers, json=payload, timeout=10)
        if res_secret.status_code in [201, 204]:
            print(f"✅ Secret '{secret_name}' aggiornato con successo su GitHub per i prossimi match!")
            return True
        else:
            print(f"❌ Errore durante l'aggiornamento del secret su GitHub: {res_secret.text}")
            return False
    except Exception as e:
        print(f"❌ Eccezione durante l'aggiornamento del secret GitHub: {e}")
        return False

# ==============================================================================
# FUNZIONI INTEGRATE CANVA API
# ==============================================================================
def get_valid_token():
    """Genera un Access Token e aggiorna il Refresh Token se Canva ne fornisce uno nuovo."""
    if not CANVA_REFRESH_TOKEN:
        print("❌ Errore: CANVA_REFRESH_TOKEN non trovato.")
        return None

    print("🔄 Richiesta di un Access Token temporaneo a Canva...")
    url = "https://api.canva.com/rest/v1/oauth/token"
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": CANVA_REFRESH_TOKEN,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    
    try:
        res = requests.post(url, data=payload, timeout=15)
        if res.status_code == 200:
            new_tokens = res.json()
            print("✅ Access Token generato con successo!")
            
            if "refresh_token" in new_tokens and new_tokens["refresh_token"] != CANVA_REFRESH_TOKEN:
                print("🔄 Canva ha emesso un nuovo Refresh Token. Aggiorno GitHub Secrets...")
                update_github_secret("CANVA_REFRESH_TOKEN", new_tokens["refresh_token"])
                
            return new_tokens["access_token"]
        else:
            print(f"❌ Errore nel recupero del token Canva: {res.text}")
            return None
    except Exception as e:
        print(f"Errore connessione Canva OAuth: {e}")
        return None

def get_canva_image(access_token):
    if not access_token:
        return None

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    start_url = "https://api.canva.com/rest/v1/exports"
    payload = {
        "design_id": CANVA_DESIGN_ID,
        "format": {"type": "png", "pages": [PAGINA_TARGET]}
    }

    try:
        print("🎨 Richiesta generazione immagine a Canva...")
        response = requests.post(start_url, headers=headers, json=payload, timeout=15)
        if response.status_code not in [200, 201]:
            print(f"❌ Errore avvio export Canva: {response.text}")
            return None
        
        job_data = response.json()
        job_id = job_data.get("id") or job_data.get("job", {}).get("id")
        
        if not job_id:
            return None
        
        status_url = f"https://api.canva.com/rest/v1/exports/{job_id}"
        print("⏳ Attesa rendering della grafica su Canva...")
        for i in range(40):
            time.sleep(4)
            check_res = requests.get(status_url, headers=headers, timeout=15)
            if check_res.status_code == 200:
                status_data = check_res.json()
                status_corrente = status_data.get("status") or status_data.get("job", {}).get("status")
                print(f"   [Controllo {i+1}/40] Stato Canva: {status_corrente}")
                
                if status_corrente == "success":
                    urls_list = status_data.get("urls") or status_data.get("job", {}).get("urls")
                    download_url = urls_list[0] if urls_list else (status_data.get("url") or status_data.get("job", {}).get("url"))
                    
                    if download_url:
                        print("📥 Download file PNG completato.")
                        img_res = requests.get(download_url, timeout=20)
                        return img_res.content
                        
                elif status_corrente == "failed":
                    return None
                    
        print("❌ Timeout Canva.")
    except Exception as e:
        print(f"❌ Errore durante il recupero da Canva: {e}")
    return None

# ==============================================================================

def build_split_scorers_text(events, home_id, away_id):
    if not events: return ""
    home_scorers, away_scorers = [], []
    
    for e in events:
        if e.get('type', '').lower() == 'goal' and "shootout" not in e.get('detail', '').lower():
            elapsed = e.get('time', {}).get('elapsed', '?')
            extra = e.get('time', {}).get('extra')
            minute_str = f"{elapsed}+{extra}" if extra else f"{elapsed}"
            player_name = e.get('player', {}).get('name', 'Giocatore')
            detail = e.get('detail', '').lower()
            event_team_id = e.get('team', {}).get('id')
            
            if "penalty" in detail: player_name += " (Rig.)"
            elif "own goal" in detail: player_name += " (Autogol)"
            
            scorer_entry = f"{minute_str}’ {player_name}"
            if event_team_id == home_id: home_scorers.append(scorer_entry)
            elif event_team_id == away_id: away_scorers.append(scorer_entry)
                
    if home_scorers and away_scorers:
        return f"{E_BALL} <i>" + ", ".join(home_scorers) + " // " + ", ".join(away_scorers) + "</i>\n"
    elif home_scorers:
        return f"{E_BALL} <i>" + ", ".join(home_scorers) + "</i>\n"
    elif away_scorers:
        return f"{E_BALL} <i>" + ", ".join(away_scorers) + "</i>\n"
    return ""

# ==============================================================================
# LOGICA GESTIONE GRAFICA STATISTICHE CON PLAYWRIGHT E TEXTURE (1620x1980)
# ==============================================================================
def recupera_e_genera_stats_html(match_id, headers, home_id, away_id, home_name, away_name, home_goals, away_goals, momento, league_name="SERIE A"):
    print(f"📊 Recupero statistiche reali dall'API per il momento {momento}...")
    stats_url = f"https://v3.football.api-sports.io/fixtures/statistics?fixture={match_id}"
    
    h_logo = JUVE_LOGO_URL if "juventus" in home_name.lower() else API_LOGO_URL.format(home_id)
    a_logo = JUVE_LOGO_URL if "juventus" in away_name.lower() else API_LOGO_URL.format(away_id)
    badge_label = MOMENTI_CONFIG[momento]['badge']
    
    # Valori di fallback predefiniti
    api_stats = {"Shots on Goal": [0,0], "Total Shots": [0,0], "Fouls": [0,0], "Corner Kicks": [0,0], 
                 "Ball Possession": ["50%","50%"], "Yellow Cards": [0,0], "Red Cards": [0,0], 
                 "expected_goals": ["0.0","0.0"], "Passes accurate": [0,0]}
                                 
    try:
        res = requests.get(stats_url, headers=headers, timeout=15).json()
        if res.get('response') and len(res['response']) >= 2:
            for team_data in res['response']:
                t_id = team_data['team']['id']
                idx = 0 if t_id == home_id else 1
                for s in team_data['statistics']:
                    api_stats[s['type']] = api_stats.get(s['type'], [0,0])
                    api_stats[s['type']][idx] = s['value']
    except Exception as e:
        print(f"⚠️ Errore nel recupero statistiche API: {e}. Uso valori di fallback.")

    def pulisci_val_int(val):
        if val is None: return 0
        return int(str(val).replace('%', '').strip())

    def pulisci_val_float(val):
        if val is None: return 0.0
        return float(str(val).strip())

    def calcola_percentuale_barra(h_val, a_val, tipo="int"):
        if tipo == "float":
            h, a = pulisci_val_float(h_val), pulisci_val_float(a_val)
        else:
            h, a = pulisci_val_int(h_val), pulisci_val_int(a_val)
        if (h + a) == 0: return 50
        return int((h / (h + a)) * 100)

    pos_h = str(api_stats["Ball Possession"][0]) if api_stats["Ball Possession"][0] is not None else "50%"
    pos_a = str(api_stats["Ball Possession"][1]) if api_stats["Ball Possession"][1] is not None else "50%"
    bp_perc = calcola_percentuale_barra(pos_h, pos_a)

    raw_xg_h = api_stats.get("expected_goals", ["0.0", "0.0"])[0]
    raw_xg_a = api_stats.get("expected_goals", ["0.0", "0.0"])[1]

    xg_h = str(raw_xg_h) if raw_xg_h is not None else "0.0"
    xg_a = str(raw_xg_a) if raw_xg_a is not None else "0.0"

    if pulisci_val_float(xg_h) == 0.0 and pulisci_val_float(xg_a) == 0.0:
        xg_perc = 50
    else:
        xg_perc = calcola_percentuale_barra(xg_h, xg_a, tipo="float")

    stats_mappate = [
        ("Possesso palla", pos_h, pos_a, bp_perc),
        ("Tiri totali", str(api_stats["Total Shots"][0] or 0), str(api_stats["Total Shots"][1] or 0), calcola_percentuale_barra(api_stats["Total Shots"][0], api_stats["Total Shots"][1])),
        ("Tiri in porta", str(api_stats["Shots on Goal"][0] or 0), str(api_stats["Shots on Goal"][1] or 0), calcola_percentuale_barra(api_stats["Shots on Goal"][0], api_stats["Shots on Goal"][1])),
        ("xG", xg_h, xg_a, xg_perc),
        ("Passaggi riusciti", str(api_stats.get("Passes accurate", [0,0])[0] or 0), str(api_stats.get("Passes accurate", [0,0])[1] or 0), calcola_percentuale_barra(api_stats.get("Passes accurate", [0,0])[0], api_stats.get("Passes accurate", [0,0])[1])),
        ("Corner", str(api_stats["Corner Kicks"][0] or 0), str(api_stats["Corner Kicks"][1] or 0), calcola_percentuale_barra(api_stats["Corner Kicks"][0], api_stats["Corner Kicks"][1])),
        ("Falli", str(api_stats["Fouls"][0] or 0), str(api_stats["Fouls"][1] or 0), calcola_percentuale_barra(api_stats["Fouls"][0], api_stats["Fouls"][1])),
        ("Ammoniti", str(api_stats["Yellow Cards"][0] or 0), str(api_stats["Yellow Cards"][1] or 0), calcola_percentuale_barra(api_stats["Yellow Cards"][0], api_stats["Yellow Cards"][1])),
        ("Espulsi", str(api_stats["Red Cards"][0] or 0), str(api_stats["Red Cards"][1] or 0), calcola_percentuale_barra(api_stats["Red Cards"][0], api_stats["Red Cards"][1]))
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

    html_content = f"""
<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Barlow+Condensed:wght@700;900&display=swap" rel="stylesheet">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  width: 1620px;
  height: 1980px;
  background:
    radial-gradient(circle at top left, #1e3a8a 0%, transparent 40%),
    radial-gradient(circle at bottom right, #7c3aed 0%, transparent 40%),
    #060816;
  font-family: 'Inter', sans-serif;
  padding: 50px 60px;
  overflow: hidden;
}}
.card {{
  width: 1500px;
  height: 1880px;
  margin: 0 auto;
  background: linear-gradient(180deg, rgba(17,24,39,0.96), rgba(10,14,28,0.96));
  border-radius: 70px;
  overflow: hidden;
  border: 3px solid rgba(255,255,255,0.08);
  box-shadow: 0 50px 100px rgba(0,0,0,0.6), inset 0 2px 0 rgba(255,255,255,0.04);
  display: flex;
  flex-direction: column;
}}
.header {{ 
  position: relative; 
  padding: 75px 80px 55px; 
  border-bottom: 3px solid rgba(255,255,255,0.06); 
}}
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
.bar-home, .bar-away {{ position: absolute; top: 0; height: 100%; }}
.bar-home {{ left: 0; background: linear-gradient(90deg, #60a5fa, #2563eb); }}
.bar-away {{ right: 0; background: linear-gradient(90deg, #ef4444, #dc2626); }}
</style>
</head>
<body>
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
</div>
</body>
</html>
"""

    path_html = "/tmp/stats.html"
    path_raw_png = "/tmp/stats_raw.png"
    path_final_png = "/tmp/stats_final.png"
    
    with open(path_html, "w", encoding="utf-8") as f: 
        f.write(html_content)
    
    print("📸 Avvio rendering con Playwright (Risoluzione Social 1620x1980)...")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-web-security", "--allow-running-insecure-content"])
        page = browser.new_page(viewport={"width": 1620, "height": 1980}, device_scale_factor=1.0)
        page.goto(f"file://{path_html}")
        page.wait_for_timeout(3000)
        page.screenshot(path=path_raw_png, omit_background=False)
        browser.close()

    def applica_texture_finale(input_path, texture_path, output_path):
        try:
            base = Image.open(input_path).convert("RGBA")
            texture = Image.open(texture_path).convert("RGBA")
            texture = texture.resize(base.size, Image.Resampling.LANCZOS)
            out = Image.alpha_composite(base, texture)
            out.convert("RGB").save(output_path, "PNG")
            print("🎨 Texture ad alta risoluzione fusa con successo!")
        except Exception as e:
            print(f"Errore applicazione texture: {e}")

    if os.path.exists("texture.PNG"):
        applica_texture_finale(path_raw_png, "texture.PNG", path_final_png)
        return path_final_png
    else:
        return path_raw_png

# ==============================================================================
# LOGICA DI GESTIONE E CICLO DEL MATCH LIVE
# ==============================================================================
def avvia_ciclo_partita():
    print("✅ Procedo al recupero del match...")

    if not API_KEY:
        print("Errore: API_KEY mancante.")
        return
        
    headers = {"x-apisports-key": API_KEY}
    url = "https://v3.football.api-sports.io/fixtures"
    match_id = None

    while not match_id:
        today_date = datetime.now().strftime('%Y-%m-%d')
        print(f"🔄 [Controllo Palinsesto] Cerco partita della Juventus ({today_date})...")
        
        try:
            live_res = requests.get(f"{url}?live=all", headers=headers, timeout=10).json()
            if live_res.get('response'):
                for f in live_res['response']:
                    if f['teams']['home']['id'] == JUVE_ID or f['teams']['away']['id'] == JUVE_ID:
                        match_id = f['fixture']['id']
                        print(f"🔥 Match trovato già LIVE! Aggancio ID: {match_id}")
                        break
            
            if not match_id:
                date_res = requests.get(f"{url}?team={JUVE_ID}&date={today_date}", headers=headers, timeout=10).json()
                if date_res.get('response') and len(date_res['response']) > 0:
                    match_id = date_res['response'][0]['fixture']['id']
                    print(f"📅 Match trovato nel palinsesto di oggi! ID: {match_id}")

            if not match_id:
                next_res = requests.get(f"{url}?team={JUVE_ID}&next=1", headers=headers, timeout=10).json()
                if next_res.get('response') and len(next_res['response']) > 0:
                    match_data = next_res['response'][0]
                    match_id = match_data['fixture']['id']
                    print(f"📌 Agganciato the prossimo match in calendario. ID: {match_id} ({match_data['fixture']['date']})")

        except Exception as e:
            print(f"⚠️ Errore temporaneo nel recupero dei dati dall'API: {e}")

        if not match_id:
            print("❌ Nessun match trovato nel palinsesto. Rinvio richiesta tra 30 secondi...")
            time.sleep(30)

    print(f"⏳ Bot agganciato con successo all'ID {match_id}. Entro nel ciclo di monitoraggio eventi...")
    params = {"id": match_id}

    while True:
        try:
            if os.path.exists("match_state.json"):
                with open("match_state.json", "r") as f: state = json.load(f)
            else:
                state = {
                    "live_match_id": match_id, "sent_periods": [], "goals_detected": 0,
                    "sent_subs": [], "sent_cards": [], "sent_failed_penalties": [], "penalties_count": 0,
                    "sent_stats": []
                }

            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            res = response.json()
            
            if not res.get('response') or len(res['response']) == 0:
                time.sleep(30)
                continue

            match = res['response'][0]
            fixture = match.get('fixture', {})
            status = fixture.get('status', {}).get('short', 'NS')
            elapsed_minutes = fixture.get('status', {}).get('elapsed', 0)
            
            goals_home = match.get('goals', {}).get('home')
            goals_away = match.get('goals', {}).get('away')
            g_home_int = goals_home if goals_home is not None else 0
            g_away_int = goals_away if goals_away is not None else 0

            if status in ["NS", "TBD"] and g_home_int == 0 and g_away_int == 0 and elapsed_minutes == 0:
                print(f"💤 Match ID {match_id} non ancora iniziato (Stato: {status}). Controllo tra 30 secondi...")
                time.sleep(30)
                continue
                
            league_id = match.get('league', {}).get('id', 0)
            league_name = match.get('league', {}).get('name', 'Serie A')
            current_sleep_time = 60 if status == "PEN" else (140 if status in ["ET", "AET"] else (120 if status == "HT" else (70 if league_id == 135 else 90)))
            
            e_comp = get_league_emoji(league_id)
            teams = match.get('teams', {})
            home_id, away_id = teams.get('home', {}).get('id', 0), teams.get('away', {}).get('id', 0)
            
            home_name = "Juventus" if home_id == JUVE_ID else clean_name(teams.get('home', {}).get('name', 'Home'))
            away_name = "Juventus" if away_id == JUVE_ID else clean_name(teams.get('away', {}).get('name', 'Away'))
            
            penalties = match.get('score', {}).get('penalty', {})
            p_home, p_away = penalties.get('home'), penalties.get('away')
            score_string = f"{g_home_int} ({p_home}) - ({p_away}) {g_away_int}" if p_home is not None else f"{g_home_int}-{g_away_int}"
            
            h_short = "Juve" if home_id == JUVE_ID else home_name.replace(" ", "")
            a_short = "Juve" if away_id == JUVE_ID else away_name.replace(" ", "")
            hashtag = f"#{h_short}{a_short}"
            
            print(f"[LIVE] {home_name} {score_string} {away_name} | Minuto: {elapsed_minutes}")

            if g_home_int > g_away_int:
                punteggio_periodo = f"<b>{home_name} {g_home_int}</b>-{g_away_int} {away_name}"
            elif g_away_int > g_home_int:
                punteggio_periodo = f"{home_name} {g_home_int}-<b>{g_away_int} {away_name}</b>"
            else:
                punteggio_periodo = f"{home_name} {g_home_int}-{g_away_int} {away_name}"

            # 1. INIZIO PARTITA
            if (status == "1H" or elapsed_minutes > 0) and "1H" not in state["sent_periods"]:
                send_telegram(f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{home_name} - {away_name}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("1H")
                
            # 2. FINE PRIMO TEMPO
            elif status == "HT" and "HT" not in state["sent_periods"]:
                send_telegram(f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{punteggio_periodo}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("HT")
                
                print("⏳ Attesa di 2 minuti per il consolidamento dati di FINE PRIMO TEMPO (HT)...")
                time.sleep(120)
                png_path = recupera_e_genera_stats_html(match_id, headers, home_id, away_id, home_name, away_name, g_home_int, g_away_int, "HT", league_name)
                send_telegram_stats_photo(png_path, "HT", f"{e_comp} {hashtag}")
                state["sent_stats"].append("HT")
                
            # 3. INIZIO SECONDO TEMPO
            elif status == "2H" and "2H" not in state["sent_periods"]:
                send_telegram(f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n{punteggio_periodo}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("2H")
                
            # 4. FINE SECONDO TEMPO (Solo se si va ai supplementari, lo status diventa ET)
            elif status == "ET" and "2H_END" not in state["sent_periods"]:
                send_telegram(f"<b>FINE REGOLAMENTARI {E_FLAG}</b>\n\nSi va ai tempi supplementari!\n\n{punteggio_periodo}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("2H_END")
                
                print("⏳ Attesa di 2 minuti per il consolidamento dati di FINE SECONDO TEMPO (2H_END)...")
                time.sleep(120)
                png_path = recupera_e_genera_stats_html(match_id, headers, home_id, away_id, home_name, away_name, g_home_int, g_away_int, "2H_END", league_name)
                send_telegram_stats_photo(png_path, "2H_END", f"{e_comp} {hashtag}")
                state["sent_stats"].append("2H_END")

            # 5. CODICE DETTAGLIATO PER I TEMPI SUPPLEMENTARI (STATUS ET)
            elif status == "ET":
                # Inizio 1° Tempo Supplementare (minuto 91)
                if elapsed_minutes >= 91 and elapsed_minutes <= 105 and "1ET_START" not in state["sent_periods"]:
                    send_telegram(f"<b>INIZIO 1° TEMPO SUPPLEMENTARE {E_BOLT}</b>\n\n{punteggio_periodo}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("1ET_START")
                
                # Fine 1° Tempo Supplementare (minuto 105)
                elif elapsed_minutes == 105 and "1ET_END" not in state["sent_periods"]:
                    send_telegram(f"<b>FINE 1° TEMPO SUPPLEMENTARE {E_FLAG}</b>\n\n{punteggio_periodo}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("1ET_END")
                
                # Inizio 2° Tempo Supplementare (minuto 106)
                elif elapsed_minutes >= 106 and "2ET_START" not in state["sent_periods"]:
                    send_telegram(f"<b>INIZIO 2° TEMPO SUPPLEMENTARE {E_BOLT}</b>\n\n{punteggio_periodo}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("2ET_START")

            # 6. GESTIONE RIGORI LIVE (STATUS PEN)
            if status == "PEN":
                # Flash intermedio pulito di fine supplementari
                if "ET_END_PENS" not in state["sent_periods"]:
                    send_telegram(f"<b>FINE TEMPI SUPPLEMENTARI {E_FLAG}</b>\n\n{punteggio_periodo}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("ET_END_PENS")
                
                # Tracciamento rigori colpo su colpo
                events = match.get('events', [])
                home_pen_icons, away_pen_icons = [], []
                for e in events:
                    detail, ev_type = e.get('detail', '').lower(), e.get('type', '').lower()
                    if "shootout" in detail or (ev_type == "goal" and elapsed_minutes >= 120 and "penalty" in detail):
                        icon = E_PEN_KO if ("missed" in detail or "saved" in detail or ev_type == "card") else E_PEN_OK
                        if e.get('team', {}).get('id') == home_id: home_pen_icons.append(icon)
                        else: away_pen_icons.append(icon)
                total_kicks = len(home_pen_icons) + len(away_pen_icons)
                if total_kicks > state["penalties_count"]:
                    send_telegram(f"{home_name}: " + "".join(home_pen_icons) + f"\n{away_name}: " + "".join(away_pen_icons) + f"\n\n{e_comp} {hashtag}")
                    state["penalties_count"] = total_kicks

            # 7. CHIUSURA DEFINITIVA MATCH (FISCHIO FINALE REALE)
            status_long = fixture.get('status', {}).get('long', '').lower()
            # Si chiude se lo stato è FT/AET, oppure se è PEN ed è "match finished" (rigori conclusi)
            if status in ["FT", "AET"] or (status == "PEN" and status_long == "match finished"):
                print("🏁 FISCHIO FINALE REALE RILEVATO! Connessione a Canva per l'export immediato...")
                scorers_line = build_split_scorers_text(match.get('events', []), home_id, away_id)
                
                if p_home is not None:
                    if int(p_home) > int(p_away):
                        punteggio_finale = f"<b>{home_name} {g_home_int} ({p_home})</b>-({p_away}) {g_away_int} {away_name}"
                    else:
                        punteggio_finale = f"{home_name} {g_home_int} ({p_home})-<b>({p_away}) {g_away_int} {away_name}</b>"
                else:
                    if g_home_int > g_away_int:
                        punteggio_finale = f"<b>{home_name} {g_home_int}</b>-{g_away_int} {away_name}"
                    elif g_away_int > g_home_int:
                        punteggio_finale = f"{home_name} {g_home_int}-<b>{g_away_int} {away_name}</b>"
                    else:
                        punteggio_finale = f"{home_name} {g_home_int}-{g_away_int} {away_name}"

                msg_finale = f"<b>FINE PARTITA {E_FLAG}</b>\n\n{punteggio_finale}\n{scorers_line}\n{e_comp} {hashtag}"
                
                canva_token_fresco = get_valid_token()
                if canva_token_fresco:
                    foto_canva = get_canva_image(canva_token_fresco)
                    send_telegram_with_photo(msg_finale, photo_bytes=foto_canva)
                else:
                    print("❌ Impossibile generare un token Canva valido al fischio finale. Invio solo testo.")
                    send_telegram(msg_finale)
                
                print("⏳ Attesa di 2 minuti per il consolidamento dati di FINE PARTITA (FT)...")
                time.sleep(120)
                
                png_path = recupera_e_genera_stats_html(match_id, headers, home_id, away_id, home_name, away_name, g_home_int, g_away_int, "FT", league_name)
                send_telegram_stats_photo(png_path, "FT", f"{e_comp} {hashtag}")
                state["sent_stats"].append("FT")
                
                if os.path.exists("match_state.json"): 
                    os.remove("match_state.json")
                
                print("🏁 Processo terminato con successo. Spegnimento del bot.")
                sys.exit(0)

            total_goals_now = g_home_int + g_away_int
            if total_goals_now > state["goals_detected"]:
                events, live_scorer_line = match.get('events', []), ""
                
                if events:
                    all_goals = [e for e in events if e.get('type', '').lower() == 'goal' and "shootout" not in e.get('detail', '').lower()]
                    if all_goals:
                        all_goals.sort(key=lambda x: (x.get('time', {}).get('elapsed', 0), x.get('time', {}).get('extra', 0) or 0))
                        last_goal = all_goals[-1]
                        el, ex = last_goal.get('time', {}).get('elapsed', '?'), last_goal.get('time', {}).get('extra')
                        minute_str = f"{el}+{ex}" if ex else f"{el}"
                        p_name = last_goal.get('player', {}).get('name', 'Giocatore')
                        det = last_goal.get('detail', '').lower()
                        
                        if "penalty" in det: p_name += " (Rig.)"
                        elif "own goal" in det: p_name += " (Autogol)"
                        live_scorer_line = f"{E_BALL} <i>{minute_str}’ {p_name}</i>\n"
                
                if g_home_int > g_away_int:
                    punteggio_match = f"<b>{home_name} {g_home_int}</b>-{g_away_int} {away_name}"
                elif g_away_int > g_home_int:
                    punteggio_match = f"{home_name} {g_home_int}-<b>{g_away_int} {away_name}"
                else:
                    scoring_team_id = last_goal.get('team', {}).get('id') if events and all_goals else None
                    if scoring_team_id == home_id:
                        punteggio_match = f"<b>{home_name} {g_home_int}</b>-{g_away_int} {away_name}"
                    elif scoring_team_id == away_id:
                        punteggio_match = f"{home_name} {g_home_int}-<b>{g_away_int} {away_name}"
                    else:
                        punteggio_match = f"{home_name} {g_home_int}-{g_away_int} {away_name}"
                        
                send_telegram(f"<b>GOAL {E_MIC}</b>\n\n{punteggio_match}\n{live_scorer_line}\n{e_comp} {hashtag}")
                state["goals_detected"] = total_goals_now
            elif total_goals_now < state["goals_detected"]:
                send_telegram(f"<b>GOAL ANNULLATO 📺</b>\n\n{home_name} {g_home_int}-{g_away_int} {away_name}\n\n{e_comp} {hashtag}")
                state["goals_detected"] = total_goals_now

            events = match.get('events', [])
            if events:
                subs_by_minute = {}
                for e in events:
                    ev_type, detail, minute, team_id = e.get('type', '').lower(), e.get('detail', '').lower(), e.get('time', {}).get('elapsed', 0), e.get('team', {}).get('id')
                    if ev_type == 'subst':
                        p_out, p_in = e.get('player', {}).get('name', 'Uscente'), e.get('assist', {}).get('name', 'Entrante')
                        sub_id = f"sub_{minute}_{p_out}_{p_in}".replace(" ", "_")
                        if sub_id not in state["sent_subs"]:
                            sub_key = f"{minute}_{team_id}"
                            if sub_key not in subs_by_minute: subs_by_minute[sub_key] = {"minute": minute, "team_id": team_id, "in": [], "out": [], "ids": []}
                            subs_by_minute[sub_key]["in"].append(p_in)
                            subs_by_minute[sub_key]["out"].append(p_out)
                            subs_by_minute[sub_key]["ids"].append(sub_id)
                    elif ev_type == 'card' and "red" in detail:
                        p_name = e.get('player', {}).get('name', 'Giocatore')
                        card_id = f"card_{minute}_{p_name}".replace(" ", "_")
                        if card_id not in state["sent_cards"]:
                            send_telegram(f"<b>CARTELLINO ROSSO {E_RED}</b>\n\n🔚 <i>{minute}’ {p_name}</i>\n\n{e_comp} {hashtag}")
                            state["sent_cards"].append(card_id)

                for sub_key, sub_data in subs_by_minute.items():
                    team_title = "JUVENTUS" if sub_data["team_id"] == JUVE_ID else (home_name.upper() if sub_data["team_id"] == home_id else away_name.upper())
                    send_telegram(f"<b>CAMBIO {team_title} {E_SUB}</b>\n\n{E_UP} {', '.join(sub_data['in'])}\n{E_DOWN} {', '.join(sub_data['out'])}\n\n{e_comp} {hashtag}")
                    state["sent_subs"].extend(sub_data["ids"])

            with open("match_state.json", "w") as f: json.dump(state, f)
        except Exception as e:
            print(f"Errore ciclo live: {e}")
            current_sleep_time = 30
        time.sleep(current_sleep_time)

# ==============================================================================
# FUNZIONE PRINCIPALE (GESTIONE BIVIO AUTOMAZIONE E KEEP-ALIVE)
# ==============================================================================
def main():
    print("🚀 Avvio Live Score Bot: elaborazione eventi in corso...")
    
    if str(os.getenv('ONLY_REFRESH_TOKEN', '')).strip().lower() == "true":
        print("🔒 Modalità Keep-Alive: Rinnovo il token...")
        get_valid_token()
        print("🔒 Token aggiornato correttamente. Termino l'esecuzione.")
        return

    avvia_ciclo_partita()

if __name__ == "__main__":
    main()
