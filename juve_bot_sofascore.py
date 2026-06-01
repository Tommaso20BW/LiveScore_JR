import os
import requests
import json
import time
import sys
import base64
from PIL import Image
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

try:
    from nacl import encoding, public
except ImportError:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  pynacl non installata — aggiornamento Secrets GitHub non disponibile")

# ==============================================================================
# CONFIGURAZIONE
# ==============================================================================
BOT_TOKEN           = os.getenv('TELEGRAM_TOKEN')
CHAT_ID             = os.getenv('TELEGRAM_TO')
TEAM_ID             = os.getenv('TEAM_ID', '6081')        # SofaScore ID Juventus = 2697
GH_PAT              = os.getenv('GH_PAT')
GITHUB_REPOSITORY   = os.getenv('GITHUB_REPOSITORY')
GIST_ID             = os.getenv('GIST_ID')
CLIENT_ID           = os.getenv('CANVA_CLIENT_ID')
CLIENT_SECRET       = os.getenv('CANVA_CLIENT_SECRET')
CANVA_REFRESH_TOKEN = os.getenv('CANVA_REFRESH_TOKEN')

CANVA_DESIGN_ID = "DAHI3ytu6yQ"
PAGINA_TARGET   = 11

# SofaScore base URL
SOFA_BASE = "https://api.sofascore.com/api/v1"

# Headers per simulare Firefox (necessari per SofaScore)
SOFA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
        "Gecko/20100101 Firefox/125.0"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer":         "https://www.sofascore.com/",
    "Origin":          "https://www.sofascore.com",
    "DNT":             "1",
    "Connection":      "keep-alive",
}

# Mapping SofaScore tournament slug (usato solo per emoji e nomi leggibili)
TOURNAMENT_EMOJIS = {
    # Italia
    8:    "🇮🇹",   # Serie A
    35:   "🇮🇹",   # Coppa Italia
    620:  "🇮🇹",   # Supercoppa Italiana
    # Europa
    7:    "🇪🇺",   # Champions League
    679:  "🇪🇺",   # Europa League
    17015:"🇪🇺",   # Conference League
    # Inghilterra
    17:   "🏴󠁧󠁢󠁥󠁮󠁧󠁿",  # Premier League
    19:   "🏴󠁧󠁢󠁥󠁮󠁧󠁿",  # FA Cup
    21:   "🏴󠁧󠁢󠁥󠁮󠁧󠁿",  # EFL Cup
    # Spagna
    8:    "🇪🇸",   # La Liga (id diverso in Sofa, uso come fallback)
    329:  "🇪🇸",   # Copa del Rey
    # Germania
    35:   "🇩🇪",   # Bundesliga
    # Francia
    34:   "🇫🇷",   # Ligue 1
    # Mondiali / Nazionali
    16:   "🌍",    # FIFA World Cup
    1:    "🌍",    # Amichevoli
}

def get_tournament_emoji(tournament_id: int) -> str:
    return TOURNAMENT_EMOJIS.get(tournament_id, "⚽️")

E_BOLT   = '⚡️'
E_FLAG   = '🏁'
E_MIC    = '🎙'
E_BALL   = '⚽️'
E_SUB    = '🔄'
E_UP     = '🔺'
E_DOWN   = '🔻'
E_RED    = '🟥'
E_PEN_OK = '✅'
E_PEN_KO = '❌'
E_ASSIST = '🅰️'
E_KICK   = '🥅'
E_EXIT   = '🔚'
E_STATS  = '📊'
E_CANCEL = '📺'

MOMENTI_CONFIG = {
    "HT":     {"titolo": f"<b>STATS PRIMO TEMPO</b> {E_STATS}",   "badge": "FINE PRIMO TEMPO"},
    "2H_END": {"titolo": f"<b>STATS SECONDO TEMPO</b> {E_STATS}", "badge": "FINE SECONDO TEMPO"},
    "FT":     {"titolo": f"<b>STATS FINE PARTITA</b> {E_STATS}",  "badge": "FINE PARTITA"},
}

# Mapping tipo evento SofaScore → tipo interno
# SofaScore usa "incidentType" e "incidentClass" nei dettagli partita
INCIDENT_MAP = {
    "goal":                  "goal",
    "own goal":              "own goal",
    "owngoal":               "own goal",
    "penalty":               "penalty goal",
    "penalty goal":          "penalty goal",
    "missed penalty":        "penalty missed",
    "saved penalty":         "penalty saved",
    "yellow card":           "yellow card",
    "red card":              "red card",
    "yellow red card":       "second yellow card",   # doppio giallo → rosso
    "second yellow":         "second yellow card",
    "substitution":          "substitution",
    "in":                    "substitution",
    "out":                   "substitution",
}

