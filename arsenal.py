import os
import requests
import json
import time
import sys
from datetime import datetime

# ==============================================================================
# CONFIGURAZIONE STRUTTURA VALORI (Environment e Variabili Locali)
# ==============================================================================
API_KEY = os.getenv('API_KEY')
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')
CLIENT_ID = os.getenv('CANVA_CLIENT_ID')
CLIENT_SECRET = os.getenv('CANVA_CLIENT_SECRET')

# ID Squadra forzato numerico pulito
MY_TEAM_ID = 42

# Configurazione Canva
CANVA_DESIGN_ID = "DAHI3ytu6yQ"
PAGINA_TARGET = 11
TOKEN_FILE = "canva_tokens.json"

# ==============================================================================
# SET EMOJI STANDARD
# ==============================================================================
E_BOLT = '⚡️'
E_FLAG = '🏁'
E_MIC = '🎙'
E_BALL = '⚽️'
E_SUB = '🔄'
E_UP = '🔼'
E_DOWN = '🔽'
E_RED = '🟥'
E_END = '🔚'
E_PEN_OK = '✅'
E_PEN_KO = '❌'

# ==============================================================================
# FUNZIONI DI PULIZIA NOMI SQUADRE E HASHTAG
# ==============================================================================
def clean_team_name(name, for_hashtag=False):
    if not name:
        return "Team"
    if for_hashtag:
        name_lower = name.lower()
        if "manchester city" in name_lower: return "ManCity"
        if "manchester united" in name_lower: return "ManUnited"
        if "tottenham" in name_lower: return "Spurs"

    stopwords = ["fc", "f.c.", "ac", "a.c.", "asd", "a.s.d.", "calcio", "spa", "s.p.a.", "sc", "s.c.", "afc", "a.f.c."]
    words = name.split()
    cleaned_words = [w for w in words if w.lower() not in stopwords]
    if not cleaned_words: cleaned_words = words
    
    if for_hashtag:
        return "".join(cleaned_words).replace(" ", "")
    else:
        return " ".join(cleaned_words)

def get_league_emoji(league_id):
    if league_id in [2, 3, 848]: return "🇪🇺"
    if league_id in [39, 45, 48]: return "🏴"  
    return "⚽️"

# ==============================================================================
# FUNZIONI DI SUPPORTO TELEGRAM
# ==============================================================================
def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ Errore: TELEGRAM_TOKEN o TELEGRAM_TO non configurati.")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code != 200: print(f"Errore Telegram: {res.text}")
    except Exception as e: print(f"Errore invio Telegram: {e}")

def send_telegram_with_photo(text, photo_bytes):
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
    if not os.path.exists(TOKEN_FILE):
        print(f"❌ Errore: Manca il file {TOKEN_FILE} nella repository.")
        return None

    with open(TOKEN_FILE, "r") as f:
        tokens = json.load(f)

    if tokens.get("expires_at", 0) - time.time() < 300:
        print("🔄 Token Canva scaduto. Tento il rinnovo automatico...")
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
                print(f"    [Controllo {i+1}/40] Stato Canva: {status_corrente}")
                
                if status_corrente == "success":
                    urls_list = status_data.get("urls") or status_data.get("job", {}).get("urls")
                    download_url = urls_list[0] if urls_list else (status_data.get("url") or status_data.get("job", {}).get("url"))
                    
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
# FORMATTAZIONE DINAMICA DEL TESTO
# ==============================================================================
def format_match_text(home_name, away_name, g_home, g_away, p_home=None, p_away=None):
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
        if p_home > p_away:
            return f"<b>{home_name}</b> <b>{g_home_str} ({p_home})</b> - ({p_away}) {g_away_str} {away_name}"
        elif p_away > p_home:
            return f"{home_name} {g_home_str} ({p_home}) - <b>({p_away}) {g_away_str}</b> <b>{away_name}</b>"
        else:
            return f"{c_home_name} {g_home_str} ({p_home}) - ({p_away}) {g_away_str} {c_away_name}"
    else:
        return f"{c_home_name} {g_home_str}-{g_away_str} {c_away_name}"

