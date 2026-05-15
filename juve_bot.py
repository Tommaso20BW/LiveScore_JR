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
E_RED  = '<tg-emoji emoji-id="5778513149669940622">🟥</tg-emoji>'

# Dizionario icone Competizioni automatiche
LEAGUE_EMOJIS = {
    135: '<tg-emoji emoji-id="5985546632219858247">🇮🇹</tg-emoji>', # Serie A
    137: '<tg-emoji emoji-id="5983047472354695060">🇮🇹</tg-emoji>', # Coppa Italia
    2:   '<tg-emoji emoji-id="6048563272855064239">🇪🇺</tg-emoji>', # Champions League
    3:   '<tg-emoji emoji-id="5850498991984218771">🇪🇺</tg-emoji>', # Europa League
    667: '<tg-emoji emoji-id="5357080225463149588">🤝</tg-emoji>' # Amichevoli Club
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
    511: '<tg-emoji emoji-id="5911181365138690645">🇮🇹</tg-emoji>', # Frosinone
    551: '<tg-emoji emoji-id="5190496525863654450">🇨🇭</tg-emoji>',  # Basilea
    522: '<tg-emoji emoji-id="5911464631116765226">🇮🇹</tg-emoji>',  # Palermo
    49: '<tg-emoji emoji-id="6048407545930846973"></tg-emoji>',  # Chelsea
}

def get_emoji(team_id):
    return TEAM_EMOJIS.get(team_id, "⚽️")

def get_league_emoji(league_id):
    return LEAGUE_EMOJIS.get(league_id, "⚽️")

def clean_name(name):
    return "".join(e for e in name if e.isalnum())

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"Errore invio Telegram: {e}")

