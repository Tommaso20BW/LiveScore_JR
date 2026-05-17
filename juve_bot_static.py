import os
import requests
import json
import time
import sys
from datetime import datetime

# ==============================================================================
# CONFIGURAZIONE CHIAVI E DATI REQUISITI (DA SECRETS GITHUB)
# ==============================================================================
API_KEY = os.getenv('API_KEY')
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')
JUVE_ID = 496

# ==============================================================================
# SET EMOJI STANDARD (BRANDING @Juventus_Reborn)
# ==============================================================================
E_BOLT = '⚡️'
E_FLAG = '🏁'
E_MIC = '🎙'
E_BALL = '⚽️'
E_SUB = '🔄'
E_UP = '🔼'
E_DOWN = '🔽'
E_RED = '🟥'

# Emoji specifiche per la lotteria dei rigori
E_PEN_OK = '✅'
E_PEN_KO = '❌'

# Dizionario icone Competizioni automatiche
LEAGUE_EMOJIS = {
    135: '🇮🇹', # Serie A
    137: '🇮🇹', # Coppa Italia
    2:   '🇪🇺', # Champions League
    3:   '🇪🇺', # Europa League
    667: '🤝'  # Amichevoli Club
}

def get_league_emoji(league_id):
    return LEAGUE_EMOJIS.get(league_id, "⚽️")

def clean_name(name):
    annoying_words = ["AC ", "AS ", " US", " FC", "FC ", "A.C. ", "A.S. "]
    for word in annoying_words:
        name = name.replace(word, "")
        name = name.replace(word.strip(), "")
    return " ".join(name.split())

def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("Errore: BOT_TOKEN o CHAT_ID non configurati correttamente.")
        return
        
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            print(f"Telegram API Error (Status {response.status_code}): {response.text}")
        response.raise_for_status()
    except Exception as e:
        print(f"Errore invio Telegram: {e}")

def build_split_scorers_text(events, home_id, away_id):
    if not events: return ""
    home_scorers = []
    away_scorers = []
    
    for e in events:
        if e.get('type', '').lower() == 'goal' and "shootout" not in e.get('detail', '').lower():
            elapsed = e.get('time', {}).get('elapsed', '?')
            extra = e.get('time', {}).get('extra')
            minute_str = f"{elapsed}+{extra}" if extra else f"{elapsed}"
            
            player_name = e.get('player', {}).get('name', 'Giocatore')
            detail = e.get('detail', '').lower()
            event_team_id = e.get('team', {}).get('id')
            
            if "penalty" in detail:
                player_name += " (Rig.)"
            elif "own goal" in detail:
                player_name += " (Autogol)"
            
            scorer_entry = f"{minute_str}’ {player_name}"
            
            if event_team_id == home_id:
                home_scorers.append(scorer_entry)
            elif event_team_id == away_id:
                away_scorers.append(scorer_entry)
                
    if home_scorers and away_scorers:
        return f"{E_BALL} <i>" + ", ".join(home_scorers) + " // " + ", ".join(away_scorers) + "</i>\n"
    elif home_scorers:
        return f"{E_BALL} <i>" + ", ".join(home_scorers) + "</i>\n"
    elif away_scorers:
        return f"{E_BALL} <i>" + ", ".join(away_scorers) + "</i>\n"
        
    return ""

