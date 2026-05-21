import os
import requests
import json
import time
import sys
import base64
from datetime import datetime
from html2image import Html2Image

# Usiamo NaCl (Libsodium) per criptare il secret come richiesto dalle API di GitHub
try:
    from nacl import encoding, public
except ImportError:
    print("⚠️ Errore: La libreria 'pynacl' non è installata. Necessaria per aggiornare i Secrets di GitHub.")

# ==============================================================================
# CONFIGURAZIONE CHIAVI E DATI REQUISITI (DA SECRETS GITHUB)
# ==============================================================================
API_KEY = os.getenv('API_KEY')
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')
CLIENT_ID = os.getenv('CANVA_CLIENT_ID')
CLIENT_SECRET = os.getenv('CANVA_CLIENT_SECRET')
CANVA_REFRESH_TOKEN = os.getenv('CANVA_REFRESH_TOKEN')
GH_PAT = os.getenv('GH_PAT')                 # Il tuo Personal Access Token di GitHub
GITHUB_REPOSITORY = os.getenv('GITHUB_REPOSITORY') # Es: "tuo-utente/tuo-repo"

JUVE_ID = 496
CANVA_DESIGN_ID = "DAHI3ytu6yQ"
PAGINA_TARGET = 11

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
E_CHART = '📊'

LEAGUE_EMOJIS = {
    135: '🇮🇹',   # Serie A
    137: '🇮🇹',   # Coppa Italia
    547: '🇮🇹',   # Supercoppa Italiana
    2:   '🇪🇺',   # Champions League
    3:   '🇪🇺',   # Europa League
    667: '🤝'    # Amichevoli Club
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
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"Errore invio Telegram: {e}")

def send_telegram_with_photo(text, photo_bytes, filename="matchday.png"):
    if not photo_bytes:
        print("⚠️ Immagine mancante. Invio il solo testo...")
        send_telegram(text)
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    payload = {"chat_id": CHAT_ID, "caption": text, "parse_mode": "HTML"}
    files = {"photo": (filename, photo_bytes)}
    
    try:
        res = requests.post(url, data=payload, files=files, timeout=25)
        if res.status_code == 200:
            print(f"🏁 File {filename} pubblicato con successo!")
        else:
            send_telegram(text)
    except Exception as e:
        send_telegram(text)

# ==============================================================================
# FUNZIONE AGGIORNAMENTO SECRET GITHUB
# ==============================================================================
def update_github_secret(secret_name, new_value):
    """Aggiorna programmaticamente un secret nella repository GitHub corrente."""
    if not GH_PAT or not GITHUB_REPOSITORY:
        print("⚠️ Impossibile aggiornare il secret: GH_PAT o GITHUB_REPOSITORY non presenti nell'ambiente.")
        return False

    headers = {
        "Authorization": f"Bearer {GH_PAT}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    pk_url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/secrets/public-key"
    try:
        res_pk = requests.get(pk_url, headers=headers, timeout=10)
        if res_pk.status_code != 200:
            print(f"❌ Impossibile ottenere la public key di GitHub: {res_pk.text}")
            return False
        
        pk_data = res_pk.json()
        key_id = pk_data["key_id"]
        public_key_b64 = pk_data["key"]

        public_key = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder)
        sealed_box = public.SealedBox(public_key)
        encrypted_value = sealed_box.encrypt(new_value.encode("utf-8"))
        encrypted_b64 = base64.b64encode(encrypted_value).decode("utf-8")

        secret_url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/secrets/{secret_name}"
        payload = {
            "encrypted_value": encrypted_b64,
            "key_id": key_id
        }
        
        res_secret = requests.put(secret_url, headers=headers, json=payload, timeout=10)
        if res_secret.status_code in [201, 204]:
            print(f"✅ Secret '{secret_name}' aggiornato con successo su GitHub per i prossimi match!")
            return True
        else:
            print(f"❌ Errore durante l'aggiornamento del secret su GitHub: {res_secret.text}")
            return False
    except Exception as e:
        print(f"❌ Eccezione durante l'aggiornamento del secret GitHub: {e}")
        return False

