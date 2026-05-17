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
    if not os.path.exists(TOKEN_FILE):
        print(f"❌ Errore: Manca il file {TOKEN_FILE}")
        return None
    with open(TOKEN_FILE, "r") as f: tokens = json.load(f)
    if tokens.get("expires_at", 0) - time.time() < 300:
        print("🔄 Token Canva scaduto. Tento il rinnovo automatico...")
        url = "https://api.canva.com/rest/v1/oauth/token"
        payload = {
            "grant_type": "refresh_token", "refresh_token": tokens["refresh_token"],
            "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET
        }
        try:
            res = requests.post(url, data=payload, timeout=15)
            if res.status_code == 200:
                new_tokens = res.json()
                tokens["access_token"] = new_tokens["access_token"]
                tokens["refresh_token"] = new_tokens.get("refresh_token", tokens["refresh_token"])
                tokens["expires_at"] = int(time.time()) + new_tokens["expires_in"]
                with open(TOKEN_FILE, "w") as f: json.dump(tokens, f, indent=2)
                print("✅ Token rinnovato con successo dal Bot!")
            else:
                print(f"❌ Errore rinnovo: {res.text}")
                return None
        except Exception as e: return None
    return tokens["access_token"]

def get_canva_image(access_token):
    if not access_token: return None
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    try:
        print("🎨 Richiesta generazione immagine a Canva...")
        res = requests.post("https://api.canva.com/rest/v1/exports", headers=headers, json={"design_id": CANVA_DESIGN_ID, "format": {"type": "png", "pages": [PAGINA_TARGET]}}, timeout=15)
        if res.status_code not in [200, 201]: return None
        job_id = res.json().get("id") or res.json().get("job", {}).get("id")
        
        print("⏳ Attesa rendering della grafica su Canva...")
        for i in range(20):
            time.sleep(3)
            check = requests.get(f"https://api.canva.com/rest/v1/exports/{job_id}", headers=headers, timeout=15).json()
            status = check.get("status") or check.get("job", {}).get("status")
            print(f"   [Controllo {i+1}/20] Stato Canva: {status}")
            if status == "success":
                urls = check.get("urls") or check.get("job", {}).get("urls")
                url_download = urls[0] if urls else (check.get("url") or check.get("job", {}).get("url"))
                if url_download:
                    return requests.get(url_download, timeout=20).content
    except Exception as e: print(f"Errore Canva: {e}")
    return None

