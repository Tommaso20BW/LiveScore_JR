import os
import requests
import sys
import time

# ==============================================================================
# CONFIGURAZIONE MINIMA PER TEST OFFLINE
# ==============================================================================
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')

# ID configurati come richiesto per il test
HOME_ID = 496  
AWAY_ID = 505

HOME_NAME = "Juventus"
AWAY_NAME = "Inter"
HOME_GOALS = 2
AWAY_GOALS = 0

def send_telegram_photo(png_path):
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ Errore: TELEGRAM_TOKEN o TELEGRAM_TO non configurati nelle variabili d'ambiente.")
        return
        
    print("📤 Invio della card statistiche su Telegram...")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(png_path, "rb") as f:
            res = requests.post(
                url, 
                data={"chat_id": CHAT_ID, "caption": f"📊 Test Anteprima Statistiche\n#JuveInter"}, 
                files={"photo": ("stats_test.png", f, "image/png")}, 
                timeout=20
            )
        if res.status_code == 200:
            print("✅ Card inviata con successo su Telegram!")
        else:
            print(f"❌ Errore Telegram: {res.text}")
    except Exception as e:
        print(f"❌ Invio fallito: {e}")

def genera_html_test():
    # Struttura HTML pulita che punta direttamente agli URL delle immagini
    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;600;700&family=Barlow+Condensed:wght@700;900&display=swap');
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    width: 540px;
    background: #0b0f1e;
    font-family: 'Barlow', sans-serif;
    padding: 0;
  }}
  .card {{
    width: 540px;
    background: #0b0f1e;
    border-radius: 20px;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,0.07);
  }}
  .header {{
    background: #0d1528;
    padding: 20px 28px 18px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
  }}
  .league-row {{
    text-align: center;
    font-size: 11px;
    letter-spacing: 1.5px;
    color: #4a5470;
    text-transform: uppercase;
    margin-bottom: 12px;
  }}
  .badge {{
    display: block;
    width: fit-content;
    margin: 0 auto 14px;
    background: #f0b429;
    color: #0b0f1e;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
    padding: 4px 14px;
    border-radius: 20px;
    text-transform: uppercase;
  }}
  .teams-row {{
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}
  .team {{
    text-align: center;
    flex: 1;
  }}
  .logo {{
    width: 56px;
    height: 56px;
    object-fit: contain;
    display: block;
    margin: 0 auto 8px;
  }}
  .team-name {{
    font-size: 13px;
    font-weight: 600;
    color: #c8d0e8;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 120px;
    margin: 0 auto;
  }}
  .score-box {{
    text-align: center;
    padding: 0 12px;
    flex-shrink: 0;
  }}
  .score {{
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 58px;
    font-weight: 900;
    color: #fff;
    line-height: 1;
    letter-spacing: -1px;
  }}
  .score-sep {{ color: #2a3450; }}
  .stats-body {{
    padding: 8px 22px 20px;
  }}
  .stats-title {{
    font-size: 10px;
    letter-spacing: 2px;
    color: #2e3850;
    text-transform: uppercase;
    text-align: center;
    padding: 12px 0 8px;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    margin-bottom: 4px;
  }}
  .stat-row {{
    display: flex;
    align-items: center;
    padding: 8px 6px;
    border-radius: 8px;
  }}
  .val {{
    width: 44px;
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 15px;
    font-weight: 700;
  }}
  .home-val {{ color: #4f9cf9; text-align: left; }}
  .away-val {{ color: #f05252; text-align: right; }}
  .stat-mid {{
    flex: 1;
    padding: 0 10px;
  }}
  .stat-label {{
    font-size: 11px;
    color: #4a5470;
    text-align: center;
    margin-bottom: 5px;
  }}
  .bar-track {{
    display: flex;
    height: 6px;
    border-radius: 3px;
    overflow: hidden;
    background: rgba(255,255,255,0.06);
  }}
  .bar-h {{
    background: #4f9cf9;
    border-radius: 3px 0 0 3px;
  }}
  .bar-a {{
    background: #f05252;
    border-radius: 0 3px 3px 0;
    margin-left: auto;
  }}
  .footer {{
    padding: 10px 20px 14px;
    text-align: center;
    font-size: 10px;
    color: #1e2640;
    border-top: 1px solid rgba(255,255,255,0.04);
    letter-spacing: 0.5px;
  }}
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <div class="league-row">Serie A &nbsp;·&nbsp; Matchday Test</div>
    <div class="badge">Fine partita</div>
    <div class="teams-row">
      <div class="team">
        <img src="https://media.api-sports.io/football/teams/{HOME_ID}.png" class="logo">
        <div class="team-name">{HOME_NAME}</div>
      </div>
      <div class="score-box">
        <div class="score">
          <span>{HOME_GOALS}</span>
          <span class="score-sep"> – </span>
          <span>{AWAY_GOALS}</span>
        </div>
      </div>
      <div class="team">
        <img src="https://media.api-sports.io/football/teams/{AWAY_ID}.png" class="logo">
        <div class="team-name">{AWAY_NAME}</div>
      </div>
    </div>
  </div>
  <div class="stats-body">
    <div class="stats-title">Statistiche</div>
    
    <div class="stat-row" style="background: rgba(255,255,255,0.03)">
      <div class="val home-val">58%</div>
      <div class="stat-mid">
        <div class="stat-label">Possesso palla</div>
        <div class="bar-track">
          <div class="bar-h" style="width: 58%"></div>
          <div class="bar-a" style="width: 42%"></div>
        </div>
      </div>
      <div class="val away-val">42%</div>
    </div>

    <div class="stat-row" style="background: transparent">
      <div class="val home-val">16</div>
      <div class="stat-mid">
        <div class="stat-label">Tiri totali</div>
        <div class="bar-track">
          <div class="bar-h" style="width: 64%"></div>
          <div class="bar-a" style="width: 36%"></div>
        </div>
      </div>
      <div class="val away-val">9</div>
    </div>

    <div class="stat-row" style="background: rgba(255,255,255,0.03)">
      <div class="val home-val">6</div>
      <div class="stat-mid">
        <div class="stat-label">Tiri in porta</div>
        <div class="bar-track">
          <div class="bar-h" style="width: 75%"></div>
          <div class="bar-a" style="width: 25%"></div>
        </div>
      </div>
      <div class="val away-val">2</div>
    </div>

    <div class="stat-row" style="background: transparent">
      <div class="val home-val">2.1</div>
      <div class="stat-mid">
        <div class="stat-label">xG</div>
        <div class="bar-track">
          <div class="bar-h" style="width: 75%"></div>
          <div class="bar-a" style="width: 25%"></div>
        </div>
      </div>
      <div class="val away-val">0.7</div>
    </div>

    <div class="stat-row" style="background: rgba(255,255,255,0.03)">
      <div class="val home-val">480</div>
      <div class="stat-mid">
        <div class="stat-label">Passaggi riusciti</div>
        <div class="bar-track">
          <div class="bar-h" style="width: 58%"></div>
          <div class="bar-a" style="width: 42%"></div>
        </div>
      </div>
      <div class="val away-val">350</div>
    </div>

    <div class="stat-row" style="background: transparent">
      <div class="val home-val">7</div>
      <div class="stat-mid">
        <div class="stat-label">Corner</div>
        <div class="bar-track">
          <div class="bar-h" style="width: 70%"></div>
          <div class="bar-a" style="width: 30%"></div>
        </div>
      </div>
      <div class="val away-val">3</div>
    </div>

    <div class="stat-row" style="background: rgba(255,255,255,0.03)">
      <div class="val home-val">55</div>
      <div class="stat-mid">
        <div class="stat-label">Duelli vinti</div>
        <div class="bar-track">
          <div class="bar-h" style="width: 53%"></div>
          <div class="bar-a" style="width: 47%"></div>
        </div>
      </div>
      <div class="val away-val">48</div>
    </div>

    <div class="stat-row" style="background: transparent">
      <div class="val home-val">38</div>
      <div class="stat-mid">
        <div class="stat-label">Recuperi</div>
        <div class="bar-track">
          <div class="bar-h" style="width: 55%"></div>
          <div class="bar-a" style="width: 45%"></div>
        </div>
      </div>
      <div class="val away-val">31</div>
    </div>

    <div class="stat-row" style="background: rgba(255,255,255,0.03)">
      <div class="val home-val">11</div>
      <div class="stat-mid">
        <div class="stat-label">Falli</div>
        <div class="bar-track">
          <div class="bar-h" style="width: 44%"></div>
          <div class="bar-a" style="width: 56%"></div>
        </div>
      </div>
      <div class="val away-val">14</div>
    </div>

    <div class="stat-row" style="background: transparent">
      <div class="val home-val">1</div>
      <div class="stat-mid">
        <div class="stat-label">Ammoniti</div>
        <div class="bar-track">
          <div class="bar-h" style="width: 25%"></div>
          <div class="bar-a" style="width: 75%"></div>
        </div>
      </div>
      <div class="val away-val">3</div>
    </div>

    <div class="stat-row" style="background: rgba(255,255,255,0.03)">
      <div class="val home-val">0</div>
      <div class="stat-mid">
        <div class="stat-label">Espulsi</div>
        <div class="bar-track">
          <div class="bar-h" style="width: 0%"></div>
          <div class="bar-a" style="width: 0%"></div>
        </div>
      </div>
      <div class="val away-val">0</div>
    </div>

  </div>
  <div class="footer">⚽ @Juventus_Reborn &nbsp;·&nbsp; dati: API-Football</div>
</div>
</body>
</html>"""
    return html_content

def main():
    print("🚀 Avvio del test offline immediato...")
    
    html_path = "/tmp/stats_test_card.html"
    png_path = "/tmp/stats_test_card.png"
    
    # Scrittura del file HTML temporaneo
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(genera_html_test())
    
    print("🎨 Apertura headless browser con Playwright per il rendering...")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 540, "height": 900})
            page.goto(f"file://{html_path}")
            
            print("⏳ Attesa caricamento font e loghi esterni da media.api-sports.io...")
            page.wait_for_timeout(2000)  # 2 secondi completi per garantire il download dei loghi
            
            card = page.query_selector(".card")
            card.screenshot(path=png_path)
            browser.close()
            print("📸 Immagine generata correttamente localmente!")
    except Exception as e:
        print(f"❌ Errore durante l'uso di Playwright: {e}")
        sys.exit(1)
        
    # Invia lo screenshot generato direttamente su Telegram
    send_telegram_photo(png_path)
    print("🏁 Test completato.")

if __name__ == "__main__":
    main()