# ==============================================================================
# FUNZIONI INTEGRATE CANVA API
# ==============================================================================
def get_valid_token():
    """Genera un Access Token e aggiorna il Refresh Token se Canva ne fornisce uno nuovo."""
    if not CANVA_REFRESH_TOKEN:
        print("❌ Errore: CANVA_REFRESH_TOKEN non trovato.")
        return None

    print("🔄 Richiesta di un Access Token temporaneo a Canva...")
    url = "https://api.canva.com/rest/v1/oauth/token"
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": CANVA_REFRESH_TOKEN,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    
    try:
        res = requests.post(url, data=payload, timeout=15)
        if res.status_code == 200:
            new_tokens = res.json()
            print("✅ Access Token generato con successo!")
            
            if "refresh_token" in new_tokens and new_tokens["refresh_token"] != CANVA_REFRESH_TOKEN:
                print("🔄 Canva ha emesso un nuovo Refresh Token. Aggiorno GitHub Secrets...")
                update_github_secret("CANVA_REFRESH_TOKEN", new_tokens["refresh_token"])
                
            return new_tokens["access_token"]
        else:
            print(f"❌ Errore nel recupero del token Canva: {res.text}")
            return None
    except Exception as e:
        print(f"Errore connessione Canva OAuth: {e}")
        return None

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
                    download_url = urls_list[0] if urls_list else (status_data.get("url") or status_data.get("job", {}).get("url"))
                    
                    if download_url:
                        print("📥 Download file PNG completato.")
                        img_res = requests.get(download_url, timeout=20)
                        return img_res.content
                        
                elif status_corrente == "failed":
                    return None
                    
        print("❌ Timeout Canva.")
    except Exception as e:
        print(f"❌ Errore durante il recupero da Canva: {e}")
    return None

# ==============================================================================
# NUOVA FUNZIONE: GENERAZIONE SCREENSHOT STATISTICHE DA TEMPLATE HTML
# ==============================================================================
def invia_statistiche_match(match_id, score_string, logo_home, logo_away, tipo_periodo, hashtag, e_comp):
    print(f"⏳ Attendo 2 minuti prima di inviare le statistiche di fine {tipo_periodo}...")
    time.sleep(120)
    print(f"📊 Recupero statistiche da API-Football per il match ID {match_id}...")
    
    headers = {"x-apisports-key": API_KEY}
    url_stats = f"https://v3.football.api-sports.io/fixtures/statistics?fixture={match_id}"
    
    try:
        res = requests.get(url_stats, headers=headers, timeout=15).json()
        if not res.get('response') or len(res['response']) < 2:
            print("⚠️ Statistiche non disponibili o insufficienti.")
            return

        # API-Football restituisce una lista di 2 elementi (uno per squadra)
        stats_home = {item['type']: item['value'] for item in res['response'][0]['statistics']}
        stats_away = {item['type']: item['value'] for item in res['response'][1]['statistics']}
        
        # Prepariamo l'oggetto JSON da iniettare nell'HTML
        payload_js = {
            "score": score_string,
            "logo_l": logo_home,
            "logo_r": logo_away,
            "stats": [
                {"label": "Possesso Palla", "l": stats_home.get("Ball Possession", "50%"), "r": stats_away.get("Ball Possession", "50%")},
                {"label": "Tiri Totali", "l": stats_home.get("Total Shots", 0), "r": stats_away.get("Total Shots", 0)},
                {"label": "Tiri in Porta", "l": stats_home.get("Shots on Goal", 0), "r": stats_away.get("Shots on Goal", 0)},
                {"label": "Falli", "l": stats_home.get("Fouls", 0), "r": stats_away.get("Fouls", 0)},
                {"label": "Calci d'Angolo", "l": stats_home.get("Corner Kicks", 0), "r": stats_away.get("Corner Kicks", 0)},
                {"label": "Passaggi Totali", "l": stats_home.get("Total passes", 0), "r": stats_away.get("Total passes", 0)},
                {"label": "Precisione Passaggi", "l": stats_home.get("Passes %", "0%"), "r": stats_away.get("Passes %", "0%")}
            ]
        }

        # Leggiamo il template originale
        with open("template.html", "r", encoding="utf-8") as f:
            html_content = f.read()

        # Iniettiamo i dati dentro il tag script dedicato (che configureremo sotto)
        marker = "/* INJECT_DATA_HERE */"
        injection = f"const matchData = {json.dumps(payload_js)};"
        html_content = html_content.replace(marker, injection)

        # Salviamo un file temporaneo elaborato
        with open("temp_render.html", "w", encoding="utf-8") as f:
            f.write(html_content)

        print("📸 Generazione screenshot HTML in corso...")
        hti = Html2Image(browser='chrome', custom_flags=['--headless', '--no-sandbox', '--disable-gpu'])
        # Specifichiamo la dimensione esatta della card per non catturare spazio vuoto
        hti.screenshot(html_file='temp_render.html', save_as='stats.png', size=(540, 600))

        if os.path.exists("stats.png"):
            with open("stats.png", "rb") as img_file:
                img_bytes = img_file.read()
            
            msg = f"<b>STATISTICHE FINE {tipo_periodo.upper()} {E_CHART}</b>\n\n{e_comp} {hashtag}"
            send_telegram_with_photo(msg, photo_bytes=img_bytes, filename="stats.png")
            
            # Pulizia file temporanei
            os.remove("temp_render.html")
            os.remove("stats.png")
        else:
            print("❌ Errore: Screenshot non generato.")
            
    except Exception as e:
        print(f"❌ Errore durante la generazione delle statistiche: {e}")

