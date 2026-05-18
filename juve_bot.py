import os
import requests
import json
import time
import sys
import base64
from datetime import datetime

# Importiamo la libreria di crittografia richiesta da GitHub per aggiornare i Secrets
try:
    from nacl import public
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pynacl"])
    from nacl import public

# ==============================================================================
# CONFIGURAZIONE (Secret di GitHub)
# ==============================================================================
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')
API_KEY = os.getenv('FOOTBALL_API_KEY')
CLIENT_ID = os.getenv('CANVA_CLIENT_ID')
CLIENT_SECRET = os.getenv('CANVA_CLIENT_SECRET')
GH_PAT = os.getenv('GH_PAT')
REPO_NAME = os.getenv('GITHUB_REPOSITORY') 

# Configurazione Canva e ID Squadra
CANVA_DESIGN_ID = "DAHI3ytu6yQ"
PAGINA_TARGET = 11
MY_TEAM_ID = 496  # ID Juventus su API-Football

# Emoji Branding @Juventus_Reborn
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
# FUNZIONE DI PULIZIA NOMI SQUADRE E HASHTAG SPECIALI
# ==============================================================================
def clean_team_name(name, for_hashtag=False):
    if not name:
        return "Team"
    
    if for_hashtag:
        name_lower = name.lower()
        if "manchester city" in name_lower:
            return "ManCity"
        if "manchester united" in name_lower:
            return "ManUnited"

    stopwords = ["fc", "f.c.", "ac", "a.c.", "asd", "a.s.d.", "calcio", "spa", "s.p.a.", "sc", "s.c."]
    words = name.split()
    cleaned_words = [w for w in words if w.lower() not in stopwords]
    
    if not cleaned_words:
        cleaned_words = words
        
    if for_hashtag:
        return "".join(cleaned_words).replace(" ", "")
    else:
        return " ".join(cleaned_words)

# ==============================================================================
# FUNZIONI DI AGGIORNAMENTO SICURO NEI GITHUB SECRETS
# ==============================================================================
def update_github_secret(secret_name, new_value):
    if not GH_PAT or not REPO_NAME:
        print("⚠️ GitHub PAT o nome Repository mancanti in env. Impossibile aggiornare il Secret.")
        return False

    headers = {"Authorization": f"token {GH_PAT}", "Accept": "application/vnd.github.v3+json"}
    
    try:
        url_key = f"https://api.github.com/repos/{REPO_NAME}/actions/secrets/public-key"
        res_key = requests.get(url_key, headers=headers)
        if res_key.status_code != 200:
            print(f"❌ Errore recupero chiave pubblica GitHub: {res_key.text}")
            return False
        
        key_data = res_key.json()
        key_id = key_data['key_id']
        public_key_b64 = key_data['key']

        public_key = public.PublicKey(base64.b64decode(public_key_b64))
        box = public.SealedBox(public_key)
        encrypted_value = base64.b64encode(box.encrypt(new_value.encode('utf-8'))).decode('utf-8')

        url_secret = f"https://api.github.com/repos/{REPO_NAME}/actions/secrets/{secret_name}"
        data = {"encrypted_value": encrypted_value, "key_id": key_id}
        res_secret = requests.put(url_secret, headers=headers, json=data)
        
        if res_secret.status_code in [201, 204]:
            print(f"🔒 Secret {secret_name} aggiornato con successo su GitHub!")
            return True
        else:
            print(f"❌ Errore salvataggio Secret su GitHub: {res_secret.text}")
            return False
    except Exception as e:
        print(f"❌ Errore durante l'aggiornamento del Secret: {e}")
        return False

# ==============================================================================
# FUNZIONI DI SUPPORTO E UTILITY
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
    except Exception as e: print(f"Errore invio: {e}")

def send_telegram_post_with_photo(text, photo_bytes):
    if not photo_bytes:
        print("⚠️ Immagine Canva mancante. Invio solo testo...")
        send_telegram(text)
        return
    print("📤 Spedisco il post con grafica Canva su Telegram...")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    payload = {"chat_id": CHAT_ID, "caption": text, "parse_mode": "HTML"}
    files = {"photo": ("matchday.png", photo_bytes)}
    try:
        res = requests.post(url, data=payload, files=files, timeout=25)
        if res.status_code == 200:
            print("🏁 Grafica finale pubblicata con successo su Telegram!")
        else:
            print(f"❌ Errore foto Telegram: {res.text}. Invio solo testo...")
            send_telegram(text)
    except Exception as e:
        print(f"Errore invio foto: {e}")
        send_telegram(text)

