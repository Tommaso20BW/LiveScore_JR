import os
import requests
import json
import time

# ==============================================================================
# CONFIGURAZIONE CHIAVI E DATI REQUISITI (DA SECRETS GITHUB)
# ==============================================================================
API_KEY = os.getenv('API_KEY')
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')
JUVE_ID = 496

# ==============================================================================
# SET EMOJI CUSTOM FORMATTATE IN HTML TELEGRAM (BRANDING @Juventus_Reborn)
# ==============================================================================
E_BOLT = '<tg-emoji emoji-id="5778411071182217227">⚡️</tg-emoji>'
E_FLAG = '<tg-emoji emoji-id="5778434989855089204">🏁</tg-emoji>'
E_MIC  = '<tg-emoji emoji-id="5382013970905309819">🎙</tg-emoji>'
E_BALL = '<tg-emoji emoji-id="5373101763442255191">⚽️</tg-emoji>'
E_SUB  = '<tg-emoji emoji-id="5780817872070646566">🔄</tg-emoji>'
E_UP   = '<tg-emoji emoji-id="5449683594425410231">🔼</tg-emoji>'
E_DOWN = '<tg-emoji emoji-id="5447183459602669338">🔽</tg-emoji>'

# --- NUOVE EMOJI EVENTI SPECIALI AGGIORNATE ---
E_VAR    = '<tg-emoji emoji-id="5780478896071777414">📺</tg-emoji>'
E_YELLOW = '<tg-emoji emoji-id="5780818219962997856">🟨</tg-emoji>'
E_RED    = '<tg-emoji emoji-id="5778513149669940622">🟥</tg-emoji>'
E_SAVE   = '<tg-emoji emoji-id="5778268624296878374">🧤</tg-emoji>'

# Dizionario icone Competizioni automatiche
LEAGUE_EMOJIS = {
    135: '<tg-emoji emoji-id="5985546632219858247">🇮🇹</tg-emoji>', # Serie A
    137: '<tg-emoji emoji-id="5983047472354695060">🇮🇹</tg-emoji>', # Coppa Italia
    2:   '<tg-emoji emoji-id="6048563272855064239">🇪🇺</tg-emoji>', # Champions League
    3:   '<tg-emoji emoji-id="5850498991984218771">🇪🇺</tg-emoji>'  # Europa League
}

# Dizionario Master delle Squadre di Serie A
TEAM_EMOJIS = {
    496: '<tg-emoji emoji-id="6028591382870888482">⚪️</tg-emoji>', # Juventus
    499: '<tg-emoji emoji-id="5910979475905974750">🇮🇹</tg-emoji>', # Atalanta
    500: '<tg-emoji emoji-id="5911440952962061517">🇮🇹</tg-emoji>', # Bologna
    490: '<tg-emoji emoji-id="5913307249396158963">🇮🇹</tg-emoji>', # Cagliari
    895: '<tg-emoji emoji-id="5911329799208440998">🇮🇹</tg-emoji>', # Como
    520: '<tg-emoji emoji-id="5913404448801034977">🇮🇹</tg-emoji>', # Cremonese
    502: '<tg-emoji emoji-id="5913639563900752614">🇮🇹</tg-emoji>', # Fiorentina
    495: '<tg-emoji emoji-id="5911268059053560883">🇮🇹</tg-emoji>', # Genoa
    505: '<tg-emoji emoji-id="5911036032035329229">🇮🇹</tg-emoji>', # Inter
    487: '<tg-emoji emoji-id="5911295933391312208">🇮🇹</tg-emoji>', # Lazio
    867: '<tg-emoji emoji-id="5911196788366251729">🇮🇹</tg-emoji>', # Lecce
    489: '<tg-emoji emoji-id="5911391075506852997">🇮🇹</tg-emoji>', # Milan
    492: '<tg-emoji emoji-id="5785268171153872458">🇮🇹</tg-emoji>', # Napoli
    523: '<tg-emoji emoji-id="5913350542666503216">🇮🇹</tg-emoji>', # Parma
    801: '<tg-emoji emoji-id="5911205468495156874">🇮🇹</tg-emoji>', # Pisa
    497: '<tg-emoji emoji-id="5911111254092551875">🇮🇹</tg-emoji>', # Roma
    488: '<tg-emoji emoji-id="5911488085933169181">🇮🇹</tg-emoji>', # Sassuolo
    503: '<tg-emoji emoji-id="5911471790827247161">🇮🇹</tg-emoji>', # Torino
    494: '<tg-emoji emoji-id="5910997690862278694">🇮🇹</tg-emoji>', # Udinese
    504: '<tg-emoji emoji-id="5911515857191703670">🇮🇹</tg-emoji>', # Verona
    508: '<tg-emoji emoji-id="5911176739458912845">🇮🇹</tg-emoji>', # Bari
    515: '<tg-emoji emoji-id="5911075708943209811">🇮🇹</tg-emoji>', # Venezia
    511: '<tg-emoji emoji-id="5911181365138690645">🇮🇹</tg-emoji>'  # Frosinone
}