# ==============================================================================
# SIMULATORE DI EVENTI DI UNA PARTITA (Genera finti dati API-Sports)
# ==============================================================================
def genera_finta_api(step):
    """Restituisce un finto oggetto di risposta API basato sullo step del test."""
    finta_risposta = {
        "response": [{
            "fixture": {"status": {"short": "1H", "long": "First Half", "elapsed": step * 15}},
            "league": {"id": 135},
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
    
    if step == 0:  # Inizio Partita
        match["fixture"]["status"]["short"] = "1H"
        match["fixture"]["status"]["elapsed"] = 1
        
    elif step == 1:  # Gol della Juventus
        match["fixture"]["status"]["elapsed"] = 23
        match["goals"]["home"] = 1
        match["events"].append({
            "type": "Goal", "detail": "Normal Goal", "team": {"id": 496},
            "time": {"elapsed": 23, "extra": None}, "player": {"name": "D. Vlahović"}
        })
        
    elif step == 2:  # Primo tempo finito
        match["fixture"]["status"]["short"] = "HT"
        match["fixture"]["status"]["elapsed"] = 45
        match["goals"]["home"] = 1
        
    elif step == 3:  # Cambio Juventus nel secondo tempo
        match["fixture"]["status"]["short"] = "2H"
        match["fixture"]["status"]["elapsed"] = 60
        match["goals"]["home"] = 1
        match["events"].append({
            "type": "subst", "detail": "Substitution", "team": {"id": 496},
            "time": {"elapsed": 60}, "player": {"name": "K. Thuram"}, "assist": {"name": "M. Locatelli"}
        })
        
    elif step == 4:  # Cartellino Rosso all'Inter
        match["fixture"]["status"]["short"] = "2H"
        match["fixture"]["status"]["elapsed"] = 75
        match["goals"]["home"] = 1
        match["events"].append({
            "type": "card", "detail": "Red Card", "team": {"id": 505},
            "time": {"elapsed": 75}, "player": {"name": "L. Martinez"}
        })
        
    elif step == 5:  # Fischio Finale (FT)
        match["fixture"]["status"]["short"] = "FT"
        match["fixture"]["status"]["long"] = "Match Finished"
        match["fixture"]["status"]["elapsed"] = 90
        match["goals"]["home"] = 1
        
    return finta_risposta

# ==============================================================================
# CICLO PRINCIPALE DEL TEST
# ==============================================================================
def main():
    print("🚀 AVVIO SIMULATORE DI PARTITA DI TEST...")
    if os.path.exists("match_state.json"): os.remove("match_state.json")
    
    # Eseguiamo i 6 step della partita distanziati da 10 secondi per il test
    for step in range(6):
        print(f"\n--- 🔄 SIMULAZIONE STEP {step} ---")
        res = genera_finta_api(step)
        
        # Riproduzione esatta della logica del tuo bot reale
        if os.path.exists("match_state.json"):
            with open("match_state.json", "r") as f: state = json.load(f)
        else:
            state = {"live_match_id": 9999, "sent_periods": [], "goals_detected": 0, "sent_subs": [], "sent_cards": [], "penalties_count": 0}

        match = res['response'][0]
        fixture = match.get('fixture', {})
        status = fixture.get('status', {}).get('short', 'NS')
        elapsed_minutes = fixture.get('status', {}).get('elapsed', 0)
        g_home_int = match.get('goals', {}).get('home', 0)
        g_away_int = match.get('goals', {}).get('away', 0)
        
        home_name, away_name = "Juventus", "Inter"
        hashtag = "#JuveInter"
        score_string = f"{g_home_int}-{g_away_int}"

        # 1. Periodi
        if (status == "1H" or elapsed_minutes > 0) and "1H" not in state["sent_periods"]:
            send_telegram(f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{home_name} - {away_name}\n\n🇮🇹 {hashtag}")
            state["sent_periods"].append("1H")
        elif status == "HT" and "HT" not in state["sent_periods"]:
            send_telegram(f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{home_name} {score_string} {away_name}\n\n🇮🇹 {hashtag}")
            state["sent_periods"].append("HT")
        elif status == "2H" and "2H" not in state["sent_periods"]:
            send_telegram(f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n{home_name} {score_string} {away_name}\n\n🇮🇹 {hashtag}")
            state["sent_periods"].append("2H")

        # 3. Fine Partita -> SCATTA CANVA
        status_long = fixture.get('status', {}).get('long', '').lower()
        if status in ["FT", "AET", "PEN"] or "finished" in status_long:
            print("🏁 SIMULAZIONE: Rilevato Fischio Finale! Scarico da Canva...")
            msg_finale = f"<b>FINE PARTITA {E_FLAG}</b>\n\n{home_name} {score_string} {away_name}\n{E_BALL} <i>23’ D. Vlahović</i>\n\n🇮🇹 {hashtag}"
            
            token = get_valid_token()
            foto = get_canva_image(token)
            send_telegram_post_with_photo(msg_finale, photo_bytes=foto)
            
            if os.path.exists("match_state.json"): os.remove("match_state.json")
            print("🏁 Test completato con successo!")
            sys.exit(0)

        # 4. Gol
        total_goals_now = g_home_int + g_away_int
        if total_goals_now > state["goals_detected"]:
            send_telegram(f"<b>GOAL {E_MIC}</b>\n\n{home_name} {score_string} {away_name}\n{E_BALL} <i>23’ D. Vlahović</i>\n\n🇮🇹 {hashtag}")
            state["goals_detected"] = total_goals_now

        # 5. Eventi (Cambi/Rossi)
        events = match.get('events', [])
        for e in events:
            if e.get('type').lower() == 'subst':
                sub_id = f"sub_{elapsed_minutes}_Thuram_Locatelli"
                if sub_id not in state["sent_subs"]:
                    send_telegram(f"<b>CAMBIO JUVENTUS {E_SUB}</b>\n\n{E_UP} M. Locatelli\n{E_DOWN} K. Thuram\n\n🇮🇹 {hashtag}")
                    state["sent_subs"].append(sub_id)
            elif e.get('type').lower() == 'card':
                card_id = f"card_{elapsed_minutes}_Martinez"
                if card_id not in state["sent_cards"]:
                    send_telegram(f"<b>CARTELLINO ROSSO {E_RED}</b>\n\n🔚 <i>{elapsed_minutes}’ L. Martinez</i>\n\n🇮🇹 {hashtag}")
                    state["sent_cards"].append(card_id)

        with open("match_state.json", "w") as f: json.dump(state, f)
        time.sleep(10) # Aspetta 10 secondi tra un evento simulato e l'altro

if __name__ == "__main__":
    main()
