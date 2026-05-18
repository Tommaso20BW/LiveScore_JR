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
# CONFIGURAZIONE (Usa gli stessi Secret del bot reale)
# ==============================================================================
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')
CLIENT_ID = os.getenv('CANVA_CLIENT_ID')
CLIENT_SECRET = os.getenv('CANVA_CLIENT_SECRET')
GH_PAT = os.getenv('GH_PAT')
REPO_NAME = os.getenv('GITHUB_REPOSITORY') # Viene popolato in automatico da GitHub

# Configurazione Canva
CANVA_DESIGN_ID = "DAHI3ytu6yQ"
PAGINA_TARGET = 11

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
        # 1. Recupera la chiave pubblica del repository
        url_key = f"https://api.github.com/repos/{REPO_NAME}/actions/secrets/public-key"
        res_key = requests.get(url_key, headers=headers)
        if res_key.status_code != 200:
            print(f"❌ Errore recupero chiave pubblica GitHub: {res_key.text}")
            return False
        
        key_data = res_key.json()
        key_id = key_data['key_id']
        public_key_b64 = key_data['key']

        # 2. Cripta il valore del token
        public_key = public.PublicKey(base64.b64decode(public_key_b64))
        box = public.SealedBox(public_key)
        encrypted_value = base64.b64encode(box.encrypt(new_value.encode('utf-8'))).decode('utf-8')

        # 3. Invia il Secret aggiornato a GitHub
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
# FUNZIONI DI INVIO E CONNESSIOINE (Identiche al bot reale)
# ==============================================================================
def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ Errore: TELEGRAM_TOKEN o TELEGRAM_TO non configurati nei Secret.")
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
            print("🏁 Grafica fine partita pubblicata con successo su Telegram!")
        else:
            print(f"❌ Errore foto Telegram: {res.text}. Invio solo testo...")
            send_telegram(text)
    except Exception as e:
        print(f"Errore invio foto: {e}")
        send_telegram(text)

def get_valid_token():
    """Recupera il refresh token dall'environment di GitHub, ne chiede uno nuovo e aggiorna il Secret."""
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
            
            # Se Canva ha fornito un nuovo Refresh Token, lo salviamo subito nei Secrets di GitHub
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
# FUNZIONE DI SUPPORTO PER IL VANTAGGIO IN GRASSETTO (SOLO CRONACA PERIODI E FINALE)
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
            return f"{c_home_name} <b>{g_home_str} ({p_home})</b> - ({p_away}) {g_away_str} {c_away_name}"
        elif p_away > p_home:
            return f"{c_home_name} {g_home_str} ({p_home}) - <b>({p_away}) {g_away_str}</b> {c_away_name}"
        else:
            return f"{c_home_name} {g_home_str} ({p_home}) - ({p_away}) {g_away_str} {c_away_name}"
    else:
        return f"{c_home_name} {g_home_str}-{g_away_str} {c_away_name}"