def normalize_incident(incident_type: str, incident_class: str = "") -> str:
    """Normalizza il tipo di incidente SofaScore."""
    combined = f"{incident_type} {incident_class}".strip().lower()
    # Cerca prima la stringa combinata
    for k, v in sorted(INCIDENT_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if k in combined:
            return v
    # Poi il solo tipo
    t = incident_type.strip().lower()
    for k, v in sorted(INCIDENT_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if k in t:
            return v
    return t

def fmt_player(full_name: str) -> str:
    if not full_name:
        return "N/A"
    parts = full_name.strip().split()
    if len(parts) == 1:
        return parts[0]
    return parts[0][0].upper() + ". " + " ".join(parts[1:])

# ==============================================================================
# TELEGRAM
# ==============================================================================
def send_telegram(text: str):
    if not BOT_TOKEN or not CHAT_ID:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  BOT_TOKEN o CHAT_ID mancanti")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Errore send_telegram: {e}")

def send_telegram_edit(message_id: int, text: str):
    if not BOT_TOKEN or not CHAT_ID or not message_id:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    try:
        r = requests.post(url, json={
            "chat_id": CHAT_ID, "message_id": message_id,
            "text": text, "parse_mode": "HTML"
        }, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Errore editMessageText: {e}")

def send_telegram_get_id(text: str) -> int | None:
    if not BOT_TOKEN or not CHAT_ID:
        return None
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
        r.raise_for_status()
        return r.json().get("result", {}).get("message_id")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Errore send_telegram_get_id: {e}")
        return None

def send_telegram_with_photo(text: str, photo_bytes):
    if not photo_bytes:
        send_telegram(text)
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        r = requests.post(url, data={"chat_id": CHAT_ID, "caption": text, "parse_mode": "HTML"},
                          files={"photo": ("matchday.png", photo_bytes)}, timeout=25)
        if r.status_code != 200:
            send_telegram(text)
    except Exception:
        send_telegram(text)

def send_telegram_stats_photo(png_path: str, momento: str, hashtag: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    caption = f"{MOMENTI_CONFIG[momento]['titolo']}\n\n{hashtag}"
    try:
        with open(png_path, "rb") as f:
            requests.post(url, data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "HTML"},
                          files={"photo": ("stats.png", f, "image/png")}, timeout=25)
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Errore invio foto statistiche: {e}")

# ==============================================================================
# GITHUB SECRETS
# ==============================================================================
def update_github_secret(secret_name: str, new_value: str):
    if not GH_PAT or not GITHUB_REPOSITORY:
        return False
    headers = {
        "Authorization": f"Bearer {GH_PAT}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    try:
        pk = requests.get(f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/secrets/public-key",
                          headers=headers, timeout=10).json()
        pub_key = public.PublicKey(pk["key"].encode("utf-8"), encoding.Base64Encoder)
        encrypted = base64.b64encode(public.SealedBox(pub_key).encrypt(new_value.encode())).decode()
        r = requests.put(f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/secrets/{secret_name}",
                         headers=headers, json={"encrypted_value": encrypted, "key_id": pk["key_id"]}, timeout=10)
        return r.status_code in [201, 204]
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Errore update GitHub secret: {e}")
    return False

# ==============================================================================
# GIST
# ==============================================================================
def _gist_headers():
    return {"Authorization": f"Bearer {GH_PAT}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}

def leggi_stato_da_gist():
    if not GH_PAT or not GIST_ID:
        return None
    try:
        r = requests.get(f"https://api.github.com/gists/{GIST_ID}", headers=_gist_headers(), timeout=10)
        if r.status_code != 200:
            return None
        content = r.json()["files"]["match_state.json"]["content"].strip()
        if not content or content == "{}":
            return None
        return json.loads(content)
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Errore lettura Gist: {e}")
        return None

def salva_stato_su_gist(state: dict):
    if not GH_PAT or not GIST_ID:
        return
    try:
        payload = {"files": {"match_state.json": {"content": json.dumps(state, ensure_ascii=False, indent=2)}}}
        requests.patch(f"https://api.github.com/gists/{GIST_ID}", headers=_gist_headers(),
                       json=payload, timeout=10)
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Errore salvataggio Gist: {e}")

def resetta_gist():
    if not GH_PAT or not GIST_ID:
        return
    try:
        payload = {"files": {"match_state.json": {"content": "{}"}}}
        requests.patch(f"https://api.github.com/gists/{GIST_ID}", headers=_gist_headers(),
                       json=payload, timeout=10)
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Errore reset Gist: {e}")

# ==============================================================================
# CANVA
# ==============================================================================
def get_valid_token():
    if not CANVA_REFRESH_TOKEN:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ CANVA_REFRESH_TOKEN mancante")
        return None
    try:
        r = requests.post("https://api.canva.com/rest/v1/oauth/token", data={
            "grant_type": "refresh_token", "refresh_token": CANVA_REFRESH_TOKEN,
            "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET
        }, timeout=15)
        if r.status_code == 200:
            tokens = r.json()
            if "refresh_token" in tokens and tokens["refresh_token"] != CANVA_REFRESH_TOKEN:
                update_github_secret("CANVA_REFRESH_TOKEN", tokens["refresh_token"])
            return tokens["access_token"]
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Errore token Canva: {r.text}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Errore connessione Canva: {e}")
    return None

def get_canva_image(access_token: str):
    if not access_token:
        return None
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    try:
        r = requests.post("https://api.canva.com/rest/v1/exports", headers=headers, json={
            "design_id": CANVA_DESIGN_ID, "format": {"type": "png", "pages": [PAGINA_TARGET]}
        }, timeout=15)
        if r.status_code not in [200, 201]:
            return None
        job_data = r.json()
        job_id = job_data.get("id") or job_data.get("job", {}).get("id")
        if not job_id:
            return None
        status_url = f"https://api.canva.com/rest/v1/exports/{job_id}"
        time.sleep(3)
        for _ in range(60):
            time.sleep(3)
            check = requests.get(status_url, headers=headers, timeout=15)
            if check.status_code == 200:
                d = check.json()
                stato = d.get("status") or d.get("job", {}).get("status")
                if stato == "success":
                    urls = d.get("urls") or d.get("job", {}).get("urls")
                    url_dl = urls[0] if urls else (d.get("url") or d.get("job", {}).get("url"))
                    if url_dl:
                        time.sleep(10)
                        return requests.get(url_dl, timeout=30).content
                elif stato == "failed":
                    return None
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Errore export Canva: {e}")
    return None

# ==============================================================================
# SOFASCORE API  (tramite Playwright Firefox per bypassare i blocchi bot)
# ==============================================================================

def _sofa_fetch(path: str, retries: int = 3) -> dict | None:
    """
    Esegue una richiesta a SofaScore tramite Playwright Firefox.
    Questo è l'unico modo affidabile per bypassare i controlli anti-bot di SofaScore
    su ambienti server (GitHub Actions incluso).
    """
    url = f"{SOFA_BASE}{path}"
    for attempt in range(retries):
        try:
            with sync_playwright() as p:
                browser = p.firefox.launch(headless=True)
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
                        "Gecko/20100101 Firefox/125.0"
                    ),
                    locale="it-IT",
                    extra_http_headers={
                        "Accept":          "application/json, text/plain, */*",
                        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8",
                        "Referer":         "https://www.sofascore.com/",
                        "DNT":             "1",
                    },
                )
                page = context.new_page()
                # Prima visita la home per impostare i cookie, poi la API
                try:
                    page.goto("https://www.sofascore.com/", wait_until="domcontentloaded", timeout=20000)
                except Exception:
                    pass
                response = page.goto(url, wait_until="domcontentloaded", timeout=20000)
                if response and response.status == 200:
                    body = page.evaluate("() => document.body.innerText")
                    browser.close()
                    return json.loads(body)
                browser.close()
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  SofaScore fetch tentativo {attempt+1}/{retries}: {e}")
            time.sleep(3)
    return None


def _sofa_fetch_requests(path: str) -> dict | None:
    """Fallback leggero con requests (funziona solo se non bloccato)."""
    url = f"{SOFA_BASE}{path}"
    try:
        r = requests.get(url, headers=SOFA_HEADERS, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def sofa_get(path: str) -> dict | None:
    """Prima prova requests (più veloce), poi Playwright se bloccato."""
    data = _sofa_fetch_requests(path)
    if data is not None:
        return data
    return _sofa_fetch(path)


# ==============================================================================
# TROVA PARTITA (SofaScore)
# ==============================================================================

def trova_partita_oggi(team_id: str) -> dict | None:
    """
    Cerca eventi del team nei ±1 giorno usando l'endpoint SofaScore
    /team/{id}/events/next/0  e  /team/{id}/events/last/0
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔍 Cerco partita per team_id={team_id} su SofaScore...")

    # Prova prima next event, poi last event
    endpoints = [
        f"/team/{team_id}/events/next/0",
        f"/team/{team_id}/events/last/0",
    ]

    now_utc   = datetime.now(timezone.utc)
    window_s  = 86400  # ±24h

    for ep in endpoints:
        data = sofa_get(ep)
        if not data:
            continue
        events = data.get("events", [])
        for event in events:
            start_ts = event.get("startTimestamp", 0)
            diff = abs(now_utc.timestamp() - start_ts)
            if diff <= window_s:
                t_id   = event.get("tournament", {}).get("id", 0)
                t_name = event.get("tournament", {}).get("name", "Sconosciuto")
                category = event.get("tournament", {}).get("category", {}).get("name", "")
                match_id   = event.get("id")
                home_team  = event.get("homeTeam", {})
                away_team  = event.get("awayTeam", {})
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Partita trovata: {t_name} — "
                      f"{home_team.get('name','?')} vs {away_team.get('name','?')} — event_id={match_id}")
                return {
                    "event_id":       str(match_id),
                    "tournament_id":  t_id,
                    "tournament_name": t_name,
                    "category":       category,
                    "home_id":        str(home_team.get("id", "")),
                    "away_id":        str(away_team.get("id", "")),
                    "home_name":      home_team.get("name", "Home"),
                    "away_name":      away_team.get("name", "Away"),
                    "start_ts":       start_ts,
                }
    return None


# ==============================================================================
# FETCH EVENTO LIVE  (SofaScore)
# ==============================================================================

def fetch_evento(event_id: str) -> dict | None:
    """Recupera i dettagli live di un evento SofaScore."""
    return sofa_get(f"/event/{event_id}")


def fetch_incidents(event_id: str) -> list:
    """Recupera tutti gli incidenti (gol, cartellini, cambi, ecc.) di un evento."""
    data = sofa_get(f"/event/{event_id}/incidents")
    if not data:
        return []
    return data.get("incidents", [])


def fetch_statistics(event_id: str) -> dict:
    """
    Recupera le statistiche di un evento SofaScore.
    Restituisce {"home": {...}, "away": {...}}
    """
    data = sofa_get(f"/event/{event_id}/statistics")
    result = {"home": {}, "away": {}}
    if not data:
        return result
    for period in data.get("statistics", []):
        for group in period.get("groups", []):
            for item in group.get("statisticsItems", []):
                key = item.get("key", "").lower()
                if not key:
                    continue
                h_val = item.get("home", "0")
                a_val = item.get("away", "0")
                # Teniamo il valore del primo periodo trovato che non sia 0
                if key not in result["home"] or str(result["home"][key]) in ("0", "0%", ""):
                    result["home"][key] = h_val
                    result["away"][key] = a_val
    return result


# ==============================================================================
# PARSE STATUS  (SofaScore)
# ==============================================================================

def parse_status_sofa(event_data: dict) -> tuple[str, int]:
    """
    Converte lo stato SofaScore nel formato interno usato dal bot.
    Ritorna (status_code, elapsed_minutes)

    Status codes interni:
      NS       = non iniziata
      1H       = primo tempo
      HT       = intervallo
      2H       = secondo tempo
      ET       = supplementari
      HT_ET    = intervallo supplementari
      PEN      = rigori
      AET      = fine dopo supplementari (post)
      FT       = fine partita
    """
    try:
        event = event_data.get("event", event_data)
        status = event.get("status", {})
        code   = status.get("code", 0)
        desc   = status.get("description", "").lower()
        period = event.get("lastPeriod", "")  # es. "1st", "2nd", "overtime", "penalties"
        minutes = event.get("statusTime", {}).get("initial", 0) // 60

        # SofaScore status codes:
        # 0  = Not started
        # 6  = 1st half
        # 7  = Halftime
        # 8  = 2nd half
        # 9  = Extra time (1st)
        # 10 = Extra time halftime
        # 11 = Extra time (2nd)
        # 30 = After extra time (result determined)
        # 31 = Penalties
        # 100 = Ended (FT)
        # 120 = Ended after extra time
        # 110 = Ended after penalties

        if code == 0:
            return "NS", 0
        if code == 6:
            return "1H", minutes
        if code == 7:
            return "HT", 45
        if code == 8:
            return "2H", minutes
        if code in (9, 11):
            return "ET", minutes
        if code == 10:
            return "HT_ET", 105
        if code == 31:
            return "PEN", 120
        if code in (30, 120):
            return "AET", 120
        if code == 110:
            return "PEN", 120
        if code == 100:
            return "FT", 90

        # Fallback su descrizione testuale
        if "not started" in desc:
            return "NS", 0
        if "halftime" in desc or "half time" in desc:
            return "HT", 45
        if "ended" in desc or "finished" in desc or "full time" in desc:
            return "FT", 90
        if "penalties" in desc:
            return "PEN", 120
        if "extra" in desc:
            return "ET", minutes
        if "1st" in desc or "first" in desc:
            return "1H", minutes
        if "2nd" in desc or "second" in desc:
            return "2H", minutes

        return "NS", 0
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Errore parse_status_sofa: {e}")
        return "NS", 0


# ==============================================================================
# PARSE SCORE  (SofaScore)
# ==============================================================================

def parse_score_sofa(event_data: dict) -> tuple[int, int]:
    """Ritorna (home_goals, away_goals) dall'evento SofaScore."""
    try:
        event = event_data.get("event", event_data)
        hs = event.get("homeScore", {})
        as_ = event.get("awayScore", {})
        # Preferisci current score, poi display, poi 0
        g_home = int(hs.get("current", hs.get("display", 0)) or 0)
        g_away = int(as_.get("current", as_.get("display", 0)) or 0)
        return g_home, g_away
    except Exception:
        return 0, 0


# ==============================================================================
# PARSE EVENTS / INCIDENTS  (SofaScore)
# ==============================================================================

def parse_events_sofa(incidents: list, home_id: str, away_id: str) -> list:
    """
    Converte gli incidenti SofaScore nel formato eventi interno.
    Struttura incidente SofaScore (esempio):
      {
        "incidentType": "goal",            # "goal" | "card" | "substitution" | "period" | ...
        "incidentClass": "",               # "ownGoal" | "penalty" | "yellowCard" | "redCard" | "yellowRedCard" | ...
        "time": 23,
        "addedTime": 2,                    # tempo di recupero
        "isHome": true,
        "player": {"name": "Vlahovic", "id": 12345},
        "playerIn": {"name": "Milik", "id": 67890},   # per sostituzioni
        "assist1": {"name": "Yildiz", "id": 99999},
        "id": 111222,
        "reversedPeriodTime": 67,
        ...
      }
    """
    events   = []
    seen_ids = set()

    for inc in incidents:
        try:
            inc_type  = inc.get("incidentType", "").lower()
            inc_class = inc.get("incidentClass", "").lower()
            inc_id    = str(inc.get("id", ""))

            # Saltiamo gli incidenti di periodo (inizio/fine tempo)
            if inc_type == "period" or inc_type == "injurytime":
                continue

            # Deduplication
            if inc_id and inc_id in seen_ids:
                continue
            if inc_id:
                seen_ids.add(inc_id)

            is_home  = inc.get("isHome", True)
            team_id  = home_id if is_home else away_id
            time_min = inc.get("time", 0)
            added    = inc.get("addedTime", 0)
            minute   = time_min + (added if added else 0)

            # --- Gol ---
            if inc_type == "goal":
                player_name = inc.get("player", {}).get("name", "")
                assist_name = inc.get("assist1", {}).get("name", "")

                # Determina il sottotipo
                if inc_class == "owngoal":
                    norm = "own goal"
                elif inc_class == "penalty":
                    norm = "penalty goal"
                else:
                    norm = "goal"

                events.append({
                    "type":        norm,
                    "minute":      minute,
                    "team_id":     team_id,
                    "player_name": player_name,
                    "assist_name": assist_name,
                    "uid":         inc_id or f"goal_{minute}_{player_name}",
                })

            # --- Cartellini ---
            elif inc_type == "card":
                player_name = inc.get("player", {}).get("name", "")
                if inc_class in ("yellowredcard", "yellowred", "yellow_red"):
                    norm = "second yellow card"
                elif inc_class == "redcard" or inc_class == "red":
                    norm = "red card"
                else:
                    norm = "yellow card"

                events.append({
                    "type":        norm,
                    "minute":      minute,
                    "team_id":     team_id,
                    "player_name": player_name,
                    "assist_name": "",
                    "uid":         inc_id or f"card_{minute}_{player_name}",
                })

            # --- Sostituzioni ---
            elif inc_type == "substitution":
                player_out = inc.get("playerOut", inc.get("player", {})).get("name", "")
                player_in  = inc.get("playerIn", {}).get("name", "")
                events.append({
                    "type":        "substitution",
                    "minute":      minute,
                    "team_id":     team_id,
                    "player_name": player_out,   # chi esce
                    "assist_name": player_in,    # chi entra
                    "uid":         inc_id or f"sub_{minute}_{player_out}",
                })

            # --- Rigori dal dischetto (shootout) ---
            elif inc_type == "penaltyshotout" or inc_type == "penalty_shootout" or \
                 (inc_type == "goal" and inc.get("isPenaltyShootout")):
                player_name = inc.get("player", {}).get("name", "")
                scored      = inc.get("scored", inc.get("didScore", False))
                saved       = inc.get("saved", False)
                if scored:
                    norm = "shootout goal"
                elif saved:
                    norm = "shootout saved"
                else:
                    norm = "shootout miss"
                events.append({
                    "type":        norm,
                    "minute":      120,
                    "team_id":     team_id,
                    "player_name": player_name,
                    "assist_name": "",
                    "uid":         inc_id or f"shootout_{team_id}_{player_name}",
                })

            # --- Rigori sbagliati durante la partita ---
            elif inc_type == "missedpenalty" or inc_class in ("missedpenalty", "savedpenalty"):
                player_name = inc.get("player", {}).get("name", "")
                if "saved" in inc_class:
                    norm = "penalty saved"
                else:
                    norm = "penalty missed"
                events.append({
                    "type":        norm,
                    "minute":      minute,
                    "team_id":     team_id,
                    "player_name": player_name,
                    "assist_name": "",
                    "uid":         inc_id or f"failpen_{minute}_{player_name}",
                })

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Errore parsing incident: {e}")

    return events


# ==============================================================================
# STATISTICHE  (SofaScore)
# ==============================================================================

def recupera_e_genera_stats_html(
    event_id: str,
    home_id: str, away_id: str,
    home_name: str, away_name: str,
    home_goals: int, away_goals: int,
    momento: str,
    league_name: str = "SERIE A",
    pen_home: int = 0, pen_away: int = 0
) -> str:
    """Genera l'immagine statistiche usando dati SofaScore + Playwright Firefox per lo screenshot."""

    JUVE_ID   = str(TEAM_ID)
    JUVE_LOGO = "https://upload.wikimedia.org/wikipedia/commons/9/99/Juventus_FC_2017_squared_icon_%28white%29.png"

    def sofa_logo(team_id_str: str) -> str:
        if team_id_str == JUVE_ID:
            return JUVE_LOGO
        return f"https://api.sofascore.app/api/v1/team/{team_id_str}/image"

    h_logo      = sofa_logo(home_id)
    a_logo      = sofa_logo(away_id)
    badge_label = MOMENTI_CONFIG[momento]["badge"]
    if momento == "FT" and (pen_home > 0 or pen_away > 0):
        badge_label = "FINE PARTITA d.c.r."

    raw = fetch_statistics(event_id)

    def g(side, *keys, fallback="0"):
        for key in keys:
            val = raw[side].get(key.lower())
            if val is not None and str(val) not in ("0", "", "0.0", "0%", "0.0%"):
                return val
        for key in keys:
            val = raw[side].get(key.lower())
            if val is not None:
                return val
        return fallback

    def perc(h_val, a_val):
        try:
            h = float(str(h_val).replace("%", "").strip())
            a = float(str(a_val).replace("%", "").strip())
            return 50 if (h + a) == 0 else int(h / (h + a) * 100)
        except Exception:
            return 50

    def fmt_pct(val):
        try:
            v = float(str(val).replace("%", "").strip())
            if v <= 1.0:
                return f"{int(v*100)}%"
            return f"{int(v)}%"
        except Exception:
            return str(val)

    # Chiavi SofaScore per le statistiche
    pos_h_raw  = g("home", "ballPossession", "possession", fallback="50")
    pos_a_raw  = g("away", "ballPossession", "possession", fallback="50")
    pos_h      = fmt_pct(pos_h_raw)
    pos_a      = fmt_pct(pos_a_raw)
    try:
        bp_perc = int(float(str(pos_h_raw).replace("%", "")))
        if bp_perc <= 1:
            bp_perc = int(bp_perc * 100)
    except Exception:
        bp_perc = 50

    sot_h    = g("home", "onTargetScoringAttempt", "shotsOnGoal", fallback="0")
    sot_a    = g("away", "onTargetScoringAttempt", "shotsOnGoal", fallback="0")
    shots_h  = g("home", "totalScoringAttempts",   "totalShots",  fallback="0")
    shots_a  = g("away", "totalScoringAttempts",   "totalShots",  fallback="0")
    falli_h  = g("home", "foulsCommited",   "fouls",      fallback="0")
    falli_a  = g("away", "foulsCommited",   "fouls",      fallback="0")
    gialli_h = g("home", "yellowCards",               fallback="0")
    gialli_a = g("away", "yellowCards",               fallback="0")
    rossi_h  = g("home", "redCards",                  fallback="0")
    rossi_a  = g("away", "redCards",                  fallback="0")
    corner_h = g("home", "cornerKicks",    "corners",   fallback="0")
    corner_a = g("away", "cornerKicks",    "corners",   fallback="0")
    saves_h  = g("home", "saves",                     fallback="0")
    saves_a  = g("away", "saves",                     fallback="0")
    offside_h = g("home", "offsideTrap", "offside",   fallback="0")
    offside_a = g("away", "offsideTrap", "offside",   fallback="0")
    blk_h    = g("home", "blockedScoringAttempt", "blockedShots", fallback="0")
    blk_a    = g("away", "blockedScoringAttempt", "blockedShots", fallback="0")
    pass_h   = g("home", "totalPasses",  "passes",    fallback="0")
    pass_a   = g("away", "totalPasses",  "passes",    fallback="0")
    passpct_h = fmt_pct(g("home", "accuratePasses",  "passAccuracy", fallback="0"))
    passpct_a = fmt_pct(g("away", "accuratePasses",  "passAccuracy", fallback="0"))

    stats_mappate = [
        ("Possesso palla",      pos_h,     pos_a,     bp_perc),
        ("Tiri in porta",       sot_h,     sot_a,     perc(sot_h,     sot_a)),
        ("Tiri totali",         shots_h,   shots_a,   perc(shots_h,   shots_a)),
        ("Tiri bloccati",       blk_h,     blk_a,     perc(blk_h,     blk_a)),
        ("Corner",              corner_h,  corner_a,  perc(corner_h,  corner_a)),
        ("Fuorigioco",          offside_h, offside_a, perc(offside_h, offside_a)),
        ("Falli",               falli_h,   falli_a,   perc(falli_h,   falli_a)),
        ("Ammoniti",            gialli_h,  gialli_a,  perc(gialli_h,  gialli_a)),
        ("Espulsi",             rossi_h,   rossi_a,   perc(rossi_h,   rossi_a)),
        ("Parate",              saves_h,   saves_a,   perc(saves_h,   saves_a)),
        ("Passaggi totali",     pass_h,    pass_a,    perc(pass_h,    pass_a)),
        ("Precisione passaggi", passpct_h, passpct_a, perc(
            str(passpct_h).replace("%",""), str(passpct_a).replace("%",""))),
    ]

    rows_html = "".join([f'''
<div class="stat-row">
  <div class="stat-top">
    <div class="val home-val">{h}</div>
    <div class="stat-label">{label}</div>
    <div class="val away-val">{a}</div>
  </div>
  <div class="bar-track">
    <div class="bar-home" style="width:{hp}%"></div>
    <div class="bar-away" style="width:{100-hp}%"></div>
  </div>
</div>
''' for label, h, a, hp in stats_mappate])

    if pen_home > 0 or pen_away > 0:
        score_block_html = (
            f'<div class="score">{home_goals} \u2013 {away_goals}</div>'
            f'<div class="pen-score">({pen_home} - {pen_away})</div>'
        )
    else:
        score_block_html = f'<div class="score">{home_goals} \u2013 {away_goals}</div>'

    html_content = f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Barlow+Condensed:wght@700;900&display=swap" rel="stylesheet">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  width: 1620px; height: 1980px;
  background:
    radial-gradient(circle at top left, #1e3a8a 0%, transparent 40%),
    radial-gradient(circle at bottom right, #7c3aed 0%, transparent 40%),
    #060816;
  font-family: 'Inter', sans-serif;
  display: flex;
  align-items: center;
  justify-content: center;
}}
.card {{
  width: 1500px; height: 1900px;
  background: linear-gradient(180deg, rgba(17,24,39,0.96), rgba(10,14,28,0.96));
  border-radius: 50px; overflow: hidden;
  border: 3px solid rgba(255,255,255,0.08);
  box-shadow: 0 50px 100px rgba(0,0,0,0.6), inset 0 2px 0 rgba(255,255,255,0.04);
  display: flex; flex-direction: column;
}}
.header {{
  padding: 55px 80px 40px;
  border-bottom: 2px solid rgba(255,255,255,0.06);
  flex-shrink: 0;
}}
.league-row {{ text-align: center; color: #7c8cb5; font-size: 26px; letter-spacing: 5px; text-transform: uppercase; font-weight: 700; margin-bottom: 25px; }}
.badge {{ width: fit-content; margin: 0 auto 30px; padding: 12px 36px; border-radius: 999px; background: linear-gradient(135deg, #facc15, #f59e0b); color: #111827; font-size: 20px; font-weight: 900; letter-spacing: 3px; text-transform: uppercase; }}
.teams-row {{ display: flex; align-items: center; justify-content: space-between; padding: 0 20px; }}
.team {{ width: 320px; text-align: center; }}
.logo {{ width: 150px; height: 150px; object-fit: contain; display: block; margin: 0 auto 20px; }}
.team-name {{ color: white; font-weight: 800; font-size: 34px; }}
.score-wrap {{ text-align: center; }}
.score {{ font-family: 'Barlow Condensed', sans-serif; font-size: 170px; line-height: 0.85; font-weight: 900; color: white; letter-spacing: -4px; }}
.pen-score {{ font-family: 'Barlow Condensed', sans-serif; font-size: 40px; line-height: 1.1; font-weight: 700; color: #8fa1c7; text-align: center; margin-top: 8px; }}
.match-status {{ margin-top: 16px; color: #8fa1c7; font-size: 22px; font-weight: 600; text-transform: uppercase; letter-spacing: 2px; }}
.stats-body {{
  flex: 1;
  padding: 0 80px;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
}}
.stats-title {{ text-align: center; color: #91a4d0; font-size: 24px; font-weight: 800; letter-spacing: 4px; text-transform: uppercase; }}
.stat-row {{ }}
.stat-top {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }}
.val {{ width: 120px; color: white; font-weight: 900; font-size: 40px; font-family: 'Barlow Condensed', sans-serif; }}
.home-val {{ text-align: left; }}
.away-val {{ text-align: right; }}
.stat-label {{ color: #b4c0df; font-size: 26px; font-weight: 700; }}
.bar-track {{ position: relative; height: 16px; border-radius: 999px; overflow: hidden; background: rgba(255,255,255,0.06); }}
.bar-home, .bar-away {{ position: absolute; top: 0; height: 100%; }}
.bar-home {{ left: 0; background: linear-gradient(90deg, #60a5fa, #2563eb); }}
.bar-away {{ right: 0; background: linear-gradient(90deg, #ef4444, #dc2626); }}
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <div class="league-row">{league_name.upper()}</div>
    <div class="badge">{badge_label}</div>
    <div class="teams-row">
      <div class="team"><img src="{h_logo}" class="logo"><div class="team-name">{home_name}</div></div>
      <div class="score-wrap">{score_block_html}<div class="match-status">LIVE STATS</div></div>
      <div class="team"><img src="{a_logo}" class="logo"><div class="team-name">{away_name}</div></div>
    </div>
  </div>
  <div class="stats-body">
    <div class="stats-title">STATISTICHE ANALITICHE</div>
    {rows_html}
  </div>
</div>
</body>
</html>"""

    path_html      = "/tmp/stats.html"
    path_raw_png   = "/tmp/stats_raw.png"
    path_final_png = "/tmp/stats_final.png"

    with open(path_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    # Screenshot con Playwright Firefox (come richiesto)
    with sync_playwright() as p:
        browser = p.firefox.launch(args=[])
        page = browser.new_page(viewport={"width": 1620, "height": 4000})
        page.goto(f"file://{path_html}")
        page.wait_for_timeout(3000)
        page.screenshot(path=path_raw_png, clip={"x": 0, "y": 0, "width": 1620, "height": 1980})
        browser.close()

    if os.path.exists("texture.png"):
        try:
            base_img = Image.open(path_raw_png).convert("RGBA")
            texture  = Image.open("texture.png").convert("RGBA").resize(base_img.size, Image.Resampling.LANCZOS)
            Image.alpha_composite(base_img, texture).convert("RGB").save(path_final_png, "PNG")
            return path_final_png
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Errore texture stats: {e}")

    return path_raw_png


# ==============================================================================
# HELPERS
# ==============================================================================

def build_score_str(home_name, away_name, g_home, g_away):
    if g_home > g_away:
        return f"<b>{home_name} {g_home}</b>-{g_away} {away_name}"
    elif g_away > g_home:
        return f"{home_name} {g_home}-<b>{g_away} {away_name}</b>"
    else:
        return f"{home_name} {g_home}-{g_away} {away_name}"

TEAM_ABBREVIATIONS = {
    "juventus": "Juve", "inter": "Inter", "ac milan": "Milan", "as roma": "Roma",
    "napoli": "Napoli", "lazio": "Lazio", "fiorentina": "Fiorentina", "atalanta": "Atalanta",
    "real madrid": "Real", "fc barcelona": "Barca", "barcelona": "Barca",
    "manchester city": "ManCity", "manchester united": "ManUtd",
    "liverpool": "Liverpool", "chelsea": "Chelsea", "arsenal": "Arsenal",
    "paris saint-germain": "PSG", "bayern munich": "Bayern", "borussia dortmund": "BVB",
}

def build_hashtag(home_name, away_name):
    def abbr(name):
        return TEAM_ABBREVIATIONS.get(name.lower(), name.replace(" ", ""))
    return f"#{abbr(home_name)}{abbr(away_name)}"


# ==============================================================================
# CICLO PRINCIPALE
# ==============================================================================

def avvia_ciclo_partita():
    team_id = str(TEAM_ID).strip()

    partita = trova_partita_oggi(team_id)
    if not partita:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 📭 Nessun evento trovato per team_id={team_id}.")
        return

    event_id      = partita["event_id"]
    tournament_id = partita["tournament_id"]
    league_name   = partita["tournament_name"]
    home_name     = partita["home_name"]
    away_name     = partita["away_name"]
    home_id       = partita["home_id"]
    away_id       = partita["away_id"]
    start_ts      = partita["start_ts"]

    e_comp  = get_tournament_emoji(tournament_id)
    hashtag = build_hashtag(home_name, away_name)

    state = leggi_stato_da_gist()
    if state is None or state.get("event_id") != event_id:
        state = {
            "event_id":               event_id,
            "sent_periods":           [],
            "goals_detected":         0,
            "prev_home_goals":        0,
            "prev_away_goals":        0,
            "sent_subs":              [],
            "sent_cards":             [],
            "penalties_count":        0,
            "sent_stats":             [],
            "sent_failed_penalties":  [],
            "shootout_message_id":    None,
            "goal_messages":          {},
        }

    while True:
        sleep_time    = 6
        state_changed = False
        try:
            # Fetch dati evento
            event_data = fetch_evento(event_id)
            if not event_data:
                time.sleep(10)
                continue

            status, elapsed = parse_status_sofa(event_data)
            g_home, g_away  = parse_score_sofa(event_data)
            score_str       = build_score_str(home_name, away_name, g_home, g_away)

            # Fetch incidenti
            incidents = fetch_incidents(event_id)
            events    = parse_events_sofa(incidents, home_id, away_id)

            if "_intro_logged" not in state:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 PARTITA TROVATA: {league_name} | "
                      f"{home_name} vs {away_name} | event_id={event_id}")
                state["_intro_logged"] = True

            # Heartbeat log (1 al minuto, solo se non NS)
            _now_ts  = int(time.time())
            _log_key = f"{status}_{elapsed}_{g_home}_{g_away}"
            if status != "NS" and (
                state.get("_last_log_key") != _log_key or
                (_now_ts - state.get("_last_log_ts", 0)) >= 60
            ):
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 📡 {status} {elapsed}' | "
                      f"{home_name} {g_home}-{g_away} {away_name}")
                state["_last_log_key"] = _log_key
                state["_last_log_ts"]  = _now_ts

            # --- Non iniziata ---
            if status == "NS":
                now_utc            = datetime.now(timezone.utc)
                minutes_to_kickoff = (start_ts - now_utc.timestamp()) / 60
                if minutes_to_kickoff > 60:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🛑 Troppo presto "
                          f"({minutes_to_kickoff:.0f} min al via) — bot fermato")
                    sys.exit(0)
                if "_ns_logged" not in state:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏳ In attesa del calcio d'inizio "
                          f"({minutes_to_kickoff:.0f} min al via)")
                    state["_ns_logged"] = True
                time.sleep(6)
                continue

            # Polling più frequente durante i rigori
            if status == "PEN":
                sleep_time = 5

            # --- Inizio primo tempo ---
            if status == "1H" and "1H" not in state["sent_periods"]:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚡️ INIZIO PARTITA → Telegram inviato")
                send_telegram(f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{home_name} - {away_name}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("1H")
                salva_stato_su_gist(state)
                state_changed = True

            # --- Catchup: partita già in corso ma gist vuoto ---
            if state["goals_detected"] == 0 and (g_home + g_away) > 0 and not state.get("goal_messages"):
                _seen_uids = set()
                _deduped   = []
                for e in events:
                    if e["type"] in ("goal", "own goal", "penalty goal"):
                        uid = e.get("uid", f"{e['minute']}_{e.get('player_name','')}")
                        if uid not in _seen_uids:
                            _seen_uids.add(uid)
                            _deduped.append(e)
                goal_events_all = sorted(_deduped, key=lambda x: x["minute"])
                ch, ca = 0, 0
                for ge in goal_events_all:
                    if ch + ca >= g_home + g_away:
                        break
                    if ge["type"] == "own goal":
                        if ge["team_id"] == home_id:
                            ca += 1
                        else:
                            ch += 1
                    else:
                        if ge["team_id"] == home_id:
                            ch += 1
                        else:
                            ca += 1

                    p_name = ge.get("player_name", "")
                    a_name = ge.get("assist_name", "")
                    ps     = fmt_player(p_name) if p_name else ""
                    if ge["type"] == "own goal" and ps:
                        ps += " (Autogol)"
                    elif ge["type"] == "penalty goal" and ps:
                        ps += " (Rig.)"

                    scorer_line = f"{E_BALL} <i>{ps}</i>\n" if ps else ""
                    assist_line = f"{E_ASSIST} <i>{fmt_player(a_name)}</i>\n" if a_name and a_name != p_name else ""

                    if ge["type"] == "own goal":
                        actual_tid = away_id if ge["team_id"] == home_id else home_id
                    else:
                        actual_tid = ge["team_id"]
                    if actual_tid == home_id:
                        goal_score = f"<b>{home_name} {ch}</b>-{ca} {away_name}"
                    else:
                        goal_score = f"{home_name} {ch}-<b>{ca} {away_name}</b>"

                    goal_text = f"<b>GOAL · {ge['minute']}' {E_MIC}</b>\n\n{goal_score}\n{scorer_line}{assist_line}\n{e_comp} {hashtag}"
                    goal_key  = f"{ch}_{ca}"
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚽️  CATCHUP GOAL {ge['minute']}' "
                          f"{home_name} {ch}-{ca} {away_name} → Telegram inviato")
                    msg_id = send_telegram_get_id(goal_text)
                    state.setdefault("goal_messages", {})[goal_key] = {
                        "msg_id": msg_id, "scorer": p_name, "assist": a_name,
                        "minute": ge["minute"], "type": ge["type"],
                        "home_n": home_name, "away_n": away_name,
                        "g_home": ch, "g_away": ca,
                        "home_id": home_id, "away_id": away_id, "score_tid": actual_tid,
                    }
                    time.sleep(2)

                state["goals_detected"]  = g_home + g_away
                state["prev_home_goals"] = g_home
                state["prev_away_goals"] = g_away
                state_changed = True

            # --- Fine primo tempo ---
            if status == "HT" and "HT" not in state["sent_periods"]:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🏁 FINE 1° TEMPO "
                      f"({home_name} {g_home}-{g_away} {away_name}) → Telegram inviato")
                send_telegram(f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("HT")
                salva_stato_su_gist(state)
                state_changed = True
                time.sleep(120)
                png_path = recupera_e_genera_stats_html(
                    event_id, home_id, away_id, home_name, away_name, g_home, g_away, "HT", league_name)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 📊 STATS 1° TEMPO → foto Telegram inviata")
                send_telegram_stats_photo(png_path, "HT", f"{e_comp} {hashtag}")
                state["sent_stats"].append("HT")
                state_changed = True

            # --- Inizio secondo tempo ---
            if status == "2H" and "2H" not in state["sent_periods"]:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚡️ INIZIO 2° TEMPO → Telegram inviato")
                send_telegram(f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("2H")
                salva_stato_su_gist(state)
                state_changed = True

            # --- Fine regolamentari → supplementari ---
            if status in ("ET", "PEN", "AET") and "2H_END" not in state["sent_periods"] and "FT" not in state["sent_periods"]:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🏁 FINE REGOLAMENTARI "
                      f"({home_name} {g_home}-{g_away} {away_name}) → Telegram inviato")
                send_telegram(f"<b>FINE REGOLAMENTARI {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("2H_END")
                salva_stato_su_gist(state)
                state_changed = True
                if status == "ET":
                    time.sleep(120)
                    png_path = recupera_e_genera_stats_html(
                        event_id, home_id, away_id, home_name, away_name, g_home, g_away, "2H_END", league_name)
                    send_telegram_stats_photo(png_path, "2H_END", f"{e_comp} {hashtag}")
                    state["sent_stats"].append("2H_END")
                    state_changed = True

            # --- Supplementari ---
            if status == "ET":
                # SofaScore distingue 1ET (code 9) e 2ET (code 11) tramite parse_status_sofa
                # Qui gestiamo solo le transizioni di messaggio
                if "1ET_START" not in state["sent_periods"]:
                    send_telegram(f"<b>INIZIO 1T SUPPLEMENTARE {E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("1ET_START")
                    salva_stato_su_gist(state)
                    state_changed = True

            if status == "HT_ET":
                if "1ET_START" not in state["sent_periods"]:
                    state["sent_periods"].append("1ET_START")
                if "1ET_END" not in state["sent_periods"]:
                    send_telegram(f"<b>FINE 1T SUPPLEMENTARE {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("1ET_END")
                    salva_stato_su_gist(state)
                    state_changed = True

            # --- Rigori ---
            if status == "PEN":
                if "ET_END_PENS" not in state["sent_periods"]:
                    if "1ET_START" in state["sent_periods"] or "2ET_START" in state["sent_periods"]:
                        send_telegram(f"<b>FINE SUPPLEMENTARI {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("ET_END_PENS")
                    salva_stato_su_gist(state)
                    state_changed = True

                home_pen_icons, away_pen_icons = [], []
                for e in events:
                    if e["type"] in ("shootout goal", "shootout miss", "shootout saved"):
                        icon = E_PEN_OK if e["type"] == "shootout goal" else E_PEN_KO
                        (home_pen_icons if e["team_id"] == home_id else away_pen_icons).append(icon)

                total_kicks = len(home_pen_icons) + len(away_pen_icons)
                if total_kicks > state["penalties_count"]:
                    send_telegram(
                        f"<b>RIGORI {E_KICK}</b>\n\n"
                        f"{home_name}: " + ("".join(home_pen_icons) if home_pen_icons else "—") + "\n"
                        f"{away_name}: " + ("".join(away_pen_icons) if away_pen_icons else "—") + f"\n\n{e_comp} {hashtag}"
                    )
                    state["penalties_count"] = total_kicks
                    state_changed = True

            # --- Fine partita ---
            is_finished = status in ("FT", "AET") or \
                (status == "PEN" and event_data.get("event", {}).get("status", {}).get("code", 0) == 110)

            if is_finished and "FT" not in state["sent_periods"]:
                home_scorers, away_scorers = [], []
                for e in events:
                    if e["type"] in ("goal", "own goal", "penalty goal"):
                        ps  = fmt_player(e["player_name"])
                        if e["type"] == "own goal":
                            ps += " (Autogol)"
                        elif e["type"] == "penalty goal":
                            ps += " (Rig.)"
                        entry = f"{e['minute']}' {ps}"
                        tid   = e["team_id"]
                        if e["type"] == "own goal":
                            tid = away_id if tid == home_id else home_id
                        (home_scorers if tid == home_id else away_scorers).append(entry)

                scorers_line = ""
                if home_scorers or away_scorers:
                    parts = []
                    if home_scorers:
                        parts.append(", ".join(home_scorers))
                    if away_scorers:
                        parts.append(", ".join(away_scorers))
                    scorers_line = f"{E_BALL} <i>{' // '.join(parts)}</i>\n"

                has_shootout = "ET_END_PENS" in state["sent_periods"] or status == "PEN"
                if has_shootout:
                    home_pen_goals = sum(1 for e in events if e["type"] == "shootout goal" and e["team_id"] == home_id)
                    away_pen_goals = sum(1 for e in events if e["type"] == "shootout goal" and e["team_id"] == away_id)
                    if home_pen_goals > 0 or away_pen_goals > 0:
                        if home_pen_goals > away_pen_goals:
                            score_str = f"<b>{home_name} {g_home} ({home_pen_goals})</b>-({away_pen_goals}) {g_away} {away_name}"
                        elif away_pen_goals > home_pen_goals:
                            score_str = f"{home_name} {g_home} ({home_pen_goals})-<b>({away_pen_goals}) {g_away} {away_name}</b>"

                msg_finale = f"<b>FINE PARTITA {E_FLAG}</b>\n\n{score_str}\n{scorers_line}\n{e_comp} {hashtag}"

                is_juve_match = home_id == str(TEAM_ID) or away_id == str(TEAM_ID)
                if is_juve_match:
                    canva_token = get_valid_token()
                    if canva_token:
                        foto = get_canva_image(canva_token)
                        send_telegram_with_photo(msg_finale, foto)
                    else:
                        send_telegram(msg_finale)
                else:
                    send_telegram(msg_finale)

                state["sent_periods"].append("FT")
                time.sleep(120)
                ft_pen_home = sum(1 for e in events if e["type"] == "shootout goal" and e["team_id"] == home_id)
                ft_pen_away = sum(1 for e in events if e["type"] == "shootout goal" and e["team_id"] == away_id)
                png_path = recupera_e_genera_stats_html(
                    event_id, home_id, away_id, home_name, away_name, g_home, g_away,
                    "FT", league_name, pen_home=ft_pen_home, pen_away=ft_pen_away)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 📊 STATS FINE PARTITA → foto Telegram inviata")
                send_telegram_stats_photo(png_path, "FT", f"{e_comp} {hashtag}")
                state["sent_stats"].append("FT")
                state["_reset_done"] = True
                resetta_gist()
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🏆 FINE PARTITA "
                      f"({home_name} {g_home}-{g_away} {away_name}) — bot terminato")
                sys.exit(0)

            # --- Rilevamento goal ---
            total_goals_now = g_home + g_away
            prev_home = state.get("prev_home_goals", 0)
            prev_away = state.get("prev_away_goals", 0)

            if total_goals_now > state["goals_detected"]:
                # Conferma punteggio attendendo 15s
                time.sleep(15)
                ev_confirm = fetch_evento(event_id)
                if ev_confirm:
                    g_home_c, g_away_c = parse_score_sofa(ev_confirm)
                    if g_home_c + g_away_c != total_goals_now:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Punteggio instabile "
                              f"({g_home}-{g_away} → {g_home_c}-{g_away_c}), attendo conferma...")
                        time.sleep(sleep_time)
                        continue
                    g_home, g_away = g_home_c, g_away_c
                    events = parse_events_sofa(fetch_incidents(event_id), home_id, away_id)
                    score_str = build_score_str(home_name, away_name, g_home, g_away)

                if g_home > prev_home:
                    scoring_tid = home_id
                elif g_away > prev_away:
                    scoring_tid = away_id
                else:
                    scoring_tid = None

                goal_events = [e for e in events if e["type"] in ("goal", "own goal", "penalty goal")]

                if scoring_tid:
                    team_goals   = [e for e in goal_events if e["type"] != "own goal" and e["team_id"] == scoring_tid]
                    own_goals_vs = [e for e in goal_events if e["type"] == "own goal" and e["team_id"] != scoring_tid]
                    candidates   = sorted(team_goals + own_goals_vs, key=lambda x: x["minute"])
                    expected_count = g_home if scoring_tid == home_id else g_away
                    last = candidates[expected_count - 1] if len(candidates) >= expected_count else (candidates[-1] if candidates else None)

                    if not last:
                        time.sleep(sleep_time)
                        continue

                    player_name        = last.get("player_name", "")
                    assist_name        = last.get("assist_name", "")
                    actual_scoring_tid = scoring_tid

                    if player_name:
                        ps = fmt_player(player_name)
                        if last["type"] == "own goal":
                            ps += " (Autogol)"
                            actual_scoring_tid = away_id if last["team_id"] == home_id else home_id
                        elif last["type"] == "penalty goal":
                            ps += " (Rig.)"
                        scorer_line = f"{E_BALL} <i>{ps}</i>\n"
                    else:
                        scorer_line = ""

                    assist_line = ""
                    if assist_name and assist_name != player_name:
                        assist_line = f"{E_ASSIST} <i>{fmt_player(assist_name)}</i>\n"

                    if actual_scoring_tid == home_id:
                        goal_score = f"<b>{home_name} {g_home}</b>-{g_away} {away_name}"
                    else:
                        goal_score = f"{home_name} {g_home}-<b>{g_away} {away_name}</b>"

                    goal_key  = f"{g_home}_{g_away}"
                    goal_text = (f"<b>GOAL · {last['minute']}' {E_MIC}</b>\n\n"
                                 f"{goal_score}\n{scorer_line}{assist_line}\n{e_comp} {hashtag}")

                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚽️  GOAL {last['minute']}' "
                          f"{home_name} {g_home}-{g_away} {away_name} → Telegram inviato")
                    msg_id = send_telegram_get_id(goal_text)
                    state.setdefault("goal_messages", {})[goal_key] = {
                        "msg_id": msg_id, "scorer": player_name, "assist": assist_name,
                        "minute": last["minute"], "type": last["type"],
                        "home_n": home_name, "away_n": away_name,
                        "g_home": g_home, "g_away": g_away,
                        "home_id": home_id, "away_id": away_id,
                        "score_tid": actual_scoring_tid,
                    }

                state["goals_detected"]  = g_home + g_away
                state["prev_home_goals"] = g_home
                state["prev_away_goals"] = g_away
                state_changed = True

            # --- Correzione marcatori (se arrivano in ritardo) ---
            for goal_key, saved in list(state.get("goal_messages", {}).items()):
                msg_id   = saved.get("msg_id")
                if not msg_id:
                    continue
                s_home_id = saved.get("home_id", home_id)
                s_away_id = saved.get("away_id", away_id)
                s_home_n  = saved.get("home_n", home_name)
                s_away_n  = saved.get("away_n", away_name)
                s_tid     = saved.get("score_tid", "")
                gh        = saved.get("g_home", 0)
                ga        = saved.get("g_away", 0)

                try:
                    idx = int(goal_key.split("_")[0]) - 1 if s_tid == s_home_id else int(goal_key.split("_")[1]) - 1
                except Exception:
                    continue

                team_candidates = [
                    e for e in events
                    if e["type"] in ("goal", "penalty goal") and e["team_id"] == s_tid
                ] + [
                    e for e in events
                    if e["type"] == "own goal" and e["team_id"] != s_tid
                ]
                candidates = sorted(team_candidates, key=lambda x: x["minute"])

                if idx < 0 or idx >= len(candidates):
                    continue

                current        = candidates[idx]
                current_scorer = current.get("player_name", "")
                current_assist = current.get("assist_name", "")
                current_type   = current.get("type", saved.get("type", "goal"))

                if (current_scorer != saved.get("scorer")) or \
                   (current_assist != saved.get("assist", "")) or \
                   (current_type   != saved.get("type", "goal")):

                    if current_scorer:
                        ps_new = fmt_player(current_scorer)
                        if current_type == "own goal":
                            ps_new += " (Autogol)"
                        elif current_type == "penalty goal":
                            ps_new += " (Rig.)"
                        scorer_line_new = f"{E_BALL} <i>{ps_new}</i>\n"
                    else:
                        scorer_line_new = ""

                    assist_line_new = ""
                    if current_assist and current_assist != current_scorer:
                        assist_line_new = f"{E_ASSIST} <i>{fmt_player(current_assist)}</i>\n"

                    if current_type == "own goal":
                        actual_tid = s_away_id if s_tid == s_home_id else s_home_id
                    else:
                        actual_tid = s_tid

                    if actual_tid == s_home_id:
                        goal_score_new = f"<b>{s_home_n} {gh}</b>-{ga} {s_away_n}"
                    else:
                        goal_score_new = f"{s_home_n} {gh}-<b>{ga} {s_away_n}</b>"

                    goal_text_new = (f"<b>GOAL · {current['minute']}' {E_MIC}</b>\n\n"
                                     f"{goal_score_new}\n{scorer_line_new}{assist_line_new}\n"
                                     f"{e_comp} {hashtag}")

                    changes = []
                    if current_scorer != saved.get("scorer"):
                        changes.append(f"marcatore: {saved.get('scorer')} → {current_scorer}")
                    if current_assist != saved.get("assist", ""):
                        changes.append(f"assist: {saved.get('assist','—') or '—'} → {current_assist or '—'}")
                    if current_type != saved.get("type", "goal"):
                        changes.append(f"tipo: {saved.get('type','goal')} → {current_type}")

                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✏️  CORREZIONE goal {goal_key}: "
                          f"{', '.join(changes)} → messaggio editato")
                    send_telegram_edit(msg_id, goal_text_new)
                    state["goal_messages"][goal_key].update({
                        "scorer": current_scorer, "assist": current_assist,
                        "type": current_type, "score_tid": actual_tid,
                    })
                    state_changed = True

            # --- Cambi ---
            new_subs_check = [
                {**e, "sub_id": e["uid"]} for e in events
                if e["type"] == "substitution" and e["uid"] not in state["sent_subs"]
            ]
            if new_subs_check:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 Cambio rilevato, raggruppo per 60s...")
                for _ in range(10):
                    time.sleep(6)
                fresh_incidents = fetch_incidents(event_id)
                events_subs = parse_events_sofa(fresh_incidents, home_id, away_id)
                new_subs = [
                    {**e, "sub_id": e["uid"]} for e in events_subs
                    if e["type"] == "substitution" and e["uid"] not in state["sent_subs"]
                ]
                groups = []
                for sub in new_subs:
                    placed = False
                    for g in groups:
                        if g["team_id"] == sub["team_id"] and abs(g["minute"] - sub["minute"]) <= 2:
                            g["subs"].append(sub)
                            placed = True
                            break
                    if not placed:
                        groups.append({"team_id": sub["team_id"], "minute": sub["minute"], "subs": [sub]})

                for g in groups:
                    team_title = home_name.upper() if g["team_id"] == home_id else away_name.upper()
                    ins   = ", ".join(fmt_player(s["assist_name"]) for s in g["subs"])
                    outs  = ", ".join(fmt_player(s["player_name"]) for s in g["subs"])
                    _min  = g["subs"][0]["minute"]
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 CAMBIO {team_title} {_min}' | "
                          f"↑ {ins} / ↓ {outs} → Telegram inviato")
                    send_telegram(
                        f"<b>CAMBIO {team_title} · {_min}' {E_SUB}</b>\n\n"
                        f"{E_UP} {ins}\n{E_DOWN} {outs}\n\n{e_comp} {hashtag}"
                    )
                    state["sent_subs"].extend(s["sub_id"] for s in g["subs"])
                    state_changed = True

            # --- Cartellini rossi / doppio giallo ---
            for e in events:
                if e["type"] in ("red card", "second yellow card"):
                    p_name  = fmt_player(e["player_name"])
                    card_id = f"card_{e['minute']}_{e['player_name']}".replace(" ", "_")
                    if card_id not in state["sent_cards"]:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🟥 ROSSO {e['minute']}' "
                              f"{p_name} → Telegram inviato")
                        send_telegram(
                            f"<b>CARTELLINO ROSSO · {e['minute']}' {E_RED}</b>\n\n"
                            f"{E_EXIT} <i>{p_name}</i>\n\n{e_comp} {hashtag}"
                        )
                        state["sent_cards"].append(card_id)
                        state_changed = True

            # --- Rigori sbagliati (durante la partita) ---
            for e in events:
                if e["type"] in ("penalty missed", "penalty saved"):
                    pen_id = f"failpen_{e['minute']}_{e['player_name']}".replace(" ", "_")
                    if pen_id not in state["sent_failed_penalties"]:
                        state["sent_failed_penalties"].append(pen_id)
                        state_changed = True
                        team_name = home_name if e["team_id"] == home_id else away_name
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🥅 RIGORE SBAGLIATO "
                              f"{team_name.upper()} {e['minute']}' {fmt_player(e['player_name'])} → Telegram inviato")
                        send_telegram(
                            f"<b>RIGORE SBAGLIATO {team_name.upper()} · {e['minute']}' {E_KICK}</b>\n\n"
                            f"{E_PEN_KO} <i>{fmt_player(e['player_name'])}</i>\n\n"
                            f"{e_comp} {hashtag}"
                        )

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Errore ciclo live: {e}")
            sleep_time = 10

        finally:
            if isinstance(state, dict) and not state.get("_reset_done") and state_changed:
                salva_stato_su_gist(state)

        time.sleep(sleep_time)


# ==============================================================================
# MAIN
# ==============================================================================
def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Bot avviato (SofaScore via Playwright Firefox)")

    if str(os.getenv('ONLY_REFRESH_TOKEN', '')).strip().lower() == "true":
        get_valid_token()
        return

    avvia_ciclo_partita()

if __name__ == "__main__":
    main()
