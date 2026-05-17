import os
import requests
import json
import time
import sys
from datetime import datetime

# ==============================================================================
# CONFIGURAZIONE (Secret di GitHub)
# ==============================================================================
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')
API_KEY = os.getenv('FOOTBALL_API_KEY')
CLIENT_ID = os.getenv('CANVA_CLIENT_ID')
CLIENT_SECRET = os.getenv('CANVA_CLIENT_SECRET')

# Configurazione Canva e ID Squadra
CANVA_DESIGN_ID = "DAHI3ytu6yQ"
PAGINA_TARGET = 11
MY_TEAM_ID = 496  # ID Juventus su API-Football
TOKEN_FILE = "canva_tokens.json"

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
    if not os.path.exists(TOKEN_FILE): return None
    with open(TOKEN_FILE, "r") as f: tokens = json.load(f)
    if tokens.get("expires_at", 0) - time.time() < 300:
        url = "https://api.canva.com/rest/v1/oauth/token"
        payload = {"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}
        try:
            res = requests.post(url, data=payload, timeout=15)
            if res.status_code == 200:
                new_tokens = res.json()
                tokens["access_token"] = new_tokens["access_token"]
                tokens["refresh_token"] = new_tokens.get("refresh_token", tokens["refresh_token"])
                tokens["expires_at"] = int(time.time()) + new_tokens["expires_in"]
                with open(TOKEN_FILE, "w") as f: json.dump(tokens, f, indent=2)
        except: return None
    return tokens["access_token"]

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
    print("🚀 AVVIO BOT REALE LIVE MATCH CON GRASSETTO DINAMICO SUI GOAL...")
    
    if not os.path.exists("match_state.json"):
        print("❌ Errore: Nessun match_state.json trovato. Esegui prima lo script di aggancio match.")
        return

    with open("match_state.json", "r") as f: state = json.load(f)
    match_id = state.get("live_match_id")
    if not match_id:
        print("❌ Errore: live_match_id assente nel file di stato.")
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
    hashtag = f"#{home_name.replace(' ', '')}{away_name.replace(' ', '')}"
    
    g_home_int = match.get('goals', {}).get('home') or 0
    g_away_int = match.get('goals', {}).get('away') or 0
    
    penalties = match.get('score', {}).get('penalty', {})
    p_home, p_away = penalties.get('home'), penalties.get('away')

    # Linea di stato standard con grassetto condizionale al vantaggio (per periodi)
    match_status_line = format_match_text(home_name, away_name, g_home_int, g_away_int)

    # 1. GESTIONE PERIODI DI GIOCO
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

    # 2. GESTIONE EVENTO GOAL LIVE (Bold fisso a chi segna)
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
                marcatore = f"{time_str}’ {p_name}"

                # Applica il grassetto alla squadra marcatrice dell'evento, anche in caso di pareggio
                if team_id_scorer == home_id:
                    current_home_name = f"<b>{home_name}</b>"
                    g_home_str = f"<b>{g_home_int}</b>"
                elif team_id_scorer == away_id:
                    current_away_name = f"<b>{away_name}</b>"
                    g_away_str = f"<b>{g_away_int}</b>"

        send_telegram(f"<b>GOAL {E_MIC}</b>\n\n{current_home_name} {g_home_str}-{g_away_str} {current_away_name}\n{E_BALL} <i>{marcatore}</i>\n\n🇮🇹 {hashtag}")
        state["goals_detected"] = total_goals_now

    # 3. CRONACA LOTTERIA DEI RIGORI LIVE
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
            msg_pen = f"<b>LOTTERIA DEI RIGORI 🎯</b>\n\n{home_name}: " + "".join(home_pen_icons) + f"\n{away_name}: " + "".join(away_pen_icons) + f"\n\n🇮🇹 {hashtag}"
            send_telegram(msg_pen)
            state["penalties_count"] = total_kicks

    # 4. FINE MATCH FINALE (Canva + Resoconto Marcatori Totali)
    if "finished" in status_long or status in ["FT", "AET"] or (status == "PEN" and p_home is not None):
        print("🏁 Fine della partita rilevata. Preparazione riepilogo finale...")
        
        # Estrazione marcatori ordinati per tabellino finale sotto la foto
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

        # Titolo personalizzato dinamico a seconda del risultato della tua squadra (Juventus)
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
        msg_finale = f"{title_prefix}\n\n{final_status_line}\n{scorers_line}\n\n🇮🇹 {hashtag}"
        
        # Export e pubblicazione con grafica Canva
        token = get_valid_token()
        foto = get_canva_image(token)
        send_telegram_post_with_photo(msg_finale, photo_bytes=foto)
        
        if os.path.exists("match_state.json"): os.remove("match_state.json")
        print("🏁 Flusso terminato con successo. File di stato rimosso.")
        return

    # Salvataggio dello stato per l'esecuzione successiva
    with open("match_state.json", "w") as f: json.dump(state, f)

if __name__ == "__main__":
    main()