def get_emoji(team_id):
    return TEAM_EMOJIS.get(team_id, "⚽️")

def get_league_emoji(league_id):
    return LEAGUE_EMOJIS.get(league_id, "⚽️")

def clean_name(name):
    return "".join(e for e in name if e.isalnum())

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Errore invio Telegram: {e}")

def build_scorers_text(events):
    scorers = []
    for e in events:
        if e.get('type', '').lower() == 'goal':
            elapsed = e.get('time', {}).get('elapsed', '?')
            extra = e.get('time', {}).get('extra')
            minute_str = f"{elapsed}+{extra}" if extra else f"{elapsed}"
            
            player_name = e.get('player', {}).get('name', 'Giocatore')
            detail = e.get('detail', '').lower()
            
            if "penalty" in detail:
                player_name += " (Rig.)"
            elif "own goal" in detail:
                player_name += " (Autogol)"
                
            scorers.append(f"{minute_str}’ {player_name}")
    if scorers:
        return f"{E_BALL} <i>" + ", ".join(scorers) + "</i>\n"
    return ""

def main():
    print("⚪️⚫️ BOT LIVE AVVIATO - Monitoraggio continuo ogni 60 secondi...")
    
    # URL e parametri fissi dell'API
    url = "https://v3.football.api-sports.io/fixtures"
    headers = {"x-apisports-key": API_KEY}
    params = {"team": JUVE_ID, "live": "all"}

    while True:
        try:
            # Caricamento persistenza dello stato interno al ciclo
            if os.path.exists("match_state.json"):
                with open("match_state.json", "r") as f:
                    state = json.load(f)
            else:
                state = {"live_match_id": None, "sent_periods": [], "goals_detected": 0, "sent_subs": [], "sent_cards": []}

            if "sent_subs" not in state: state["sent_subs"] = []
            if "sent_cards" not in state: state["sent_cards"] = []

            # Chiamata HTTP
            res = requests.get(url, headers=headers, params=params).json()
            
            # Se la partita non è ancora iniziata o non è rilevata live
            if not res.get('response') or len(res['response']) == 0:
                print("In attesa che la partita della Juventus inizi o appaia nei feed Live...")
                time.sleep(60)
                continue

            match = res['response'][0]
            fixture = match.get('fixture', {})
            status = fixture.get('status', {}).get('short', 'NS')
            current_match_id = fixture.get('id')
            
            league_id = match.get('league', {}).get('id', 0)
            e_comp = get_league_emoji(league_id)
            
            teams = match.get('teams', {})
            home_id = teams.get('home', {}).get('id', 0)
            away_id = teams.get('away', {}).get('id', 0)
            home_name = teams.get('home', {}).get('name', 'Home')
            away_name = teams.get('away', {}).get('name', 'Away')
            
            home_emoji, away_emoji = get_emoji(home_id), get_emoji(away_id)
            
            goals_home = match.get('goals', {}).get('home')
            goals_away = match.get('goals', {}).get('away')
            
            g_home_int = goals_home if goals_home is not None else 0
            g_away_int = goals_away if goals_away is not None else 0
            total_goals_now = g_home_int + g_away_int
            
            h_name = "Juve" if home_id == JUVE_ID else clean_name(home_name)
            a_name = "Juve" if away_id == JUVE_ID else clean_name(away_name)
            hashtag = f"#{h_name}{a_name}"
            
            # Se è una nuova partita rispetto a quella salvata, resetta lo stato
            if state.get("live_match_id") != current_match_id:
                state = {"live_match_id": current_match_id, "sent_periods": [], "goals_detected": 0, "sent_subs": [], "sent_cards": []}

            print(f"[LIVE JUVE] {home_name} {g_home_int}-{g_away_int} {away_name} | Stato: {status}")

            # --------------------------------------------------------------------------
            # 1. BLOCCHI CRONACA PERIODI DI GARA
            # --------------------------------------------------------------------------
            if status == "1H" and "1H" not in state["sent_periods"]:
                msg = f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{home_emoji} {home_name} - {away_name} {away_emoji}\n\n{e_comp} {hashtag}"
                send_telegram(msg)
                state["sent_periods"].append("1H")

            elif status == "HT" and "HT" not in state["sent_periods"]:
                msg = f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{home_emoji} {home_name} {g_home_int}-{g_away_int} {away_name} {away_emoji}\n\n{e_comp} {hashtag}"
                send_telegram(msg)
                state["sent_periods"].append("HT")

            elif status == "2H" and "2H" not in state["sent_periods"]:
                msg = f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n{home_emoji} {home_name} {g_home_int}-{g_away_int} {away_name} {away_emoji}\n\n{e_comp} {hashtag}"
                send_telegram(msg)
                state["sent_periods"].append("2H")

            elif status in ["FT", "AET", "PEN"] and "FT" not in state["sent_periods"]:
                scorers_line = build_scorers_text(match.get('events', []))
                msg = f"<b>FINE PARTITA {E_FLAG}</b>\n\n{home_emoji} {home_name} {g_home_int}-{g_away_int} {away_name} {away_emoji}\n{scorers_line}\n{e_comp} {hashtag}"
                send_telegram(msg)
                state["sent_periods"].append("FT")
                
                # Salviamo un'ultima volta prima di distruggere la persistenza
                with open("match_state.json", "w") as f:
                    json.dump(state, f)
                
                # Rilevato il fischio finale: spezziamo il ciclo per spegnere l'Action di GitHub
                print("Partita terminata. Chiusura automatica del bot.")
                if os.path.exists("match_state.json"):
                    os.remove("match_state.json")
                break

            # --------------------------------------------------------------------------
            # 2. AVVISI GOL LIVE
            # --------------------------------------------------------------------------
            if status in ["1H", "2H", "ET"] and total_goals_now > state["goals_detected"]:
                scorers_line = build_scorers_text(match.get('events', []))
                msg = f"<b>GOAL {E_MIC}</b>\n\n{home_emoji} {home_name} {g_home_int}-{g_away_int} {away_name} {away_emoji}\n{scorers_line}\n{e_comp} {hashtag}"
                send_telegram(msg)
                state["goals_detected"] = total_goals_now

            # --------------------------------------------------------------------------
            # 3. GESTIONE EVENTI SPECIALI DA ELENCO (CAMBI E CARTELLINI)
            # --------------------------------------------------------------------------
            events = match.get('events', [])
            subs_by_minute = {}
            
            for e in events:
                ev_type = e.get('type', '').lower()
                minute = e.get('time', {}).get('elapsed', 0)
                
                # --- SOSTITUZIONI (Solo Juventus) ---
                if ev_type == 'subst' and e.get('team', {}).get('id') == JUVE_ID:
                    p_out = e.get('player', {}).get('name', 'Uscente')
                    p_in = e.get('assist', {}).get('name', 'Entrante')
                    sub_id = f"sub_{minute}_{p_out}_{p_in}".replace(" ", "_")
                    
                    if sub_id not in state["sent_subs"]:
                        if minute not in subs_by_minute:
                            subs_by_minute[minute] = {"in": [], "out": [], "ids": []}
                        subs_by_minute[minute]["in"].append(p_in)
                        subs_by_minute[minute]["out"].append(p_out)
                        subs_by_minute[minute]["ids"].append(sub_id)

                # --- CARTELLINI (SOLO ROSSI) ---
                elif ev_type == 'card':
                    p_name = e.get('player', {}).get('name', 'Giocatore')
                    card_detail = e.get('detail', '').lower()
                    card_id = f"card_{minute}_{p_name}_{card_detail}".replace(" ", "_")
                    
                    if card_id not in state["sent_cards"]:
                        team_name = e.get('team', {}).get('name', 'Squadra')
                        
                        # Filtrato per catturare solo i cartellini rossi (diretti o per doppia ammonizione)
                        if "red" in card_detail:
                            msg = f"<b>CARTELLINO ROSSO {E_RED}</b>\n\nEspulso {p_name} ({team_name}) al minuto {minute}’.\n\n{e_comp} {hashtag}"
                            send_telegram(msg)
                            state["sent_cards"].append(card_id)

            # Invio dei cambi raggruppati
            for min_key, sub_data in subs_by_minute.items():
                ins_text = ", ".join(sub_data["in"])
                outs_text = ", ".join(sub_data["out"])
                msg = f"<b>CAMBIO JUVENTUS {E_SUB}</b>\n\n{E_UP} {ins_text}\n{E_DOWN} {outs_text}\n\n{e_comp} {hashtag}"
                send_telegram(msg)
                state["sent_subs"].extend(sub_data["ids"])

            # Salva lo stato finale modificato su file locale JSON
            with open("match_state.json", "w") as f:
                json.dump(state, f)

        except Exception as e:
            print(f"Errore durante l'esecuzione del ciclo live: {e}")

        # Aspetta 90 secondi prima del prossimo controllo
        time.sleep(90)

if __name__ == "__main__":
    main()
