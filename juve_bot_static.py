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
CLIENT_ID = os.getenv('CANVA_CLIENT_ID')
CLIENT_SECRET = os.getenv('CANVA_CLIENT_SECRET')
JUVE_ID = 496

# Configurazione del tuo design specifico Canva
CANVA_DESIGN_ID = "DAHI3ytu6yQ"
PAGINA_TARGET = 11
TOKEN_FILE = "canva_tokens.json"

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
E_PEN_OK = '✅'
E_PEN_KO = '❌'

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
        print("Errore: BOT_TOKEN o CHAT_ID non configurati.")
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

def send_telegram_with_photo(text, photo_bytes):
    """Invia il post completo di Fine Partita (Foto Canva + Testo) su Telegram."""
    if not photo_bytes:
        print("⚠️ Immagine Canva mancante o in timeout. Ripiego sull'invio del solo testo...")
        send_telegram(text)
        return

    print("📤 Spedisco il post con grafica Canva su Telegram...")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    payload = {"chat_id": CHAT_ID, "caption": text, "parse_mode": "HTML"}
    files = {"photo": ("matchday.png", photo_bytes)}
    
    try:
        res = requests.post(url, data=payload, files=files, timeout=25)
        if res.status_code == 200:
            print("🏁 Grafica fine partita pubblicata con successo su Telegram!")
        else:
            print(f"❌ Errore invio foto Telegram: {res.text}. Provo invio solo testo...")
            send_telegram(text)
    except Exception as e:
        print(f"Errore durante l'invio della foto a Telegram: {e}")
        send_telegram(text)

# ==============================================================================
# FUNZIONI INTEGRATE CANVA API
# ==============================================================================
def get_valid_token():
    """Recupera il token dal file JSON e lo rinnova automaticamente se scaduto."""
    if not os.path.exists(TOKEN_FILE):
        print(f"❌ Errore: Manca il file {TOKEN_FILE} nella repository.")
        return None

    with open(TOKEN_FILE, "r") as f:
        tokens = json.load(f)

    if tokens.get("expires_at", 0) - time.time() < 300:
        print("🔄 Token Canva scaduto. Tento il rinnovo automatico tramite Refresh Token...")
        url = "https://api.canva.com/rest/v1/oauth/token"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET
        }
        
        try:
            res = requests.post(url, data=payload, timeout=15)
            if res.status_code == 200:
                new_tokens = res.json()
                tokens["access_token"] = new_tokens["access_token"]
                tokens["refresh_token"] = new_tokens.get("refresh_token", tokens["refresh_token"])
                tokens["expires_at"] = int(time.time()) + new_tokens["expires_in"]
                
                with open(TOKEN_FILE, "w") as f:
                    json.dump(tokens, f, indent=2)
                print("✅ Token rinnovato con successo dal Bot!")
            else:
                print(f"❌ Errore nel rinnovo automatico: {res.text}")
                return None
        except Exception as e:
            print(f"Errore connessione rinnovo token Canva: {e}")
            return None

    return tokens["access_token"]

def get_canva_image(access_token):
    """Avvia il Job di esportazione su Canva e scarica il file PNG risultante."""
    if not access_token:
        return None

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    start_url = "https://api.canva.com/rest/v1/exports"
    payload = {
        "design_id": CANVA_DESIGN_ID,
        "format": {"type": "png", "pages": [PAGINA_TARGET]}
    }

    try:
        print("🎨 Richiesta generazione immagine a Canva...")
        response = requests.post(start_url, headers=headers, json=payload, timeout=15)
        if response.status_code not in [200, 201]:
            print(f"❌ Errore avvio export Canva: {response.text}")
            return None
        
        job_data = response.json()
        job_id = job_data.get("id") or job_data.get("job", {}).get("id")
        
        if not job_id:
            print(f"❌ Impossibile trovare il Job ID nella risposta di Canva.")
            return None
        
        status_url = f"https://api.canva.com/rest/v1/exports/{job_id}"
        print("⏳ Attesa rendering della grafica su Canva...")
        for i in range(40):
            time.sleep(4)
            check_res = requests.get(status_url, headers=headers, timeout=15)
            if check_res.status_code == 200:
                status_data = check_res.json()
                
                status_corrente = status_data.get("status") or status_data.get("job", {}).get("status")
                print(f"   [Controllo {i+1}/40] Stato Canva: {status_corrente}")
                
                if status_corrente == "success":
                    urls_list = status_data.get("urls") or status_data.get("job", {}).get("urls")
                    download_url = None
                    
                    if urls_list and len(urls_list) > 0:
                        download_url = urls_list[0]
                    else:
                        download_url = status_data.get("url") or status_data.get("job", {}).get("url")
                    
                    if download_url:
                        print("📥 Download file PNG da Canva completato.")
                        img_res = requests.get(download_url, timeout=20)
                        return img_res.content
                    else:
                        print(f"❌ Stato 'success' ma nessun URL trovato nel JSON.")
                        return None
                        
                elif status_corrente == "failed":
                    print(f"❌ Il rendering di Canva è fallito.")
                    return None
                    
        print("❌ Timeout: Canva ha impiegato troppo tempo per generare l'immagine.")
    except Exception as e:
        print(f"❌ Errore durante il recupero da Canva: {e}")
    return None