# ==============================================================================
# SIMULATORE DI UNA PARTITA COMPLETA FINO AI RIGORI (9 STEP)
# ==============================================================================
def genera_finta_api_partita_completa(step):
    finta_risposta = {
        "response": [{
            "fixture": {"status": {"short": "1H", "long": "First Half", "elapsed": 0}},
            "league": {"id": 137}, 
            "teams": {
                "home": {"id": 496, "name": "Juventus"},
                "away": {"id": 505, "name": "Inter"}
            },
            "goals": {"home": 0, "away": 0},
            "score": {"penalty": {"home": None, "away": None}},
            "events": []
        }]
    }
    match = finta_risposta["response"][0]
    
    if step == 0:
        match["fixture"]["status"]["short"] = "1H"
        match["fixture"]["status"]["elapsed"] = 1
        
    elif step == 1:
        match["fixture"]["status"]["short"] = "1H"
        match["fixture"]["status"]["elapsed"] = 30
        match["goals"]["away"] = 1
        match["events"].append({
            "type": "Goal", "detail": "Normal Goal", "team": {"id": 505},
            "time": {"elapsed": 30, "extra": None}, "player": {"name": "L. Martinez"}
        })
        
    elif step == 2:
        match["fixture"]["status"]["short"] = "HT"
        match["fixture"]["status"]["elapsed"] = 45
        match["goals"]["away"] = 1
        
    elif step == 3:
        match["fixture"]["status"]["short"] = "2H"
        match["fixture"]["status"]["elapsed"] = 65
        match["goals"]["home"] = 1
        match["goals"]["away"] = 1
        match["events"].extend([
            {"type": "Goal", "detail": "Normal Goal", "team": {"id": 505}, "time": {"elapsed": 30}, "player": {"name": "L. Martinez"}},
            {"type": "Goal", "detail": "Normal Goal", "team": {"id": 496}, "time": {"elapsed": 65}, "player": {"name": "D. Vlahović"}}
        ])
        
    elif step == 4:
        match["fixture"]["status"]["short"] = "ET"
        match["fixture"]["status"]["elapsed"] = 90
        match["goals"]["home"] = 1
        match["goals"]["away"] = 1
        
    elif step == 5:
        match["fixture"]["status"]["short"] = "ET"
        match["fixture"]["status"]["elapsed"] = 120
        match["goals"]["home"] = 1
        match["goals"]["away"] = 1
        
    elif step == 6:
        match["fixture"]["status"]["short"] = "PEN"
        match["fixture"]["status"]["elapsed"] = 120
        match["goals"]["home"] = 1
        match["goals"]["away"] = 1
        match["events"].extend([
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 496}},
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 505}}
        ])
        
    elif step == 7:
        match["fixture"]["status"]["short"] = "PEN"
        match["fixture"]["status"]["elapsed"] = 120
        match["goals"]["home"] = 1
        match["goals"]["away"] = 1
        match["events"].extend([
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 496}},
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 505}},
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 496}},
            {"type": "Goal", "detail": "Missed Penalty Shootout", "team": {"id": 505}}
        ])
        
    elif step == 8:
        match["fixture"]["status"]["short"] = "PEN"
        match["fixture"]["status"]["long"] = "Match Finished"
        match["fixture"]["status"]["elapsed"] = 120
        match["goals"]["home"] = 1
        match["goals"]["away"] = 1
        match["score"]["penalty"]["home"] = 3
        match["score"]["penalty"]["away"] = 1
        match["events"].extend([
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 496}},
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 505}},
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 496}},
            {"type": "Goal", "detail": "Missed Penalty Shootout", "team": {"id": 505}},
            {"type": "Goal", "detail": "Penalty Shootout", "team": {"id": 496}}
        ])
        
    return finta_risposta

