import os
import requests
import json
import time
import sys
import base64
from PIL import Image
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

ITALY_TZ = ZoneInfo('Europe/Rome')
def now_it(): return datetime.now(ITALY_TZ).strftime('%H:%M:%S')
from playwright.sync_api import sync_playwright

try:
    from nacl import encoding, public
except ImportError:
    print(f"[{now_it()}] ⚠️  pynacl non installata — aggiornamento Secrets GitHub non disponibile")

# ==============================================================================
# CONFIGURAZIONE
# ==============================================================================
BOT_TOKEN           = os.getenv('TELEGRAM_TOKEN')
CHAT_ID             = os.getenv('TELEGRAM_TO')
TEAM_ID             = os.getenv('TEAM_ID', '111')
GH_PAT              = os.getenv('GH_PAT')
GITHUB_REPOSITORY   = os.getenv('GITHUB_REPOSITORY')
GIST_ID             = os.getenv('GIST_ID')
CLIENT_ID           = os.getenv('CANVA_CLIENT_ID')
CLIENT_SECRET       = os.getenv('CANVA_CLIENT_SECRET')
CANVA_REFRESH_TOKEN = os.getenv('CANVA_REFRESH_TOKEN')

CANVA_DESIGN_ID = "DAHI3ytu6yQ"
PAGINA_TARGET   = 11

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# ==============================================================================
# LEGHE — caricato da leagues.json
# Formato: { "slug": { "emoji": "🇮🇹" } }
# ==============================================================================
_LEAGUES_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leagues.json")

def _load_leagues() -> dict:
    try:
        with open(_LEAGUES_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        print(f"[{now_it()}] ⚠️  leagues.json non trovato — emoji leghe disabilitate")
        return {}
    except Exception as e:
        print(f"[{now_it()}] ⚠️  Errore caricamento leagues.json: {e}")
        return {}

LEAGUE_MAP: dict = _load_leagues()
LEAGUE_SLUGS: list = list(LEAGUE_MAP.keys())

def get_league_emoji(slug): return LEAGUE_MAP.get(slug, {}).get("emoji", "⚽️")

# ==============================================================================
# KIT / TEMA GRAFICA STATS
#   home    → Juve gioca in casa (campionato)
#   away    → Juve gioca in trasferta (campionato)
#   third   → coppe (Coppa Italia, Supercoppa, Champions, Europa, ecc.)
#   default → partita senza la Juve
# ==============================================================================
JUVE_ID = str(TEAM_ID)  # default '111'

def _is_league_slug(slug: str) -> bool:
    """True se lo slug ESPN è un campionato (es. 'ita.1', 'eng.2'):
    3 lettere + '.' + numero. Tutto il resto è considerato coppa."""
    parts = (slug or "").split(".")
    return (len(parts) == 2 and len(parts[0]) == 3
            and parts[0].isalpha() and parts[1].isdigit())

# Parole chiave di fallback per riconoscere una coppa dal nome/slug
_CUP_KEYWORDS = (
    "copp", "cup", "champions", "europa", "conference", "super",
    "supercoppa", "mondiale", "club world", "cwc", "shield",
    "playoff", "play-off",
)

def is_cup_competition(league_slug: str, league_name: str = "") -> bool:
    """Determina se la competizione è una coppa.
    Priorità: override esplicito in leagues.json ({"slug": {"type": "cup"}})
    → formato slug campionato → keyword di fallback."""
    slug = (league_slug or "").lower()
    name = (league_name or "").lower()

    # 1) override esplicito da leagues.json
    tipo = str(LEAGUE_MAP.get(league_slug, {}).get("type", "")).lower()
    if tipo in ("cup", "coppa"):
        return True
    if tipo in ("league", "campionato"):
        return False

    # 2) formato slug: i campionati sono "xxx.N"
    if _is_league_slug(slug):
        return False

    # 3) fallback per keyword
    return any(k in slug or k in name for k in _CUP_KEYWORDS)

def determina_kit(home_id, away_id, league_slug: str = "", league_name: str = "") -> str:
    """Restituisce il tema della maglia da applicare alla grafica stats."""
    juve_in_casa       = str(home_id) == JUVE_ID
    juve_in_trasferta  = str(away_id) == JUVE_ID
    if not (juve_in_casa or juve_in_trasferta):
        return "default"
    if is_cup_competition(league_slug, league_name):
        return "third"
    return "home" if juve_in_casa else "away"

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

# Mapping testo ESPN → tipo interno normalizzato
EVENT_TYPE_MAP = {
    "goal":                     "goal",
    "own goal":                 "own goal",
    "penalty goal":             "penalty goal",
    "penalty - goal":           "penalty goal",
    "penalty - scored":         "penalty goal",
    "penalty missed":           "penalty missed",
    "penalty saved":            "penalty saved",
    "penalty - missed":         "penalty missed",
    "penalty - saved":          "penalty saved",
    "yellow card":              "yellow card",
    "red card":                 "red card",
    "second yellow card":       "second yellow card",
    "yellow card - second":     "second yellow card",
    "substitution":             "substitution",
    "substitution - player on": "substitution",
    "substitution - off":       "substitution",
    "penalty shootout - goal":  "shootout goal",
    "shootout goal":             "shootout goal",
    "shootout miss":             "shootout miss",
    "shootout saved":            "shootout saved",
    "penalty shootout - miss":  "shootout miss",
    "penalty shootout - saved": "shootout saved",
}

def normalize_event_type(raw: str) -> str:
    if not raw:
        return ""
    low = raw.strip().lower()
    for k, v in sorted(EVENT_TYPE_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if k in low:
            return v
    return low

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
        print(f"[{now_it()}] ⚠️  BOT_TOKEN o CHAT_ID mancanti")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"[{now_it()}] ❌ Errore send_telegram: {e}")

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
        print(f"[{now_it()}] ❌ Errore editMessageText: {e}")

def send_telegram_get_id(text: str) -> int | None:
    if not BOT_TOKEN or not CHAT_ID:
        print(f"[{now_it()}] ⚠️  BOT_TOKEN o CHAT_ID mancanti")
        return None
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
        r.raise_for_status()
        msg_id = r.json().get("result", {}).get("message_id")
        return msg_id
    except Exception as e:
        print(f"[{now_it()}] ❌ Errore send_telegram_get_id: {e}")
        return None

def delete_telegram_message(message_id: int):
    if not BOT_TOKEN or not CHAT_ID or not message_id:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "message_id": message_id}, timeout=10)
    except Exception as e:
        print(f"[{now_it()}] ⚠️  Errore deleteMessage: {e}")

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
        print(f"[{now_it()}] ❌ Errore invio foto statistiche: {e}")

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
        if r.status_code in [201, 204]:
            return True
    except Exception as e:
        print(f"[{now_it()}] ❌ Errore update GitHub secret: {e}")
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
        print(f"[{now_it()}] ❌ Errore lettura Gist: {e}")
        return None

def salva_stato_su_gist(state: dict):
    if not GH_PAT or not GIST_ID:
        return
    try:
        payload = {"files": {"match_state.json": {"content": json.dumps(state, ensure_ascii=False, indent=2)}}}
        r = requests.patch(f"https://api.github.com/gists/{GIST_ID}", headers=_gist_headers(),
                           json=payload, timeout=10)
        if r.status_code == 200:
            pass
    except Exception as e:
        print(f"[{now_it()}] ❌ Errore salvataggio Gist: {e}")

def resetta_gist():
    if not GH_PAT or not GIST_ID:
        return
    try:
        payload = {"files": {"match_state.json": {"content": "{}"}}}
        requests.patch(f"https://api.github.com/gists/{GIST_ID}", headers=_gist_headers(),
                       json=payload, timeout=10)
    except Exception as e:
        print(f"[{now_it()}] ❌ Errore reset Gist: {e}")