def main():
    print("BOT LIVE AVVIATO - Monitoraggio continuo...")
    
    url = "https://v3.football.api-sports.io/fixtures"
    if not API_KEY:
        print("Errore: API_KEY mancante nelle variabili d'ambiente.")
        return
        
    headers = {"x-apisports-key": API_KEY}
    today_date = datetime.now().strftime('%Y-%m-%d')
    params = {"team": JUVE_ID, "date": today_date}

    while True:
        try:
            if os.path.exists("match_state.json"):
                with open("match_state.json", "r") as f:
                    state = json.load(f)
            else:
                state = {
                    "live_match_id": None, 
                    "sent_periods": [], 
                    "goals_detected": 0, 
                    "sent_subs": [], 
                    "sent_cards": [],
                    "sent_failed_penalties": [],
                    "penalties_count": 0  
                }

            if "sent_subs" not in state: state["sent_subs"] = []
            if "sent_cards" not in state: state["sent_cards"] = []
            if "sent_failed_penalties" not in state: state["sent_failed_penalties"] = []
            if "penalties_count" not in state: state["penalties_count"] = 0

            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            res = response.json()
            
            # Se la partita non è ancora inserita nei palinsesti odierni dell'API, ricontrolla ogni 30 secondi
            if not res.get('response') or len(res['response']) == 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] In attesa della partita della Juventus ({today_date}). Prossimo controllo tra 30s...")
                time.sleep(30)
                continue

            match = res['response'][0]
            fixture = match.get('fixture', {})
            status = fixture.get('status', {}).get('short', 'NS')
            current_match_id = fixture.get('id')
            elapsed_minutes = fixture.get('status', {}).get('elapsed', 0)
            
            goals_home = match.get('goals', {}).get('home')
            goals_away = match.get('goals', {}).get('away')
            g_home_int = goals_home if goals_home is not None else 0
            g_away_int = goals_away if goals_away is not None else 0

            # MODIFICA AGGIORNAMENTO: Se non è iniziata, aggiorna ogni 30 secondi
            if status in ["NS", "TBD"]:
                if g_home_int == 0 and g_away_int == 0 and elapsed_minutes == 0:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Partita non ancora iniziata (Stato: {status}). Aggiornamento tra 30s...")
                    time.sleep(30)
                    continue
                
            # Tempi di attesa dinamici a partita INIZIATA
            if status == "PEN":
                current_sleep_time = 30   
            elif status in ["ET", "AET"]:
                current_sleep_time = 45  
            else:
                current_sleep_time = 60   
            
            league_id = match.get('league', {}).get('id', 0)
            e_comp = get_league_emoji(league_id)
            
            teams = match.get('teams', {})
            home_id = teams.get('home', {}).get('id', 0)
            away_id = teams.get('away', {}).get('id', 0)
            
            home_name = "Juventus" if home_id == JUVE_ID else clean_name(teams.get('home', {}).get('name', 'Home'))
            away_name = "Juventus" if away_id == JUVE_ID else clean_name(teams.get('away', {}).get('name', 'Away'))
            
            penalties = match.get('score', {}).get('penalty', {})
            p_home = penalties.get('home')
            p_away = penalties.get('away')
            
            if p_home is not None and p_away is not None:
                score_string = f"{g_home_int} ({p_home}) - ({p_away}) {g_away_int}"
            else:
                score_string = f"{g_home_int}-{g_away_int}"
            
            h_short = "Juve" if home_id == JUVE_ID else home_name.replace(" ", "")
            a_short = "Juve" if away_id == JUVE_ID else away_name.replace(" ", "")
            hashtag = f"#{h_short}{a_short}"
            
            if state.get("live_match_id") != current_match_id:
                state = {
                    "live_match_id": current_match_id, 
                    "sent_periods": [], 
                    "goals_detected": 0, 
                    "sent_subs": [], 
                    "sent_cards": [],
                    "sent_failed_penalties": [],
                    "penalties_count": 0
                }

            print(f"[LIVE] {home_name} {score_string} {away_name} | Stato: {status} | Minuto: {elapsed_minutes}")

            # --------------------------------------------------------------------------
            # 1. BLOCCHI CRONACA PERIODI DI GARA
            # --------------------------------------------------------------------------
            if (status == "1H" or elapsed_minutes > 0) and "1H" not in state["sent_periods"]:
                msg = f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{home_name} - {away_name}\n\n{e_comp} {hashtag}"
                send_telegram(msg)
                state["sent_periods"].append("1H")

            elif status == "HT" and "HT" not in state["sent_periods"]:
                msg = f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{home_name} {g_home_int}-{g_away_int} {away_name}\n\n{e_comp} {hashtag}"
                send_telegram(msg)
                state["sent_periods"].append("HT")

            elif status == "2H" and "2H" not in state["sent_periods"]:
                msg = f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n{home_name} {g_home_int}-{g_away_int} {away_name}\n\n{e_comp} {hashtag}"
                send_telegram(msg)
                state["sent_periods"].append("2H")

            elif status in ["ET", "AET", "PEN"] and "2H_END" not in state["sent_periods"]:
                msg = f"<b>FINE SECONDO TEMPO {E_FLAG}</b>\n\n{home_name} {g_home_int}-{g_away_int} {away_name}\n\n{e_comp} {hashtag}"
                send_telegram(msg)
                state["sent_periods"].append("2H_END")

            if status == "ET":
                if elapsed_minutes <= 105 and "1ET_START" not in state["sent_periods"]:
                    msg = f"<b>INIZIO PRIMO TEMPO SUPPLEMENTARE {E_BOLT}</b>\n\n{home_name} {g_home_int}-{g_away_int} {away_name}\n\n{e_comp} {hashtag}"
                    send_telegram(msg)
                    state["sent_periods"].append("1ET_START")
                elif elapsed_minutes > 105 and "2ET_START" not in state["sent_periods"]:
                    msg = f"<b>INIZIO SECONDO TEMPO SUPPLEMENTARE {E_BOLT}</b>\n\n{home_name} {g_home_int}-{g_away_int} {away_name}\n\n{e_comp} {hashtag}"
                    send_telegram(msg)
                    state["sent_periods"].append("2ET_START")

            # ==============================================================================
            # GESTIONE LOTTERIA DEI RIGORI COLPO SU COLPO
            # ==============================================================================
            if status == "PEN":
                events = match.get('events', [])
                home_pen_icons = []
                away_pen_icons = []
                
                for e in events:
                    detail = e.get('detail', '').lower()
                    ev_type = e.get('type', '').lower()
                    
                    if "shootout" in detail or (ev_type == "goal" and elapsed_minutes >= 120 and "penalty" in detail):
                        ev_team_id = e.get('team', {}).get('id')
                        is_missed = "missed" in detail or "saved" in detail or ev_type == "card"
                        icon = E_PEN_KO if is_missed else E_PEN_OK
                        
                        if ev_team_id == home_id:
                            home_pen_icons.append(icon)
                        elif ev_team_id == away_id:
                            away_pen_icons.append(icon)
                
                total_kicks_now = len(home_pen_icons) + len(away_pen_icons)
                
                if total_kicks_now > state["penalties_count"]:
                    home_line = f"{home_name}: " + "".join(home_pen_icons)
                    away_line = f"{away_name}: " + "".join(away_pen_icons)
                    
                    msg_single_penalty = f"{home_line}\n{away_line}\n\n{e_comp} {hashtag}"
                    send_telegram(msg_single_penalty)
                    state["penalties_count"] = total_kicks_now

            # ==============================================================================
            # SPEGNIMENTO AUTOMATICO A FINE PARTITA
            # ==============================================================================
            status_long = fixture.get('status', {}).get('long', '').lower()
            is_finished = status in ["FT", "AET", "PEN"] and ("finished" in status_long or "match finished" in status_long)
            
            if is_finished and "FT" not in state["sent_periods"]:
                scorers_line = build_split_scorers_text(match.get('events', []), home_id, away_id)
                msg = f"<b>FINE PARTITA {E_FLAG}</b>\n\n{home_name} {score_string} {away_name}\n{scorers_line}\n{e_comp} {hashtag}"
                send_telegram(msg)
                state["sent_periods"].append("FT")
                
                with open("match_state.json", "w") as f:
                    json.dump(state, f)
                
                if os.path.exists("match_state.json"):
                    os.remove("match_state.json")
                    
                print("🏁 Partita terminata con successo. Chiusura del processo bot in corso...")
                sys.exit(0)

            # --------------------------------------------------------------------------
            # 2. AVVISI GOL LIVE E ANNULLAMENTO VAR
            # --------------------------------------------------------------------------
            total_goals_now = g_home_int + g_away_int
            if status in ["1H", "2H", "ET"] or elapsed_minutes > 0:
                if total_goals_now > state["goals_detected"]:
                    events = match.get('events', [])
                    live_scorer_line = ""
                    
                    if events:
                        for e in reversed(events):
                            if e.get('type', '').lower() == 'goal':
                                elapsed = e.get('time', {}).get('elapsed', '?')
                                extra = e.get('time', {}).get('extra')
                                minute_str = f"{elapsed}+{extra}" if extra else f"{elapsed}"
                                player_name = e.get('player', {}).get('name', 'Giocatore')
                                detail = e.get('detail', '').lower()
                                
                                if "penalty" in detail: player_name += " (Rig.)"
                                elif "own goal" in detail: player_name += " (Autogol)"
                                
                                live_scorer_line = f"{E_BALL} <i>{minute_str}’ {player_name}</i>\n"
                                break
                    
                    msg = f"<b>GOAL {E_MIC}</b>\n\n{home_name} {g_home_int}-{g_away_int} {away_name}\n{live_scorer_line}\n{e_comp} {hashtag}"
                    send_telegram(msg)
                    state["goals_detected"] = total_goals_now
                
                elif total_goals_now < state["goals_detected"]:
                    msg = f"<b>GOAL ANNULLATO 📺</b>\n\n{home_name} {g_home_int}-{g_away_int} {away_name}\n\n{e_comp} {hashtag}"
                    send_telegram(msg)
                    state["goals_detected"] = total_goals_now

            # --------------------------------------------------------------------------
            # 3. GESTIONE EVENTI SPECIALI DA ELENCO (CAMBI, CARTELLINI, RIGORI FALLITI)
            # --------------------------------------------------------------------------
            events = match.get('events', [])
            if events:
                subs_by_minute = {}
                
                for e in events:
                    ev_type = e.get('type', '').lower()
                    detail = e.get('detail', '').lower()
                    minute = e.get('time', {}).get('elapsed', 0)
                    team_id = e.get('team', {}).get('id')
                    
                    if ev_type == 'subst':
                        p_out = e.get('player', {}).get('name', 'Uscente')
                        p_in = e.get('assist', {}).get('name', 'Entrante')
                        sub_id = f"sub_{minute}_{p_out}_{p_in}".replace(" ", "_")
                        if sub_id not in state["sent_subs"]:
                            sub_key = f"{minute}_{team_id}"
                            if sub_key not in subs_by_minute:
                                subs_by_minute[sub_key] = {"minute": minute, "team_id": team_id, "in": [], "out": [], "ids": []}
                            subs_by_minute[sub_key]["in"].append(p_in)
                            subs_by_minute[sub_key]["out"].append(p_out)
                            subs_by_minute[sub_key]["ids"].append(sub_id)

                    elif ev_type == 'card':
                        p_name = e.get('player', {}).get('name', 'Giocatore')
                        card_detail = e.get('detail', '').lower()
                        card_id = f"card_{minute}_{p_name}_{card_detail}".replace(" ", "_")
                        
                        if card_id not in state["sent_cards"] and "red" in card_detail:
                            msg = f"<b>CARTELLINO ROSSO {E_RED}</b>\n\n🔚 <i>{minute}’ {p_name}</i>\n\n{e_comp} {hashtag}"
                            send_telegram(msg)
                            state["sent_cards"].append(card_id)

                    if "penalty" in detail and ("missed" in detail or "saved" in detail) and "shootout" not in detail and elapsed_minutes < 120:
                        p_name = e.get('player', {}).get('name', 'Giocatore')
                        pen_failed_id = f"pen_fail_{minute}_{p_name}".replace(" ", "_")
                        if pen_failed_id not in state["sent_failed_penalties"]:
                            has_scored_now = any(evt.get('type', '').lower() == 'goal' and evt.get('team', {}).get('id') == team_id and evt.get('time', {}).get('elapsed', 0) == minute for evt in events)
                            if has_scored_now: continue
                            if team_id == JUVE_ID:
                                msg = f"<b>RIGORE SBAGLIATO ❌</b>\n\n😢 <i>{minute}' {p_name}</i>\n\n{e_comp} {hashtag}"
                            else:
                                msg = f"<b>RIGORE SBAGLIATO 🎉</b>\n\n😎 <i>{minute}' {p_name}</i>\n\n{e_comp} {hashtag}"
                            send_telegram(msg)
                            state["sent_failed_penalties"].append(pen_failed_id)

                for sub_key, sub_data in subs_by_minute.items():
                    t_id = sub_data["team_id"]
                    if t_id == JUVE_ID:
                        team_title = "JUVENTUS"
                    else:
                        team_title = home_name.upper() if t_id == home_id else away_name.upper()
                    
                    msg = f"<b>CAMBIO {team_title} {E_SUB}</b>\n\n{E_UP} {', '.join(sub_data['in'])}\n{E_DOWN} {', '.join(sub_data['out'])}\n\n{e_comp} {hashtag}"
                    send_telegram(msg)
                    state["sent_subs"].extend(sub_data["ids"])

            with open("match_state.json", "w") as f:
                json.dump(state, f)

        except Exception as e:
            print(f"Errore ciclo live: {e}")
            current_sleep_time = 30  

        time.sleep(current_sleep_time)

if __name__ == "__main__":
    main()
