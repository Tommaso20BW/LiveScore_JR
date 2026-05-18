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
E_PEN_OK = '✅'
E_PEN_KO = '❌'

# ==============================================================================
# FUNZIONI DI AGGIORNAMENTO SICURO NEI GITHUB SECRETS
# ==============================================================================
def update_github_secret(secret_name, new_value):
    """Aggiorna in modo sicuro un Secret direttamente su GitHub senza salvare file locali."""
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
    """Formatta i periodi parziali e finali mettendo in bold chi è in vantaggio."""
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
            return f"{c_home_name} <b>{g_home_str} ({p_home})</b> - ({p_away}) {g_away_str} {c_away_name}"
        elif p_away > p_home:
            return f"{c_home_name} {g_home_str} ({p_home}) - <b>({p_away}) {g_away_str}</b> {c_away_name}"
        else:
            return f"{c_home_name} {g_home_str} ({p_home}) - ({p_away}) {g_away_str} {c_away_name}"
    else:
        return f"{c_home_name} {g_home_str}-{g_away_str} {c_away_name}"

# ==============================================================================
# INTEGRAZIONE CANVA API v1
# ==============================================================================
def get_valid_token():
    refresh_token = os.getenv('CANVA_REFRESH_TOKEN')
    if not refresh_token:
        print("❌ Errore: CANVA_REFRESH_TOKEN non presente nelle variabili d'ambiente.")
        return None

    url = "https://api.canva.com/rest/v1/oauth/token"
    payload = {
        "grant_type": "refresh_token", 
        "refresh_token": refresh_token, 
        "client_id": CLIENT_ID, 
        "client_secret": CLIENT_SECRET
    }
    
    try:
        print("🔄 Richiesta di un nuovo Access Token a Canva...")
        res = requests.post(url, data=payload, timeout=15)
        if res.status_code == 200:
            new_tokens = res.json()
            new_access_token = new_tokens["access_token"]
            new_refresh_token = new_tokens.get("refresh_token", refresh_token)
            
            if new_refresh_token != refresh_token:
                print("🔄 Canva ha generato un nuovo Refresh Token. Lo aggiorno su GitHub...")
                update_github_secret("CANVA_REFRESH_TOKEN", new_refresh_token)
            
            return new_access_token
        else:
            print(f"❌ Errore rigenerazione token Canva: {res.text}")
            return None
    except Exception as e: 
        print(f"❌ Errore connessione OAuth Canva: {e}")
        return None

def get_canva_image(access_token):
    if not access_token: return None
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    try:
        res = requests.post("https://api.canva.com/rest/v1/exports", headers=headers, json={"design_id": CANVA_DESIGN_ID, "format": {"type": "png", "pages": [PAGINA_TARGET]}}, timeout=15)
        if res.status_code not in [200, 201]: return None
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
# LOGICA REFRESH DATI API FOOTBALL
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
    except Exception as e: print(f"Errore API Fetch: {e}")
    return None