# ==============================================================================
# CANVA
# ==============================================================================
def get_valid_token():
    if not CANVA_REFRESH_TOKEN:
        print(f"[{now_it()}] ❌ CANVA_REFRESH_TOKEN mancante")
        return None
    try:
        print(f"[{now_it()}] 🔑 Richiedo access token Canva tramite refresh token...")
        r = requests.post("https://api.canva.com/rest/v1/oauth/token", data={
            "grant_type": "refresh_token", "refresh_token": CANVA_REFRESH_TOKEN,
            "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET
        }, timeout=15)
        if r.status_code == 200:
            tokens = r.json()
            if "refresh_token" in tokens and tokens["refresh_token"] != CANVA_REFRESH_TOKEN:
                print(f"[{now_it()}] 🔄 Nuovo refresh token ricevuto — aggiorno GitHub Secret...")
                update_github_secret("CANVA_REFRESH_TOKEN", tokens["refresh_token"])
                print(f"[{now_it()}] ✅ GitHub Secret CANVA_REFRESH_TOKEN aggiornato")
            else:
                print(f"[{now_it()}] ✅ Access token Canva ottenuto (refresh token invariato)")
            return tokens["access_token"]
        print(f"[{now_it()}] ❌ Errore token Canva: {r.text}")
    except Exception as e:
        print(f"[{now_it()}] ❌ Errore connessione Canva: {e}")
    return None

def get_canva_image(access_token: str):
    if not access_token:
        return None
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    try:
        print(f"[{now_it()}] 🎨 Avvio export Canva (design={CANVA_DESIGN_ID}, pagina={PAGINA_TARGET})...")
        r = requests.post("https://api.canva.com/rest/v1/exports", headers=headers, json={
            "design_id": CANVA_DESIGN_ID, "format": {"type": "png", "pages": [PAGINA_TARGET]}
        }, timeout=15)
        if r.status_code not in [200, 201]:
            print(f"[{now_it()}] ❌ Errore avvio export Canva: HTTP {r.status_code} — {r.text}")
            return None
        job_data = r.json()
        job_id = job_data.get("id") or job_data.get("job", {}).get("id")
        if not job_id:
            print(f"[{now_it()}] ❌ Export Canva: job_id non trovato nella risposta")
            return None
        print(f"[{now_it()}] ⏳ Export Canva avviato (job_id={job_id}), attendo completamento...")
        status_url = f"https://api.canva.com/rest/v1/exports/{job_id}"
        time.sleep(3)
        for i in range(60):
            time.sleep(3)
            check = requests.get(status_url, headers=headers, timeout=15)
            if check.status_code == 200:
                d = check.json()
                stato = d.get("status") or d.get("job", {}).get("status")
                if stato == "success":
                    urls = d.get("urls") or d.get("job", {}).get("urls")
                    url_dl = urls[0] if urls else (d.get("url") or d.get("job", {}).get("url"))
                    if url_dl:
                        print(f"[{now_it()}] ✅ Export Canva completato, scarico immagine...")
                        time.sleep(10)
                        img = requests.get(url_dl, timeout=30).content
                        print(f"[{now_it()}] 🖼️  Immagine Canva scaricata ({len(img) // 1024} KB)")
                        return img
                elif stato == "failed":
                    print(f"[{now_it()}] ❌ Export Canva fallito (job_id={job_id})")
                    return None
    except Exception as e:
        print(f"[{now_it()}] ❌ Errore export Canva: {e}")
    return None

# ==============================================================================
# PARSE EVENTS
# ==============================================================================
def _extract_team_id_from_commentary(item: dict, home_name: str, away_name: str,
                                      home_id: str, away_id: str) -> str:
    play = item.get("play", {})
    team_name = play.get("team", {}).get("displayName", "")
    team_id   = play.get("team", {}).get("id", "")
    if team_id:
        return str(team_id)
    if team_name:
        if team_name.lower() == home_name.lower():
            return home_id
        if team_name.lower() == away_name.lower():
            return away_id
    text = item.get("text", "")
    if home_name and home_name.lower() in text.lower():
        return home_id
    if away_name and away_name.lower() in text.lower():
        return away_id
    return ""


def parse_events(data: dict, home_name: str = "", away_name: str = "",
                 home_id: str = "", away_id: str = "") -> list:
    events    = []
    seen_ids  = set()

    def safe_minute(clock_val) -> int:
        try:
            s = str(clock_val).strip()
            if "+" in s:
                parts_plus = s.split("+")
                base  = int(float(parts_plus[0].replace("'", "").strip()))
                extra = int(float(parts_plus[1].replace("'", "").strip()))
                return base + extra
            s = s.replace("'", "").strip()
            if ":" in s:
                return int(float(s.split(":")[0]))
            return int(float(s))
        except Exception:
            return 0

    def extract_athlete(participants, index=0) -> str:
        try:
            return participants[index].get("athlete", {}).get("displayName", "")
        except Exception:
            return ""

    def add_event(ev_type, minute, team_id, player_name, assist_name, uid):
        if uid in seen_ids:
            return
        seen_ids.add(uid)
        norm = normalize_event_type(ev_type)
        if not norm:
            return
        for existing in events:
            if (existing["type"] == norm
                    and abs(existing["minute"] - minute) <= 1
                    and existing["team_id"] == str(team_id)
                    and existing["player_name"] == player_name):
                return
        events.append({
            "type":        norm,
            "minute":      minute,
            "team_id":     str(team_id),
            "player_name": player_name,
            "assist_name": assist_name,
            "uid":         uid,
        })

    # --- FONTE 1: commentary[].play ---
    for item in data.get("commentary", []):
        play = item.get("play")
        if not play:
            continue
        try:
            ev_type = play.get("type", {}).get("text", "")
            if not ev_type:
                continue
            uid     = str(play.get("id", "")) or f"c_{item.get('sequence','')}"
            clock   = play.get("clock", {}).get("displayValue",
                       play.get("clock", {}).get("value", "0"))
            minute  = safe_minute(clock)
            parts   = play.get("participants", [])

            if normalize_event_type(ev_type) == "substitution":
                player = extract_athlete(parts, 1)
                assist = extract_athlete(parts, 0)
            else:
                player = extract_athlete(parts, 0)
                assist = extract_athlete(parts, 1)

            period_num = play.get("period", {}).get("number", 0)
            if period_num == 5:
                raw_type = play.get("type", {}).get("type", "")
                ev_low = ev_type.lower()
                if "scored" in raw_type or "scored" in ev_low:
                    ev_type = "shootout goal"
                elif "missed" in raw_type or "missed" in ev_low:
                    ev_type = "shootout miss"
                elif "saved" in raw_type or "saved" in ev_low:
                    ev_type = "shootout saved"

            team_id = _extract_team_id_from_commentary(item, home_name, away_name, home_id, away_id)
            add_event(ev_type, minute, team_id, player, assist, uid)
        except Exception as e:
            print(f"[{now_it()}] ⚠️  Errore parsing commentary: {e}")

    # --- FONTE 2: keyEvents[] ---
    for item in data.get("keyEvents", []):
        try:
            play    = item if "type" in item else item.get("play", item)
            ev_type = play.get("type", {}).get("text", "")
            if not ev_type:
                continue
            uid     = str(play.get("id", "")) or f"ke_{play.get('clock',{}).get('value','')}"
            clock   = play.get("clock", {}).get("displayValue",
                       play.get("clock", {}).get("value", "0"))
            minute  = safe_minute(clock)
            parts   = play.get("participants", [])

            if normalize_event_type(ev_type) == "substitution":
                player = extract_athlete(parts, 1)
                assist = extract_athlete(parts, 0)
            else:
                player = extract_athlete(parts, 0)
                assist = extract_athlete(parts, 1)

            t_name  = play.get("team", {}).get("displayName", "")
            t_id    = play.get("team", {}).get("id", "")
            if not t_id and t_name:
                tl = t_name.lower()
                if tl == (home_name or "").lower():
                    t_id = home_id
                elif tl == (away_name or "").lower():
                    t_id = away_id
            add_event(ev_type, minute, t_id, player, assist, uid)
        except Exception as e:
            print(f"[{now_it()}] ⚠️  Errore parsing keyEvent: {e}")

    # --- FONTE 3: scoringPlays[] (fallback) ---
    for item in data.get("scoringPlays", []):
        try:
            ev_type = item.get("type", {}).get("text", "goal")
            clock   = item.get("clock", {}).get("displayValue", "0")
            minute  = safe_minute(clock)
            team_id = item.get("team", {}).get("id", "")
            parts   = item.get("participants", [])
            player  = extract_athlete(parts, 0)
            assist  = extract_athlete(parts, 1)
            uid     = str(item.get("id", f"sp_{minute}_{player}"))
            add_event(ev_type, minute, team_id, player, assist, uid)
        except Exception as e:
            print(f"[{now_it()}] ⚠️  Errore parsing scoringPlay: {e}")

    # --- FONTE 4: shootout[] ---
    for team_shootout in data.get("shootout", []):
        try:
            t_id_raw = str(team_shootout.get("id", ""))
            t_name   = team_shootout.get("team", "")
            if t_id_raw:
                t_id = t_id_raw
            elif isinstance(t_name, str) and t_name:
                t_id = home_id if t_name.lower() == home_name.lower() else away_id
            else:
                t_id = ""
            kicks = team_shootout.get("shots") or team_shootout.get("shootoutAttempts", [])
            for kick in kicks:
                did_score = kick.get("didScore", kick.get("scored", False))
                saved     = kick.get("saved", False)
                player    = kick.get("player") or kick.get("athlete", {}).get("displayName", "")
                uid       = str(kick.get("id", f"shootout_{t_id}_{player}"))
                if did_score:
                    ev_type = "shootout goal"
                elif saved:
                    ev_type = "shootout saved"
                else:
                    ev_type = "shootout miss"
                add_event(ev_type, 120, t_id, player, "", uid)
        except Exception as e:
            print(f"[{now_it()}] ⚠️  Errore parsing shootout: {e}")

    return events