def build_split_scorers_text(events, home_id, away_id):
    home_scorers = []
    away_scorers = []
    
    for e in events:
        if e.get('type', '').lower() == 'goal':
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
    print("⚪️⚫️ BOT LIVE AVVIATO - Monitoraggio continuo...")
    
    url = "https://v3.football.api-sports.io/fixtures"
    headers = {"x-apisports-key": API_KEY}
    params = {"team": JUVE_ID, "live": "all"}

    while True:
        current_sleep_time = 90
        
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
                    "sent_failed_penalties": []
                }

            if "sent_subs" not in state: state["sent_subs"] = []
            if "sent_cards" not in state: state["sent_cards"] = []
            if "sent_failed_penalties" not in state: state["sent_failed_penalties"] = []

            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            res = response.json()
            
            if not res.get('response') or len(res['response']) == 0:
                print("In attesa che la partita della Juventus inizi o appaia nei feed Live...")
                time.sleep(60)
                continue

            match = res['response'][0]
            fixture = match.get('fixture', {})
            status = fixture.get('status', {}).get('short', 'NS')
            current_match_id = fixture.get('id')
            elapsed_minutes = fixture.get('status', {}).get('elapsed', 0)
            
            # Controllo sleep time per i supplementari o rigori
            if status in ["ET", "AET", "PEN"]:
                current_sleep_time = 140
            else:
                current_sleep_time = 90
            
            league_id = match.get('league', {}).get('id', 0)
            e_comp = get_league_emoji(league_id)
            
            teams = match.get('teams', {})
            home_id = teams.get('home', {}).get('id', 0)
            away_id = teams.get('away', {}).get('id', 0)
            home_name = teams.get('home', {}).get('name', 'Home')
            away_name = teams.get('away', {}).get('name', 'Away')
            
            home_emoji, away_emoji = get_emoji(home_id), get_emoji(away_id)
            
            # Punteggi regolamentari
            goals_home = match.get('goals', {}).get('home')
            goals_away = match.get('goals', {}).get('away')
            g_home_int = goals_home if goals_home is not None else 0
            g_away_int = goals_away if goals_away is not None else 0
            
            # Gestione Punteggio Rigori (Formato Simmetrico Elegante)
            penalties = match.get('score', {}).get('penalty', {})
            p_home = penalties.get('home')
            p_away = penalties.get('away')
            
            if p_home is not None and p_away is not None:
                score_string = f"{g_home_int} ({p_home}) - ({p_away}) {g_away_int}"
            else:
                score_string = f"{g_home_int}-{g_away_int}"
            
            h_name = "Juve" if home_id == JUVE_ID else clean_name(home_name)
            a_name = "Juve" if away_id == JUVE_ID else clean_name(away_name)
            hashtag = f"#{h_name}{a_name}"
            
            if state.get("live_match_id") != current_match_id:
                state = {
                    "live_match_id": current_match_id, 
                    "sent_periods": [], 
                    "goals_detected": 0, 
                    "sent_subs": [], 
                    "sent_cards": [],
                    "sent_failed_penalties": []
                }

            print(f"[LIVE JUVE] {home_name} {score_string} {away_name} | Stato: {status} | Minuto: {elapsed_minutes}")

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

            elif status in ["ET", "AET", "PEN"] and "2H_END" not in state["sent_periods"]:
                msg = f"<b>FINE SECONDO TEMPO {E_FLAG}</b>\n\n{home_emoji} {home_name} {g_home_int}-{g_away_int} {away_name} {away_emoji}\n\n{e_comp} {hashtag}"
                send_telegram(msg)
                state["sent_periods"].append("2H_END")

            # Gestione sdoppiata inizio Supplementari
            if status == "ET":
                if elapsed_minutes <= 105 and "1ET_START" not in state["sent_periods"]:
                    msg = f"<b>INIZIO PRIMO TEMPO SUPPLEMENTARE {E_BOLT}</b>\n\n{home_emoji} {home_name} {g_home_int}-{g_away_int} {away_name} {away_emoji}\n\n{e_comp} {hashtag}"
                    send_telegram(msg)
                    state["sent_periods"].append("1ET_START")
                elif elapsed_minutes > 105 and "2ET_START" not in state["sent_periods"]:
                    msg = f"<b>INIZIO SECONDO TEMPO SUPPLEMENTARE {E_BOLT}</b>\n\n{home_emoji} {home_name} {g_home_int}-{g_away_int} {away_name} {away_emoji}\n\n{e_comp} {hashtag}"
                    send_telegram(msg)
                    state["sent_periods"].append("2ET_START")

            # Controllo chiusura partita definitiva (90', 120' o Rigori completati)
            elif status in ["FT", "AET", "PEN"]:
                is_finished = fixture.get('status', {}).get('long') == "Match Finished" or status == "FT"
                if is_finished and "FT" not in state["sent_periods"]:
                    scorers_line = build_split_scorers_text(match.get('events', []), home_id, away_id)
                    msg = f"<b>FINE PARTITA {E_FLAG}</b>\n\n{home_emoji} {home_name} {score_string} {away_name} {away_emoji}\n{scorers_line}\n{e_comp} {hashtag}"
                    send_telegram(msg)
                    state["sent_periods"].append("FT")
                    
                    if os.path.exists("match_state.json"):
                        os.remove("match_state.json")
                    break

            # --------------------------------------------------------------------------
            # 2. AVVISI GOL LIVE E ANNULLAMENTO VAR
            # --------------------------------------------------------------------------
            total_goals_now = g_home_int + g_away_int
            if status in ["1H", "2H", "ET"]:
                if total_goals_now > state["goals_detected"]:
                    events = match.get('events', [])
                    live_scorer_line = ""
                    
                    for e in reversed(events):
                        if e.get('type', '').lower() == 'goal':
                            elapsed = e.get('time', {}).get('elapsed', '?')
                            extra = e.get('time', {}).get('extra')
                            minute_str = f"{elapsed}+{extra}" if extra else f"{elapsed}"
                            player_name = e.get('player', {}).get('name', 'Giocatore')
                            detail = e.get('detail', '').lower()
                            
                            if "penalty" in detail: player_name += " (Rig.)"
                            elif "own goal" in detail: player_name += " (Autogol)"
                            
                            live_scorer_line = f"{E_BALL} {minute_str}’ {player_name}\n"
                            break
                    
                    msg = f"<b>GOAL {E_MIC}</b>\n\n{home_emoji} {home_name} {g_home_int}-{g_away_int} {away_name} {away_emoji}\n{live_scorer_line}\n{e_comp} {hashtag}"
                    send_telegram(msg)
                    state["goals_detected"] = total_goals_now
                
                elif total_goals_now < state["goals_detected"]:
                    msg = f"<b>GOAL ANNULLATO <tg-emoji emoji-id='5780478896071777414'>📺</tg-emoji></b>\n\n{home_emoji} {home_name} {g_home_int}-{g_away_int} {away_name} {away_emoji}\n\n{e_comp} {hashtag}"
                    send_telegram(msg)
                    state["goals_detected"] = total_goals_now

            # --------------------------------------------------------------------------
            # 3. GESTIONE EVENTI SPECIALI DA ELENCO (CAMBI, CARTELLINI, RIGORI FALLITI)
            # --------------------------------------------------------------------------
            events = match.get('events', [])
            subs_by_minute = {}
            
            for e in events:
                ev_type = e.get('type', '').lower()
                detail = e.get('detail', '').lower()
                minute = e.get('time', {}).get('elapsed', 0)
                team_id = e.get('team', {}).get('id')
                
                if ev_type == 'subst' and team_id == JUVE_ID:
                    p_out = e.get('player', {}).get('name', 'Uscente')
                    p_in = e.get('assist', {}).get('name', 'Entrante')
                    sub_id = f"sub_{minute}_{p_out}_{p_in}".replace(" ", "_")
                    if sub_id not in state["sent_subs"]:
                        if minute not in subs_by_minute:
                            subs_by_minute[minute] = {"in": [], "out": [], "ids": []}
                        subs_by_minute[minute]["in"].append(p_in)
                        subs_by_minute[minute]["out"].append(p_out)
                        subs_by_minute[minute]["ids"].append(sub_id)

                elif ev_type == 'card':
                    p_name = e.get('player', {}).get('name', 'Giocatore')
                    card_detail = e.get('detail', '').lower()
                    card_id = f"card_{minute}_{p_name}_{card_detail}".replace(" ", "_")
                    
                    if card_id not in state["sent_cards"] and "red" in card_detail:
                        # Formato Richiesto per Cartellino Rosso
                        msg = f"<b>CARTELLINO ROSSO {E_RED}</b>\n\n🔚 <i>{minute}’ {p_name}</i>\n\n{e_comp} {hashtag}"
                        send_telegram(msg)
                        state["sent_cards"].append(card_id)

                if "penalty" in detail and ("missed" in detail or "saved" in detail):
                    p_name = e.get('player', {}).get('name', 'Giocatore')
                    pen_failed_id = f"pen_fail_{minute}_{p_name}".replace(" ", "_")
                    if pen_failed_id not in state["failed_penalties" if "failed_penalties" in state else "sent_failed_penalties"]:
                        has_scored_now = any(evt.get('type', '').lower() == 'goal' and evt.get('team', {}).get('id') == team_id and evt.get('time', {}).get('elapsed', 0) == minute for evt in events)
                        if has_scored_now: continue
                        if team_id == JUVE_ID:
                            msg = f"<b>RIGORE SBAGLIATO <tg-emoji emoji-id='5465665476971471368'>❌</tg-emoji></b>\n\n<tg-emoji emoji-id='5370881342659631698'>😢</tg-emoji> <i>{minute}' {p_name}</i>\n\n{e_comp} {hashtag}"
                        else:
                            msg = f"<b>RIGORE SBAGLIATO <tg-emoji emoji-id='5436040291507247633'>🎉</tg-emoji></b>\n\n<tg-emoji emoji-id='5373141891321699086'>😎</tg-emoji> <i>{minute}' {p_name}</i>\n\n{e_comp} {hashtag}"
                        send_telegram(msg)
                        state["sent_failed_penalties"].append(pen_failed_id)

            for min_key, sub_data in subs_by_minute.items():
                msg = f"<b>CAMBIO JUVENTUS {E_SUB}</b>\n\n{E_UP} {', '.join(sub_data['in'])}\n{E_DOWN} {', '.join(sub_data['out'])}\n\n{e_comp} {hashtag}"
                send_telegram(msg)
                state["sent_subs"].extend(sub_data["ids"])

            with open("match_state.json", "w") as f:
                json.dump(state, f)

        except Exception as e:
            print(f"Errore ciclo live: {e}")

        time.sleep(current_sleep_time)

if __name__ == "__main__":
    main()
