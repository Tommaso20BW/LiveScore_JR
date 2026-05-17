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
# SIMULATORE DI EVENTI CON LOTTERIA DEI RIGORI
# ==============================================================================
def genera_finta_api_rigori(step):
    """Genera la sequenza di eventi: Fine 90° -> Fine 120° -> Rigori in tempo reale -> FT"""
    finta_risposta = {
        "response": [{
            "fixture": {"status": {"short": "2H", "long": "Second Half", "elapsed": 90}},
            "league": {"id": 137}, # Coppa Italia (Prevede i rigori)
            "teams": {
                "home": {"id": 496, "name": "Juventus"},
                "away": {"id": 505, "name": "Inter"}
            },
            "goals": {"home": 1, "away": 1},
            "score": {"penalty": {"home": None, "away": None}},
            "events": []
        }]
    }
    match = finta_risposta["response"][0]
    
    if step == 0:  # Fine 90 minuti regolamentari (1-1)
        match["fixture"]["status"]["short"] = "2H"
        
    elif step == 1:  # Fine Tempi Supplementari (1-1)
        match["fixture"]["status"]["short"] = "ET"
        match["fixture"]["status"]["elapsed"] = 120
        
    elif step == 2:  # Inizio Rigori - Primi due rigori calciati
        match["fixture"]["status"]["short"] = "PEN"
        match["fixture"]["status"]["elapsed"] = 120
        match["events"].extend([
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 496}}, # Juve segna
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 505}}  # Inter segna
        ])
        
    elif step == 3:  # Oltranza Rigori - L'Inter sbaglia un rigore
        match["fixture"]["status"]["short"] = "PEN"
        match["fixture"]["status"]["elapsed"] = 120
        match["events"].extend([
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 496}}, # Juve segna
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 505}}, # Inter segna
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 496}}, # Juve segna
            {"type": "Goal", "detail": "Missed Penalty Shootout", "team": {"id": 505}} # Inter sbaglia! ❌
        ])
        
    elif step == 4:  # Ultimo rigore decisivo segnato dalla Juve
        match["fixture"]["status"]["short"] = "PEN"
        match["fixture"]["status"]["elapsed"] = 120
        match["events"].extend([
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 496}},
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 505}},
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 496}},
            {"type": "Goal", "detail": "Missed Penalty Shootout", "team": {"id": 505}},
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 496}}  # Juve segna il rigore decisivo!
        ])
        
    elif step == 5:  # Fischio Finale Assoluto (La Juve vince ai rigori)
        match["fixture"]["status"]["short"] = "PEN"
        match["fixture"]["status"]["long"] = "Match Finished"
        match["fixture"]["status"]["elapsed"] = 120
        match["score"]["penalty"]["home"] = 4
        match["score"]["penalty"]["away"] = 1
        match["events"].extend([
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 496}},
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 505}},
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 496}},
            {"type": "Goal", "detail": "Missed Penalty Shootout", "team": {"id": 505}},
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 496}}
        ])
        
    return finta_risposta

# ==============================================================================
# CICLO PRINCIPALE DEL TEST
# ==============================================================================
def main():
    print("🚀 AVVIO SIMULATORE CALCI DI RIGORE...")
    if os.path.exists("match_state.json"): os.remove("match_state.json")
    
    # Eseguiamo i 6 step della lotteria distanziati da 8 secondi
    for step in range(6):
        print(f"\n--- 🔄 SIMULAZIONE STEP RIGORI {step} ---")
        res = genera_finta_api_rigori(step)
        
        if os.path.exists("match_state.json"):
            with open("match_state.json", "r") as f: state = json.load(f)
        else:
            state = {"live_match_id": 8888, "sent_periods": [], "goals_detected": 0, "sent_subs": [], "sent_cards": [], "penalties_count": 0}

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

        # 1. Cronaca Periodi (Supplementari / Fine 90)
        if status in ["ET", "AET", "PEN"] and "2H_END" not in state["sent_periods"]:
            send_telegram(f"<b>FINE SECONDO TEMPO {E_FLAG}</b>\n\n{home_name} {g_home_int}-{g_away_int} {away_name}\n\n🇮🇹 {hashtag}")
            state["sent_periods"].append("2H_END")

        # 2. Lotteria dei Rigori in Tempo Reale
        if status == "PEN" and "finished" not in status_long:
            events = match.get('events', [])
            home_pen_icons, away_pen_icons = [], []
            for e in events:
                detail, ev_type = e.get('detail', '').lower(), e.get('type', '').lower()
                if "shootout" in detail or (ev_type == "goal" and elapsed_minutes >= 120 and "penalty" in detail):
                    icon = E_PEN_KO if ("missed" in detail or "saved" in detail or ev_type == "card") else E_PEN_OK
                    if e.get('team', {}).get('id') == 496: home_pen_icons.append(icon)
                    else: away_pen_icons.append(icon)
                    
            total_kicks = len(home_pen_icons) + len(away_pen_icons)
            if total_kicks > state["penalties_count"]:
                msg_pen = f"<b>LOTTERIA DEI RIGORI 🎯</b>\n\n{home_name}: " + "".join(home_pen_icons) + f"\n{away_name}: " + "".join(away_pen_icons) + f"\n\n🇮🇹 {hashtag}"
                send_telegram(msg_pen)
                state["penalties_count"] = total_kicks

        # 3. Fine Partita Assoluta dopo i Rigori -> SCATTA CANVA
        if "finished" in status_long or (status == "PEN" and p_home is not None):
            print("🏁 Rilevata fine totale dei rigori! Scarico da Canva...")
            msg_finale = f"<b>JUVENTUS VINCE AI RIGORI! 🏆🏆</b>\n\n{home_name} {score_string} {away_name}\n\n🇮🇹 {hashtag}"
            
            token = get_valid_token()
            foto = get_canva_image(token)
            send_telegram_post_with_photo(msg_finale, photo_bytes=foto)
            
            if os.path.exists("match_state.json"): os.remove("match_state.json")
            print("🏁 Test Rigori completato con successo!")
            sys.exit(0)

        with open("match_state.json", "w") as f: json.dump(state, f)
        time.sleep(8)

if __name__ == "__main__":
    main()
