import os
import requests
import json

BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')
API_KEY = os.getenv('API_KEY')

# ID specifico dell'UCSA per bloccare il test su questa partita ucraina
TEAM_ID = 19904

# File temporaneo per non sovrascrivere lo stato della Juventus
STATE_FILE = "match_state_test.json"

url_api = f"https://v3.football.api-sports.io/fixtures?live=all&team={TEAM_ID}"
headers = {"x-rapidapi-key": API_KEY, "x-rapidapi-host": "v3.football.api-sports.io"}

print("Controllo eventi live per UCSA - Bukovyna...")
response = requests.get(url_api, headers=headers).json()

if not response.get("response"):
    print("Nessun dato live trovato in questo turno per questa partita.")
else:
    fixture = response["response"][0]
    status = fixture["fixture"]["status"]["short"]
    elapsed = fixture["fixture"]["status"]["elapsed"]
    home = fixture["teams"]["home"]["name"]
    away = fixture["teams"]["away"]["name"]
    goals_home = fixture["goals"]["home"]
    goals_away = fixture["goals"]["away"]
    events = fixture.get("events", [])
    
    # Carichiamo gli eventi già inviati nel test per non fare spam
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            sent_events = json.load(f)
    else:
        sent_events = []

    new_events = []
    url_tg = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    # Analizziamo i gol, cartellini e cambi in diretta
    for event in events:
        event_id = f"{event['time']['elapsed']}_{event['type']}_{event['detail']}_{event['player']['name']}"
        
        if event_id not in sent_events:
            ev_type = event["type"]
            ev_time = event["time"]["elapsed"]
            p_name = event["player"]["name"]
            p_assist = event["assist"]["name"] if event.get("assist") else ""
            
            if ev_type == "Goal":
                msg_event = f"<b>GOAL ⚽️</b>\n\n{home} {goals_home} - {goals_away} {away}\n🎙 Minuto {ev_time}’: Segna {p_name}!"
                requests.post(url_tg, data={"chat_id": CHAT_ID, "text": msg_event, "parse_mode": "HTML"})
            
            elif ev_type == "Card":
                detail = event["detail"] # Yellow Card / Red Card
                emoji_card = "🟨" if "Yellow" in detail else "🟥"
                msg_event = f"<b>CARTELLINO {emoji_card}</b>\n\nMinuto {ev_time}’: Ammonito {p_name} ({home if event['team']['id'] == fixture['teams']['home']['id'] else away})."
                requests.post(url_tg, data={"chat_id": CHAT_ID, "text": msg_event, "parse_mode": "HTML"})
                
            elif ev_type == "Subst":
                msg_event = f"<b>CAMBIO 🔄</b>\n\nMinuto {ev_time}’:\n🔼 Entra: {p_assist}\n🔽 Esce: {p_name}"
                requests.post(url_tg, data={"chat_id": CHAT_ID, "text": msg_event, "parse_mode": "HTML"})

            new_events.append(event_id)

    # Salviamo lo stato del test
    sent_events.extend(new_events)
    with open(STATE_FILE, "w") as f:
        json.dump(sent_events, f)
        
    print(f"Controllo eseguito. Punteggio attuale: {goals_home}-{goals_away}. Minuto: {elapsed}’")