def build_split_scorers_text(events, home_id, away_id):
    if not events: return ""
    home_scorers, away_scorers = [], []
    for e in events:
        if e.get('type', '').lower() == 'goal' and "shootout" not in e.get('detail', '').lower():
            el = e.get('time', {}).get('elapsed', '?')
            ex = e.get('time', {}).get('extra')
            t_str = f"{el}+{ex}" if ex else f"{el}"
            p_name = e.get('player', {}).get('name', 'Giocatore')
            if e.get('detail', '').lower() == "own goal": p_name += " (AG)"
            elif e.get('detail', '').lower() == "penalty": p_name += " (R)"
            
            scorer_entry = f"{t_str}’ {p_name}"
            if e.get('team', {}).get('id') == home_id: home_scorers.append(scorer_entry)
            else: away_scorers.append(scorer_entry)

    if home_scorers and away_scorers:
        return f"\n⚽️ <i>{', '.join(home_scorers)} // {', '.join(away_scorers)}</i>"
    elif home_scorers:
        return f"\n⚽️ <i>{', '.join(home_scorers)}</i>"
    elif away_scorers:
        return f"\n⚽️ <i>{', '.join(away_scorers)}</i>"
    return ""

# ==============================================================================
# RETRIEVAL API-FOOTBALL
# ==============================================================================
def fetch_live_match(match_id):
    if not API_KEY: return None
    url = f"https://v3.football.api-sports.io/fixtures?id={match_id}"
    headers = {"x-apisports-key": API_KEY}
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            data = res.json()
            if data.get("response"): return data["response"][0]
    except Exception as e: print(f"Errore API Fetch ID: {e}")
    return None

