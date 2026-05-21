import os
import requests
import json
import time
import sys
import base64
import subprocess
from datetime import datetime
from nacl import encoding, public

# CONFIGURAZIONE
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

E_BOLT, E_FLAG, E_MIC, E_BALL, E_SUB, E_UP, E_DOWN, E_RED, E_PEN_OK, E_PEN_KO = '⚡️', '🏁', '🎙', '⚽️', '🔄', '🔼', '🔽', '🟥', '✅', '❌'

def send_telegram(text):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"})

def send_telegram_with_photo(text, photo_bytes):
    if not photo_bytes: return send_telegram(text)
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto", data={"chat_id": CHAT_ID, "caption": text, "parse_mode": "HTML"}, files={"photo": ("matchday.png", photo_bytes)})

def update_github_secret(secret_name, new_value):
    headers = {"Authorization": f"Bearer {GH_PAT}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    res_pk = requests.get(f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/secrets/public-key", headers=headers).json()
    pk = public.PublicKey(res_pk["key"].encode("utf-8"), encoding.Base64Encoder)
    enc = base64.b64encode(public.SealedBox(pk).encrypt(new_value.encode("utf-8"))).decode("utf-8")
    requests.put(f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/secrets/{secret_name}", headers=headers, json={"encrypted_value": enc, "key_id": res_pk["key_id"]})

def get_valid_token():
    res = requests.post("https://api.canva.com/rest/v1/oauth/token", data={"grant_type": "refresh_token", "refresh_token": CANVA_REFRESH_TOKEN, "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}).json()
    if "refresh_token" in res and res["refresh_token"] != CANVA_REFRESH_TOKEN: update_github_secret("CANVA_REFRESH_TOKEN", res["refresh_token"])
    return res.get("access_token")

def get_canva_image(token):
    job = requests.post("https://api.canva.com/rest/v1/exports", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json={"design_id": CANVA_DESIGN_ID, "format": {"type": "png", "pages": [PAGINA_TARGET]}}).json()
    job_id = job.get("id")
    for _ in range(40):
        time.sleep(5)
        stat = requests.get(f"https://api.canva.com/rest/v1/exports/{job_id}", headers={"Authorization": f"Bearer {token}"}).json()
        if stat.get("status") == "success": return requests.get(stat["urls"][0]).content
    return None

def avvia_ciclo_partita():
    headers = {"x-apisports-key": API_KEY}
    match_id = None
    # Ciclo ricerca match
    while not match_id:
        res = requests.get(f"https://v3.football.api-sports.io/fixtures?team={JUVE_ID}&next=1", headers=headers).json()
        if res.get('response'): match_id = res['response'][0]['fixture']['id']
        time.sleep(30)

    while True:
        try:
            # Stato salvato per stats e logica
            if os.path.exists("match_state.json"):
                with open("match_state.json", "r") as f: state = json.load(f)
            else:
                state = {"sent_stats": [], "goals_detected": 0, "sent_subs": [], "sent_cards": [], "penalties_count": 0}

            match = requests.get(f"https://v3.football.api-sports.io/fixtures?id={match_id}", headers=headers).json()['response'][0]
            status = match['fixture']['status']['short']

            # 1. LANCIO STATISTICHE (Stats Manager)
            if status in ["HT", "FT", "PEN"]:
                if f"sent_stats_{status}" not in state.get("sent_stats", []):
                    subprocess.Popen(["python", "stats_manager.py", str(match_id), API_KEY, BOT_TOKEN, CHAT_ID, status])
                    state.setdefault("sent_stats", []).append(f"sent_stats_{status}")
                    with open("match_state.json", "w") as f: json.dump(state, f)

            # 2. LOGICA EVENTI (GOL, CARTELLINI, ECC.)
            for e in match.get('events', []):
                # Esempio Gol:
                if e['type'] == 'Goal' and e['time']['elapsed'] not in state.get("sent_goals", []):
                    send_telegram(f"⚽️ {e['player']['name']} - {e['detail']}")
                    state.setdefault("sent_goals", []).append(e['time']['elapsed'])
                    with open("match_state.json", "w") as f: json.dump(state, f)

            # 3. FINE PARTITA
            if status in ["FT", "AET", "PEN"]:
                img = get_canva_image(get_valid_token())
                send_telegram_with_photo("🏁 Partita finita", img)
                if os.path.exists("match_state.json"): os.remove("match_state.json")
                sys.exit(0)

            time.sleep(60)
        except Exception as e:
            print(f"Errore: {e}")
            time.sleep(60)

if __name__ == "__main__":
    avvia_ciclo_partita()
