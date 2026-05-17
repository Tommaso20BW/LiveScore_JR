import os
import requests
import json
import time
import sys
from datetime import datetime

# ==============================================================================
# CONFIGURAZIONE (Usa gli stessi Secret del bot reale)
# ==============================================================================
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')
CLIENT_ID = os.getenv('CANVA_CLIENT_ID')
CLIENT_SECRET = os.getenv('CANVA_CLIENT_SECRET')

# Configurazione Canva
CANVA_DESIGN_ID = "DAHI3ytu6yQ"
PAGINA_TARGET = 11
TOKEN_FILE = "canva_tokens.json"

# Emoji Branding @Juventus_Reborn
E_BOLT = '⚡️'
E_FLAG = '🏁'
E_MIC = '🎙'
E_BALL = '⚽️'
E_SUB = '🔄'
E_UP = '🔼'
E_DOWN = '🔽'
E_RED = '🟥'
E_PEN_OK = '✅'
E_PEN_KO = '❌'

# ==============================================================================
# FUNZIONI DI INVIO E CONNESSIOINE (Identiche al bot reale)
# ==============================================================================
def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ Errore: TELEGRAM_TOKEN o TELEGRAM_TO non configurati nei Secret.")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code != 200: print(f"Errore Telegram: {res.text}")
    except Exception as e: print(f"Errore invio: {e}")

def send_telegram_post_with_photo(text, photo_bytes):
    if not photo_bytes:
        print("⚠️ Immagine Canva mancante. Invio solo testo...")
        send_telegram(text)
        return
    print("📤 Spedisco il post con grafica Canva su Telegram...")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    payload = {"chat_id": CHAT_ID, "caption": text, "parse_mode": "HTML"}
    files = {"photo": ("matchday.png", photo_bytes)}
    try:
        res = requests.post(url, data=payload, files=files, timeout=25)
        if res.status_code == 200:
            print("🏁 Grafica fine partita pubblicata con successo su Telegram!")
        else:
            print(f"❌ Errore foto Telegram: {res.text}. Invio solo testo...")
            send_telegram(text)
    except Exception as e:
        print(f"Errore invio foto: {e}")
        send_telegram(text)

def get_valid_token():
    if not os.path.exists(TOKEN_FILE): return None
    with open(TOKEN_FILE, "r") as f: tokens = json.load(f)
    if tokens.get("expires_at", 0) - time.time() < 300:
        url = "https://api.canva.com/rest/v1/oauth/token"
        payload = {"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}
        try:
            res = requests.post(url, data=payload, timeout=15)
            if res.status_code == 200:
                new_tokens = res.json()
                tokens["access_token"] = new_tokens["access_token"]
                tokens["refresh_token"] = new_tokens.get("refresh_token", tokens["refresh_token"])
                tokens["expires_at"] = int(time.time()) + new_tokens["expires_in"]
                with open(TOKEN_FILE, "w") as f: json.dump(tokens, f, indent=2)
        except: return None
    return tokens["access_token"]

def get_canva_image(access_token):
    if not access_token: return None
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    try:
        res = requests.post("https://api.canva.com/rest/v1/exports", headers=headers, json={"design_id": CANVA_DESIGN_ID, "format": {"type": "png", "pages": [PAGINA_TARGET]}}, timeout=15)
        if res.status_code not in [200, 201]: return None
        job_id = res.json().get("id") or res.json().get("job", {}).get("id")
        for i in range(20):
            time.sleep(3)
            check = requests.get(f"https://api.canva.com/rest/v1/exports/{job_id}", headers=headers, timeout=15).json()
            status = check.get("status") or check.get("job", {}).get("status")
            if status == "success":
                urls = check.get("urls") or check.get("job", {}).get("urls")
                url_download = urls[0] if urls else (check.get("url") or check.get("job", {}).get("url"))
                if url_download: return requests.get(url_download, timeout=20).content
    except Exception as e: print(f"Errore Canva: {e}")
    return None

# ==============================================================================
# SIMULATORE DI UNA PARTITA COMPLETA FINO AI RIGORI (9 STEP)
# ==============================================================================
def genera_finta_api_partita_completa(step):
    finta_risposta = {
        "response": [{
            "fixture": {"status": {"short": "1H", "long": "First Half", "elapsed": 0}},
            "league": {"id": 137}, # Coppa Italia
            "teams": {
                "home": {"id": 496, "name": "Juventus"},
                "away": {"id": 505, "name": "Inter"}
            },
            "goals": {"home": 0, "away": 0},
            "score": {"penalty": {"home": None, "away": None}},
            "events": []
        }]
    }
    match = finta_risposta["response"][0]
    
    if step == 0:  # Fischio d'inizio
        match["fixture"]["status"]["short"] = "1H"
        match["fixture"]["status"]["elapsed"] = 1
        
    elif step == 1:  # Gol dell'Inter (0-1)
        match["fixture"]["status"]["short"] = "1H"
        match["fixture"]["status"]["elapsed"] = 30
        match["goals"]["away"] = 1
        match["events"].append({
            "type": "Goal", "detail": "Normal Goal", "team": {"id": 505},
            "time": {"elapsed": 30, "extra": None}, "player": {"name": "L. Martinez"}
        })
        
    elif step == 2:  # Fine Primo Tempo (0-1)
        match["fixture"]["status"]["short"] = "HT"
        match["fixture"]["status"]["elapsed"] = 45
        match["goals"]["away"] = 1
        
    elif step == 3:  # Gol del Pareggio della Juve (1-1)
        match["fixture"]["status"]["short"] = "2H"
        match["fixture"]["status"]["elapsed"] = 65
        match["goals"]["home"] = 1
        match["goals"]["away"] = 1
        match["events"].extend([
            {"type": "Goal", "detail": "Normal Goal", "team": {"id": 505}, "time": {"elapsed": 30}, "player": {"name": "L. Martinez"}},
            {"type": "Goal", "detail": "Normal Goal", "team": {"id": 496}, "time": {"elapsed": 65}, "player": {"name": "D. Vlahović"}}
        ])
        
    elif step == 4:  # Fine 90' Regolamentari (1-1) -> Si va ai supplementari
        match["fixture"]["status"]["short"] = "ET"
        match["fixture"]["status"]["elapsed"] = 90
        match["goals"]["home"] = 1
        match["goals"]["away"] = 1
        
    elif step == 5:  # Fine 120' Supplementari (1-1) -> Si va ai rigori
        match["fixture"]["status"]["short"] = "ET"
        match["fixture"]["status"]["elapsed"] = 120
        match["goals"]["home"] = 1
        match["goals"]["away"] = 1
        
    elif step == 6:  # Lotteria Rigori - Round 1 (Juve segna, Inter segna)
        match["fixture"]["status"]["short"] = "PEN"
        match["fixture"]["status"]["elapsed"] = 120
        match["goals"]["home"] = 1
        match["goals"]["away"] = 1
        match["events"].extend([
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 496}},
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 505}}
        ])
        
    elif step == 7:  # Lotteria Rigori - Round 2 (Juve segna, Inter SBLAGLIA ❌)
        match["fixture"]["status"]["short"] = "PEN"
        match["fixture"]["status"]["elapsed"] = 120
        match["goals"]["home"] = 1
        match["goals"]["away"] = 1
        match["events"].extend([
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 496}},
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 505}},
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 496}},
            {"type": "Goal", "detail": "Missed Penalty Shootout", "team": {"id": 505}} # Inter fallisce!
        ])
        
    elif step == 8:  # Fine Totale della partita (La Juve segna l'ultimo e vince!)
        match["fixture"]["status"]["short"] = "PEN"
        match["fixture"]["status"]["long"] = "Match Finished"
        match["fixture"]["status"]["elapsed"] = 120
        match["goals"]["home"] = 1
        match["goals"]["away"] = 1
        match["score"]["penalty"]["home"] = 3
        match["score"]["penalty"]["away"] = 1
        match["events"].extend([
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 496}},
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 505}},
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 496}},
            {"type": "Goal", "detail": "Missed Penalty Shootout", "team": {"id": 505}},
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 496}} # Rigore della vittoria
        ])
        
    return finta_risposta

