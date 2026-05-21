import sys, requests, os
from playwright.sync_api import sync_playwright

def genera_stats(m_id, key, bot, chat, stato):
    url = f"https://v3.football.api-sports.io/fixtures/statistics?fixture={m_id}"
    data = requests.get(url, headers={"x-apisports-key": key}).json().get('response', [])
    if not data: return

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"file:///{os.getcwd()}/template.html")
        # QUI VANNO I COMANDI DI INSERIMENTO DATI NEL TEMPLATE
        page.locator(".stat-card").screenshot(path="stats.png")
        browser.close()
    
    requests.post(f"https://api.telegram.org/bot{bot}/sendPhoto", 
                  data={'chat_id': chat, 'caption': f"📊 Statistiche {stato}"}, 
                  files={'photo': open('stats.png', 'rb')})

if __name__ == "__main__":
    genera_stats(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
