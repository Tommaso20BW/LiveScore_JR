import os
import requests
from datetime import datetime, timezone, timedelta

def vedi_calendario_juve():
    # Recupera la chiave dalle variabili d'ambiente (o incollala direttamente qui tra virgolette per fare un test al volo)
    api_key = os.getenv('API_KEY') or "LA_TUA_API_KEY_QUI"
    juve_id = 496

    if api_key == "LA_TUA_API_KEY_QUI" or not api_key:
        print("❌ Inserisci una API_KEY valida per testare lo script.")
        return

    url = "https://v3.football.api-sports.io/fixtures"
    headers = {"x-apisports-key": api_key}
    
    # Chiediamo tutti i match della stagione (usiamo 2025 perché l'anno calcistico 25/26 è indicizzato come 2025)
    params = {
        "team": juve_id,
        "season": "2025"
    }

    print(f"🔄 Interrogazione API-Football per il Team ID {juve_id}...")
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        fixtures = data.get('response', [])
        
        if not fixtures:
            print("❌ Nessun match trovato. Controlla se la stagione o l'API Key sono corrette.")
            print(f"Risposta API: {data}")
            return

        print(f"\n🎯 Trovate {len(fixtures)} partite nel calendario. Ecco l'elenco:\n")
        print(f"{'ID FIXTURE':<12} | {'DATA E ORA (ITA)':<19} | {'PARTITA':<45} | {'STATO':<5}")
        print("-" * 90)

        # Configura il fuso orario italiano (UTC+2 per l'ora legale corrente di maggio)
        fuso_italiano = timezone(timedelta(hours=2))

        # Ordina le partite in base alla data d'inizio
        fixtures.sort(key=lambda x: x['fixture']['date'])

        for f in fixtures:
            match_id = f['fixture']['id']
            stato = f['fixture']['status']['short']
            
            # Converte la data ISO dell'API in datetime UTC e poi nel fuso italiano
            data_iso = f['fixture']['date'].replace('Z', '+00:00')
            kickoff_utc = datetime.fromisoformat(data_iso)
            kickoff_ita = kickoff_utc.astimezone(fuso_italiano).strftime('%Y-%m-%d %H:%M')

            home_name = f['teams']['home']['name']
            away_name = f['teams']['away']['name']
            match_str = f"{home_name} vs {away_name}"

            # Se la partita ha già un punteggio, mostralo di fianco
            if f['goals']['home'] is not None and f['goals']['away'] is not None:
                match_str += f" ({f['goals']['home']}-{f['goals']['away']})"

            print(f"{match_id:<12} | {kickoff_ita:<19} | {match_str:<45} | {stato:<5}")

    except Exception as e:
        print(f"❌ Errore durante la richiesta: {e}")

if __name__ == "__main__":
    vedi_calendario_juve()