def format_match_text(home_name, away_name, g_home, g_away, p_home=None, p_away=None):
    # Logica aggiornata: sia il nome della squadra sia il rispettivo punteggio vanno in bold fissi se > dell'avversario
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

# ==============================================================================
# INTEGRAZIONE CANVA API v1
# ==============================================================================
def get_valid_token():
    refresh_token = os.getenv('CANVA_REFRESH_TOKEN')
    if not refresh_token: return None
    url = "https://api.canva.com/rest/v1/oauth/token"
    payload = {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}
    try:
        res = requests.post(url, data=payload, timeout=15)
        if res.status_code == 200:
            new_tokens = res.json()
            new_access_token = new_tokens["access_token"]
            new_refresh_token = new_tokens.get("refresh_token", refresh_token)
            if new_refresh_token != refresh_token:
                update_github_secret("CANVA_REFRESH_TOKEN", new_refresh_token)
            return new_access_token
        return None
    except Exception as e: return None

def get_canva_image(access_token):
    if not access_token: return None
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    try:
        res = requests.post("https://api.canva.com/rest/v1/exports", headers=headers, json={"design_id": CANVA_DESIGN_ID, "format": {"type": "png", "pages": [PAGINA_TARGET]}}, timeout=15)
        if res.status_code not in [201, 200]: return None
        job_id = res.json().get("id") or res.json().get("job", {}).get("id")
        for i in range(20):
            time.sleep(3)
            check = requests.get(f"https://api.canva.com/rest/v1/exports/{job_id}", headers=headers, timeout=15).json()
            status = check.get("status") or check.get("job", {}).get("status")
            if status == "success":
                urls = check.get("urls") or check.get("job", {}).get("urls")
                url_download = urls[0] if urls else (check.get("url") or check.get("job", {}).get("url"))
                if url_download: return requests.get(url_download, timeout=20).content
    except Exception as e: print(f"Errore Canva: {e}")
    return None

# ==============================================================================
# FUNZIONI INTERROGAZIONE API-FOOTBALL
# ==============================================================================
def get_current_live_match_id():
    """Cerca se c'è una partita in diretta per la squadra impostata (MY_TEAM_ID)"""
    if not API_KEY: return None
    url = f"https://v3.football.api-sports.io/fixtures?team={MY_TEAM_ID}&live=all"
    headers = {"x-apisports-key": API_KEY}
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            data = res.json()
            if data.get("response"):
                # Restituisce l'ID della prima partita in diretta trovata
                return data["response"][0].get("fixture", {}).get("id")
    except Exception as e:
        print(f"Errore ricerca match live: {e}")
    return None

def fetch_live_match(match_id):
    if not API_KEY: return None
    url = f"https://v3.football.api-sports.io/fixtures?id={match_id}"
    headers = {"x-apisports-key": API_KEY}
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            data = res.json()
            if data.get("response"): return data["response"][0]
    except Exception as e: print(f"Errore API Fetch: {e}")
    return None

