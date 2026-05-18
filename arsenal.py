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
# CONFIGURAZIONE (Secret di GitHub / Variabili d'Ambiente)
# ==============================================================================
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')
API_KEY = os.getenv('API_KEY')
CLIENT_ID = os.getenv('CANVA_CLIENT_ID')
CLIENT_SECRET = os.getenv('CANVA_CLIENT_SECRET')
GH_PAT = os.getenv('GH_PAT')
REPO_NAME = os.getenv('GITHUB_REPOSITORY') 

# Configurazione Canva e ID Squadra
CANVA_DESIGN_ID = "DAHI3ytu6yQ"
PAGINA_TARGET = 11
MY_TEAM_ID = 42  # ID Arsenal su API-Football

# Emoji Branding Arsenal
E_BOLT = '⚡️'
E_FLAG = '🏁'
E_MIC = '🎙'
E_BALL = '⚽️'
E_GUN = '🔴'      
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
def search_today_match():
    if not API_KEY:
        print("❌ API_KEY mancante.")
        return None
        
    url = "https://v3.football.api-sports.io/fixtures"
    headers = {"x-apisports-key": API_KEY}
    today_date = datetime.now().strftime('%Y-%m-%d')
    params = {"team": MY_TEAM_ID, "date": today_date}
    
    try:
        print(f"🔍 Controllo palinsesto API per l'Arsenal in data {today_date}...")
        res = requests.get(url, headers=headers, params=params, timeout=15)
        if res.status_code == 200:
            fixtures = res.json().get("response", [])
            if not fixtures:
                print("ℹ️ Nessun match programmato per l'Arsenal oggi.")
                return None
                
            match = fixtures[0]
            match_id = match.get('fixture', {}).get('id')
            status = match.get('fixture', {}).get('status', {}).get('short', 'NS')
            print(f"✅ Match trovato! ID: {match_id} | Stato attuale: {status}")
            
            return {
                "live_match_id": match_id, 
                "sent_periods": [], 
                "goals_detected": 0, 
                "penalties_count": 0
            }
    except Exception as e:
        print(f"❌ Errore durante la ricerca della partita: {e}")
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
# LOOP DI ESECUZIONE CONTINUA (MANUALE)
# ==============================================================================
def main():
    print("🚀 Avvio Live Score Bot (Arsenal) in modalità CONTINUA/MANUALE...")
    
    # 1. Recupero token Canva unico all'avvio (valido 2 ore, copre la partita)
    shared_access_token = get_valid_token()
    if not shared_access_token:
        print("❌ Impossibile avviare il bot senza token Canva valido.")
        return

    # 2. Ricerca del match di oggi
    state = search_today_match()
    if not state:
        print("🛑 Esecuzione interrotta: nessuna partita in palinsesto oggi.")
        return

    match_id = state["live_match_id"]
    
    # Allineamento iniziale dei gol per evitare spam se avviato a partita in corso
    match_init = fetch_live_match(match_id)
    if match_init:
        g_home_init = match_init.get('goals', {}).get('home') or 0
        g_away_init = match_init.get('goals', {}).get('away') or 0
        state["goals_detected"] = g_home_init + g_away_init
        print(f"📊 Allineamento iniziale completato. Gol già rilevati: {state['goals_detected']}")

    # 3. Inizio del ciclo di monitoraggio live
    print("⏳ Entro nel loop di controllo live (30s di intervallo)...")
    while True:
        try:
            match = fetch_live_match(match_id)
            if not match:
                print("⚠️ Impossibile ricevere dati aggiornati dall'API. Riprovo al prossimo ciclo.")
                time.sleep(30)
                continue

            fixture = match.get('fixture', {})
            status = fixture.get('status', {}).get('short', 'NS')
            status_long = fixture.get('status', {}).get('long', '').lower()
            elapsed_minutes = fixture.get('status', {}).get('elapsed', 0)
            
            t_home = match.get('teams', {}).get('home', {})
            t_away = match.get('teams', {}).get('away', {})
            home_name, away_name = t_home.get('name', 'Home'), t_away.get('name', 'Away')
            home_id, away_id = t_home.get('id'), t_away.get('id')
            hashtag = f"#{home_name.replace(' ', '')}{away_name.replace(' ', '')} #COYG"
            
            g_home_int = match.get('goals', {}).get('home') or 0
            g_away_int = match.get('goals', {}).get('away') or 0
            
            penalties = match.get('score', {}).get('penalty', {})
            p_home, p_away = penalties.get('home'), penalties.get('away')

            match_status_line = format_match_text(home_name, away_name, g_home_int, g_away_int)

            # 3.1 GESTIONE PERIODI DI GIOCO
            if (status == "1H" or elapsed_minutes > 0) and "1H" not in state["sent_periods"]:
                send_telegram(f"<b>KICK-OFF {E_BOLT}</b>\n\n{home_name} - {away_name}\n\n🔴 {hashtag}")
                state["sent_periods"].append("1H")
                
            elif status == "HT" and "HT" not in state["sent_periods"]:
                send_telegram(f"<b>HALF-TIME {E_FLAG}</b>\n\n{match_status_line}\n\n🔴 {hashtag}")
                state["sent_periods"].append("HT")
                
            elif status == "ET" and elapsed_minutes == 90 and "2H_END" not in state["sent_periods"]:
                send_telegram(f"<b>FULL-TIME (REGULAR TIME) {E_FLAG}</b>\n\n{match_status_line}\n\nEXTRA-TIME! ⏳\n\n🔴 {hashtag}")
                state["sent_periods"].append("2H_END")
                
            elif status == "ET" and elapsed_minutes == 120 and "ET_END" not in state["sent_periods"]:
                send_telegram(f"<b>END OF EXTRA-TIME {E_FLAG}</b>\n\n{match_status_line}\n\nGOAL SHOOTOUT! 🎯\n\n🔴 {hashtag}")
                state["sent_periods"].append("ET_END")

            # 3.2 GESTIONE EVENTO GOAL LIVE
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
                        p_name = last_goal.get('player', {}).get('name', 'Player')
                        marcatore = f"{time_str}’ {p_name}"

                        if team_id_scorer == home_id:
                            current_home_name = f"<b>{home_name}</b>"
                            g_home_str = f"<b>{g_home_int}</b>"
                        elif team_id_scorer == away_id:
                            current_away_name = f"<b>{away_name}</b>"
                            g_away_str = f"<b>{g_away_int}</b>"

                send_telegram(f"<b>GOAL {E_MIC}</b>\n\n{current_home_name} {g_home_str}-{g_away_str} {current_away_name}\n{E_BALL} <i>{marcatore}</i>\n\n🔴 {hashtag}")
                state["goals_detected"] = total_goals_now

            # 3.3 CRONACA LOTTERIA DEI RIGORI LIVE
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
                    msg_pen = f"<b>PENALTY SHOOTOUT 🎯</b>\n\n{home_name}: " + "".join(home_pen_icons) + f"\n{away_name}: " + "".join(away_pen_icons) + f"\n\n🔴 {hashtag}"
                    send_telegram(msg_pen)
                    state["penalties_count"] = total_kicks

            # 3.4 FINE MATCH FINALE (Condizione d'uscita dal Loop)
            if "finished" in status_long or status in ["FT", "AET"]:
                print("🏁 Fine della partita rilevata. Preparazione riepilogo finale...")
                
                events = match.get('events', [])
                home_scorers, away_scorers = [], []
                for e in events:
                    detail_lower = e.get('detail', '').lower()
                    elapsed = e.get('time', {}).get('elapsed', 0)
                    
                    # Filtriamo tenendo solo i goal dei tempi regolamentari/supplementari (esclusi rigori finali)
                    if e.get('type', '').lower() == 'goal' and "shootout" not in detail_lower and elapsed <= 120:
                        ex = e.get('time', {}).get('extra')
                        t_str = f"{elapsed}+{ex}" if ex else f"{elapsed}"
                        p_name = e.get('player', {}).get('name', 'Player')
                        
                        if detail_lower == "own goal": p_name += " (AG)"
                        elif detail_lower == "penalty": p_name += " (R)"
                        
                        scorer_entry = f"{t_str}’ {p_name}"
                        if e.get('team', {}).get('id') == home_id: home_scorers.append(scorer_entry)
                        else: away_scorers.append(scorer_entry)

                scorers_line = ""
                if home_scorers or away_scorers:
                    scorers_line = f"\n⚽️ <i>{', '.join(home_scorers)} // {', '.join(away_scorers)}</i>"

                title_prefix = "<b>FULL-TIME! 🏁</b>"
                if MY_TEAM_ID in [home_id, away_id]:
                    is_home = (MY_TEAM_ID == home_id)
                    if p_home is not None and p_away is not None:
                        if (p_home > p_away and is_home) or (p_away > p_home and not is_home):
                            title_prefix = f"<b>{home_name.upper()} WIN ON PENALTIES! 🏆🔴⚪️</b>"
                    else:
                        if (g_home_int > g_away_int and is_home) or (g_away_int > g_home_int and not is_home):
                            title_prefix = f"<b>GUNNERS WIN! 🔥🔴⚪️</b>"
                        elif g_home_int == g_away_int:
                            title_prefix = f"<b>POINTS SHARED! 🤝</b>"
                        else:
                            title_prefix = f"<b>FULL-TIME 🏁</b>"

                final_status_line = format_match_text(home_name, away_name, g_home_int, g_away_int, p_home, p_away)
                msg_finale = f"{title_prefix}\n\n{final_status_line}{scorers_line}\n\n🔴 {hashtag}"
                
                foto = get_canva_image(shared_access_token)
                send_telegram_post_with_photo(msg_finale, photo_bytes=foto)
                
                break # Rompe il loop while True e termina lo script con successo

        except Exception as e:
            print(f"❌ Errore nel loop live: {e}")
            
        # Pausa di 30 secondi prima del prossimo controllo API
        time.sleep(30)
        
    print("👋 Processo completato. Il bot si è spento regolarmente.")

if __name__ == "__main__":
    main()
