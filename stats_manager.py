import sys
import requests
import os
from playwright.sync_api import sync_playwright

def genera_e_invia_stats(match_id, api_key, bot_token, chat_id, label):
    print(f"📊 Generazione statistiche per {label}...")
    
    # 1. Recupero dati dall'API (endpoint statistics)
    url = f"https://v3.football.api-sports.io/fixtures/statistics?fixture={match_id}"
    headers = {"x-apisports-key": api_key}
    stats_json = requests.get(url, headers=headers).json()
    
    # 2. Generazione immagine con Playwright (usando il tuo template.html)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"file:///{os.getcwd()}/template.html")
        # --- QUI INSERISCI LA TUA LOGICA PER COMPILARE L'HTML CON STATS_JSON ---
        page.locator(".stat-card").screenshot(path="match_stats.png")
        browser.close()
    
    # 3. Invio a Telegram
    url_tg = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    with open("match_stats.png", "rb") as f:
        requests.post(url_tg, data={'chat_id': chat_id, 'caption': f"📊 Statistiche {label}"}, files={'photo': f})

if __name__ == "__main__":
    # Quando chiamato dal bot principale:
    # python stats_manager.py <match_id> <api_key> <bot_token> <chat_id> <label>
    genera_e_invia_stats(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