# ==============================================================================
# STATISTICHE
# ==============================================================================
def _estrai_stats_espn(data: dict) -> dict:
    raw = {"home": {}, "away": {}}

    try:
        for team_data in data.get("boxscore", {}).get("teams", []):
            side = "home" if team_data.get("homeAway") == "home" else "away"
            for s in team_data.get("statistics", []):
                key = s.get("name", "").lower()
                val = s.get("displayValue", "0")
                if key:
                    raw[side][key] = val
    except Exception as e:
        print(f"[{now_it()}] ⚠️  Errore parsing boxscore.teams: {e}")

    try:
        for comp in data.get("header", {}).get("competitions", [{}]):
            for competitor in comp.get("competitors", []):
                side = "home" if competitor.get("homeAway") == "home" else "away"
                for s in competitor.get("statistics", []):
                    key = s.get("name", "").lower()
                    val = s.get("displayValue", s.get("value", "0"))
                    if key and key not in raw[side]:
                        raw[side][key] = str(val)
    except Exception as e:
        print(f"[{now_it()}] ⚠️  Errore parsing header competitors: {e}")

    return raw


def recupera_e_genera_stats_html(data_espn: dict, home_id: str, away_id: str,
                                  home_name: str, away_name: str,
                                  home_goals: int, away_goals: int,
                                  momento: str, league_name: str = "SERIE A",
                                  league_slug: str = "",
                                  pen_home: int = 0, pen_away: int = 0):

    # Tema maglia (home / away / third / default) — calcolato subito perché
    # determina anche quale logo Juve usare.
    juve_kit = determina_kit(home_id, away_id, league_slug, league_name)
    print(f"[{now_it()}] 🎨 Kit grafica stats: {juve_kit} (lega: {league_name} / {league_slug or 'n.d.'})")

    # Logo Juve in base al kit:
    #   home / away    → logo nero (SVG, 2020)
    #   third / default → icona bianca quadrata (PNG, 2017)
    JUVE_LOGO_BLACK = "https://upload.wikimedia.org/wikipedia/commons/e/ed/Juventus_FC_-_logo_black_%28Italy%2C_2020%29.svg"
    JUVE_LOGO_WHITE = "https://upload.wikimedia.org/wikipedia/commons/9/99/Juventus_FC_2017_squared_icon_%28white%29.png"
    juve_logo   = JUVE_LOGO_BLACK if juve_kit in ("home", "away") else JUVE_LOGO_WHITE

    h_logo      = juve_logo if str(home_id) == JUVE_ID else f"https://a.espncdn.com/i/teamlogos/soccer/500/{home_id}.png"
    a_logo      = juve_logo if str(away_id) == JUVE_ID else f"https://a.espncdn.com/i/teamlogos/soccer/500/{away_id}.png"
    badge_label = MOMENTI_CONFIG[momento]["badge"]
    if momento == "FT" and (pen_home > 0 or pen_away > 0):
        badge_label = "FINE PARTITA d.c.r."
    raw         = _estrai_stats_espn(data_espn)

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

    pos_h_raw = g("home", "possessionPct", "possessionpct", "possession", fallback="50")
    pos_a_raw = g("away", "possessionPct", "possessionpct", "possession", fallback="50")
    pos_h     = fmt_pct(pos_h_raw)
    pos_a     = fmt_pct(pos_a_raw)
    try:
        bp_perc = int(float(str(pos_h_raw).replace("%", "")))
        if bp_perc <= 1:
            bp_perc = int(bp_perc * 100)
    except Exception:
        bp_perc = 50

    sot_h    = g("home", "shotsOnTarget",   "shotsontarget",   fallback="0")
    sot_a    = g("away", "shotsOnTarget",   "shotsontarget",   fallback="0")
    shots_h  = g("home", "totalShots",      "totalshots",      fallback="0")
    shots_a  = g("away", "totalShots",      "totalshots",      fallback="0")
    falli_h  = g("home", "foulsCommitted",  "foulscommitted",  "fouls", fallback="0")
    falli_a  = g("away", "foulsCommitted",  "foulscommitted",  "fouls", fallback="0")
    gialli_h = g("home", "yellowCards",     "yellowcards",     fallback="0")
    gialli_a = g("away", "yellowCards",     "yellowcards",     fallback="0")
    rossi_h  = g("home", "redCards",        "redcards",        fallback="0")
    rossi_a  = g("away", "redCards",        "redcards",        fallback="0")
    corner_h = g("home", "wonCorners",      "woncorners",
                          "cornerKicks",    "cornerkicks",
                          "corners",        "corner",          fallback="0")
    corner_a = g("away", "wonCorners",      "woncorners",
                          "cornerKicks",    "cornerkicks",
                          "corners",        "corner",          fallback="0")
    saves_h  = g("home", "saves",           fallback="0")
    saves_a  = g("away", "saves",           fallback="0")
    offside_h = g("home", "offsides",       fallback="0")
    offside_a = g("away", "offsides",       fallback="0")
    blk_h    = g("home", "blockedShots",    "blockedshots",    fallback="0")
    blk_a    = g("away", "blockedShots",    "blockedshots",    fallback="0")
    pass_h   = g("home", "totalPasses",     "totalpasses",     fallback="0")
    pass_a   = g("away", "totalPasses",     "totalpasses",     fallback="0")
    passpct_h = fmt_pct(g("home", "passPct", "passpct",        fallback="0"))
    passpct_a = fmt_pct(g("away", "passPct", "passpct",        fallback="0"))

    stats_mappate = [
        ("Possesso palla",    pos_h,      pos_a,      bp_perc),
        ("Tiri in porta",     sot_h,      sot_a,      perc(sot_h,      sot_a)),
        ("Tiri totali",       shots_h,    shots_a,    perc(shots_h,    shots_a)),
        ("Tiri bloccati",     blk_h,      blk_a,      perc(blk_h,      blk_a)),
        ("Corner",            corner_h,   corner_a,   perc(corner_h,   corner_a)),
        ("Fuorigioco",        offside_h,  offside_a,  perc(offside_h,  offside_a)),
        ("Falli",             falli_h,    falli_a,    perc(falli_h,    falli_a)),
        ("Ammoniti",          gialli_h,   gialli_a,   perc(gialli_h,   gialli_a)),
        ("Espulsi",           rossi_h,    rossi_a,    perc(rossi_h,    rossi_a)),
        ("Parate",            saves_h,    saves_a,    perc(saves_h,    saves_a)),
        ("Passaggi totali",   pass_h,     pass_a,     perc(pass_h,     pass_a)),
        ("Precisione passaggi", passpct_h, passpct_a, perc(
            str(passpct_h).replace("%",""), str(passpct_a).replace("%",""))),
    ]

    rows_html = "".join([
        f'<div class="stat-row">'
        f'<div class="stat-top">'
        f'<div class="val home-val">{h}</div>'
        f'<div class="stat-label">{label}</div>'
        f'<div class="val away-val">{a}</div>'
        f'</div>'
        f'<div class="bar-track">'
        f'<div class="bar-home" style="width:{hp}%"></div>'
        f'<div class="bar-away" style="width:{100-hp}%"></div>'
        f'</div>'
        f'</div>'
        for label, h, a, hp in stats_mappate
    ])

    if pen_home > 0 or pen_away > 0:
        score_block_html = (
            f'<div class="score">{home_goals} \u2013 {away_goals}</div>'
            f'<div class="pen-score">({pen_home} - {pen_away})</div>'
        )
    else:
        score_block_html = f'<div class="score">{home_goals} \u2013 {away_goals}</div>'

    # Carica il template HTML esterno
    _template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats.html")
    try:
        with open(_template_path, "r", encoding="utf-8") as f:
            template = f.read()
    except FileNotFoundError:
        print(f"[{now_it()}] ❌ stats.html non trovato in {_template_path}")
        return None

    # Determina il tema maglia (home / away / third / default)
    html_content = (
        template
        .replace("{JUVE_KIT}",    juve_kit)
        .replace("{LEAGUE_NAME}", league_name.upper())
        .replace("{BADGE_LABEL}", badge_label)
        .replace("{H_LOGO}",      h_logo)
        .replace("{HOME_NAME}",   home_name)
        .replace("{SCORE_BLOCK}", score_block_html)
        .replace("{A_LOGO}",      a_logo)
        .replace("{AWAY_NAME}",   away_name)
        .replace("{ROWS_HTML}",   rows_html)
    )

    path_html      = "/tmp/stats.html"
    path_raw_png   = "/tmp/stats_raw.png"
    path_final_png = "/tmp/stats_final.png"

    with open(path_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-web-security", "--allow-running-insecure-content"])
        page = browser.new_page(viewport={"width": 1620, "height": 4000}, device_scale_factor=1.0)
        page.goto(f"file://{path_html}")
        page.wait_for_timeout(3000)
        page.screenshot(path=path_raw_png, clip={"x": 0, "y": 0, "width": 1620, "height": 1980}, omit_background=False)
        browser.close()

    if os.path.exists("texture.png"):
        try:
            base_img = Image.open(path_raw_png).convert("RGBA")
            texture  = Image.open("texture.png").convert("RGBA").resize(base_img.size, Image.Resampling.LANCZOS)
            Image.alpha_composite(base_img, texture).convert("RGB").save(path_final_png, "PNG")
            return path_final_png
        except Exception as e:
            print(f"[{now_it()}] ⚠️  Errore texture stats: {e}")

    return path_raw_png

# ==============================================================================
# ESPN API
# ==============================================================================
def trova_partita_oggi(team_id: str):
    now_utc       = datetime.now(timezone.utc)
    dates_to_try  = [
        now_utc.strftime("%Y%m%d"),
        (now_utc + timedelta(days=1)).strftime("%Y%m%d"),
    ]
    print(f"[{now_it()}] 🔍 Cerco partita per team_id={team_id}...")

    for date_str in dates_to_try:
        for slug in LEAGUE_SLUGS:
            url = f"{ESPN_BASE}/{slug}/scoreboard"
            try:
                r = requests.get(url, params={"dates": date_str}, timeout=10)
                if r.status_code != 200:
                    continue
                data        = r.json()
                league_name = data.get("leagues", [{}])[0].get("name", slug)
                for event in data.get("events", []):
                    competitions = event.get("competitions", [])
                    if not competitions:
                        continue
                    competitors = competitions[0].get("competitors", [])
                    ids = [c.get("team", {}).get("id", "") for c in competitors]
                    if team_id in ids:
                        print(f"[{now_it()}] ✅ Partita trovata: {league_name} — event_id={event['id']}")
                        return {
                            "event_id":    event["id"],
                            "league_slug": slug,
                            "league_name": league_name,
                            "competitors": competitors,
                        }
            except Exception:
                pass

    return None


def fetch_evento(event_id: str, league_slug: str):
    try:
        r = requests.get(f"{ESPN_BASE}/{league_slug}/summary",
                         params={"event": event_id}, timeout=15)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception as e:
        print(f"[{now_it()}] ❌ Errore fetch evento: {e}")
        return None


def parse_score(competitors):
    home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
    away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
    return (
        home.get("team", {}).get("id", ""),
        away.get("team", {}).get("id", ""),
        home.get("team", {}).get("displayName", "Home"),
        away.get("team", {}).get("displayName", "Away"),
        int(home.get("score", 0) or 0),
        int(away.get("score", 0) or 0),
    )


def parse_status(data: dict):
    try:
        comp   = data["header"]["competitions"][0]
        status = comp.get("status", {})
        stype  = status.get("type", {})
        state  = stype.get("state", "pre")
        name   = stype.get("name", "").upper()
        desc   = stype.get("description", "").lower()
        clock  = status.get("displayClock", "0:00")
        period = status.get("period", 1)

        try:
            raw_clock = clock.replace("'", "").split("+")[0].split(":")[0].strip()
            elapsed = int(raw_clock)
        except Exception:
            elapsed = 0

        if state == "pre":
            return "NS", 0

        if state == "post":
            if "PEN" in name:
                return "PEN", 120
            if "AET" in name or "EXTRA" in name:
                return "AET", 120
            return "FT", 90

        if "HALFTIME" in name or "HALF_TIME" in name:
            return "HT", 45
        if "EXTRA_TIME_HALF" in name or "HALFTIME_ET" in name:
            return "HT_ET", 105
        if "PENALTY" in name or "SHOOTOUT" in name:
            return "PEN", elapsed
        if "EXTRA" in name or "OT" in name:
            return "ET", elapsed
        if "END_PERIOD" in name:
            if period <= 2:
                return "HT", 45
            return "ET", elapsed
        if period == 1:
            return "1H", elapsed
        if period == 2:
            return "2H", elapsed
        if period == 3:
            return "ET", elapsed
        if period == 4:
            return "ET", elapsed

        return "1H", elapsed
    except Exception as e:
        print(f"[{now_it()}] ⚠️  Errore parse_status: {e}")
        return "NS", 0


def build_score_str(home_name, away_name, g_home, g_away):
    if g_home > g_away:
        return f"<b>{home_name} {g_home}</b>-{g_away} {away_name}"
    elif g_away > g_home:
        return f"{home_name} {g_home}-<b>{g_away} {away_name}</b>"
    else:
        return f"{home_name} {g_home}-{g_away} {away_name}"


# ==============================================================================
# MAPPA SQUADRE — caricata da teams.json
# ==============================================================================
_TEAMS_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "teams.json")

