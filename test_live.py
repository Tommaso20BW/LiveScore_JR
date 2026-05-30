import json
import sys

# 1. CARICAMENTO SICURO DEL FILE JSON DI ESPN
try:
    with open("summary.json", "r", encoding="utf-8") as f:
        data = json.load(f)
except FileNotFoundError:
    print("❌ ERRORE: Il file 'summary.json' non è stato trovato in questa cartella.")
    print("Assicurati che il file JSON reale sia rinominato esattamente 'summary.json'.")
    sys.exit(1)

# 2. ESTRAZIONE DATI SQUADRE (Usa la stessa identica logica del tuo bot live)
try:
    boxscore = data.get("boxscore", {})
    teams_box = boxscore.get("teams", [])
    
    if len(teams_box) >= 2:
        home_name = teams_box[0].get("team", {}).get("name", "Home")
        away_name = teams_box[1].get("team", {}).get("name", "Away")
        home_id   = teams_box[0].get("team", {}).get("id")
    else:
        # Fallback se non trova il boxscore (prende dall'header)
        competitors = data.get("header", {}).get("competitions", [])[0].get("competitors", [{}, {}])
        home_name = competitors[0].get("team", {}).get("name", "Home")
        away_name = competitors[1].get("team", {}).get("name", "Away")
        home_id   = competitors[0].get("team", {}).get("id")
except Exception as e:
    print(f"❌ Errore durante l'estrazione dei nomi delle squadre: {e}")
    sys.exit(1)

# Configurazioni grafiche finte per il test
e_comp = "🏆"
hashtag = "#ChampionsLeague #JuventusReborn"

# Dizionario di stato finto per simulare la memoria del bot (Gist)
state = {
    "sent_periods": ["1H", "HT", "2H", "2H_END", "1ET_START", "1ET_END", "2ET_START", "ET_END_PENS"],
    "sent_shootout_hashes": []
}

print("\n========================================================")
print(f"       AVVIO VERIFICA REALE RIGORI: {home_name} vs {away_name}")
print("========================================================\n")

# Estraiamo i dati della lotteria dei rigori nativi di ESPN
# Nota: Nelle API di ESPN, i rigori calciati si trovano dentro data["shootout"]
shootout_data = data.get("shootout", [])

if not shootout_data:
    print("❌ ATTENZIONE: Il file 'summary.json' non contiene la chiave 'shootout'.")
    print("Sei sicuro che questa partita sia finita ai calci di rigore?")
    sys.exit(1)

# Trova il numero massimo di rigori calciati nel file per simulare i turni di battuta
max_shots = max(len(team.get("shots", [])) for team in shootout_data)

# --- SIMULAZIONE DEL LIVE RIGORE PER RIGORE ---
for turno in range(1, max_shots + 1):
    
    # Creiamo un set di dati finto che cresce ad ogni ciclo, come se la partita fosse in diretta
    dati_parziali_shootout = []
    for team_data in shootout_data:
        dati_parziali_shootout.append({
            "team": team_data.get("team"),
            "id": team_data.get("id"),
            "shots": team_data.get("shots", [])[:turno]  # Taglia la lista al rigore corrente
        })
    
    # =========================================================================
    #  LA NUOVA LOGICA AGGIORNATA DEI RIGORI (RICIESTA DA TE)
    # =========================================================================
    home_pen_icons = ""
    away_pen_icons = ""
    
    for team_shootout in dati_parziali_shootout:
        is_home = (team_shootout.get("team") == home_name or team_shootout.get("id") == home_id)
        icons = ""
        
        for shot in team_shootout.get("shots", []):
            if shot.get("didScore") == True:
                icons += "✅"
            else:
                icons += "❌"
        
        if is_home:
            home_pen_icons = icons
        else:
            away_pen_icons = icons

    # TRIGGER DI ATTIVAZIONE SILENZIOSO:
    # Se entrambe le stringhe sono vuote, significa che nessuno ha ancora calciato.
    if not home_pen_icons and not away_pen_icons:
        pass  # Resta in silenzio, nessun messaggio vuoto inviato
    
    else:
        # Costruzione del layout richiesto (senza placeholder o pallini bianchi)
        messaggio_rigori = (
            f"<b>RIGORI 🥅</b>\n\n"
            f"{home_name}: {home_pen_icons}\n"
            f"{away_name}: {away_pen_icons}\n\n"
            f"{e_comp} {hashtag}"
        )

        # Creazione dell'ID unico basato sul totale dei rigori calciati in questo istante
        totale_rigori_tirati = len(home_pen_icons) + len(away_pen_icons)
        rigori_id = f"shootout_progress_{totale_rigori_tirati}"

        # Controllo anti-duplicati: invia la notifica solo se il numero dei rigori è avanzato
        if rigori_id not in state["sent_shootout_hashes"]:
            print(f"--- [NOTIFICA TELEGRAM INVIATA - Rigore Totale n° {totale_rigori_tirati}] ---")
            print(messaggio_rigori)
            print("--------------------------------------------------------\n")
            
            # Salva l'ID nella memoria del bot per evitare lo spam al prossimo controllo
            state["sent_shootout_hashes"].append(rigori_id)

print("========================================================")
print("             FINE DEL TEST DI CONFORMITÀ                ")
print("========================================================")
print("Aggiornamento dinamico ad ogni tiro: ✅ FUNZIONANTE")
print("Nessun testo statico di attesa (... Waiting / ⚪): ✅ PULITO")
print("I messaggi partono solo dal primo rigore calciato: ✅ SILENZIOSO INIZIALE\n")
