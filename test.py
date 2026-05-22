import os
import requests
from PIL import Image
from playwright.sync_api import sync_playwright

# ==============================================================================
# CONFIGURAZIONE
# ==============================================================================
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')

HOME_ID = 496  
AWAY_ID = 505
HOME_NAME = "Juventus"
AWAY_NAME = "Inter"
HOME_GOALS = 2
AWAY_GOALS = 0

MOMENTO_CODICE = "HT" 

MOMENTI_CONFIG = {
    "HT": {"titolo": "📊 <b>STATS PRIMO TEMPO</b>", "badge": "FINE PRIMO TEMPO"},
    "2H": {"titolo": "📊 <b>STATS SECONDO TEMPO</b>", "badge": "FINE SECONDO TEMPO"},
    "FT": {"titolo": "📊 <b>STATS FINE PARTITA</b>", "badge": "FINE PARTITA"}
}

JUVE_LOGO_URL = "https://upload.wikimedia.org/wikipedia/commons/9/99/Juventus_FC_2017_squared_icon_%28white%29.png"
API_LOGO_URL = "https://media.api-sports.io/football/teams/{}.png"

def send_telegram_photo(png_path, momento):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    caption = f"{MOMENTI_CONFIG[momento]['titolo']}\n\n🇮🇹 #JuveInter"
    with open(png_path, "rb") as f:
        requests.post(url, data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "HTML"}, 
                      files={"photo": ("stats.png", f, "image/png")})
    print("✅ Inviato su Telegram in formato HTML 1620x1980 con tutte le statistiche e texture!")

def genera_html(momento):
    h_logo = JUVE_LOGO_URL if "juventus" in HOME_NAME.lower() else API_LOGO_URL.format(HOME_ID)
    a_logo = JUVE_LOGO_URL if "juventus" in AWAY_NAME.lower() else API_LOGO_URL.format(AWAY_ID)
    badge_label = MOMENTI_CONFIG[momento]['badge']

    # Lista completa di tutte le 11 statistiche richieste
    stats_data = [
        ("Possesso palla", "58%", "42%", 58),
        ("Tiri totali", "16", "9", 64),
        ("Tiri in porta", "6", "2", 75),
        ("xG", "2.1", "0.7", 75),
        ("Passaggi riusciti", "480", "350", 58),
        ("Corner", "7", "3", 70),
        ("Duelli vinti", "55%", "45%", 55),
        ("Recuperi", "38", "31", 55),
        ("Falli", "11", "14", 44),
        ("Ammoniti", "1", "3", 25),
        ("Espulsi", "0", "0", 50)
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
    </div>''' for label, h, a, hp in stats_data])

    return f"""<!DOCTYPE html>
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
    <div class="league-row">SERIE A &nbsp;·&nbsp; MATCHDAY TEST</div>
    <div class="badge">{badge_label}</div>
    <div class="teams-row">
      <div class="team"><img src="{h_logo}" class="logo" crossorigin="anonymous"><div class="team-name">{HOME_NAME}</div></div>
      <div class="score-wrap"><div class="score">{HOME_GOALS}–{AWAY_GOALS}</div><div class="match-status">LIVE STATS</div></div>
      <div class="team"><img src="{a_logo}" class="logo" crossorigin="anonymous"><div class="team-name">{AWAY_NAME}</div></div>
    </div>
  </div>
  <div class="stats-body">
    <div class="stats-title">STATISTICHE ANALITICHE</div>
    {rows_html}
  </div>
</div>
</body>
</html>"""

def main():
    path_html = "/tmp/test.html"
    path_raw_png = "/tmp/test_raw.png"
    path_final_png = "/tmp/test_final.png"

    with open(path_html, "w", encoding="utf-8") as f: 
        f.write(genera_html(MOMENTO_CODICE))
    
    print("📸 Rendering con Playwright (Risoluzione 1620x1980)...")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-web-security", "--allow-running-insecure-content"])
        page = browser.new_page(viewport={"width": 1620, "height": 1980}, device_scale_factor=1.0)
        page.goto(f"file://{path_html}")
        page.wait_for_timeout(3000)
        
        # Screenshot full page per non perdere i gradienti esterni del layout 1620x1980
        page.screenshot(path=path_raw_png, omit_background=False)
        browser.close()
        
    # ==============================================================================
    # SOVRAPPOSIZIONE TEXTURE CON PILLOW
    # ==============================================================================
    if os.path.exists("texture.PNG"):
        try:
            print("🎨 Applicazione della grana di texture.PNG (1620x1980) in corso...")
            base_img = Image.open(path_raw_png).convert("RGBA")
            texture_img = Image.open("texture.PNG").convert("RGBA")
            
            # Adatta la texture precisamente a 1620x1980
            texture_img = texture_img.resize(base_img.size, Image.Resampling.LANCZOS)
            
            # Unione dei due livelli
            final_img = Image.alpha_composite(base_img, texture_img)
            final_img.save(path_final_png, "PNG")
            
            send_telegram_photo(path_final_png, MOMENTO_CODICE)
        except Exception as e:
            print(f"⚠️ Errore durante la sovrapposizione: {e}. Invio senza grana.")
            send_telegram_photo(path_raw_png, MOMENTO_CODICE)
    else:
        print("⚠️ File 'texture.PNG' non trovato. Invio l'immagine base ad alta definizione.")
        send_telegram_photo(path_raw_png, MOMENTO_CODICE)

if __name__ == "__main__":
    main()