def _load_teams() -> dict:
    try:
        with open(_TEAMS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        print(f"[{now_it()}] ⚠️  teams.json non trovato in {_TEAMS_JSON_PATH} — nomi squadre non tradotti")
        return {}
    except Exception as e:
        print(f"[{now_it()}] ⚠️  Errore caricamento teams.json: {e}")
        return {}

TEAM_MAP: dict = _load_teams()

def translate_team(name: str) -> str:
    entry = TEAM_MAP.get(name)
    if entry:
        return entry[0]
    name_lower = name.lower()
    for k, v in TEAM_MAP.items():
        if k.lower() == name_lower:
            return v[0]
    return name

def build_hashtag(home_name, away_name):
    def abbr(name):
        entry = TEAM_MAP.get(name)
        if entry:
            return entry[1]
        name_lower = name.lower()
        for k, v in TEAM_MAP.items():
            if k.lower() == name_lower:
                return v[1]
        return name.replace(" ", "")
    return f"#{abbr(home_name)}{abbr(away_name)}"

# ==============================================================================
# CICLO PRINCIPALE
# ==============================================================================
def avvia_ciclo_partita():
    team_id = str(TEAM_ID).strip()

    try:
        test_r = requests.get(f"{ESPN_BASE}/ita.1/scoreboard",
                               params={"dates": datetime.now(timezone.utc).strftime("%Y%m%d")}, timeout=10)
    except Exception as e:
        print(f"[{now_it()}] ⚠️  Test connettività API fallito: {e}")

    partita = trova_partita_oggi(team_id)
    if not partita:
        print(f"[{now_it()}] 📭 Nessun evento trovato per team_id={team_id}.")
        return

    event_id    = partita["event_id"]
    league_slug = partita["league_slug"]
    league_name = partita["league_name"]

    state = leggi_stato_da_gist()
    if state is None or state.get("event_id") != event_id:
        state = {
            "event_id":               event_id,
            "sent_periods":           [],
            "goals_detected":         0,
            "prev_home_goals":        0,
            "prev_away_goals":        0,
            "sent_subs":              {},
            "sent_cards":             [],
            "penalties_count":        0,
            "sent_stats":             [],
            "sent_failed_penalties":  [],
            "shootout_message_id":    None,
            "goal_messages":          {},
            "cancel_msg_id":          None,
        }
    if isinstance(state.get("sent_subs"), list):
        state["sent_subs"] = {}
    # Retrocompatibilità: assicura che cancel_msg_id esista
    if "cancel_msg_id" not in state:
        state["cancel_msg_id"] = None

    while True:
        sleep_time = 6
        state_changed = False
        try:
            data = fetch_evento(event_id, league_slug)
            if not data:
                time.sleep(10)
                continue

            status, elapsed = parse_status(data)

            try:
                competitors = data["header"]["competitions"][0]["competitors"]
            except Exception:
                competitors = partita["competitors"]

            home_id, away_id, home_name_raw, away_name_raw, g_home, g_away = parse_score(competitors)
            home_name = translate_team(home_name_raw)
            away_name = translate_team(away_name_raw)
            score_str = build_score_str(home_name, away_name, g_home, g_away)
            hashtag   = build_hashtag(home_name_raw, away_name_raw)
            e_comp    = get_league_emoji(league_slug)

            events = parse_events(data, home_name_raw, away_name_raw, home_id, away_id)

            if "_intro_logged" not in state:
                print(f"[{now_it()}] 🚀 PARTITA TROVATA: {league_name} | {home_name} vs {away_name} | event_id={event_id}")
                h_raw, a_raw = home_name_raw, away_name_raw
                h_it,  a_it  = home_name, away_name
                if h_raw != h_it:
                    print(f"[{now_it()}] 📋 Traduzione: '{h_raw}' → '{h_it}'")
                else:
                    print(f"[{now_it()}] 📋 '{h_raw}' non in teams.json — usato nome ESPN")
                if a_raw != a_it:
                    print(f"[{now_it()}] 📋 Traduzione: '{a_raw}' → '{a_it}'")
                else:
                    print(f"[{now_it()}] 📋 '{a_raw}' non in teams.json — usato nome ESPN")
                state["_intro_logged"] = True

            _now_ts = int(time.time())
            _log_key = f"{status}_{elapsed}_{g_home}_{g_away}"
            if status != "NS" and (state.get("_last_log_key") != _log_key or (_now_ts - state.get("_last_log_ts", 0)) >= 60):
                print(f"[{now_it()}] 📡 {status} {elapsed}' | {home_name} {g_home}-{g_away} {away_name}")
                state["_last_log_key"] = _log_key
                state["_last_log_ts"] = _now_ts

            # --- Non ancora iniziata ---
            if status == "NS":
                try:
                    comp       = data["header"]["competitions"][0]
                    start_str  = comp.get("date", "")
                    if start_str:
                        start_time         = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                        now_utc            = datetime.now(timezone.utc)
                        minutes_to_kickoff = (start_time - now_utc).total_seconds() / 60
                        if minutes_to_kickoff > 60:
                            print(f"[{now_it()}] 🛑 Troppo presto ({minutes_to_kickoff:.0f} min al via) — bot fermato")
                            sys.exit(0)
                        if "_ns_logged" not in state:
                            print(f"[{now_it()}] ⏳ In attesa del calcio d'inizio ({minutes_to_kickoff:.0f} min al via)")
                            state["_ns_logged"] = True
                except Exception as e:
                    print(f"[{now_it()}] ⚠️  Impossibile leggere orario partita: {e}")
                time.sleep(6)
                continue

            if status == "PEN":
                sleep_time = 6

            # --- Inizio primo tempo ---
            if status == "1H" and "1H" not in state["sent_periods"]:
                print(f"[{now_it()}] ⚡️ INIZIO PARTITA → Telegram inviato")
                send_telegram(f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{home_name} - {away_name}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("1H")
                salva_stato_su_gist(state)
                state_changed = True

            # --- Catchup: partita già in corso con gist vuoto ---
            if state["goals_detected"] == 0 and (g_home + g_away) > 0 and not state.get("goal_messages"):
                _seen_uids = set()
                _seen_min_player = set()
                _deduped = []
                for e in events:
                    if e["type"] in ("goal", "own goal", "penalty goal"):
                        uid = e.get("uid", f"{e['minute']}_{e.get('player_name','')}")
                        min_player_key = f"{e['minute']}_{e.get('player_name','').strip().lower()}"
                        if uid not in _seen_uids and min_player_key not in _seen_min_player:
                            _seen_uids.add(uid)
                            _seen_min_player.add(min_player_key)
                            _deduped.append(e)
                goal_events_all = sorted(_deduped, key=lambda x: x["minute"])
                ch, ca = 0, 0
                for ge in goal_events_all:
                    if ch + ca >= g_home + g_away:
                        break
                    if ge["team_id"] == home_id:
                        ch += 1
                    else:
                        ca += 1

                    p_name = ge.get("player_name", "")
                    a_name = ge.get("assist_name", "")
                    ps = fmt_player(p_name) if p_name else ""
                    if ge["type"] == "own goal" and ps:
                        ps += " (Autogol)"
                    elif ge["type"] == "penalty goal" and ps:
                        ps += " (Rig.)"

                    scorer_line = f"{E_BALL} <i>{ps}</i>\n" if ps else ""
                    assist_line = f"{E_ASSIST} <i>{fmt_player(a_name)}</i>\n" if a_name and a_name != p_name else ""

                    actual_tid = ge["team_id"]

                    if actual_tid == home_id:
                        goal_score = f"<b>{home_name} {ch}</b>-{ca} {away_name}"
                    else:
                        goal_score = f"{home_name} {ch}-<b>{ca} {away_name}</b>"

                    goal_text = f"<b>GOAL · {ge['minute']}\' {E_MIC}</b>\n\n{goal_score}\n{scorer_line}{assist_line}\n{e_comp} {hashtag}"
                    goal_key  = f"{ch}_{ca}"

                    print(f"[{now_it()}] ⚽️  CATCHUP GOAL {ge['minute']}\' {home_name} {ch}-{ca} {away_name} → Telegram inviato")
                    msg_id = send_telegram_get_id(goal_text)
                    state.setdefault("goal_messages", {})[goal_key] = {
                        "msg_id":    msg_id,
                        "scorer":    p_name,
                        "assist":    a_name,
                        "minute":    ge["minute"],
                        "type":      ge["type"],
                        "home_n":    home_name,
                        "away_n":    away_name,
                        "g_home":    ch,
                        "g_away":    ca,
                        "home_id":   home_id,
                        "away_id":   away_id,
                        "score_tid": actual_tid,
                    }
                    time.sleep(2)

                state["goals_detected"]  = g_home + g_away
                state["prev_home_goals"] = g_home
                state["prev_away_goals"] = g_away
                state_changed = True

            # --- Fine primo tempo ---
            if status == "HT" and "HT" not in state["sent_periods"]:
                print(f"[{now_it()}] 🏁 FINE 1° TEMPO ({home_name} {g_home}-{g_away} {away_name}) → Telegram inviato")
                send_telegram(f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("HT")
                salva_stato_su_gist(state)
                state_changed = True
                time.sleep(120)
                data_fresh = fetch_evento(event_id, league_slug) or data
                png_path = recupera_e_genera_stats_html(data_fresh, home_id, away_id,
                                                         home_name, away_name, g_home, g_away,
                                                         "HT", league_name, league_slug=league_slug)
                print(f"[{now_it()}] 📊 STATS 1° TEMPO → foto Telegram inviata")
                send_telegram_stats_photo(png_path, "HT", f"{e_comp} {hashtag}")
                state["sent_stats"].append("HT")
                state_changed = True

            # --- Inizio secondo tempo ---
            if status == "2H" and "2H" not in state["sent_periods"]:
                print(f"[{now_it()}] ⚡️ INIZIO 2° TEMPO → Telegram inviato")
                send_telegram(f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("2H")
                salva_stato_su_gist(state)
                state_changed = True

            # --- Fine regolamentari → supplementari ---
            if status in ("ET", "PEN", "AET") and "2H_END" not in state["sent_periods"] and "FT" not in state["sent_periods"]:
                print(f"[{now_it()}] 🏁 FINE REGOLAMENTARI ({home_name} {g_home}-{g_away} {away_name}) → Telegram inviato")
                send_telegram(f"<b>FINE REGOLAMENTARI {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("2H_END")
                salva_stato_su_gist(state)
                state_changed = True
                if status == "ET":
                    time.sleep(120)
                    data_fresh = fetch_evento(event_id, league_slug) or data
                    png_path = recupera_e_genera_stats_html(data_fresh, home_id, away_id,
                                                             home_name, away_name, g_home, g_away,
                                                             "2H_END", league_name, league_slug=league_slug)
                    send_telegram_stats_photo(png_path, "2H_END", f"{e_comp} {hashtag}")
                    state["sent_stats"].append("2H_END")
                    state_changed = True

            # --- Supplementari ---
            if status == "ET":
                try:
                    comp_status = data["header"]["competitions"][0].get("status", {})
                    stype_name  = comp_status.get("type", {}).get("name", "").upper()
                    et_period   = comp_status.get("period", 1)
                except Exception:
                    stype_name = ""
                    et_period  = 1

                is_et_halftime = any(kw in stype_name for kw in
                                     ("HALFTIME", "HALF_TIME", "HT_ET", "EXTRA_TIME_HALF"))
                is_second_et = (et_period >= 4 or (elapsed >= 106 and et_period >= 3))

                if "1ET_START" not in state["sent_periods"] and not is_et_halftime and not is_second_et:
                    send_telegram(f"<b>INIZIO 1T SUPPLEMENTARE {E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("1ET_START")
                    salva_stato_su_gist(state)
                    state_changed = True

                if (is_et_halftime or is_second_et) and "1ET_END" not in state["sent_periods"]:
                    send_telegram(f"<b>FINE 1T SUPPLEMENTARE {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("1ET_END")
                    salva_stato_su_gist(state)
                    state_changed = True

                if is_second_et and "2ET_START" not in state["sent_periods"]:
                    send_telegram(f"<b>INIZIO 2T SUPPLEMENTARE {E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("2ET_START")
                    salva_stato_su_gist(state)
                    state_changed = True

            # --- Intervallo supplementari ---
            if status == "HT_ET":
                if "1ET_START" not in state["sent_periods"]:
                    state["sent_periods"].append("1ET_START")
                    state_changed = True
                if "1ET_END" not in state["sent_periods"]:
                    send_telegram(f"<b>FINE 1T SUPPLEMENTARE {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("1ET_END")
                    salva_stato_su_gist(state)
                    state_changed = True

            # --- Rigori ---
            if status == "PEN":
                if "ET_END_PENS" not in state["sent_periods"]:
                    if "2ET_START" in state["sent_periods"] or "1ET_START" in state["sent_periods"]:
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
            comp_state_espn = (
                data.get("header", {}).get("competitions", [{}])[0]
                    .get("status", {}).get("type", {}).get("state", "")
            )
            is_finished = (
                status in ("FT", "AET") or
                (status == "PEN" and comp_state_espn == "post")
            )
            if is_finished and "FT" not in state["sent_periods"]:
                home_scorers, away_scorers = [], []
                for e in events:
                    if e["type"] in ("goal", "own goal", "penalty goal"):
                        ps = fmt_player(e["player_name"])
                        if e["type"] == "own goal":
                            ps += " (Autogol)"
                        elif e["type"] == "penalty goal":
                            ps += " (Rig.)"
                        entry = f"{e['minute']}' {ps}"
                        tid = e["team_id"]
                        (home_scorers if tid == home_id else away_scorers).append(entry)

                if home_scorers or away_scorers:
                    parts = []
                    if home_scorers:
                        parts.append(", ".join(home_scorers))
                    if away_scorers:
                        parts.append(", ".join(away_scorers))
                    scorers_line = f"{E_BALL} <i>{' // '.join(parts)}</i>\n"
                else:
                    scorers_line = ""

                has_shootout = (
                    "ET_END_PENS" in state["sent_periods"] or
                    status == "PEN" or
                    len(data.get("shootout", [])) > 0
                )
                if has_shootout:
                    home_pen_goals = sum(1 for e in events if e["type"] == "shootout goal" and e["team_id"] == home_id)
                    away_pen_goals = sum(1 for e in events if e["type"] == "shootout goal" and e["team_id"] == away_id)
                    if home_pen_goals > 0 or away_pen_goals > 0:
                        if home_pen_goals > away_pen_goals:
                            pen_score_str = (
                                f"<b>{home_name} {g_home} ({home_pen_goals})</b>-({away_pen_goals}) {g_away} {away_name}"
                            )
                        elif away_pen_goals > home_pen_goals:
                            pen_score_str = (
                                f"{home_name} {g_home} ({home_pen_goals})-<b>({away_pen_goals}) {g_away} {away_name}</b>"
                            )
                        else:
                            pen_score_str = (
                                f"{home_name} {g_home} ({home_pen_goals})-({away_pen_goals}) {g_away} {away_name}"
                            )
                        score_str = pen_score_str

                msg_finale = f"<b>FINE PARTITA {E_FLAG}</b>\n\n{score_str}\n{scorers_line}\n{e_comp} {hashtag}"

                is_juve_match = home_id == '111' or away_id == '111'
                if is_juve_match:
                    canva_token = get_valid_token()
                    if canva_token:
                        foto = get_canva_image(canva_token)
                        send_telegram_with_photo(msg_finale, foto)
                    else:
                        send_telegram(msg_finale)
                else:
                    send_telegram(msg_finale)

                time.sleep(120)
                data_fresh = fetch_evento(event_id, league_slug) or data
                ft_pen_home = sum(1 for e in events if e["type"] == "shootout goal" and e["team_id"] == home_id)
                ft_pen_away = sum(1 for e in events if e["type"] == "shootout goal" and e["team_id"] == away_id)
                png_path = recupera_e_genera_stats_html(data_fresh, home_id, away_id,
                                                         home_name, away_name, g_home, g_away,
                                                         "FT", league_name, league_slug=league_slug,
                                                         pen_home=ft_pen_home, pen_away=ft_pen_away)
                print(f"[{now_it()}] 📊 STATS FINE PARTITA → foto Telegram inviata")
                send_telegram_stats_photo(png_path, "FT", f"{e_comp} {hashtag}")
                state["sent_stats"].append("FT")
                state_changed = True
                state["_reset_done"] = True
                resetta_gist()
                print(f"[{now_it()}] 🏆 FINE PARTITA ({home_name} {g_home}-{g_away} {away_name}) — bot terminato")
                sys.exit(0)

            # --- Rilevamento goal ---
            total_goals_now = g_home + g_away
            prev_home = state.get("prev_home_goals", 0)
            prev_away = state.get("prev_away_goals", 0)

            if total_goals_now > state["goals_detected"]:
                time.sleep(15)
                data_confirm = fetch_evento(event_id, league_slug) or data
                try:
                    competitors_confirm = data_confirm["header"]["competitions"][0]["competitors"]
                except Exception:
                    competitors_confirm = competitors
                _, _, _, _, g_home_c, g_away_c = parse_score(competitors_confirm)
                if g_home_c + g_away_c != total_goals_now:
                    print(f"[{now_it()}] ⚠️  Punteggio instabile ({g_home}-{g_away} → {g_home_c}-{g_away_c}), attendo conferma...")
                    time.sleep(sleep_time)
                    continue
                data   = data_confirm
                g_home = g_home_c
                g_away = g_away_c
                events = parse_events(data, home_name_raw, away_name_raw, home_id, away_id)
                score_str = build_score_str(home_name, away_name, g_home, g_away)

                if g_home > prev_home:
                    scoring_tid = home_id
                    expected_home_goals = g_home
                    expected_away_goals = prev_away
                elif g_away > prev_away:
                    scoring_tid = away_id
                    expected_home_goals = prev_home
                    expected_away_goals = g_away
                else:
                    scoring_tid = None
                    expected_home_goals = g_home
                    expected_away_goals = g_away

                goal_events = [e for e in events
                               if e["type"] in ("goal", "own goal", "penalty goal")]

                if scoring_tid:
                    team_goals = [e for e in goal_events if e["type"] != "own goal" and e["team_id"] == scoring_tid]
                    own_goals_vs = [e for e in goal_events if e["type"] == "own goal" and e["team_id"] != scoring_tid]
                    candidates = sorted(team_goals + own_goals_vs, key=lambda x: x["minute"])

                    expected_count = g_home if scoring_tid == home_id else g_away

                    last = candidates[expected_count - 1] if len(candidates) >= expected_count else (candidates[-1] if candidates else None)

                    if not last:
                        time.sleep(sleep_time)
                        continue

                    player_name = last.get("player_name", "")
                    assist_name = last.get("assist_name", "")
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

                    if assist_name and assist_name != player_name:
                        assist_line = f"{E_ASSIST} <i>{fmt_player(assist_name)}</i>\n"
                    else:
                        assist_line = ""

                    if actual_scoring_tid == home_id:
                        goal_score = f"<b>{home_name} {g_home}</b>-{g_away} {away_name}"
                    else:
                        goal_score = f"{home_name} {g_home}-<b>{g_away} {away_name}</b>"

                    goal_text = f"<b>GOAL · {last['minute']}' {E_MIC}</b>\n\n{goal_score}\n{scorer_line}{assist_line}\n{e_comp} {hashtag}"
                    goal_key = f"{g_home}_{g_away}"

                    if not state.get("goal_messages", {}).get(goal_key, {}).get("msg_id"):
                        _scorer_log = f" {fmt_player(player_name)}" if player_name else " (marcatore in attesa)"
                        _assist_log = f" | assist: {fmt_player(assist_name)}" if assist_name and assist_name != player_name else ""
                        print(f"[{now_it()}] ⚽️  GOAL{_scorer_log}{_assist_log} ({home_name} {g_home}-{g_away} {away_name}) → Telegram inviato")
                        msg_id = send_telegram_get_id(goal_text)
                        state.setdefault("goal_messages", {})[goal_key] = {
                            "msg_id":    msg_id,
                            "scorer":    player_name,
                            "assist":    assist_name,
                            "minute":    last["minute"],
                            "type":      last["type"],
                            "home_n":    home_name,
                            "away_n":    away_name,
                            "g_home":    g_home,
                            "g_away":    g_away,
                            "home_id":   home_id,
                            "away_id":   away_id,
                            "score_tid": actual_scoring_tid,
                        }
                        state_changed = True

                state["goals_detected"] = total_goals_now
                state_changed = True
                state["prev_home_goals"] = g_home
                state_changed = True
                state["prev_away_goals"] = g_away
                state_changed = True

            elif total_goals_now < state["goals_detected"]:
                # ======================================================
                # GOAL ANNULLATO — logica corretta
                # ======================================================
                print(f"[{now_it()}] ⚠️  Possibile annullamento, attendo conferma (120s)...")
                time.sleep(120)
                data_cancel = fetch_evento(event_id, league_slug) or data
                try:
                    competitors_cancel = data_cancel["header"]["competitions"][0]["competitors"]
                except Exception:
                    competitors_cancel = competitors
                _, _, _, _, g_home_c, g_away_c = parse_score(competitors_cancel)

                if g_home_c + g_away_c < state["goals_detected"]:
                    # ✅ Annullamento confermato
                    g_home = g_home_c
                    g_away = g_away_c
                    score_str = build_score_str(home_name, away_name, g_home, g_away)
                    print(f"[{now_it()}] 📺 GOAL ANNULLATO → Telegram inviato")
                    cancel_msg_id = send_telegram_get_id(
                        f"<b>GOAL ANNULLATO {E_CANCEL}</b>\n\n{score_str}\n\n{e_comp} {hashtag}"
                    )
                    # Salva msg_id per eventuale cancellazione futura
                    state["cancel_msg_id"] = cancel_msg_id

                    # Pulisci goal_messages per le chiavi non più valide
                    keys_to_remove = [
                        k for k in state.get("goal_messages", {})
                        if int(k.split("_")[0]) + int(k.split("_")[1]) > g_home_c + g_away_c
                    ]
                    for k in keys_to_remove:
                        state["goal_messages"].pop(k, None)

                    state["goals_detected"]  = g_home_c + g_away_c
                    state["prev_home_goals"] = g_home_c
                    state["prev_away_goals"] = g_away_c
                    state_changed = True

                else:
                    # ✅ Punteggio tornato normale: era un errore ESPN
                    print(f"[{now_it()}] ℹ️  Punteggio tornato stabile ({g_home_c}-{g_away_c}), aggiorno eventi per correzione marcatori")

                    # Se avevamo già inviato un "GOAL ANNULLATO" per errore, cancellalo
                    if state.get("cancel_msg_id"):
                        print(f"[{now_it()}] 🗑️  Cancello messaggio GOAL ANNULLATO (falso positivo)")
                        delete_telegram_message(state["cancel_msg_id"])
                        state["cancel_msg_id"] = None

                    data   = data_cancel
                    events = parse_events(data, home_name_raw, away_name_raw, home_id, away_id)
                    g_home = g_home_c
                    g_away = g_away_c
                    state["prev_home_goals"] = g_home_c
                    state["prev_away_goals"] = g_away_c
                    # goals_detected rimane invariato — corretto
                    state_changed = True

            # --- Correzione marcatori ---
            for goal_key, saved in list(state.get("goal_messages", {}).items()):
                msg_id = saved.get("msg_id")
                if not msg_id:
                    continue

                try:
                    gh, ga = map(int, goal_key.split("_"))
                except ValueError:
                    continue

                s_home_id = saved.get("home_id", home_id)
                s_away_id = saved.get("away_id", away_id)
                s_home_n  = saved.get("home_n", home_name)
                s_away_n  = saved.get("away_n", away_name)
                s_tid     = saved.get("score_tid")

                goal_events_all = [e for e in events if e["type"] in ("goal", "own goal", "penalty goal")]

                if s_tid == s_home_id:
                    team_goals   = [e for e in goal_events_all if e["type"] != "own goal" and e["team_id"] == s_home_id]
                    own_goals_vs = [e for e in goal_events_all if e["type"] == "own goal" and e["team_id"] == s_home_id]
                    candidates   = sorted(team_goals + own_goals_vs, key=lambda x: x["minute"])
                    idx = gh - 1
                else:
                    team_goals   = [e for e in goal_events_all if e["type"] != "own goal" and e["team_id"] == s_away_id]
                    own_goals_vs = [e for e in goal_events_all if e["type"] == "own goal" and e["team_id"] == s_away_id]
                    candidates   = sorted(team_goals + own_goals_vs, key=lambda x: x["minute"])
                    idx = ga - 1

                if idx < 0 or idx >= len(candidates):
                    continue

                current = candidates[idx]
                current_scorer = current.get("player_name", "")
                current_assist = current.get("assist_name", "")
                current_type = current.get("type", saved.get("type", "goal"))

                if (current_scorer != saved.get("scorer")) or \
                   (current_assist != saved.get("assist", "")) or \
                   (current_type != saved.get("type", "goal")):

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

                    actual_tid = s_tid

                    if actual_tid == s_home_id:
                        goal_score_new = f"<b>{s_home_n} {gh}</b>-{ga} {s_away_n}"
                    else:
                        goal_score_new = f"{s_home_n} {gh}-<b>{ga} {s_away_n}</b>"

                    e_comp_saved = get_league_emoji(league_slug)
                    hashtag_saved = build_hashtag(s_home_n, s_away_n)
                    goal_text_new = f"<b>GOAL · {current['minute']}' {E_MIC}</b>\n\n{goal_score_new}\n{scorer_line_new}{assist_line_new}\n{e_comp_saved} {hashtag_saved}"

                    changes = []
                    if current_scorer != saved.get("scorer"):
                        changes.append(f"marcatore: {saved.get('scorer')} → {current_scorer}")
                    if current_assist != saved.get("assist", ""):
                        old_a = saved.get("assist", "—") or "—"
                        new_a = current_assist or "—"
                        changes.append(f"assist: {old_a} → {new_a}")
                    if current_type != saved.get("type", "goal"):
                        changes.append(f"tipo: {saved.get('type', 'goal')} → {current_type}")

                    print(f"[{now_it()}] ✏️  CORREZIONE goal {goal_key}: {', '.join(changes)} → messaggio editato")
                    send_telegram_edit(msg_id, goal_text_new)

                    state["goal_messages"][goal_key]["scorer"]    = current_scorer
                    state["goal_messages"][goal_key]["assist"]    = current_assist
                    state["goal_messages"][goal_key]["type"]      = current_type
                    state["goal_messages"][goal_key]["score_tid"] = actual_tid
                    state_changed = True

            # --- Cambi ---
            new_subs_fresh  = []
            new_subs_edit   = []

            for e in events:
                if e["type"] != "substitution":
                    continue
                sub_id = e["uid"]
                already_sent = any(sub_id in slot["sub_ids"] for slot in state["sent_subs"].values())
                if already_sent:
                    continue
                # Bug 1: stesso cambio ma ESPN ha corretto il minuto → uid diverso ma giocatore uguale
                already_sent_by_name = any(
                    k.split(":")[0] == e["team_id"] and fmt_player(e["player_name"]) in slot["outs"]
                    for k, slot in state["sent_subs"].items()
                )
                if already_sent_by_name:
                    continue

                slot_key = None
                for k, slot in state["sent_subs"].items():
                    if k.split(":")[0] == e["team_id"] and abs(slot["minute"] - e["minute"]) <= 2:
                        slot_key = k
                        break

                if slot_key:
                    new_subs_edit.append((e, slot_key))
                else:
                    new_subs_fresh.append(e)

            for e, slot_key in new_subs_edit:
                slot       = state["sent_subs"][slot_key]
                team_title = home_name.upper() if e["team_id"] == home_id else away_name.upper()
                # Bug 2: ESPN restituisce gli stessi sub più volte, evita duplicati nello slot
                if fmt_player(e["player_name"]) in slot["outs"]:
                    continue
                slot["ins"].append(fmt_player(e["assist_name"]))
                slot["outs"].append(fmt_player(e["player_name"]))
                slot["sub_ids"].append(e["uid"])
                ins_str  = ", ".join(slot["ins"])
                outs_str = ", ".join(slot["outs"])
                new_text = (
                    f"<b>CAMBIO {team_title} · {slot['minute']}' {E_SUB}</b>\n\n"
                    f"{E_UP} {ins_str}\n"
                    f"{E_DOWN} {outs_str}\n\n"
                    f"{e_comp} {hashtag}"
                )
                print(f"[{now_it()}] ✏️  CAMBIO EDIT {team_title} {slot['minute']}' | ↑ {ins_str} / ↓ {outs_str}")
                send_telegram_edit(slot["msg_id"], new_text)
                state_changed = True

            if new_subs_fresh:
                print(f"[{now_it()}] 🔄 Cambio rilevato, attendo 10s per raggruppare...")
                time.sleep(10)
                data_fresh2 = fetch_evento(event_id, league_slug) or data
                events_fresh2 = parse_events(data_fresh2, home_name_raw, away_name_raw, home_id, away_id)

                pending = []
                for e in events_fresh2:
                    if e["type"] != "substitution":
                        continue
                    sub_id = e["uid"]
                    already_sent = any(sub_id in slot["sub_ids"] for slot in state["sent_subs"].values())
                    if already_sent:
                        continue
                    if any(sub_id == ex["uid"] for _, _ in new_subs_edit for ex in [e]):
                        pass
                    slot_key = None
                    for k, slot in state["sent_subs"].items():
                        if k.split(":")[0] == e["team_id"] and abs(slot["minute"] - e["minute"]) <= 2:
                            slot_key = k
                            break
                    if slot_key:
                        slot       = state["sent_subs"][slot_key]
                        team_title = home_name.upper() if e["team_id"] == home_id else away_name.upper()
                        slot["ins"].append(fmt_player(e["assist_name"]))
                        slot["outs"].append(fmt_player(e["player_name"]))
                        slot["sub_ids"].append(sub_id)
                        ins_str  = ", ".join(slot["ins"])
                        outs_str = ", ".join(slot["outs"])
                        new_text = (
                            f"<b>CAMBIO {team_title} · {slot['minute']}' {E_SUB}</b>\n\n"
                            f"{E_UP} {ins_str}\n"
                            f"{E_DOWN} {outs_str}\n\n"
                            f"{e_comp} {hashtag}"
                        )
                        print(f"[{now_it()}] ✏️  CAMBIO EDIT (post-attesa) {team_title} {slot['minute']}' | ↑ {ins_str} / ↓ {outs_str}")
                        send_telegram_edit(slot["msg_id"], new_text)
                        state_changed = True
                    else:
                        pending.append(e)

                groups = []
                for sub in pending:
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
                    ins_str  = ", ".join(fmt_player(s["assist_name"]) for s in g["subs"])
                    outs_str = ", ".join(fmt_player(s["player_name"]) for s in g["subs"])
                    _min_ref = g["minute"]
                    new_text = (
                        f"<b>CAMBIO {team_title} · {_min_ref}' {E_SUB}</b>\n\n"
                        f"{E_UP} {ins_str}\n"
                        f"{E_DOWN} {outs_str}\n\n"
                        f"{e_comp} {hashtag}"
                    )
                    print(f"[{now_it()}] 🔄 CAMBIO {team_title} {_min_ref}' | ↑ {ins_str} / ↓ {outs_str} → Telegram inviato")
                    msg_id = send_telegram_get_id(new_text)
                    new_key = f"{g['team_id']}:{_min_ref}"
                    state["sent_subs"][new_key] = {
                        "msg_id":  msg_id,
                        "minute":  _min_ref,
                        "ins":     [fmt_player(s["assist_name"]) for s in g["subs"]],
                        "outs":    [fmt_player(s["player_name"]) for s in g["subs"]],
                        "sub_ids": [s["uid"] for s in g["subs"]],
                    }
                    state_changed = True

            # --- Cartellini rossi / doppio giallo ---
            for e in events:
                if e["type"] in ("red card", "second yellow card"):
                    p_name  = fmt_player(e["player_name"])
                    card_id = f"card_{e['player_name']}".replace(" ", "_")
                    if card_id not in state["sent_cards"]:
                        is_second_yellow = e["type"] == "second yellow card"
                        label = "DOPPIO GIALLO" if is_second_yellow else "CARTELLINO ROSSO"
                        print(f"[{now_it()}] 🟥 {label} {e['minute']}' {p_name} → Telegram inviato")
                        send_telegram(
                            f"<b>{label} · {e['minute']}' {E_RED}</b>\n\n"
                            f"{E_EXIT} <i>{p_name}</i>\n\n{e_comp} {hashtag}"
                        )
                        state["sent_cards"].append(card_id)
                        state_changed = True

            # --- Rigori sbagliati ---
            for e in events:
                if e["type"] in ("penalty missed", "penalty saved"):
                    pen_id = f"failpen_{e['minute']}_{e['player_name']}".replace(" ", "_")
                    if pen_id not in state["sent_failed_penalties"]:
                        state["sent_failed_penalties"].append(pen_id)
                        state_changed = True
                        team_name = home_name if e["team_id"] == home_id else away_name
                        print(f"[{now_it()}] 🥅 RIGORE SBAGLIATO {team_name.upper()} {e['minute']}' {fmt_player(e['player_name'])} → Telegram inviato")
                        send_telegram(
                            f"<b>RIGORE SBAGLIATO {team_name.upper()} · {e['minute']}' {E_KICK}</b>\n\n"
                            f"{E_PEN_KO} <i>{fmt_player(e['player_name'])}</i>\n\n"
                            f"{e_comp} {hashtag}"
                        )

        except Exception as e:
            print(f"[{now_it()}] ❌ Errore ciclo live: {e}")
            sleep_time = 6

        finally:
            if isinstance(state, dict) and not state.get("_reset_done") and state_changed:
                salva_stato_su_gist(state)

        time.sleep(sleep_time)

# ==============================================================================
# MAIN
# ==============================================================================
def main():
    print(f"[{now_it()}] 🚀 Bot avviato")

    if str(os.getenv('ONLY_REFRESH_TOKEN', '')).strip().lower() == "true":
        get_valid_token()
        return

    avvia_ciclo_partita()

if __name__ == "__main__":
    main()