# ==============================================================================
# CICLO PRINCIPALE
# ==============================================================================
def main():
    print("🚀 AVVIO SIMULATORE COMPLETO: MATCH DI 120 MINUTI + RIGORI...")
    if os.path.exists("match_state.json"): os.remove("match_state.json")
    
    for step in range(9):
        print(f"\n--- 🔄 SIMULAZIONE STEP COMPLETO {step} ---")
        res = genera_finta_api_partita_completa(step)
        
        if os.path.exists("match_state.json"):
            with open("match_state.json", "r") as f: state = json.load(f)
        else:
            state = {"live_match_id": 7777, "sent_periods": [], "goals_detected": 0, "sent_subs": [], "sent_cards": [], "penalties_count": 0}

        match = res['response'][0]
        fixture = match.get('fixture', {})
        status = fixture.get('status', {}).get('short', 'NS')
        status_long = fixture.get('status', {}).get('long', '').lower()
        elapsed_minutes = fixture.get('status', {}).get('elapsed', 0)
        
        g_home_int = match.get('goals', {}).get('home', 0)
        g_away_int = match.get('goals', {}).get('away', 0)
        home_name, away_name = "Juventus", "Inter"
        hashtag = "#JuveInter"
        
        penalties = match.get('score', {}).get('penalty', {})
        p_home, p_away = penalties.get('home'), penalties.get('away')

        match_status_line = format_match_text(home_name, away_name, g_home_int, g_away_int)

        if (status == "1H" or elapsed_minutes > 0) and "1H" not in state["sent_periods"]:
            send_telegram(f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{home_name} - {away_name}\n\n🇮🇹 {hashtag}")
            state["sent_periods"].append("1H")
        elif status == "HT" and "HT" not in state["sent_periods"]:
            send_telegram(f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{match_status_line}\n\n🇮🇹 {hashtag}")
            state["sent_periods"].append("HT")
        elif status == "ET" and elapsed_minutes == 90 and "2H_END" not in state["sent_periods"]:
            send_telegram(f"<b>FINE TEMPI REGOLAMENTARI {E_FLAG}</b>\n\n{match_status_line}\n\nSI VA AI SUPPLEMENTARI! ⏳\n\n🇮🇹 {hashtag}")
            state["sent_periods"].append("2H_END")
        elif status == "ET" and elapsed_minutes == 120 and "ET_END" not in state["sent_periods"]:
            send_telegram(f"<b>FINE TEMPI SUPPLEMENTARI {E_FLAG}</b>\n\n{match_status_line}\n\nSI DECIDE TUTTO AI RIGORI! 🎯\n\n🇮🇹 {hashtag}")
            state["sent_periods"].append("ET_END")

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
                    p_name = last_goal.get('player', {}).get('name', 'Giocatore')
                    marcatore = f"{el}’ {p_name}"

                    if team_id_scorer == 496: 
                        current_home_name = f"<b>{home_name}</b>"
                        g_home_str = f"<b>{g_home_int}</b>"
                    else:
                        current_away_name = f"<b>{away_name}</b>"
                        g_away_str = f"<b>{g_away_int}</b>"

            send_telegram(f"<b>GOAL {E_MIC}</b>\n\n{current_home_name} {g_home_str}-{g_away_str} {current_away_name}\n{E_BALL} <i>{marcatore}</i>\n\n🇮🇹 {hashtag}")
            state["goals_detected"] = total_goals_now

        if status == "PEN" and "finished" not in status_long:
            events = match.get('events', [])
            home_pen_icons, away_pen_icons = [], []
            for e in events:
                detail, ev_type = e.get('detail', '').lower(), e.get('type', '').lower()
                if "shootout" in detail or (ev_type == "goal" and elapsed_minutes >= 120 and "penalty" in detail):
                    icon = E_PEN_KO if ("missed" in detail or "saved" in detail) else E_PEN_OK
                    if e.get('team', {}).get('id') == 496: home_pen_icons.append(icon)
                    else: away_pen_icons.append(icon)
                    
            total_kicks = len(home_pen_icons) + len(away_pen_icons)
            if total_kicks > state["penalties_count"]:
                msg_pen = f"<b>LOTTERIA DEI RIGORI 🎯</b>\n\n{home_name}: " + "".join(home_pen_icons) + f"\n{away_name}: " + "".join(away_pen_icons) + f"\n\n🇮🇹 {hashtag}"
                send_telegram(msg_pen)
                state["penalties_count"] = total_kicks

        if "finished" in status_long or (status == "PEN" and p_home is not None):
            print("🏁 FINE TOTALE! Vittoria ai rigori. Avvio Canva...")
            final_status_line = format_match_text(home_name, away_name, g_home_int, g_away_int, p_home, p_away)
            msg_finale = f"<b>JUVENTUS VINCE AI RIGORI! 🏆⚪️⚫️</b>\n\n{final_status_line}\n\n⚽️ <i>30’ L. Martinez // 65’ D. Vlahović</i>\n\n🇮🇹 {hashtag}"
            
            token = get_valid_token()
            foto = get_canva_image(token)
            send_telegram_post_with_photo(msg_finale, photo_bytes=foto)
            
            if os.path.exists("match_state.json"): os.remove("match_state.json")
            print("🏁 Test Partita Completa + Rigori completato!")
            sys.exit(0)

        with open("match_state.json", "w") as f: json.dump(state, f)
        time.sleep(8)

if __name__ == "__main__":
    main()
