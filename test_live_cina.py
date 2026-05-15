import os
import requests
import json
import time

BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')
API_KEY = os.getenv('API_KEY')

# ID specifico Karvan per il test live
TEAM_ID = 11239  
STATE_FILE = "match_state_test.json"

url_api = f"https://v3.football.api-sports.io/fixtures?live=all&team={TEAM_ID}"
headers = {"x-rapidapi-key": API_KEY, "x-rapidapi-host": "v3.football.api-sports.io"}

print("🚀 MOTORE LIVE AVVIATO - Controllo continuo ogni 90 secondi (Inter U20)...")

# Questo ciclo tiene il bot ACCESO per tutta la partita
while True:
    try:
        response = requests.get(url_api, headers=headers).json()
        
        if response.get("response"):
            fixture = response["response"][0]
            status = fixture["fixture"]["status"]["short"]
            home = fixture["teams"]["home"]["name"]
            away = fixture["teams"]["away"]["name"]
            goals_home = fixture["goals"]["home"]
            goals_away = fixture["goals"]["away"]
            events = fixture.get("events", [])
            
            print(f"[LIVE TEST] {home} {goals_home}-{goals_away} {away} | Stato: {status}")

            # Se la partita è finita, il bot si spegne da solo e chiude il server
            if status in ["FT", "AET", "PEN"]:
                msg_fine = f"🏁 <b>FINE PARTITA</b>\n\n{home} {goals_home} - {goals_away} {away}\n\nIl match è terminato. Spegnimento automatico del bot."
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": msg_fine, "parse_mode": "HTML"})
                break

            # Gestione eventi (Gol, Cartellini, Cambi)
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    sent_events = json.load(f)
            else:
                sent_events = []

            new_events = []
            url_tg = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

            for event in events:
                event_id = f"{event['time']['elapsed']}_{event['type']}_{event['detail']}_{event['player']['name']}"
                
                if event_id not in sent_events:
                    ev_type = event["type"]
                    ev_time = event["time"]["elapsed"]
                    p_name = event["player"]["name"]
                    
                    if ev_type == "Goal":
                        msg_event = f"<b>GOAL ⚽️</b>\n\n{home} {goals_home} - {goals_away} {away}\n🎙 Minuto {ev_time}’: Segna {p_name}!"
                        requests.post(url_tg, data={"chat_id": CHAT_ID, "text": msg_event, "parse_mode": "HTML"})
                    
                    elif ev_type == "Card":
                        detail = event["detail"]
                        emoji_card = "🟨" if "Yellow" in detail else "🟥"
                        msg_event = f"<b>CARTELLINO {emoji_card}</b>\n\nMinuto {ev_time}’: Ammonito {p_name}."
                        requests.post(url_tg, data={"chat_id": CHAT_ID, "text": msg_event, "parse_mode": "HTML"})
                        
                    elif ev_type == "Subst":
                        p_assist = event["assist"]["name"] if event.get("assist") else "N.D."
                        msg_event = f"<b>CAMBIO 🔄</b>\n\nMinuto {ev_time}’:\n🔼 Entra: {p_assist}\n🔽 Esce: {p_name}"
                        requests.post(url_tg, data={"chat_id": CHAT_ID, "text": msg_event, "parse_mode": "HTML"})

                    new_events.append(event_id)

            sent_events.extend(new_events)
            with open(STATE_FILE, "w") as f:
                json.dump(sent_events, f)

        else:
            print("Nessun dato live al momento per il Karvan (pausa, fine o match non iniziato).")

    except Exception as e:
        print(f"Errore temporaneo: {e}")
    
    # Blocca lo script per 90 secondi esatti, poi ricomincia il giro da solo
    time.sleep(90)