# ==============================================================================
# CICLO PRINCIPALE
# ==============================================================================
def main():
    print("🚀 AVVIO SIMULATORE COMPLETO: MATCH DI 120 MINUTI + RIGORI...")
    if os.path.exists("match_state.json"): os.remove("match_state.json")
    
    # Giriamo per i 9 step totali distanziati da 8 secondi per goderci la sfilata su Telegram
    for step in range(9):
        print(f"\n--- 🔄 SIMULAZIONE STEP COMPLETO {step} ---")
        res = genera_finta_api_partita_completa(step)
        
        if os.path.exists("match_state.json"):
            with open("match_state.json", "r") as f: state = json.load(f)
        else:
            state = {"live_match_id": 7777, "sent_periods": [], "goals_detected": 0, "sent_subs": [], "sent_cards": [], "penalties_count": 0}

        match = res['response'][0]
        fixture = match.get('fixture', {})
        status = fixture.get('status', {}).get('short', 'NS')
        status_long = fixture.get('status', {}).get('long', '').lower()
        elapsed_minutes = fixture.get('status', {}).get('elapsed', 0)
        
        g_home_int = match.get('goals', {}).get('home', 0)
        g_away_int = match.get('goals', {}).get('away', 0)
        home_name, away_name = "Juventus", "Inter"
        hashtag = "#JuveInter"
        
        penalties = match.get('score', {}).get('penalty', {})
        p_home, p_away = penalties.get('home'), penalties.get('away')
        score_string = f"{g_home_int} ({p_home}) - ({p_away}) {g_away_int}" if p_home is not None else f"{g_home_int}-{g_away_int}"

        # 1. Periodi Regolamentari e Supplementari
        if (status == "1H" or elapsed_minutes > 0) and "1H" not in state["sent_periods"]:
            send_telegram(f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{home_name} - {away_name}\n\n🇮🇹 {hashtag}")
            state["sent_periods"].append("1H")
        elif status == "HT" and "HT" not in state["sent_periods"]:
            send_telegram(f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{home_name} {g_home_int}-{g_away_int} {away_name}\n\n🇮🇹 {hashtag}")
            state["sent_periods"].append("HT")
        elif status == "ET" and elapsed_minutes == 90 and "2H_END" not in state["sent_periods"]:
            send_telegram(f"<b>FINE TEMPI REGOLAMENTARI {E_FLAG}</b>\n\n{home_name} {g_home_int}-{g_away_int} {away_name}\n\nSI VA AI SUPPLEMENTARI! ⏳\n\n🇮🇹 {hashtag}")
            state["sent_periods"].append("2H_END")
        elif status == "ET" and elapsed_minutes == 120 and "ET_END" not in state["sent_periods"]:
            send_telegram(
