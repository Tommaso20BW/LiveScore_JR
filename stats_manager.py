import sys, requests, os, time
from playwright.sync_api import sync_playwright

def genera_stats(m_id, key, bot, chat, stato):
    # Ritardo di 2 minuti come richiesto
    time.sleep(120) 
    
    # 1. Recupero Statistiche dall'API
    url = f"https://v3.football.api-sports.io/fixtures/statistics?fixture={m_id}"
    headers = {"x-apisports-key": key}
    res = requests.get(url, headers=headers).json()
    data = res.get('response', [])
    
    if not data: return

    # Mappatura dati (cerca le stats necessarie nell'array dell'API)
    stats_dict = {}
    for team_stats in data:
        team_id = team_stats['team']['id']
        for s in team_stats['statistics']:
            # Esempio di estrazione: Possesso e Tiri totali
            if s['type'] == 'Ball Possession': stats_dict[f"poss_{team_id}"] = s['value']
            if s['type'] == 'Total Shots': stats_dict[f"tiri_{team_id}"] = s['value']

    # 2. Generazione Grafica
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"file:///{os.getcwd()}/template.html")
        
        # Iniezione dati nell'HTML (modifica gli ID in base al tuo file)
        # Esempio: page.evaluate(f"document.getElementById('possesso_h').innerText = '{stats_dict.get('poss_ID_HOME', '0%')}'")
        
        page.locator(".stat-card").screenshot(path="stats.png")
        browser.close()
    
    # 3. Invio a Telegram
    requests.post(f"https://api.telegram.org/bot{bot}/sendPhoto", 
                  data={'chat_id': chat, 'caption': f"📊 Statistiche {stato} - {time.strftime('%H:%M')}"}, 
                  files={'photo': open('stats.png', 'rb')})

if __name__ == "__main__":
    # Parametri passati dal bot principale
    genera_stats(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
