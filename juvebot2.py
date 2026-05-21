import os
import requests
import json
import time
import sys
import base64
import subprocess
from datetime import datetime
from nacl import encoding, public

# --- CONFIGURAZIONE ---
API_KEY = os.getenv('API_KEY')
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')
CLIENT_ID = os.getenv('CANVA_CLIENT_ID')
CLIENT_SECRET = os.getenv('CANVA_CLIENT_SECRET')
CANVA_REFRESH_TOKEN = os.getenv('CANVA_REFRESH_TOKEN')
GH_PAT = os.getenv('GH_PAT')
GITHUB_REPOSITORY = os.getenv('GITHUB_REPOSITORY')

JUVE_ID = 2939
CANVA_DESIGN_ID = "DAHI3ytu6yQ"
PAGINA_TARGET = 11

# --- EMOJI E FUNZIONI UTILI ---
E_BOLT, E_FLAG, E_MIC, E_BALL, E_SUB, E_UP, E_DOWN, E_RED, E_PEN_OK, E_PEN_KO = '⚡️', '🏁', '🎙', '⚽️', '🔄', '🔼', '🔽', '🟥', '✅', '❌'

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"})

def send_telegram_with_photo(text, photo_bytes):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    files = {"photo": ("matchday.png", photo_bytes)}
    requests.post(url, data={"chat_id": CHAT_ID, "caption": text, "parse_mode": "HTML"}, files=files)

# [INSERIRE QUI LE FUNZIONI DI CANVA E GITHUB ORIGINALI]

def avvia_ciclo_partita():
    headers = {"x-apisports-key": API_KEY}
    url = "https://v3.football.api-sports.io/fixtures"
    match_id = None

    # Logica recupero match
    while not match_id:
        res = requests.get(f"{url}?team={JUVE_ID}&next=1", headers=headers).json()
        if res.get('response'):
            match_id = res['response'][0]['fixture']['id']
        time.sleep(30)

    print(f"✅ Bot attivo su ID: {match_id}")
    params = {"id": match_id}

    while True:
        try:
            if os.path.exists("match_state.json"):
                with open("match_state.json", "r") as f: state = json.load(f)
            else:
                state = {"sent_stats": [], "sent_periods": [], "goals_detected": 0, "sent_subs": [], "sent_cards": [], "penalties_count": 0}

            res = requests.get(url, headers=headers, params=params).json()
            match = res['response'][0]
            fixture = match['fixture']
            status = fixture['status']['short']
            
            # --- INTEGRAZIONE STATISTICHE (LANCIO ESTERNO) ---
            if status in ["HT", "FT", "PEN"]:
                stat_key = f"sent_stats_{status}"
                if stat_key not in state.get("sent_stats", []):
                    print(f"📊 Lancio generazione stats per {status}")
                    subprocess.Popen(["python", "stats_manager.py", str(match_id), API_KEY, BOT_TOKEN, CHAT_ID, status])
                    state.setdefault("sent_stats", []).append(stat_key)
                    with open("match_state.json", "w") as f: json.dump(state, f)

            # --- LOGICA ORIGINALE EVENTI ---
            # ... (Tutto il tuo codice originale per Gol/Cartellini/Periodi qui) ...

            # 3. FISCHIO FINALE
            if status in ["FT", "AET", "PEN"]:
                # ... (Logica Canva finale) ...
                sys.exit(0)

        except Exception as e:
            print(f"Errore: {e}")
            time.sleep(60)

if __name__ == "__main__":
    avvia_ciclo_partita()