# ==============================================================================
# PIPELINE MACRO PRESA DATI E CICLO REALE
# ==============================================================================
def main():
    print("🚀 Avvio Live Score Bot: elaborazione eventi in corso...")
    
    # 1. Controllo e il rinnovo del Token Canva
    shared_access_token = get_valid_token()

    # 2. Modalità Keep-Alive
    if os.getenv('ONLY_REFRESH_TOKEN') == "true":
        print("🔒 Modalità Keep-Alive: Token aggiornato correttamente. Termino l'esecuzione.")
        return

    # 3. CONTROLLO PARTITA
    if not os.path.exists("match_state.json"):
        print("Stato del match non trovato. Nessuna partita attiva in coda.")
        return

    with open("match_state.json", "r") as f: state = json.load(f)
    match_id = state.get("live_match_id")
    if not match_id:
        print("Errore: live_match_id assente nel file di stato.")
        return

    match = fetch_live_match(match_id)
    if not match:
        print("⚠️ Impossibile ricevere dati aggiornati dall'API. Riprovo al prossimo cron.")
        return

    fixture = match.get('fixture', {})
    status = fixture.get('status', {}).get('short', 'NS')
    status_long = fixture.get('status', {}).get('long', '').lower()
    elapsed_minutes = fixture.get('status', {}).get('elapsed', 0)
    
    t_home = match.get('teams', {}).get('home', {})
    t_away = match.get('teams', {}).get('away', {})
    home_name, away_name = t_home.get('name', 'Home'), t_away.get('name', 'Away')
    home_id, away_id = t_home.get('id'), t_away.get('id')
    hashtag = f"#Jve{home_name.replace(' ', '') if home_id != MY_TEAM_ID else away_name.replace(' ', '')}" # Fallback generico o pulito
    hashtag = f"#Juve{away_name.replace(' ', '')}" if home_id == MY_TEAM_ID else f"#Juve{home_name.replace(' ', '')}"
    
    g_home_int = match.get('goals', {}).get('home') or 0
    g_away_int = match.get('goals', {}).get('away') or 0
    
    penalties = match.get('score', {}).get('penalty', {})
    p_home, p_away = penalties.get('home'), penalties.get('away')

    match_status_line = format_match_text(home_name, away_name, g_home_int, g_away_int)

    # --------------------------------------------------------------------------
    # 3.1 GESTIONE PERIODI DI GIOCO
    # --------------------------------------------------------------------------
    if status == "1H" and "1H" not in state["sent_periods"]:
        send_telegram(f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{home_name} - {away_name}\n\n🇮🇹 {hashtag}")
        state["sent_periods"].append("1H")
        
    elif status == "HT" and "HT" not in state["sent_periods"]:
        send_telegram(f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{match_status_line}\n\n🇮🇹 {hashtag}")
        state["sent_periods"].append("HT")
        
    elif status == "2H" and "2H_START" not in state["sent_periods"]:
        send_telegram(f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n{match_status_line}\n\n🇮🇹 {hashtag}")
        state["sent_periods"].append("2H_START")
        
    elif status == "ET" and elapsed_minutes == 90 and "2H_END" not in state["sent_periods"]:
        send_telegram(f"<b>FINE SECONDO TEMPO {E_FLAG}</b>\n\n{match_status_line}\n\n🇮🇹 {hashtag}")
        state["sent_periods"].append("2H_END")
        
    elif status == "ET" and elapsed_minutes > 90 and "ET_START" not in state["sent_periods"]:
        send_telegram(f"<b>INIZIO PRIMO TEMPO SUPPLEMENTARE {E_BOLT}</b>\n\n{match_status_line}\n\n🇮🇹 {hashtag}")
        state["sent_periods"].append("ET_START")
        
    elif status == "ET" and elapsed_minutes == 120 and "ET_END" not in state["sent_periods"]:
        send_telegram(f"<b>FINE SECONDO TEMPO SUPPLEMENTARE {E_FLAG}</b>\n\n{match_status_line}\n\n🇮🇹 {hashtag}")
        state["sent_periods"].append("ET_END")

    # --------------------------------------------------------------------------
    # 3.2 GESTIONE EVENTO GOAL LIVE
    # --------------------------------------------------------------------------
    total_goals_now = g_home_int + g_away_int
    if status in ["1H", "2H", "ET"] and total_goals_now > state["goals_detected"]:
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
                
                if last_goal.get('detail', '').lower() == "own goal": p_name += " (AG)"
                elif last_goal.get('detail', '').lower() == "penalty": p_name += " (R)"
                
                marcatore = f"{time_str}’ {p_name}"

                if team_id_scorer == home_id:
                    current_home_name = f"<b>{home_name}</b>"
                    g_home_str = f"<b>{g_home_int}</b>"
                elif team_id_scorer == away_id:
                    current_away_name = f"<b>{away_name}</b>"
                    g_away_str = f"<b>{g_away_int}</b>"

        send_telegram(f"<b>GOAL {E_MIC}</b>\n\n{current_home_name} {g_home_str}-{g_away_str} {current_away_name}\n{E_BALL} <i>{marcatore}</i>\n\n🇮🇹 {hashtag}")
        state["goals_detected"] = total_goals_now

    # --------------------------------------------------------------------------
    # 3.3 GESTIONE CAMBI MULTIPLI LIVE (Raggruppati per minuto)
    # --------------------------------------------------------------------------
    if status in ["1H", "2H", "ET"]:
        events = match.get('events', [])
        grouped_subs = {}
        
        for e in events:
            if e.get('type', '').lower() == 'subst':
                elapsed = e.get('time', {}).get('elapsed', 0)
                extra = e.get('time', {}).get('extra')
                time_str = f"{elapsed}+{extra}" if extra else f"{elapsed}"
                
                team_id_event = e.get('team', {}).get('id')
                team_name = e.get('team', {}).get('name', 'Squadra').upper()
                
                player_in = e.get('player', {}).get('name', 'Giocatore In')
                player_out = e.get('assist', {}).get('name', 'Giocatore Out')
                player_in_id = e.get('player', {}).get('id', 0)
                
                sub_unique_id = f"sub_{team_id_event}_{time_str}_{player_in_id}"
                
                if sub_unique_id not in state.get("sent_substitutions", []):
                    key = (team_id_event, team_name, time_str)
                    if key not in grouped_subs:
                        grouped_subs[key] = {"in": [], "out": [], "ids": []}
                    
                    grouped_subs[key]["in"].append(player_in)
                    grouped_subs[key]["out"].append(player_out)
                    grouped_subs[key]["ids"].append(sub_unique_id)

        for (team_id_event, team_name, time_str), sub_data in grouped_subs.items():
            if team_id_event == MY_TEAM_ID:
                title_team = f"<b>CAMBIO {team_name}</b>"
            else:
                title_team = f"CAMBIO {team_name}"
                
            str_in = ", ".join(sub_data["in"])
            str_out = ", ".join(sub_data["out"])
            
            msg_sub = (
                f"{title_team} {E_SUB}\n\n"
                f"{E_UP} <i>{str_in}</i>\n"
                f"{E_DOWN} <i>{str_out}</i>\n\n"
                f"🇮🇹 {hashtag}"
            )
            
            send_telegram(msg_sub)
            if "sent_substitutions" not in state: state["sent_substitutions"] = []
            state["sent_substitutions"].extend(sub_data["ids"])

    # --------------------------------------------------------------------------
    # 3.4 CRONACA LOTTERIA DEI RIGORI LIVE
    # --------------------------------------------------------------------------
    if status == "PEN" and "finished" not in status_long:
        events = match.get('events', [])
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
            msg_pen = f"<b>RIGORI 🎯</b>\n\n{home_name}: " + "".join(home_pen_icons) + f"\n{away_name}: " + "".join(away_pen_icons) + f"\n\n🇮🇹 {hashtag}"
            send_telegram(msg_pen)
            state["penalties_count"] = total_kicks

    # --------------------------------------------------------------------------
    # 3.5 FINE MATCH FINALE (Canva + Resoconto)
    # --------------------------------------------------------------------------
    if "finished" in status_long or status in ["FT", "AET"] or (status == "PEN" and p_home is not None):
        print("🏁 Fine della partita rilevata. Preparazione riepilogo finale...")
        
        events = match.get('events', [])
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
        if home_scorers or away_scorers:
            scorers_line = f"\n⚽️ <i>{', '.join(home_scorers)} // {', '.join(away_scorers)}</i>"

        title_prefix = "<b>PARTITA TERMINATA! 🏁</b>"
        if MY_TEAM_ID in [home_id, away_id]:
            is_home = (MY_TEAM_ID == home_id)
            if p_home is not None and p_away is not None:
                if (p_home > p_away and is_home) or (p_away > p_home and not is_home):
                    title_prefix = f"<b>{home_name.upper()} VINCE AI RIGORI! 🏆⚪️⚫️</b>"
            else:
                if (g_home_int > g_away_int and is_home) or (g_away_int > g_home_int and not is_home):
                    title_prefix = f"<b>VITTORIA BIANCONERA! 🔥⚪️⚫️</b>"
                elif g_home_int == g_away_int:
                    title_prefix = f"<b>PAREGGIO ALLA FINE! 🤝</b>"
                else:
                    title_prefix = f"<b>FINE PARTITA 🏁</b>"

        final_status_line = format_match_text(home_name, away_name, g_home_int, g_away_int, p_home, p_away)
        msg_finale = f"{title_prefix}\n\n{final_status_line}{scorers_line}\n\n🇮🇹 {hashtag}"
        
        foto = get_canva_image(shared_access_token)
        send_telegram_post_with_photo(msg_finale, photo_bytes=foto)
        
        if os.path.exists("match_state.json"): os.remove("match_state.json")
        print("🏁 Flusso terminato con successo. File di stato rimosso.")
        return

    # Salvataggio dello stato aggiornato per il ciclo successivo
    with open("match_state.json", "w") as f: json.dump(state, f)

if __name__ == "__main__":
    main()