# ==============================================================================

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
            
            if "penalty" in detail: player_name += " (Rig.)"
            elif "own goal" in detail: player_name += " (Autogol)"
            
            scorer_entry = f"{minute_str}’ {player_name}"
            
            if event_team_id == home_id: home_scorers.append(scorer_entry)
            elif event_team_id == away_id: away_scorers.append(scorer_entry)
                
    if home_scorers and away_scorers:
        return f"{E_BALL} <i>" + ", ".join(home_scorers) + " // " + ", ".join(away_scorers) + "</i>\n"
    elif home_scorers:
        return f"{E_BALL} <i>" + ", ".join(home_scorers) + "</i>\n"
    elif away_scorers:
        return f"{E_BALL} <i>" + ", ".join(away_scorers) + "</i>\n"
    return ""

def format_match_text(home_name, away_name, g_home, g_away, p_home=None, p_away=None):
    """Formatta i nomi delle squadre e il punteggio applicando il grassetto a chi è in vantaggio."""
    c_home_name = home_name
    c_away_name = away_name
    g_home_str = str(g_home)
    g_away_str = str(g_away)

    if g_home > g_away:
        c_home_name = f"<b>{home_name}</b>"
        g_home_str = f"<b>{g_home}</b>"
    elif g_away > g_home:
        c_away_name = f"<b>{away_name}</b>"
        g_away_str = f"<b>{g_away}</b>"

    if p_home is not None and p_away is not None:
        # Gestione dei calci di rigore se presenti nel punteggio stringa
        if p_home > p_away:
            return f"{c_home_name} <b>{g_home_str} ({p_home})</b> - ({p_away}) {g_away_str} {c_away_name}"
        elif p_away > p_home:
            return f"{c_home_name} {g_home_str} ({p_home}) - <b>({p_away}) {g_away_str}</b> {c_away_name}"
        else:
            return f"{c_home_name} {g_home_str} ({p_home}) - ({p_away}) {g_away_str} {c_away_name}"
    else:
        return f"{c_home_name} {g_home_str}-{g_away_str} {c_away_name}"

