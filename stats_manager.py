import os
import requests
from playwright.sync_api import sync_playwright

def genera_grafica(match_data, bot_token, chat_id):
    # Estrazione dati dall'oggetto API
    stats = match_data.get('statistics', [])
    # (Qui la logica per mappare le 9 statistiche dal JSON di API-Football)
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"file:///{os.getcwd()}/template.html")
        
        # Inserimento loghi e dati
        page.evaluate(f"document.getElementById('logo-l').src = '{match_data['teams']['home']['logo']}'")
        page.evaluate(f"document.getElementById('logo-r').src = '{match_data['teams']['away']['logo']}'")
        
        # Rendering e Screenshot
        page.locator(".stat-card").screenshot(path="stats.png")
        browser.close()
        
    # Invio Telegram
    requests.post(f"https://api.telegram.org/bot{bot_token}/sendPhoto", 
                  data={'chat_id': chat_id}, files={'photo': open('stats.png', 'rb')})
