import os
import requests

BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')
API_KEY = os.getenv('API_KEY')

# Chiediamo all'API TUTTE le partite live nel mondo in questo istante
url_api = "https://v3.football.api-sports.io/fixtures?live=all"
headers = {"x-rapidapi-key": API_KEY, "x-rapidapi-host": "v3.football.api-sports.io"}

print("Recupero di tutte le partite live disponibili sul server...")
response = requests.get(url_api, headers=headers).json()

if not response.get("response"):
    print("In questo momento l'API non sta tracciando nessuna partita live nel suo database globale.")
else:
    # Prendiamo la prima partita live disponibile nell'elenco
    fixture = response["response"][0]
    status = fixture["fixture"]["status"]["short"]
    elapsed = fixture["fixture"]["status"]["elapsed"]
    home = fixture["teams"]["home"]["name"]
    away = fixture["teams"]["away"]["name"]
    goals_home = fixture["goals"]["home"]
    goals_away = fixture["goals"]["away"]
    league = fixture["league"]["name"]
    
    print(f"Match Trovato: {home} {goals_home} - {goals_away} {away} ({league})")
    
    msg = f"<b>TEST LIVE API GLOBALE ⚽️</b>\n\n🏆 Campionato: {league}\n🏟 Match: {home} - {away}\n📊 Punteggio: {goals_home} - {goals_away}\n⏱ Minuto: {elapsed}’ (Stato: {status})\n\nIl bot funziona! Connessione stabilita con successo."
    
    url_tg = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url_tg, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})
    print("-> Messaggio inviato su Telegram!")