def main():
    print("BOT LIVE AVVIATO - Recupero ID Partita...")
    
    url = "https://v3.football.api-sports.io/fixtures"
    if not API_KEY:
        print("Errore: API_KEY mancante.")
        return
        
    headers = {"x-apisports-key": API_KEY}
    today_date = datetime.now().strftime('%Y-%m-%d')
    
    match_id = None
    
    try:
        live_res = requests.get(f"{url}?live=all", headers=headers, timeout=10).json()
        if live_res.get('response'):
            for f in live_res['response']:
                if f['teams']['home']['id'] == JUVE_ID or f['teams']['away']['id'] == JUVE_ID:
                    match_id = f['fixture']['id']
                    print(f"🔥 Juve trovata LIVE! Aggancio ID Fixture: {match_id}")
                    break
    except Exception as e:
        print(f"Nota: Controllo live rapido fallito, procedo con data odierna ({e})")

    if not match_id:
        try:
            date_res = requests.get(f"{url}?team={JUVE_ID}&date={today_date}", headers=headers, timeout=10).json()
            if date_res.get('response') and len(date_res['response']) > 0:
                match_id = date_res['response'][0]['fixture']['id']
                print(f"📅 Partita trovata nel palinsesto di oggi. ID Fixture bloccato: {match_id}")
            else:
                print(f"❌ Nessuna partita della Juventus trovata per oggi ({today_date}). Bot spento.")
                sys.exit(0)
        except Exception as e:
            print(f"Errore critico nel recupero della partita per data: {e}")
            sys.exit(1)

    params = {"id": match_id}

    while True:
        try:
            if os.path.exists("match_state.json"):
                with open("match_state.json", "r") as f: state = json.load(f)
            else:
                state = {
                    "live_match_id": match_id, "sent_periods": [], "goals_detected": 0,
                    "sent_subs": [], "sent_cards": [], "sent_failed_penalties": [], "penalties_count": 0
                }

            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            res = response.json()
            
            if not res.get('response') or len(res['response']) == 0:
                print("Dati partita temporaneamente non disponibili...")
                time.sleep(30)
                continue

            match = res['response'][0]
            fixture = match.get('fixture', {})
            status = fixture.get('status', {}).get('short', 'NS')
            elapsed_minutes = fixture.get('status', {}).get('elapsed', 0)
            
            goals_home = match.get('goals', {}).get('home')
            goals_away = match.get('goals', {}).get('away')
            g_home_int = goals_home if goals_home is not None else 0
            g_away_int = goals_away if goals_away is not None else 0

            if status in ["NS", "TBD"] and g_home_int == 0 and g_away_int == 0 and elapsed_minutes == 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] In attesa del fischio d'inizio (Stato: {status}). Controllo tra 30s...")
                time.sleep(30)
                continue
                
            league_id = match.get('league', {}).get('id', 0)

            if status == "PEN":
                current_sleep_time = 60
            elif status in ["ET", "AET"]:
                current_sleep_time = 140
            elif status == "HT":
                current_sleep_time = 120
            else:
                current_sleep_time = 70 if league_id == 135 else 90
            
            e_comp = get_league_emoji(league_id)
            
            teams = match.get('teams', {})
            home_id = teams.get('home', {}).get('id', 0)
            away_id = teams.get('away', {}).get('id', 0)
            
            home_name = "Juventus" if home_id == JUVE_ID else clean_name(teams.get('home', {}).get('name', 'Home'))
            away_name = "Juventus" if away_id == JUVE_ID else clean_name(teams.get('away', {}).get('name', 'Away'))
            
            penalties = match.get('score', {}).get('penalty', {})
            p_home, p_away = penalties.get('home'), penalties.get('away')
            score_string = f"{g_home_int} ({p_home}) - ({p_away}) {g_away_int}" if p_home is not None else f"{g_home_int}-{g_away_int}"
            
            h_short = "Juve" if home_id == JUVE_ID else home_name.replace(" ", "")
            a_short = "Juve" if away_id == JUVE_ID else away_name.replace(" ", "")
            hashtag = f"#{h_short}{a_short}"
            
            print(f"[LIVE] {home_name} {score_string} {away_name} | Stato: {status} | Minuto: {elapsed_minutes} | Prossimo controllo tra {current_sleep_time}s")

            # Stringa accoppiata squadra+risultato formattata con vantaggio dinamico per la cronaca periodi
            match_status_line = format_match_text(home_name, away_name, g_home_int, g_away_int)

            # 1. CRONACA PERIODI
            if (status == "1H" or elapsed_minutes > 0) and "1H" not in state["sent_periods"]:
                msg = f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{home_name} - {away_name}\n\n{e_comp} {hashtag}"
                send_telegram(msg)
                state["sent_periods"].append("1H")

            elif status == "HT" and "HT" not in state["sent_periods"]:
                msg = f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{match_status_line}\n\n{e_comp} {hashtag}"
                send_telegram(msg)
                state["sent_periods"].append("HT")

            elif status == "2H" and "2H" not in state["sent_periods"]:
                # Caso in cui inizia il secondo tempo regolare
                msg = f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n{match_status_line}\n\n{e_comp} {hashtag}"
                send_telegram(msg)
                state["sent_periods"].append("2H")

            elif status == "ET" and elapsed_minutes <= 105 and "1ET_START" not in state["sent_periods"]:
                msg = f"<b>INIZIO PRIMO TEMPO SUPPLEMENTARE {E_BOLT}</b>\n\n{match_status_line}\n\n{e_comp} {hashtag}"
                send_telegram(msg)
                state["sent_periods"].append("1ET_START")

            elif status == "ET" and elapsed_minutes > 105 and "1ET_END" not in state["sent_periods"]:
                msg = f"<b>FINE PRIMO TEMPO SUPPLEMENTARE {E_FLAG}</b>\n\n{match_status_line}\n\n{e_comp} {hashtag}"
                send_telegram(msg)
                state["sent_periods"].append("1ET_END")

            elif status == "ET" and "2ET_START" not in state["sent_periods"] and elapsed_minutes > 105:
                # Nota: Gestito sequenzialmente in base all'avanzamento dei minuti live di API-Sports
                msg = f"<b>INIZIO SECONDO TEMPO SUPPLEMENTARE {E_BOLT}</b>\n\n{match_status_line}\n\n{e_comp} {hashtag}"
                send_telegram(msg)
                state["sent_periods"].append("2ET_START")

            elif status in ["AET", "PEN"] and "2H_END" not in state["sent_periods"]:
                msg = f"<b>FINE SECONDO TEMPO SUPPLEMENTARE {E_FLAG}</b>\n\n{match_status_line}\n\n{e_comp} {hashtag}"
                send_telegram(msg)
                state["sent_periods"].append("2H_END")

            # 2. LOTTERIA RIGORI
            if status == "PEN":
                events = match.get('events', [])
                home_pen_icons, away_pen_icons = [], []
                for e in events:
                    detail, ev_type = e.get('detail', '').lower(), e.get('type', '').lower()
                    if "shootout" in detail or (ev_type == "goal" and elapsed_minutes >= 120 and "penalty" in detail):
                        icon = E_PEN_KO if ("missed" in detail or "saved" in detail or ev_type == "card") else E_PEN_OK
                        if e.get('team', {}).get('id') == home_id: home_pen_icons.append(icon)
                        else: away_pen_icons.append(icon)
                total_kicks = len(home_pen_icons) + len(away_pen_icons)
                if total_kicks > state["penalties_count"]:
                    msg_pen = f"{home_name}: " + "".join(home_pen_icons) + f"\n{away_name}: " + "".join(away_pen_icons) + f"\n\n{e_comp} {hashtag}"
                    send_telegram(msg_pen)
                    state["penalties_count"] = total_kicks

            # 3. FINE PARTITA (FT / AET / PEN) -> SCATTA IL DOWNLOAD DA CANVA + POST FOTO
            status_long = fixture.get('status', {}).get('long', '').lower()
            if status in ["FT", "AET", "PEN"] or "finished" in status_long:
                print("🏁 FISCHIO FINALE RILEVATO! Avvio processo scaricamento grafica Canva...")
                
                # Generazione testo per il post finale con evidenza del vincitore complessivo
                scorers_line = build_split_scorers_text(match.get('events', []), home_id, away_id)
                final_status_line = format_match_text(home_name, away_name, g_home_int, g_away_int, p_home, p_away)
                msg_finale = f"<b>FINE PARTITA {E_FLAG}</b>\n\n{final_status_line}\n{scorers_line}\n{e_comp} {hashtag}"
                
                # Gestione Canva
                canva_token = get_valid_token()
                foto_canva = get_canva_image(canva_token)
                
                # Invia il post completo con foto (o testo come ripiego se fallisce)
                send_telegram_with_photo(msg_finale, photo_bytes=foto_canva)
                
                if os.path.exists("match_state.json"): 
                    os.remove("match_state.json")
                print("🏁 Ciclo completato con successo. Spegnimento automatico del bot.")
                sys.exit(0)

            # 4. GOL LIVE E VAR
            total_goals_now = g_home_int + g_away_int
            if total_goals_now > state["goals_detected"]:
                events, live_scorer_line = match.get('events', []), ""
                current_home_name = home_name
                current_away_name = away_name
                g_home_str = str(g_home_int)
                g_away_str = str(g_away_int)
                
                if events:
                    all_goals = [e for e in events if e.get('type', '').lower() == 'goal' and "shootout" not in e.get('detail', '').lower()]
                    if all_goals:
                        all_goals.sort(key=lambda x: (x.get('time', {}).get('elapsed', 0), x.get('time', {}).get('extra', 0) or 0))
                        last_goal = all_goals[-1]
                        
                        el = last_goal.get('time', {}).get('elapsed', '?')
                        ex = last_goal.get('time', {}).get('extra')
                        minute_str = f"{el}+{ex}" if ex else f"{el}"
                        p_name = last_goal.get('player', {}).get('name', 'Giocatore')
                        det = last_goal.get('detail', '').lower()
                        event_team_id = last_goal.get('team', {}).get('id')
                        
                        if event_team_id == home_id:
                            current_home_name = f"<b>{home_name}</b>"
                            g_home_str = f"<b>{g_home_int}</b>"
                        elif event_team_id == away_id:
                            current_away_name = f"<b>{away_name}</b>"
                            g_away_str = f"<b>{g_away_int}</b>"
                        
                        if "penalty" in det: p_name += " (Rig.)"
                        elif "own goal" in det: p_name += " (Autogol)"
                        live_scorer_line = f"{E_BALL} <i>{minute_str}’ {p_name}</i>\n"
                        
                live_score_string = f"{g_home_str}-{g_away_str}"
                msg = f"<b>GOAL {E_MIC}</b>\n\n{current_home_name} {live_score_string} {current_away_name}\n{live_scorer_line}\n{e_comp} {hashtag}"
                send_telegram(msg)
                state["goals_detected"] = total_goals_now
            elif total_goals_now < state["goals_detected"]:
                msg = f"<b>GOAL ANNULLATO 📺</b>\n\n{home_name} {g_home_int}-{g_away_int} {away_name}\n\n{e_comp} {hashtag}"
                send_telegram(msg)
                state["goals_detected"] = total_goals_now

            # 5. EVENTI (CAMBI, CARTELLINI)
            events = match.get('events', [])
            if events:
                subs_by_minute = {}
                for e in events:
                    ev_type, detail, minute, team_id = e.get('type', '').lower(), e.get('detail', '').lower(), e.get('time', {}).get('elapsed', 0), e.get('team', {}).get('id')
                    if ev_type == 'subst':
                        p_out, p_in = e.get('player', {}).get('name', 'Uscente'), e.get('assist', {}).get('name', 'Entrante')
                        sub_id = f"sub_{minute}_{p_out}_{p_in}".replace(" ", "_")
                        if sub_id not in state["sent_subs"]:
                            sub_key = f"{minute}_{team_id}"
                            if sub_key not in subs_by_minute: subs_by_minute[sub_key] = {"minute": minute, "team_id": team_id, "in": [], "out": [], "ids": []}
                            subs_by_minute[sub_key]["in"].append(p_in)
                            subs_by_minute[sub_key]["out"].append(p_out)
                            subs_by_minute[sub_key]["ids"].append(sub_id)
                    elif ev_type == 'card' and "red" in detail:
                        p_name = e.get('player', {}).get('name', 'Giocatore')
                        card_id = f"card_{minute}_{p_name}".replace(" ", "_")
                        if card_id not in state["sent_cards"]:
                            send_telegram(f"<b>CARTELLINO ROSSO {E_RED}</b>\n\n🔚 <i>{minute}’ {p_name}</i>\n\n{e_comp} {hashtag}")
                            state["sent_cards"].append(card_id)

                for sub_key, sub_data in subs_by_minute.items():
                    team_title = "JUVENTUS" if sub_data["team_id"] == JUVE_ID else (home_name.upper() if sub_data["team_id"] == home_id else away_name.upper())
                    send_telegram(f"<b>CAMBIO {team_title} {E_SUB}</b>\n\n{E_UP} {', '.join(sub_data['in'])}\n{E_DOWN} {', '.join(sub_data['out'])}\n\n{e_comp} {hashtag}")
                    state["sent_subs"].extend(sub_data["ids"])

            with open("match_state.json", "w") as f: json.dump(state, f)
        except Exception as e:
            print(f"Errore ciclo live: {e}")
            current_sleep_time = 30
        time.sleep(current_sleep_time)

if __name__ == "__main__":
    main()