# ==============================================================================

def build_split_scorers_text(events, home_id, away_id):
    if not events: return ""
    home_scorers, away_scorers = [], []
    
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

# ==============================================================================
# LOGICA DI GESTIONE E CICLO DEL MATCH LIVE
# ==============================================================================
def avvia_ciclo_partita():
    print("✅ Procedo al recupero del match...")

    if not API_KEY:
        print("Errore: API_KEY mancante.")
        return
        
    headers = {"x-apisports-key": API_KEY}
    url = "https://v3.football.api-sports.io/fixtures"
    match_id = None

    # [FASE 2]: RECUPERO ID PARTITA (CICLO CONTINUO FINCHÉ NON TROVA UN MATCH)
    while not match_id:
        today_date = datetime.now().strftime('%Y-%m-%d')
        print(f"🔄 [Controllo Palinsesto] Cerco partita della Juventus ({today_date})...")
        
        try:
            live_res = requests.get(f"{url}?live=all", headers=headers, timeout=10).json()
            if live_res.get('response'):
                for f in live_res['response']:
                    if f['teams']['home']['id'] == JUVE_ID or f['teams']['away']['id'] == JUVE_ID:
                        match_id = f['fixture']['id']
                        print(f"🔥 Match trovato già LIVE! Aggancio ID: {match_id}")
                        break
            
            if not match_id:
                date_res = requests.get(f"{url}?team={JUVE_ID}&date={today_date}", headers=headers, timeout=10).json()
                if date_res.get('response') and len(date_res['response']) > 0:
                    match_id = date_res['response'][0]['fixture']['id']
                    print(f"📅 Match trovato nel palinsesto di oggi! ID: {match_id}")

            if not match_id:
                next_res = requests.get(f"{url}?team={JUVE_ID}&next=1", headers=headers, timeout=10).json()
                if next_res.get('response') and len(next_res['response']) > 0:
                    match_data = next_res['response'][0]
                    match_id = match_data['fixture']['id']
                    print(f"📌 Agganciato il prossimo match in calendario. ID: {match_id} ({match_data['fixture']['date']})")

        except Exception as e:
            print(f"⚠️ Errore temporaneo nel recupero dei dati dall'API: {e}")

        if not match_id:
            print("❌ Nessun match trovato nel palinsesto. Rinvio richiesta tra 30 secondi...")
            time.sleep(30)

    print(f"⏳ Bot agganciato con successo all'ID {match_id}. Entro nel ciclo di monitoraggio eventi...")
    params = {"id": match_id}

    # [FASE 3]: CICLO EVENTI IN LIVE REALE (SI SPEGNE SOLO A FINE PARTITA)
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
                print(f"💤 Match ID {match_id} non ancora iniziato (Stato: {status}). Controllo tra 30 secondi...")
                time.sleep(30)
                continue
                
            league_id = match.get('league', {}).get('id', 0)
            current_sleep_time = 60 if status == "PEN" else (140 if status in ["ET", "AET"] else (120 if status == "HT" else (70 if league_id == 135 else 90)))
            
            e_comp = get_league_emoji(league_id)
            teams = match.get('teams', {})
            home_id, away_id = teams.get('home', {}).get('id', 0), teams.get('away', {}).get('id', 0)
            
            home_name = "Juventus" if home_id == JUVE_ID else clean_name(teams.get('home', {}).get('name', 'Home'))
            away_name = "Juventus" if away_id == JUVE_ID else clean_name(teams.get('away', {}).get('name', 'Away'))
            
            logo_home = teams.get('home', {}).get('logo', '')
            logo_away = teams.get('away', {}).get('logo', '')
            
            penalties = match.get('score', {}).get('penalty', {})
            p_home, p_away = penalties.get('home'), penalties.get('away')
            score_string = f"{g_home_int} ({p_home}) - ({p_away}) {g_away_int}" if p_home is not None else f"{g_home_int}-{g_away_int}"
            
            h_short = "Juve" if home_id == JUVE_ID else home_name.replace(" ", "")
            a_short = "Juve" if away_id == JUVE_ID else away_name.replace(" ", "")
            hashtag = f"#{h_short}{a_short}"
            
            print(f"[LIVE] {home_name} {score_string} {away_name} | Minuto: {elapsed_minutes}")

            if g_home_int > g_away_int:
                punteggio_periodo = f"<b>{home_name} {g_home_int}</b>-{g_away_int} {away_name}"
            elif g_away_int > g_home_int:
                punteggio_periodo = f"{home_name} {g_home_int}-<b>{g_away_int} {away_name}</b>"
            else:
                punteggio_periodo = f"{home_name} {g_home_int}-{g_away_int} {away_name}"

            # 1. CRONACA PERIODI
            if (status == "1H" or elapsed_minutes > 0) and "1H" not in state["sent_periods"]:
                send_telegram(f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{home_name} - {away_name}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("1H")
            elif status == "HT" and "HT" not in state["sent_periods"]:
                send_telegram(f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{punteggio_periodo}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("HT")
                # Update dello stato per evitare loop prima del thread/sleep delle statistiche
                with open("match_state.json", "w") as f: json.dump(state, f)
                invia_statistiche_match(match_id, f"{g_home_int}-{g_away_int}", logo_home, logo_away, "primo tempo", hashtag, e_comp)
            elif status == "2H" and "2H" not in state["sent_periods"]:
                send_telegram(f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n{punteggio_periodo}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("2H")
            elif status in ["ET", "AET", "PEN"] and "2H_END" not in state["sent_periods"]:
                send_telegram(f"<b>FINE SECONDO TEMPO {E_FLAG}</b>\n\n{punteggio_periodo}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("2H_END")

            # 2. RIGORI AD OLTRANZA
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
                    send_telegram(f"{home_name}: " + "".join(home_pen_icons) + f"\n{away_name}: " + "".join(away_pen_icons) + f"\n\n{e_comp} {hashtag}")
                    state["penalties_count"] = total_kicks

            # 3. FISCHIO FINALE -> GENERAZIONE GRAFICA E INVIO
            status_long = fixture.get('status', {}).get('long', '').lower()
            if status in ["FT", "AET", "PEN"] or "finished" in status_long:
                print("🏁 FISCHIO FINALE RILEVATO! Connessione a Canva per l'export...")
                scorers_line = build_split_scorers_text(match.get('events', []), home_id, away_id)
                
                if p_home is not None:
                    if int(p_home) > int(p_away):
                        punteggio_finale = f"<b>{home_name} {g_home_int} ({p_home})</b>-({p_away}) {g_away_int} {away_name}"
                    else:
                        punteggio_finale = f"{home_name} {g_home_int} ({p_home})-<b>({p_away}) {g_away_int} {away_name}</b>"
                else:
                    if g_home_int > g_away_int:
                        punteggio_finale = f"<b>{home_name} {g_home_int}</b>-{g_away_int} {away_name}"
                    elif g_away_int > g_home_int:
                        punteggio_finale = f"{home_name} {g_home_int}-<b>{g_away_int} {away_name}</b>"
                    else:
                        punteggio_finale = f"{home_name} {g_home_int}-{g_away_int} {away_name}"

                msg_finale = f"<b>FINE PARTITA {E_FLAG}</b>\n\n{punteggio_finale}\n{scorers_line}\n{e_comp} {hashtag}"
                
                canva_token_fresco = get_valid_token()
                if canva_token_fresco:
                    foto_canva = get_canva_image(canva_token_fresco)
                    send_telegram_with_photo(msg_finale, photo_bytes=foto_canva)
                else:
                    print("❌ Impossibile generare un token Canva valido al fischio finale. Invio solo testo.")
                    send_telegram(msg_finale)
                
                if os.path.exists("match_state.json"): 
                    os.remove("match_state.json")
                
                # Invio statistiche finali ritardate (il bot si chiude all'interno di questa chiamata dopo i 2 minuti)
                invia_statistiche_match(match_id, score_string if p_home is None else f"{g_home_int} ({p_home}) - ({p_away}) {g_away_int}", logo_home, logo_away, "partita", hashtag, e_comp)
                
                print("🏁 Messaggio di fine e statistiche inviati con successo. Spegnimento del bot.")
                sys.exit(0)

            # 4. GOL E UPDATE VAR
            total_goals_now = g_home_int + g_away_int
            if total_goals_now > state["goals_detected"]:
                events, live_scorer_line = match.get('events', []), ""
                
                if events:
                    all_goals = [e for e in events if e.get('type', '').lower() == 'goal' and "shootout" not in e.get('detail', '').lower()]
                    if all_goals:
                        all_goals.sort(key=lambda x: (x.get('time', {}).get('elapsed', 0), x.get('time', {}).get('extra', 0) or 0))
                        last_goal = all_goals[-1]
                        el, ex = last_goal.get('time', {}).get('elapsed', '?'), last_goal.get('time', {}).get('extra')
                        minute_str = f"{el}+{ex}" if ex else f"{el}"
                        p_name = last_goal.get('player', {}).get('name', 'Giocatore')
                        det = last_goal.get('detail', '').lower()
                        
                        if "penalty" in det: p_name += " (Rig.)"
                        elif "own goal" in det: p_name += " (Autogol)"
                        live_scorer_line = f"{E_BALL} <i>{minute_str}’ {p_name}</i>\n"
                
                if g_home_int > g_away_int:
                    punteggio_match = f"<b>{home_name} {g_home_int}</b>-{g_away_int} {away_name}"
                elif g_away_int > g_home_int:
                    punteggio_match = f"{home_name} {g_home_int}-<b>{g_away_int} {away_name}</b>"
                else:
                    scoring_team_id = last_goal.get('team', {}).get('id') if events and all_goals else None
                    if scoring_team_id == home_id:
                        punteggio_match = f"<b>{home_name} {g_home_int}</b>-{g_away_int} {away_name}"
                    elif scoring_team_id == away_id:
                        punteggio_match = f"{home_name} {g_home_int}-<b>{g_away_int} {away_name}</b>"
                    else:
                        punteggio_match = f"{home_name} {g_home_int}-{g_away_int} {away_name}"
                        
                send_telegram(f"<b>GOAL {E_MIC}</b>\n\n{punteggio_match}\n{live_scorer_line}\n{e_comp} {hashtag}")
                state["goals_detected"] = total_goals_now
            elif total_goals_now < state["goals_detected"]:
                send_telegram(f"<b>GOAL ANNULLATO 📺</b>\n\n{home_name} {g_home_int}-{g_away_int} {away_name}\n\n{e_comp} {hashtag}")
                state["goals_detected"] = total_goals_now

            # 5. CARTELLINI ROSSI E CAMBI
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

# ==============================================================================
def main():
    print("🚀 Avvio Live Score Bot: elaborazione eventi in corso...")
    if str(os.getenv('ONLY_REFRESH_TOKEN', '')).strip().lower() == "true":
        print("🔒 Modalità Keep-Alive: Rinnovo il token...")
        get_valid_token()
        print("🔒 Token aggiornato correttamente. Termino l'esecuzione.")
        return

    avvia_ciclo_partita()

if __name__ == "__main__":
    main()
