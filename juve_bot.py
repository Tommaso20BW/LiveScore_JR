import os
import requests
import json

# Caricamento configurazioni da GitHub Secrets
API_KEY = os.getenv('API_KEY')
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')
JUVE_ID = 496

# Mappatura delle tue Emoji Personalizzate
E_BOLT = '<tg-emoji emoji-id="5778411071182217227">⚡️</tg-emoji>'
E_JUVE = '<tg-emoji emoji-id="6028591382870888482">⚪️</tg-emoji>'
E_ITA  = '<tg-emoji emoji-id="5913639563900752614">🇮🇹</tg-emoji>'
E_SEA  = '<tg-emoji emoji-id="5985546632219858247">🇮🇹</tg-emoji>'
E_POINTER = '<tg-emoji emoji-id="5985659276327132147">👉</tg-emoji>'

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Errore invio Telegram: {e}")

def main():
    # Controllo memoria di stato
    if os.path.exists("match_state.json"):
        with open("match_state.json", "r") as f:
            state = json.load(f)
    else:
        state = {"simulated": False}

    if not state.get("simulated", False):
        # --- TEST DI SIMULAZIONE GRAFICA ---
        test_msg = (
            f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n"
            f"{E_JUVE} Juventus - Fiorentina {E_ITA}\n\n"
            f"{E_SEA} #JuveFiorentina\n\n"
            f"{E_POINTER} <i>Test simulazione riuscito!</i>"
        )
        send_telegram(test_msg)
        
        state["simulated"] = True
        with open("match_state.json", "w") as f:
            json.dump(state, f)
        print("Simulazione inviata correttamente su Telegram.")
        return

    # --- LOGICA REALE DI GARA DIRETTAMENTE DA API-SPORTS ---
    url = "https://v3.football.api-sports.io/fixtures"
    headers = {"x-apisports-key": API_KEY}
    params = {"team": JUVE_ID, "live": "all"}
    
    try:
        res = requests.get(url, headers=headers, params=params).json()
    except Exception as e:
        print(f"Errore API: {e}")
        return

    if not res.get('response'):
        print("La Juventus non sta giocando in questo momento.")
        return

if __name__ == "__main__":
    main()
