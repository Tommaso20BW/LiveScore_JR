import os
import requests
from playwright.sync_api import sync_playwright

# ==============================================================================
# CONFIGURAZIONE TEST
# ==============================================================================
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')

HOME_ID = 496  
AWAY_ID = 505
HOME_NAME = "Juventus"
AWAY_NAME = "Inter"
HOME_GOALS = 2
AWAY_GOALS = 0

# Parametri dinamici
COMPETIZIONE = "SERIE A"
ROUND = "MATCHDAY TEST"
MOMENTO_CODICE = "HT"  # Opzioni: "HT" (Primo Tempo), "2H" (Secondo Tempo), "FT" (Fine Partita)

# Configurazione messaggi basata sul momento
MOMENTI_CONFIG = {
    "HT": {"titolo": "📊 **STATS PRIMO TEMPO**", "badge": "FINE PRIMO TEMPO"},
    "2H": {"titolo": "📊 **STATS SECONDO TEMPO**", "badge": "FINE SECONDO TEMPO"},
    "FT": {"titolo": "📊 **STATS FINE PARTITA**", "badge": "FINE PARTITA"}
}

JUVE_LOGO_URL = "https://upload.wikimedia.org/wikipedia/commons/9/99/Juventus_FC_2017_squared_icon_%28white%29.png"
API_LOGO_URL = "https://media.api-sports.io/football/teams/{}.png"

def send_telegram_photo(png_path, momento):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    caption = f"{MOMENTI_CONFIG[momento]['titolo']}\n\n🇮🇹 #JuveInter"
    with open(png_path, "rb") as f:
        requests.post(url, data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "Markdown"}, 
                      files={"photo": ("stats.png", f, "image/png")})
    print("✅ Inviato su Telegram!")

def genera_html(momento):
    h_logo = JUVE_LOGO_URL if "juventus" in HOME_NAME.lower() else API_LOGO_URL.format(HOME_ID)
    a_logo = JUVE_LOGO_URL if "juventus" in AWAY_NAME.lower() else API_LOGO_URL.format(AWAY_ID)
    badge_label = MOMENTI_CONFIG[momento]['badge']

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
    
    rows_html = "".join([f'''<div class="stat-row">
          <div class="val home-val">{h}</div>
          <div class="stat-mid"><div class="stat-label">{label}</div><div class="bar-track"><div style="background:#4f9cf9;width:{hp}%;height:8px;border-radius:4px 0 0 4px"></div><div style="background:#f05252;width:{100-hp}%;height:8px;border-radius:0 4px 4px 0"></div></div></div>
          <div class="val away-val">{a}</div>
        </div>''' for label, h, a, hp in stats_data])

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;600;700;800&family=Barlow+Condensed:wght@700;900&display=swap');
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width: 540px; background: #0b0f1e; font-family: 'Barlow', sans-serif; }}
  .card {{ width: 540px; background: #0b0f1e; border-radius: 20px; overflow: hidden; border: 1px solid rgba(255,255,255,0.1); }}
  .header {{ background: #0d1528; padding: 25px 28px; border-bottom: 1px solid rgba(255,255,255,0.06); }}
  .league-row {{ text-align: center; font-size: 11px; letter-spacing: 1.5px; color: #4a5470; text-transform: uppercase; margin-bottom: 12px; }}
  .badge {{ display: block; width: fit-content; margin: 0 auto 14px; background: #f0b429; color: #0b0f1e; font-size: 10px; font-weight: 700; letter-spacing: 1.5px; padding: 4px 14px; border-radius: 20px; text-transform: uppercase; }}
  .teams-row {{ display: flex; align-items: center; justify-content: space-between; }}
  .logo {{ width: 65px; height: 65px; object-fit: contain; display: block; margin: 0 auto 10px; }}
  .team-name {{ color: #ffffff; font-weight: 700; font-size: 15px; text-align: center; }}
  .score {{ color: #ffffff; font-family: 'Barlow Condensed'; font-size: 60px; font-weight: 900; margin: 0 15px; }}
  .stats-body {{ padding: 20px 28px; }}
  .stats-title {{ color: #6070a0; font-size: 11px; font-weight: 800; text-transform: uppercase; margin-bottom: 15px; letter-spacing: 2px; text-align: center; }}
  .stat-row {{ display: flex; align-items: center; padding: 8px 0; }}
  .val {{ width: 50px; font-family: 'Barlow Condensed'; font-size: 19px; font-weight: 800; color: #ffffff; }}
  .home-val {{ text-align: left; }}
  .away-val {{ text-align: right; }}
  .stat-mid {{ flex: 1; padding: 0 15px; text-align: center; color: #a0aacc; font-size: 12px; font-weight: 600; }}
  .stat-label {{ margin-bottom: 5px; }}
  .bar-track {{ display: flex; height: 8px; border-radius: 4px; background: rgba(255,255,255,0.08); }}
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <div class="league-row">{COMPETIZIONE} &nbsp;·&nbsp; {ROUND}</div>
    <div class="badge">{badge_label}</div>
    <div class="teams-row">
      <div class="team"><img src="{h_logo}" class="logo" crossorigin="anonymous"><div class="team-name">{HOME_NAME}</div></div>
      <div class="score">{HOME_GOALS} – {AWAY_GOALS}</div>
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
    path = "/tmp/test.html"
    with open(path, "w", encoding="utf-8") as f: f.write(genera_html(MOMENTO_CODICE))
    
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-web-security", "--allow-running-insecure-content"])
        page = browser.new_page(viewport={"width": 540, "height": 1050}, device_scale_factor=3.0)
        page.goto(f"file://{path}")
        page.wait_for_timeout(3000)
        page.query_selector(".card").screenshot(path="/tmp/test.png", omit_background=True)
        browser.close()
        
    send_telegram_photo("/tmp/test.png", MOMENTO_CODICE)

if __name__ == "__main__":
    main()
