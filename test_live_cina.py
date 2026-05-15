import os
import requests

# Recupera i tuoi Secrets personali senza toccare nulla
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')
API_KEY = os.getenv('API_KEY')

# ID della squadra in campo ora
TEST_TEAM_ID = 1417 

url_api = f"https://v3.football.api-sports.io/fixtures?live=all&team={TEST_TEAM_ID}"
headers = {"x-rapidapi-key": API_KEY, "x-rapidapi-host": "v3.football.api-sports.io"}

print("Connessione in corso a API-Sports per recuperare il match live...")
response = requests.get(url_api, headers=headers).json()

if not response.get("response"):
    print("Nessun dato live restituito dalle API per questa squadra in questo momento.")
else:
    fixture = response["response"][0]
    status = fixture["fixture"]["status"]["short"]
    home = fixture["teams"]["home"]["name"]
    away = fixture["teams"]["away"]["name"]
    goals_home = fixture["goals"]["home"]
    goals_away = fixture["goals"]["away"]
    
    print(f"Match Rilevato: {home} {goals_home} - {goals_away} {away} (Stato: {status})")
    
    # Prepariamo un messaggio di test da inviare sul tuo canale Telegram
    msg = f"<b>TEST LIVE API-SPORTS ⚽️</b>\n\n🏟 Match: {home} - {away}\n📊 Punteggio: {goals_home} - {goals_away}\n⏱ Stato: {status}\n\nIl bot si sta collegando correttamente e legge i dati in tempo reale!"
    
    url_tg = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url_tg, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})
    print("-> Messaggio inviato con successo sul tuo canale Telegram!")
