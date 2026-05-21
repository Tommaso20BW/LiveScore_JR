import os
import requests
import sys
import time

# ==============================================================================
# CONFIGURAZIONE TEST
# ==============================================================================
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')

# ID configurati
HOME_ID = 496  
AWAY_ID = 505
HOME_NAME = "Juventus"
AWAY_NAME = "Inter"
HOME_GOALS = 2
AWAY_GOALS = 0

def send_telegram_photo(png_path):
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ Errore: TELEGRAM_TOKEN o TELEGRAM_TO non configurati.")
        return
        
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(png_path, "rb") as f:
        requests.post(
            url, 
            data={"chat_id": CHAT_ID, "caption": "📊 Test Anteprima Alta Qualità #JuveInter"}, 
            files={"photo": ("stats_test.png", f, "image/png")}
        )
    print("✅ Card inviata su Telegram!")

def genera_html_test():
    # HTML senza padding nel body per un ritaglio perfetto
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;600;700&family=Barlow+Condensed:wght@700;900&display=swap');
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width: 540px; background: #0b0f1e; font-family: 'Barlow', sans-serif; padding:0; margin:0; }}
  .card {{ width: 540px; background: #0b0f1e; border-radius: 20px; overflow: hidden; border: 1px solid rgba(255,255,255,0.07); }}
  .header {{ background: #0d1528; padding: 20px 28px 18px; border-bottom: 1px solid rgba(255,255,255,0.06); }}
  .league-row {{ text-align: center; font-size: 11px; letter-spacing: 1.5px; color: #4a5470; text-transform: uppercase; margin-bottom: 12px; }}
  .badge {{ display: block; width: fit-content; margin: 0 auto 14px; background: #f0b429; color: #0b0f1e; font-size: 10px; font-weight: 700; letter-spacing: 1.5px; padding: 4px 14px; border-radius: 20px; text-transform: uppercase; }}
  .teams-row {{ display: flex; align-items: center; justify-content: space-between; }}
  .team {{ text-align: center; flex: 1; }}
  .logo {{ width: 56px; height: 56px; object-fit: contain; display: block; margin: 0 auto 8px; }}
  .team-name {{ font-size: 13px; font-weight: 600; color: #c8d0e8; margin: 0 auto; }}
  .score-box {{ text-align: center; padding: 0 12px; }}
  .score {{ font-family: 'Barlow Condensed', sans-serif; font-size: 58px; font-weight: 900; color: #fff; line-height: 1; }}
  .stats-body {{ padding: 8px 22px 20px; }}
  .stats-title {{ font-size: 10px; letter-spacing: 2px; color: #2e3850; text-transform: uppercase; text-align: center; padding: 12px 0 8px; border-bottom: 1px solid rgba(255,255,255,0.04); margin-bottom: 4px; }}
  .stat-row {{ display: flex; align-items: center; padding: 8px 6px; }}
  .val {{ width: 44px; font-family: 'Barlow Condensed', sans-serif; font-size: 15px; font-weight: 700; }}
  .home-val {{ color: #4f9cf9; text-align: left; }}
  .away-val {{ color: #f05252; text-align: right; }}
  .stat-mid {{ flex: 1; padding: 0 10px; }}
  .stat-label {{ font-size: 11px; color: #4a5470; text-align: center; margin-bottom: 5px; }}
  .bar-track {{ display: flex; height: 6px; border-radius: 3px; overflow: hidden; background: rgba(255,255,255,0.06); }}
  .bar-h {{ background: #4f9cf9; }}
  .bar-a {{ background: #f05252; margin-left: auto; }}
  .footer {{ padding: 10px 20px 14px; text-align: center; font-size: 10px; color: #1e2640; border-top: 1px solid rgba(255,255,255,0.04); }}
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <div class="league-row">Serie A · Matchday Test</div>
    <div class="badge">Fine partita</div>
    <div class="teams-row">
      <div class="team"><img src="https://media.api-sports.io/football/teams/{HOME_ID}.png" class="logo"><div class="team-name">{HOME_NAME}</div></div>
      <div class="score-box"><div class="score"><span>{HOME_GOALS}</span> – <span>{AWAY_GOALS}</span></div></div>
      <div class="team"><img src="https://media.api-sports.io/football/teams/{AWAY_ID}.png" class="logo"><div class="team-name">{AWAY_NAME}</div></div>
    </div>
  </div>
  <div class="stats-body">
    <div class="stats-title">Statistiche</div>
    <div class="stat-row"><div class="val home-val">58%</div><div class="stat-mid"><div class="stat-label">Possesso palla</div><div class="bar-track"><div class="bar-h" style="width: 58%"></div><div class="bar-a" style="width: 42%"></div></div></div><div class="val away-val">42%</div></div>
  </div>
  <div class="footer">⚽ @Juventus_Reborn</div>
</div>
</body>
</html>"""

def main():
    html_path = "/tmp/test.html"
    png_path = "/tmp/test.png"
    
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(genera_html_test())
    
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # AUMENTO QUALITÀ: device_scale_factor=2.0
        page = browser.new_page(viewport={"width": 540, "height": 900}, device_scale_factor=2.0)
        page.goto(f"file://{html_path}")
        page.wait_for_timeout(2000)
        
        # RITAGLIO PRECISO: cattura solo la card
        card = page.query_selector(".card")
        card.screenshot(path=png_path, omit_background=True)
        browser.close()
        
    send_telegram_photo(png_path)

if __name__ == "__main__":
    main()
