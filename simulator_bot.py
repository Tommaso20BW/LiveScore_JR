import os
import requests
from playwright.sync_api import sync_playwright

def genera_e_invia_stats(match_id):
    print(f"📊 Avvio generazione statistiche per il match: {match_id}...")
    
    # 1. Verifica che il file template esista prima di iniziare
    if not os.path.exists("template.html"):
        print("❌ ERRORE: Il file template.html non esiste nella cartella corrente!")
        return

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            
            # Carichiamo il file locale
            page.goto(f"file://{os.path.abspath('template.html')}")
            
            # Eseguiamo lo screenshot
            page.screenshot(path="stats.png", full_page=True)
            browser.close()
            
        # 2. Verifica che lo screenshot sia stato creato correttamente
        if os.path.exists("stats.png"):
            print("✅ File stats.png generato correttamente. Invio a Telegram...")
            
            # 3. Invio tramite Telegram
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
            with open("stats.png", "rb") as photo:
                files = {"photo": photo}
                data = {"chat_id": CHAT_ID, "caption": "📊 Statistiche incontro"}
                response = requests.post(url, files=files, data=data)
            
            if response.status_code == 200:
                print("📡 Invio Telegram riuscito!")
            else:
                print(f"📡 Errore invio Telegram: {response.text}")
        else:
            print("❌ ERRORE: Il file stats.png non è stato creato da Playwright.")
            
    except Exception as e:
        print(f"❌ Errore critico durante la generazione: {str(e)}")
