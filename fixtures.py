import os
import requests
from datetime import datetime, timezone, timedelta

def vedi_calendario_juve_free_date():
    # Recupera la chiave dalle variabili d'ambiente (o incollala direttamente qui tra virgolette per fare un test al volo)
    api_key = os.getenv('API_KEY') or "LA_TUA_API_KEY_QUI"
    juve_id = 496

    if api_key == "LA_TUA_API_KEY_QUI" or not api_key:
        print("❌ Inserisci una API_KEY valida per testare lo script.")
        return

    url = "https://v3.football.api-sports.io/fixtures"
    headers = {"x-apisports-key": api_key}
    
    # Impostiamo il fuso orario italiano (Roma) per generare la data corretta di oggi
    fuso_italiano = timezone(timedelta(hours=2)) # UTC+2 nel periodo estivo/maggio
    today_date = datetime.now(fuso_italiano).strftime('%Y-%m-%d')

    # STRATEGIA PIANO FREE: Chiediamo tutti i match del giorno senza inserire parametri bloccati
    params = {
        "date": today_date
    }

    print(f"🔄 [Piano Free] Interrogazione palinsesto mondiale per la data di oggi: {today_date}...")
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        fixtures = data.get('response', [])
        
        if not fixtures:
            print(f"⚠️ Nessun match restituito dall'API per la data di oggi ({today_date}).")
            print(f"Risposta API: {data}")
            return

        # Cerchiamo la Juventus filtrando l'array direttamente in locale su Python
        match_juve = None
        for f in fixtures:
            home_id = f['teams']['home']['id']
            away_id = f['teams']['away']['id']
            if home_id == juve_id or away_id == juve_id:
                match_juve = f
                break

        if match_juve:
            print("\n🎯 PARTITA DELLA JUVENTUS TROVATA CON SUCCESSO!")
            print("-" * 60)
            
            match_id = match_juve['fixture']['id']
            stato = match_juve['fixture']['status']['short']
            
            # Converte l'orario ISO dell'API in orario italiano
            data_iso = match_juve['fixture']['date'].replace('Z', '+00:00')
            kickoff_utc = datetime.fromisoformat(data_iso)
            kickoff_ita = kickoff_utc.astimezone(fuso_italiano).strftime('%Y-%m-%d %H:%M')

            home_name = match_juve['teams']['home']['name']
            away_name = match_juve['teams']['away']['name']
            match_str = f"{home_name} vs {away_name}"

            if match_juve['goals']['home'] is not None and match_juve['goals']['away'] is not None:
                match_str += f" ({match_juve['goals']['home']}-{match_juve['goals']['away']})"

            print(f"🆔 FIXTURE ID : {match_id}")
            print(f"⏰ ORA ITALIANA: {kickoff_ita}")
            print(f"⚽ PARTITA    : {match_str}")
            print(f"📊 STATO      : {stato}")
            print("-" * 60)
            
            # Calcolo tempo residuo al fischio d'inizio
            now_utc = datetime.now(timezone.utc)
            minuti_mancanti = (kickoff_utc - now_utc).total_seconds() / 60
            if minuti_mancanti > 0:
                ore = int(minuti_mancanti // 60)
                minuti = int(minuti_mancanti % 60)
                print(f"⏳ Mancano ancora {ore} ore e {minuti} minuti al fischio d'inizio.")
            else:
                print(f"🏃‍♂️ Il match è in corso o è già terminato da {-int(minuti_mancanti)} minuti.")
        else:
            print(f"❌ La Juventus non gioca oggi ({today_date}) secondo il palinsesto dell'API.")
            print("💡 Nota: Se la partita si gioca domani o ieri (secondo il fuso del server), controlla i giorni adiacenti.")

    except Exception as e:
        print(f"❌ Errore durante la richiesta: {e}")

if __name__ == "__main__":
    vedi_calendario_juve_free_date()
