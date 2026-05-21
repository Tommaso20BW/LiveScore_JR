import os
import requests
import sys
import time

# ==============================================================================
# CONFIGURAZIONE (VARIABILI D'AMBIENTE)
# ==============================================================================
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')

# Test IDs (496 Rennes/Juve, 505 Inter)
HOME_ID = 496  
AWAY_ID = 505
HOME_NAME = "Juventus"
AWAY_NAME = "Inter"
HOME_GOALS = 2
AWAY_GOALS = 0

def send_telegram_photo(png_path):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(png_path, "rb") as f:
        requests.post(url, data={"chat_id": CHAT_ID, "caption": "📊 Stats Alta Qualità 3.0x #JuveInter"}, 
                      files={"photo": ("stats.png", f, "image/png")})
    print("✅ Inviato su Telegram!")

def genera_html():
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;600;700;800&family=Barlow+Condensed:wght@700;900&display=swap');
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width: 540px; background: #0b0f1e; font-family: 'Barlow', sans-serif; margin:0; padding:0; }}
  .card {{ width: 540px; background: #0b0f1e; border-radius: 20px; overflow: hidden; border: 1px solid rgba(255,255,255,0.1); }}
  .header {{ background: #0d1528; padding: 25px 28px; border-bottom: 1px solid rgba(255,255,255,0.06); }}
  .teams-row {{ display: flex; align-items: center; justify-content: space-between; }}
  .logo {{ width: 65px; height: 65px; object-fit: contain; display: block; margin: 0 auto 10px; }}
  .team-name {{ color: #ffffff; font-weight: 700; font-size: 15px; text-align: center; }}
  .score {{ color: #ffffff; font-family: 'Barlow Condensed'; font-size: 60px; font-weight: 900; }}
  .stats-body {{ padding: 20px 28px; }}
  .stats-title {{ color: #6070a0; font-size: 11px; font-weight: 800; text-transform: uppercase; margin-bottom: 15px; letter-spacing: 2px; text-align: center; }}
  .stat-row {{ display: flex; align-items: center; margin-bottom: 18px; }}
  .val {{ width: 50px; font-family: 'Barlow Condensed'; font-size: 19px; font-weight: 800; color: #ffffff; }}
  .home-val {{ text-align: left; }}
  .away-val {{ text-align: right; }}
  .stat-mid {{ flex: 1; padding: 0 15px; text-align: center; color: #a0aacc; font-size: 12px; font-weight: 600; }}
  .bar-track {{ display: flex; height: 8px; border-radius: 4px; background: rgba(255,255,255,0.08); margin-top: 6px; }}
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <div class="teams-row">
      <div class="team"><img src="https://media.api-sports.io/football/teams/{HOME_ID}.png" class="logo"><div class="team-name">{HOME_NAME}</div></div>
      <div class="score">{HOME_GOALS} – {AWAY_GOALS}</div>
      <div class="team"><img src="https://media.api-sports.io/football/teams/{AWAY_ID}.png" class="logo"><div class="team-name">{AWAY_NAME}</div></div>
    </div>
  </div>
  <div class="stats-body">
    <div class="stats-title">STATISTICHE MATCH</div>
    {''.join([f'''<div class="stat-row">
      <div class="val home-val">{h}</div>
      <div class="stat-mid">{label}<div class="bar-track"><div style="background:#4f9cf9;width:{hp}%;height:8px;border-radius:4px 0 0 4px"></div><div style="background:#f05252;width:{100-hp}%;height:8px;border-radius:0 4px 4px 0"></div></div></div>
      <div class="val away-val">{a}</div>
    </div>''' for label, h, a, hp in [
        ("Possesso Palla", "58%", "42%", 58),
        ("Tiri Totali", "16", "9", 64),
        ("Tiri in Porta", "6", "2", 75),
        ("Passaggi Riusciti", "480", "350", 58),
        ("Corner", "7", "3", 70)
    ]])}
  </div>
</div>
</body>
</html>"""

def main():
    path = "/tmp/test.html"
    with open(path, "w", encoding="utf-8") as f: f.write(genera_html())
    
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # Fattore 3.0x per nitidezza estrema
        page = browser.new_page(viewport={"width": 540, "height": 900}, device_scale_factor=3.0)
        page.goto(f"file://{path}")
        page.wait_for_timeout(2500) # Tempo extra per caricamento font e loghi
        page.query_selector(".card").screenshot(path="/tmp/test.png", omit_background=True)
        browser.close()
        
    send_telegram_photo("/tmp/test.png")

if __name__ == "__main__":
    main()