# ==============================================================================
# CORE EXECUTION PIPELINE
# ==============================================================================
def main():
    print("🚀 Avvio Live Score Bot...")

    if not os.path.exists("match_state.json"):
        print("🔍 Nessun file di stato trovato. Controllo il calendario di oggi...")
        
        # Gestione dizionario esplicito per bloccare i bug di parsing della stringa URL
        headers = {"x-apisports-key": str(API_KEY).strip()}
        url_today = "https://v3.football.api-sports.io/fixtures"
        params_today = {
            "team": int(MY_TEAM_ID),
            "date": "2026-05-18"
        }
        
        match_id = None
        try:
            # Usiamo params= invece della stringa formattata manuale per evitare errori di caratteri invisibili
            res = requests.get(url_today, headers=headers, params=params_today, timeout=15)
            if res.status_code == 200:
                data = res.json()
                if data.get("response") and len(data["response"]) > 0:
                    fixture_data = data["response"][0]
                    match_id = fixture_data.get("fixture", {}).get("id")
                    status_short = fixture_data.get("fixture", {}).get("status", {}).get("short")
                    print(f"🎯 Match trovato! ID: {match_id} | Stato: {status_short}")
                else:
                    print("📭 Nessun match in programma oggi per questa squadra. Chiudo.")
                    return
            else:
                print(f"❌ Errore API Calendario: {res.text}")
                return
        except Exception as e:
            print(f"❌ Errore connessione calendario: {e}")
            return

        if match_id:
            state = {
                "live_match_id": match_id,
                "goals_detected": 0,
                "sent_periods": [],
                "sent_subs": [],
                "sent_cards": [],
                "penalties_count": 0
            }
            with open("match_state.json", "w") as f:
                json.dump(state, f)
            print("💾 Stato inizializzato correttamente.")
    else:
        with open("match_state.json", "r") as f: 
            state = json.load(f)

    match_id = state.get("live_match_id")
    if not match_id: return

    match = fetch_live_match(match_id)
    if not match: return

    fixture = match.get('fixture', {})
    status = fixture.get('status', {}).get('short', 'NS')
    status_long = fixture.get('status', {}).get('long', '').lower()
    elapsed_minutes = fixture.get('status', {}).get('elapsed', 0)
    
    if status in ["NS", "TBD"]:
        print(f"⏱ Il match (ID: {match_id}) è in calendario, ma non è ancora iniziato (Stato: {status}).")
        return

    league_id = match.get('league', {}).get('id', 0)
    e_comp = get_league_emoji(league_id)
    
    t_home = match.get('teams', {}).get('home', {})
    t_away = match.get('teams', {}).get('away', {})
    home_name = clean_team_name(t_home.get('name', 'Home'))
    away_name = clean_team_name(t_away.get('name', 'Away'))
    home_id, away_id = t_home.get('id'), t_away.get('id')
    
    hashtag = f"#{clean_team_name(t_home.get('name'), for_hashtag=True)}{clean_team_name(t_away.get('name'), for_hashtag=True)}"
    
    g_home_int = match.get('goals', {}).get('home') or 0
    g_away_int = match.get('goals', {}).get('away') or 0
    
    penalties = match.get('score', {}).get('penalty', {})
    p_home, p_away = penalties.get('home'), penalties.get('away')

    match_status_line = format_match_text(home_name, away_name, g_home_int, g_away_int, p_home, p_away)

    if "sent_subs" not in state: state["sent_subs"] = []
    if "sent_cards" not in state: state["sent_cards"] = []
    if "sent_periods" not in state: state["sent_periods"] = []

    # 1. PERIODI DI GIOCO
    if status == "1H" and "1H" not in state["sent_periods"]:
        send_telegram(f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{home_name} - {away_name}\n\n{e_comp} {hashtag}")
        state["sent_periods"].append("1H")
    elif status == "HT" and "HT" not in state["sent_periods"]:
        send_telegram(f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{match_status_line}\n\n{e_comp} {hashtag}")
        state["sent_periods"].append("HT")
    elif status == "2H" and "2H" not in state["sent_periods"]:
        send_telegram(f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n{match_status_line}\n\n{e_comp} {hashtag}")
        state["sent_periods"].append("2H")
    elif status == "ET" and elapsed_minutes == 90 and "2H_END" not in state["sent_periods"]:
        send_telegram(f"<b>FINE SECONDO TEMPO {E_FLAG}</b>\n\n{match_status_line}\n\n{e_comp} {hashtag}")
        state["sent_periods"].append("2H_END")

    # 2. GOL LIVE / ANNULLATI
    total_goals_now = g_home_int + g_away_int
    if total_goals_now < state["goals_detected"]:
        send_telegram(f"<b>GOAL ANNULLATO {E_PEN_KO}</b>\n\n{match_status_line}\n\n{e_comp} {hashtag}")
        state["goals_detected"] = total_goals_now
    elif status in ["1H", "2H", "ET"] and total_goals_now > state["goals_detected"]:
        events = match.get('events', [])
        current_home_name, current_away_name = home_name, away_name
        g_home_str, g_away_str = str(g_home_int), str(g_away_int)
        marcatore = ""
        if events:
            all_goals = [e for e in events if e.get('type', '').lower() == 'goal']
            if all_goals:
                last_goal = all_goals[-1]
                team_id_scorer = last_goal.get('team', {}).get('id')
                el = last_goal.get('time', {}).get('elapsed', '?')
                ex = last_goal.get('time', {}).get('extra')
                time_str = f"{el}+{ex}" if ex else f"{el}"
                p_name = last_goal.get('player', {}).get('name', 'Giocatore')
                marcatore = f"{time_str}’ {p_name}"
                
                if team_id_scorer == home_id:
                    current_home_name = f"<b>{home_name}</b>"
                    g_home_str = f"<b>{g_home_int}</b>"
                elif team_id_scorer == away_id:
                    current_away_name = f"<b>{away_name}</b>"
                    g_away_str = f"<b>{g_away_int}</b>"
                    
        send_telegram(f"<b>GOAL {E_MIC}</b>\n\n{current_home_name} {g_home_str}-{g_away_str} {current_away_name}\n{E_BALL} <i>{marcatore}</i>\n\n{e_comp} {hashtag}")
        state["goals_detected"] = total_goals_now

    # 3. CAMBI
    events = match.get('events', [])
    new_subs = []
    for e in events:
        if e.get('type', '').lower() == 'subst':
            sub_id = f"{e.get('time', {}).get('elapsed')}_{e.get('player', {}).get('id')}_{e.get('assist', {}).get('id')}"
            if sub_id not in state["sent_subs"]: new_subs.append((e, sub_id))

    if new_subs:
        subs_by_team = {}
        for sub_event, sub_id in new_subs:
            t_id = sub_event.get('team', {}).get('id')
            if t_id not in subs_by_team:
                subs_by_team[t_id] = {"name": clean_team_name(sub_event.get('team', {}).get('name')), "in": [], "out": [], "ids": []}
            subs_by_team[t_id]["in"].append(sub_event.get('assist', {}).get('name', 'Giocatore'))
            subs_by_team[t_id]["out"].append(sub_event.get('player', {}).get('name', 'Giocatore'))
            subs_by_team[t_id]["ids"].append(sub_id)

        for t_id, data in subs_by_team.items():
            send_telegram(f"<b>CAMBIO {data['name'].upper()} {E_SUB}</b>\n\n{E_UP} <i>{', '.join(data['in'])}</i>\n{E_DOWN} <i>{', '.join(data['out'])}</i>\n\n{e_comp} {hashtag}")
            state["sent_subs"].extend(data["ids"])

    # 4. CARTELLINI ROSSI
    for e in events:
        if e.get('type', '').lower() == 'card' and e.get('detail', '').lower() in ['red card', 'second yellow card']:
            card_id = f"{e.get('time', {}).get('elapsed')}_{e.get('player', {}).get('id')}"
            if card_id not in state["sent_cards"]:
                t_name = clean_team_name(e.get('team', {}).get('name', 'Squadra'))
                p_name = e.get('player', {}).get('name', 'Giocatore')
                el = e.get('time', {}).get('elapsed', '?')
                ex = e.get('time', {}).get('extra')
                time_str = f"{el}+{ex}" if ex else f"{el}"
                send_telegram(f"<b>CARTELLINO ROSSO {t_name.upper()} {E_RED}</b>\n\n{E_END} <i>{time_str}’ {p_name}</i>\n\n{e_comp} {hashtag}")
                state["sent_cards"].append(card_id)

    # 5. RIGORI LIVE
    if status == "PEN" and "finished" not in status_long:
        home_pen_icons, away_pen_icons = [], []
        for e in events:
            detail = e.get('detail', '').lower()
            if "shootout" in detail or (e.get('type', '').lower() == "goal" and elapsed_minutes >= 120 and "penalty" in detail):
                icon = E_PEN_KO if ("missed" in detail or "saved" in detail) else E_PEN_OK
                if e.get('team', {}).get('id') == home_id: home_pen_icons.append(icon)
                else: away_pen_icons.append(icon)
        total_kicks = len(home_pen_icons) + len(away_pen_icons)
        if total_kicks > state.get("penalties_count", 0):
            send_telegram(f"<b>RIGORI 🎯</b>\n\n{home_name}: " + "".join(home_pen_icons) + f"\n{away_name}: " + "".join(away_pen_icons) + f"\n\n{e_comp} {hashtag}")
            state["penalties_count"] = total_kicks

    # 6. FISCHIO FINALE
    if "finished" in status_long or status in ["FT", "AET"] or (status == "PEN" and p_home is not None):
        print("🏁 FISCHIO FINALE RILEVATO! Avvio processo scaricamento grafica Canva...")
        
        scorers_line = build_split_scorers_text(events, home_id, away_id)
        msg_finale = f"<b>FINE PARTITA {E_FLAG}</b>\n\n{match_status_line}\n{scorers_line}\n\n{e_comp} {hashtag}"
        
        canva_token = get_valid_token()
        foto_canva = get_canva_image(canva_token)
        
        send_telegram_with_photo(msg_finale, photo_bytes=foto_canva)
        
        if os.path.exists("match_state.json"): 
            os.remove("match_state.json")
        print("🏁 Ciclo completato con successo. Spegnimento automatico del bot.")
        sys.exit(0)

    with open("match_state.json", "w") as f: 
        json.dump(state, f)

if __name__ == "__main__":
    main()