# ==============================================================================
# PIPELINE MAIN INTERCETTAZIONE E CICLO REALE
# ==============================================================================
def main():
    print("🚀 Avvio Live Score Bot...")
    shared_access_token = get_valid_token()

    if os.getenv('ONLY_REFRESH_TOKEN') == "true":
        print("🔒 Modalità Keep-Alive terminata.")
        return

    # Controlliamo se esiste già una partita monitorata in corso
    if not os.path.exists("match_state.json"):
        print("🔍 Nessun file di stato trovato. Controllo se la squadra sta giocando...")
        live_id = get_current_live_match_id()
        if live_id:
            print(f"🎯 Partita in diretta trovata! ID: {live_id}. Inizializzo lo stato.")
            state = {
                "live_match_id": live_id,
                "goals_detected": 0,
                "sent_periods": [],
                "sent_subs": [],
                "sent_cards": [],
                "penalties_count": 0
            }
            with open("match_state.json", "w") as f:
                json.dump(state, f)
        else:
            print("😴 Nessuna partita in diretta al momento per questa squadra.")
            return
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
    
    # --- RILEVAMENTO DELLA COMPETIZIONE TRAMITE ID PRECISI ---
    league_data = match.get('league', {})
    league_id = league_data.get('id')
    league_name_lower = league_data.get('name', '').lower()
    
    if league_id in [2, 3, 848]:
        compet_emoji = "🇪🇺"
    elif league_id == 10 or "friendly" in league_name_lower or "amichevole" in league_name_lower:
        compet_emoji = "🤝"
    elif league_id in [135, 137, 547]:
        compet_emoji = "🇮🇹"
    else:
        compet_emoji = "🇮🇹" # Fallback sicuro
    
    t_home = match.get('teams', {}).get('home', {})
    t_away = match.get('teams', {}).get('away', {})
    
    # --- ACQUISIZIONE E PULIZIA DEI NOMI PER IL TESTO ---
    home_name = clean_team_name(t_home.get('name', 'Home'))
    away_name = clean_team_name(t_away.get('name', 'Away'))
    home_id, away_id = t_home.get('id'), t_away.get('id')
    
    # --- GENERAZIONE HASHTAG SPECIALI ---
    hashtag = f"#{clean_team_name(t_home.get('name'), for_hashtag=True)}{clean_team_name(t_away.get('name'), for_hashtag=True)}"
    
    g_home_int = match.get('goals', {}).get('home') or 0
    g_away_int = match.get('goals', {}).get('away') or 0
    
    penalties = match.get('score', {}).get('penalty', {})
    p_home, p_away = penalties.get('home'), penalties.get('away')

    match_status_line = format_match_text(home_name, away_name, g_home_int, g_away_int)

    # Inizializzazioni di sicurezza nello stato
    if "sent_subs" not in state: state["sent_subs"] = []
    if "sent_cards" not in state: state["sent_cards"] = []
    if "sent_periods" not in state: state["sent_periods"] = []

    # ==============================================================================
    # 1. GESTIONE PERIODI DI GIOCO
    # ==============================================================================
    if status == "1H" and "1H" not in state["sent_periods"]:
        send_telegram(f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{home_name} - {away_name}\n\n{compet_emoji} {hashtag}")
        state["sent_periods"].append("1H")
    elif status == "HT" and "HT" not in state["sent_periods"]:
        send_telegram(f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{match_status_line}\n\n{compet_emoji} {hashtag}")
        state["sent_periods"].append("HT")
    elif status == "2H" and "2H" not in state["sent_periods"]:
        send_telegram(f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n{match_status_line}\n\n{compet_emoji} {hashtag}")
        state["sent_periods"].append("2H")
    elif status == "ET" and elapsed_minutes == 90 and "2H_END" not in state["sent_periods"]:
        send_telegram(f"<b>FINE SECONDO TEMPO {E_FLAG}</b>\n\n{match_status_line}\n\n{compet_emoji} {hashtag}")
        state["sent_periods"].append("2H_END")
    elif status == "ET" and elapsed_minutes == 91 and "ET1_START" not in state["sent_periods"]:
        send_telegram(f"<b>INIZIO PRIMO TEMPO SUPPLEMENTARE {E_BOLT}</b>\n\n{match_status_line}\n\n{compet_emoji} {hashtag}")
        state["sent_periods"].append("ET1_START")
    elif status == "ET" and elapsed_minutes == 120 and "ET_END" not in state["sent_periods"]:
        send_telegram(f"<b>FINE SECONDO TEMPO SUPPLEMENTARE {E_FLAG}</b>\n\n{match_status_line}\n\n{compet_emoji} {hashtag}")
        state["sent_periods"].append("ET_END")

    # ==============================================================================
    # 2. GESTIONE GOL LIVE / GOL ANNULLATI
    # ==============================================================================
    total_goals_now = g_home_int + g_away_int
    
    if total_goals_now < state["goals_detected"]:
        send_telegram(f"<b>GOAL ANNULLATO {E_PEN_KO}</b>\n\n{match_status_line}\n\n{compet_emoji} {hashtag}")
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
                extra = last_goal.get('time', {}).get('extra')
                time_str = f"{el}+{extra}" if extra else f"{el}"
                p_name = last_goal.get('player', {}).get('name', 'Giocatore')
                marcatore = f"{time_str}’ {p_name}"
                
                # Chi ha segnato va sempre in bold fisso (squadra + rispettivo punteggio)
                if team_id_scorer == home_id:
                    current_home_name = f"<b>{home_name}</b>"
                    g_home_str = f"<b>{g_home_int}</b>"
                elif team_id_scorer == away_id:
                    current_away_name = f"<b>{away_name}</b>"
                    g_away_str = f"<b>{g_away_int}</b>"
                    
        send_telegram(f"<b>GOAL {E_MIC}</b>\n\n{current_home_name} {g_home_str}-{g_away_str} {current_away_name}\n{E_BALL} <i>{marcatore}</i>\n\n{compet_emoji} {hashtag}")
        state["goals_detected"] = total_goals_now

    # ==============================================================================
    # 3. GESTIONE CAMBI
    # ==============================================================================
    events = match.get('events', [])
    new_subs = []
    
    for e in events:
        if e.get('type', '').lower() == 'subst':
            sub_id = f"{e.get('time', {}).get('elapsed')}_{e.get('player', {}).get('id')}_{e.get('assist', {}).get('id')}"
            if sub_id not in state["sent_subs"]:
                new_subs.append((e, sub_id))

    if new_subs:
        subs_by_team = {}
        for sub_event, sub_id in new_subs:
            t_id = sub_event.get('team', {}).get('id')
            if t_id not in subs_by_team:
                cleaned_t_name = clean_team_name(sub_event.get('team', {}).get('name'))
                subs_by_team[t_id] = {"name": cleaned_t_name, "in": [], "out": [], "ids": []}
            
            p_in = sub_event.get('assist', {}).get('name', 'Giocatore')
            p_out = sub_event.get('player', {}).get('name', 'Giocatore')
            
            subs_by_team[t_id]["in"].append(p_in)
            subs_by_team[t_id]["out"].append(p_out)
            subs_by_team[t_id]["ids"].append(sub_id)

        for t_id, data in subs_by_team.items():
            team_upper = data['name'].upper()
            msg_sub = f"<b>CAMBIO {team_upper} {E_SUB}</b>\n\n{E_UP} <i>{', '.join(data['in'])}</i>\n{E_DOWN} <i>{', '.join(data['out'])}</i>\n\n{compet_emoji} {hashtag}"
            send_telegram(msg_sub)
            state["sent_subs"].extend(data["ids"])

    # ==============================================================================
    # 4. GESTIONE CARTELLINI ROSSI
    # ==============================================================================
    for e in events:
        if e.get('type', '').lower() == 'card' and e.get('detail', '').lower() in ['red card', 'second yellow card']:
            card_id = f"{e.get('time', {}).get('elapsed')}_{e.get('player', {}).get('id')}"
            if card_id not in state["sent_cards"]:
                t_name = clean_team_name(e.get('team', {}).get('name', 'Squadra'))
                p_name = e.get('player', {}).get('name', 'Giocatore')
                el = e.get('time', {}).get('elapsed', '?')
                extra = e.get('time', {}).get('extra')
                time_str = f"{el}+{extra}" if extra else f"{el}"
                
                msg_card = f"<b>CARTELLINO ROSSO {t_name.upper()} {E_RED}</b>\n\n{E_END} <i>{time_str}’ {p_name}</i>\n\n{compet_emoji} {hashtag}"
                send_telegram(msg_card)
                state["sent_cards"].append(card_id)

    # ==============================================================================
    # 5. CRONACA LOTTERIA DEI RIGORI LIVE
    # ==============================================================================
    if status == "PEN" and "finished" not in status_long:
        home_pen_icons, away_pen_icons = [], []
        for e in events:
            detail = e.get('detail', '').lower()
            ev_type = e.get('type', '').lower()
            if "shootout" in detail or (ev_type == "goal" and elapsed_minutes >= 120 and "penalty" in detail):
                icon = E_PEN_KO if ("missed" in detail or "saved" in detail) else E_PEN_OK
                if e.get('team', {}).get('id') == home_id: home_pen_icons.append(icon)
                else: away_pen_icons.append(icon)
                
        total_kicks = len(home_pen_icons) + len(away_pen_icons)
        if total_kicks > state.get("penalties_count", 0):
            msg_pen = f"<b>RIGORI 🎯</b>\n\n{home_name}: " + "".join(home_pen_icons) + f"\n{away_name}: " + "".join(away_pen_icons) + f"\n\n{compet_emoji} {hashtag}"
            send_telegram(msg_pen)
            state["penalties_count"] = total_kicks

    # ==============================================================================
    # 6. FINE MATCH FINALE
    # ==============================================================================
    if "finished" in status_long or status in ["FT", "AET"] or (status == "PEN" and p_home is not None):
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

        scorers_line = ""
        if home_scorers and away_scorers:
            scorers_line = f"\n⚽️ <i>{', '.join(home_scorers)} // {', '.join(away_scorers)}</i>"
        elif home_scorers:
            scorers_line = f"\n⚽️ <i>{', '.join(home_scorers)}</i>"
        elif away_scorers:
            scorers_line = f"\n⚽️ <i>{', '.join(away_scorers)}</i>"

        title_prefix = "<b>FINE PARTITA 🏁</b>"
        final_status_line = format_match_text(home_name, away_name, g_home_int, g_away_int, p_home, p_away)
        msg_finale = f"{title_prefix}\n\n{final_status_line}{scorers_line}\n\n{compet_emoji} {hashtag}"
        
        foto = get_canva_image(shared_access_token)
        send_telegram_post_with_photo(msg_finale, photo_bytes=foto)
        
        if os.path.exists("match_state.json"): os.remove("match_state.json")
        return

    with open("match_state.json", "w") as f: json.dump(state, f)

if __name__ == "__main__":
    main()
