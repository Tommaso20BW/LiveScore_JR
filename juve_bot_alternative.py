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
    print("⚠️ pynacl non installata. Aggiornamento Secrets GitHub non disponibile.")

# ==============================================================================
# CONFIGURAZIONE
# ==============================================================================
BOT_TOKEN           = os.getenv('TELEGRAM_TOKEN')
CHAT_ID             = os.getenv('TELEGRAM_TO')
TEAM_ID             = '209'
GH_PAT              = os.getenv('GH_PAT')
GITHUB_REPOSITORY   = os.getenv('GITHUB_REPOSITORY')
GIST_ID             = os.getenv('GIST_ID')
CLIENT_ID           = os.getenv('CANVA_CLIENT_ID')
CLIENT_SECRET       = os.getenv('CANVA_CLIENT_SECRET')
CANVA_REFRESH_TOKEN = os.getenv('CANVA_REFRESH_TOKEN')

CANVA_DESIGN_ID = "DAHI3ytu6yQ"
PAGINA_TARGET   = 11

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

LEAGUE_SLUGS = [
    "ita.1", "ita.coppa_italia", "ita.super_cup", "ita.2",
    "uefa.champions", "uefa.europa", "uefa.europa_conf", "uefa.super_cup",
    "eng.1", "eng.fa", "eng.league_cup", "eng.community", "eng.2", "eng.3", "eng.4",
    "esp.1", "esp.copa_del_rey", "esp.super_cup", "esp.2",
    "ger.1", "ger.dfb_pokal", "ger.2",
    "fra.1", "fra.coupe_de_france", "fra.2",
    "por.1", "ned.1", "bel.1", "tur.1", "sco.1",
    "rus.1", "ukr.1", "gre.1", "aut.1", "sui.1", "den.1", "nor.1", "swe.1",
    "usa.1", "usa.open", "usa.leagues_cup", "usa.mls.is.back",
    "mex.1", "mex.copa_mx", "mex.campeon_campeones",
    "concacaf.champions",
    "bra.1", "arg.1", "col.1", "chi.1", "ecu.1", "per.1", "uru.1",
    "conmebol.libertadores", "conmebol.sudamericana",
    "aus.1", "jpn.1", "chn.1", "sau.1", "afc.champions",
    "caf.champions",
    "friendly.club",
    "usa.nwsl", "eng.w.1", "fra.w.1", "ger.w.1", "esp.w.1",
    "uefa.w.champions", "fifa.w.world", "fifa.w.world.q",
    "uefa.w.euro", "uefa.w.nations", "olympics.w.soccer",
    "fifa.world", "fifa.world.q", "fifa.confed", "fifa.friendly", "olympics.m.soccer",
    "uefa.euro", "uefa.euro.q", "uefa.nations",
    "conmebol.america", "conmebol.america.q",
    "concacaf.gold", "concacaf.nations",
    "caf.nations", "caf.nations.q",
    "afc.asian_cup", "afc.asian_cup.q"
]

LEAGUE_EMOJIS = {
    "ita.1": "🇮🇹", "ita.coppa_italia": "🇮🇹", "ita.super_cup": "🇮🇹", "ita.2": "🇮🇹",
    "uefa.champions": "🇪🇺", "uefa.europa": "🇪🇺", "uefa.europa_conf": "🇪🇺", "uefa.super_cup": "🇪🇺",
    "eng.1": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "eng.fa": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "eng.league_cup": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "eng.community": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "eng.2": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "eng.3": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "eng.4": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "esp.1": "🇪🇸", "esp.copa_del_rey": "🇪🇸", "esp.super_cup": "🇪🇸", "esp.2": "🇪🇸",
    "ger.1": "🇩🇪", "ger.dfb_pokal": "🇩🇪", "ger.2": "🇩🇪",
    "fra.1": "🇫🇷", "fra.coupe_de_france": "🇫🇷", "fra.2": "🇫🇷",
    "por.1": "🇵🇹", "ned.1": "🇳🇱", "bel.1": "🇧🇪", "tur.1": "🇹🇷", "sco.1": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "rus.1": "🇷🇺", "ukr.1": "🇺🇦", "gre.1": "🇬🇷", "aut.1": "🇦🇹", "sui.1": "🇨🇭",
    "den.1": "🇩🇰", "nor.1": "🇳🇴", "swe.1": "🇸🇪",
    "usa.1": "🇺🇸", "usa.open": "🇺🇸", "usa.leagues_cup": "🌎", "usa.mls.is.back": "🇺🇸",
    "mex.1": "🇲🇽", "mex.copa_mx": "🇲🇽", "mex.campeon_campeones": "🇲🇽",
    "concacaf.champions": "🌎",
    "bra.1": "🇧🇷", "arg.1": "🇦🇷", "col.1": "🇨🇴", "chi.1": "🇨🇱", "ecu.1": "🇪🇨",
    "per.1": "🇵🇪", "uru.1": "🇺🇾", "conmebol.libertadores": "🌎", "conmebol.sudamericana": "🌎",
    "aus.1": "🇦🇺", "jpn.1": "🇯🇵", "chn.1": "🇨🇳", "sau.1": "🇸🇦", "afc.champions": "🌏",
    "caf.champions": "🌍",
    "friendly.club": "🤝",
    "usa.nwsl": "🇺🇸", "eng.w.1": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "fra.w.1": "🇫🇷", "ger.w.1": "🇩🇪", "esp.w.1": "🇪🇸",
    "uefa.w.champions": "🇪🇺", "fifa.w.world": "🏆", "fifa.w.world.q": "🌍",
    "uefa.w.euro": "🇪🇺", "uefa.w.nations": "🇪🇺", "olympics.w.soccer": "🏅",
    "fifa.world": "🏆", "fifa.world.q": "🌍", "fifa.confed": "🏆", "fifa.friendly": "🌍", "olympics.m.soccer": "🏅",
    "uefa.euro": "🇪🇺", "uefa.euro.q": "🇪🇺", "uefa.nations": "🇪🇺",
    "conmebol.america": "🌎", "conmebol.america.q": "🌎",
    "concacaf.gold": "🌎", "concacaf.nations": "🌎",
    "caf.nations": "🌍", "caf.nations.q": "🌍",
    "afc.asian_cup": "🌏", "afc.asian_cup.q": "🌏"
}

def get_league_emoji(slug): return LEAGUE_EMOJIS.get(slug, "⚽️")

MOMENTI_CONFIG = {
    "HT":     {"titolo": "<b>STATS PRIMO TEMPO</b> 📊",   "badge": "FINE PRIMO TEMPO"},
    "2H_END": {"titolo": "<b>STATS SECONDO TEMPO</b> 📊", "badge": "FINE SECONDO TEMPO"},
    "FT":     {"titolo": "<b>STATS FINE PARTITA</b> 📊",  "badge": "FINE PARTITA"},
}

E_BOLT   = '⚡️'
E_FLAG   = '🏁'
E_MIC    = '🎙'
E_BALL   = '⚽️'
E_SUB    = '🔄'
E_UP     = '🔼'
E_DOWN   = '🔽'
E_RED    = '🟥'
E_PEN_OK = '✅'
E_PEN_KO = '❌'

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
    # Ordina per lunghezza decrescente: le chiavi piu specifiche hanno precedenza
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
        print("⚠️ BOT_TOKEN o CHAT_ID mancanti.")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"❌ Errore Telegram: {e}")

def send_telegram_edit(message_id: int, text: str):
    """Edita un messaggio Telegram già inviato."""
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
        print(f"❌ Errore editMessageText: {e}")

def send_telegram_get_id(text: str) -> int | None:
    """Invia un messaggio Telegram e restituisce il message_id."""
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️ BOT_TOKEN o CHAT_ID mancanti.")
        return None
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
        r.raise_for_status()
        msg_id = r.json().get("result", {}).get("message_id")
        return msg_id
    except Exception as e:
        print(f"❌ Errore Telegram: {e}")
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
        print(f"❌ Errore invio foto statistiche: {e}")

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
        print(f"❌ Errore update secret: {e}")
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
        print(f"❌ Errore lettura Gist: {e}")
        return None

def salva_stato_su_gist(state: dict):
    if not GH_PAT or not GIST_ID:
        return
    try:
        payload = {"files": {"match_state.json": {"content": json.dumps(state, ensure_ascii=False)}}}
        r = requests.patch(f"https://api.github.com/gists/{GIST_ID}", headers=_gist_headers(),
                           json=payload, timeout=10)
        if r.status_code == 200:
            pass
    except Exception as e:
        print(f"❌ Eccezione salvataggio Gist: {e}")

def resetta_gist():
    if not GH_PAT or not GIST_ID:
        return
    try:
        payload = {"files": {"match_state.json": {"content": "{}"}}}
        requests.patch(f"https://api.github.com/gists/{GIST_ID}", headers=_gist_headers(),
                       json=payload, timeout=10)
    except Exception as e:
        print(f"❌ Eccezione reset Gist: {e}")

# ==============================================================================
# CANVA
# ==============================================================================
def get_valid_token():
    if not CANVA_REFRESH_TOKEN:
        print("❌ CANVA_REFRESH_TOKEN mancante.")
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
        print(f"❌ Errore token Canva: {r.text}")
    except Exception as e:
        print(f"❌ Errore connessione Canva: {e}")
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
                        time.sleep(10)
                        return requests.get(url_dl, timeout=30).content
                elif stato == "failed":
                    return None
    except Exception as e:
        print(f"❌ Errore Canva: {e}")
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
            # Gestisce "45'+7'" → base=45, extra=7 → 52
            if "+" in s:
                parts_plus = s.split("+")
                base  = int(float(parts_plus[0].replace("'", "").strip()))
                extra = int(float(parts_plus[1].replace("'", "").strip()))
                return base + extra
            s = s.replace("'", "").strip()
            # Gestisce "MM:SS"
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

            # ✅ FIX: per le sostituzioni participants[0]=entra, participants[1]=esce
            if normalize_event_type(ev_type) == "substitution":
                player = extract_athlete(parts, 1)  # esce
                assist = extract_athlete(parts, 0)  # entra
            else:
                player = extract_athlete(parts, 0)
                assist = extract_athlete(parts, 1)

            # ✅ FIX ESPN: period=5 = shootout; "Penalty - Scored/Missed/Saved" va rimappato
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
            print(f"⚠️ Errore parsing commentary: {e}")

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

            # ✅ FIX: per le sostituzioni participants[0]=entra, participants[1]=esce
            if normalize_event_type(ev_type) == "substitution":
                player = extract_athlete(parts, 1)  # esce
                assist = extract_athlete(parts, 0)  # entra
            else:
                player = extract_athlete(parts, 0)
                assist = extract_athlete(parts, 1)

            t_name  = play.get("team", {}).get("displayName", "")
            t_id    = play.get("team", {}).get("id", "")
            if not t_id and t_name:
                t_id = home_id if t_name.lower() == home_name.lower() else away_id
            add_event(ev_type, minute, t_id, player, assist, uid)
        except Exception as e:
            print(f"⚠️ Errore parsing keyEvent: {e}")

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
            print(f"⚠️ Errore parsing scoringPlay: {e}")

    # --- FONTE 4: shootout[] (rigori dal dischetto) ---
    # Struttura reale ESPN: .id=team_id, .team=stringa nome, .shots[]=calci con .didScore e .player
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
            # Supporta sia shots (ESPN reale) che shootoutAttempts (schema alternativo)
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
            print(f"⚠️ Errore parsing shootout: {e}")

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
        print(f"⚠️ Errore parsing boxscore.teams: {e}")

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
        print(f"⚠️ Errore parsing header competitors stats: {e}")

    return raw


def recupera_e_genera_stats_html(data_espn: dict, home_id: str, away_id: str,
                                  home_name: str, away_name: str,
                                  home_goals: int, away_goals: int,
                                  momento: str, league_name: str = "SERIE A",
                                  pen_home: int = 0, pen_away: int = 0):

    JUVE_ID     = '111'
    JUVE_LOGO   = "https://upload.wikimedia.org/wikipedia/commons/9/99/Juventus_FC_2017_squared_icon_%28white%29.png"
    h_logo      = JUVE_LOGO if str(home_id) == JUVE_ID else f"https://a.espncdn.com/i/teamlogos/soccer/500/{home_id}.png"
    a_logo      = JUVE_LOGO if str(away_id) == JUVE_ID else f"https://a.espncdn.com/i/teamlogos/soccer/500/{away_id}.png"
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
.score-wrap {{ text-align: center; }}
.score {{ font-family: 'Barlow Condensed', sans-serif; font-size: 170px; line-height: 0.85; font-weight: 900; color: white; letter-spacing: -4px; }}
.pen-score {{ font-family: 'Barlow Condensed', sans-serif; font-size: 40px; line-height: 1.1; font-weight: 700; color: white; text-align: center; margin-top: 8px; }}
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
            print(f"⚠️ Errore texture: {e}")

    return path_raw_png

# ==============================================================================
# ESPN API
# ==============================================================================
def trova_partita_oggi(team_id: str):
    now_utc       = datetime.now(timezone.utc)
    dates_to_try  = [
        (now_utc - timedelta(days=1)).strftime("%Y%m%d"),
        now_utc.strftime("%Y%m%d"),
        (now_utc + timedelta(days=1)).strftime("%Y%m%d"),
    ]
    print(f"🔍 Cerco partita per team_id={team_id}...")

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
                        print(f"✅ Partita trovata: {league_name} — event_id={event['id']}")
                        return {
                            "event_id":    event["id"],
                            "league_slug": slug,
                            "league_name": league_name,
                            "competitors": competitors,
                        }
            except Exception:
                pass

    print(f"📭 Nessun evento trovato per team_id={team_id}.")
    return None


def fetch_evento(event_id: str, league_slug: str):
    try:
        r = requests.get(f"{ESPN_BASE}/{league_slug}/summary",
                         params={"event": event_id}, timeout=15)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception as e:
        print(f"❌ Errore fetch evento: {e}")
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

        # In gioco — usa name come riferimento principale
        if "HALFTIME" in name or "HALF_TIME" in name:
            return "HT", 45
        if "EXTRA_TIME_HALF" in name or "HALFTIME_ET" in name:
            return "HT_ET", 105
        if "PENALTY" in name or "SHOOTOUT" in name:
            return "PEN", elapsed
        if "EXTRA" in name or "OT" in name:
            return "ET", elapsed
        if "END_PERIOD" in name:
            # Fine di un periodo — determina quale
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
        print(f"⚠️ Errore parse_status: {e}")
        return "NS", 0


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

    # Test connettività API
    try:
        test_r = requests.get(f"{ESPN_BASE}/ita.1/scoreboard",
                               params={"dates": datetime.now(timezone.utc).strftime("%Y%m%d")}, timeout=10)
    except Exception as e:
        print(f"⚠️ Test API fallito: {e}")

    partita = trova_partita_oggi(team_id)
    if not partita:
        print(f"📭 Nessun evento trovato per team_id={team_id}.")
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
            "sent_subs":              [],
            "sent_cards":             [],
            "penalties_count":        0,
            "sent_stats":             [],
            "sent_failed_penalties":  [],
            "shootout_message_id":    None,
        }

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

            home_id, away_id, home_name, away_name, g_home, g_away = parse_score(competitors)
            score_str = build_score_str(home_name, away_name, g_home, g_away)
            hashtag   = build_hashtag(home_name, away_name)
            e_comp    = get_league_emoji(league_slug)

            events = parse_events(data, home_name, away_name, home_id, away_id)

            if "_intro_logged" not in state:
                print(f"📅 {league_name} — {home_name} vs {away_name}")
                state["_intro_logged"] = True
            print(f"[{status} {elapsed}'] {home_name} {g_home}-{g_away} {away_name}")

            # --- Non ancora iniziata ---
            if status == "NS":
                try:
                    comp       = data["header"]["competitions"][0]
                    start_str  = comp.get("date", "")
                    if start_str:
                        start_time         = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                        now_utc            = datetime.now(timezone.utc)
                        minutes_to_kickoff = (start_time - now_utc).total_seconds() / 60
                        if minutes_to_kickoff > 0:
                            print(f"⏳ Inizio tra {minutes_to_kickoff:.0f} min — in attesa")
                        else:
                            print(f"⏳ Partita iniziata da {abs(minutes_to_kickoff):.0f} min — in attesa")
                        if minutes_to_kickoff > 30:
                            print(f"🛑 Troppo presto ({minutes_to_kickoff:.0f} min al via) — bot fermato")
                            sys.exit(0)
                except Exception as e:
                    print(f"⚠️ Impossibile leggere orario partita: {e}")
                time.sleep(10)
                continue

            # Rigori: polling ancora più rapido
            if status == "PEN":
                sleep_time = 6

            # --- Inizio primo tempo ---
            if status == "1H" and "1H" not in state["sent_periods"]:
                send_telegram(f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{home_name} - {away_name}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("1H")
                salva_stato_su_gist(state)
                state_changed = True

            # --- Fine primo tempo ---
            if status == "HT" and "HT" not in state["sent_periods"]:
                send_telegram(f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("HT")
                salva_stato_su_gist(state)
                state_changed = True
                time.sleep(60)
                data_fresh = fetch_evento(event_id, league_slug) or data
                png_path = recupera_e_genera_stats_html(data_fresh, home_id, away_id,
                                                         home_name, away_name, g_home, g_away,
                                                         "HT", league_name)
                send_telegram_stats_photo(png_path, "HT", f"{e_comp} {hashtag}")
                state["sent_stats"].append("HT")
                state_changed = True

            # --- Inizio secondo tempo ---
            if status == "2H" and "2H" not in state["sent_periods"]:
                send_telegram(f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("2H")
                salva_stato_su_gist(state)
                state_changed = True

            # --- Fine regolamentari → supplementari ---
            # Copre sia la transizione live ET che il caso in cui ESPN salti direttamente a PEN/AET
            if status in ("ET", "PEN", "AET") and "2H_END" not in state["sent_periods"] and "FT" not in state["sent_periods"]:
                send_telegram(f"<b>FINE REGOLAMENTARI {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("2H_END")
                salva_stato_su_gist(state)
                state_changed = True
                if status == "ET":
                    # Le stats le mandiamo solo se siamo davvero a fine 2° tempo, non già ai rigori
                    time.sleep(60)
                    data_fresh = fetch_evento(event_id, league_slug) or data
                    png_path = recupera_e_genera_stats_html(data_fresh, home_id, away_id,
                                                             home_name, away_name, g_home, g_away,
                                                             "2H_END", league_name)
                    send_telegram_stats_photo(png_path, "2H_END", f"{e_comp} {hashtag}")
                    state["sent_stats"].append("2H_END")
                    state_changed = True

            # --- Supplementari ---
            if status == "ET":
                # Leggi stato ESPN preciso per determinare intervallo/2°ET
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

                # Inizio 1°ET — solo se non siamo già all'intervallo o al 2°ET
                if "1ET_START" not in state["sent_periods"] and not is_et_halftime and not is_second_et:
                    send_telegram(f"<b>INIZIO 1° TEMPO SUPPLEMENTARE {E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("1ET_START")
                    salva_stato_su_gist(state)
                    state_changed = True

                if (is_et_halftime or is_second_et) and "1ET_END" not in state["sent_periods"]:
                    send_telegram(f"<b>FINE 1° TEMPO SUPPLEMENTARE {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("1ET_END")
                    salva_stato_su_gist(state)
                    state_changed = True

                if is_second_et and "2ET_START" not in state["sent_periods"]:
                    send_telegram(f"<b>INIZIO 2° TEMPO SUPPLEMENTARE {E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("2ET_START")
                    salva_stato_su_gist(state)
                    state_changed = True

            # --- Intervallo supplementari (ESPN manda HT_ET esplicitamente) ---
            if status == "HT_ET":
                if "1ET_START" not in state["sent_periods"]:
                    state["sent_periods"].append("1ET_START")
                    state_changed = True
                if "1ET_END" not in state["sent_periods"]:
                    send_telegram(f"<b>FINE 1° TEMPO SUPPLEMENTARE {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("1ET_END")
                    salva_stato_su_gist(state)
                    state_changed = True

            # --- Rigori ---
            if status == "PEN":
                if "ET_END_PENS" not in state["sent_periods"]:
                    # Manda "FINE SUPPLEMENTARI" solo se non già inviato con altro trigger
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
                        f"<b>RIGORI 🥅</b>\n\n"
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
                        tid   = e["team_id"]
                        if e["type"] == "own goal":
                            tid = away_id if tid == home_id else home_id
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

                # Rigori: conta i gol dal dischetto per costruire il punteggio
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

                time.sleep(60)
                data_fresh = fetch_evento(event_id, league_slug) or data
                ft_pen_home = sum(1 for e in events if e["type"] == "shootout goal" and e["team_id"] == home_id)
                ft_pen_away = sum(1 for e in events if e["type"] == "shootout goal" and e["team_id"] == away_id)
                png_path = recupera_e_genera_stats_html(data_fresh, home_id, away_id,
                                                         home_name, away_name, g_home, g_away,
                                                         "FT", league_name,
                                                         pen_home=ft_pen_home, pen_away=ft_pen_away)
                send_telegram_stats_photo(png_path, "FT", f"{e_comp} {hashtag}")
                state["sent_stats"].append("FT")
                state_changed = True
                state["_reset_done"] = True
                resetta_gist()
                print("🏁 Partita terminata")
                sys.exit(0)

            # --- Rilevamento goal ---
            total_goals_now = g_home + g_away
            prev_home = state.get("prev_home_goals", 0)
            prev_away = state.get("prev_away_goals", 0)

            if total_goals_now > state["goals_detected"]:
                # Conferma il punteggio aspettando 15s e rileggendo
                time.sleep(15)
                data_confirm = fetch_evento(event_id, league_slug) or data
                try:
                    competitors_confirm = data_confirm["header"]["competitions"][0]["competitors"]
                except Exception:
                    competitors_confirm = competitors
                _, _, _, _, g_home_c, g_away_c = parse_score(competitors_confirm)
                if g_home_c + g_away_c != total_goals_now:
                    print(f"⚠️ Punteggio instabile ({g_home}-{g_away} → {g_home_c}-{g_away_c}), attendo")
                    time.sleep(sleep_time)
                    continue
                # Usa i dati confermati
                data   = data_confirm
                g_home = g_home_c
                g_away = g_away_c
                events = parse_events(data, home_name, away_name, home_id, away_id)
                score_str = build_score_str(home_name, away_name, g_home, g_away)
                # La squadra che ha appena segnato è determinata dal punteggio reale ESPN,
                # non dagli eventi (che possono avere team_id mancante/sbagliato)
                if g_home > prev_home:
                    scoring_tid = home_id
                    expected_home_goals = g_home
                    expected_away_goals = prev_away
                elif g_away > prev_away:
                    scoring_tid = away_id
                    expected_home_goals = prev_home
                    expected_away_goals = g_away
                else:
                    # Entrambe hanno segnato nello stesso ciclo (raro): gestisci separatamente
                    scoring_tid = None
                    expected_home_goals = g_home
                    expected_away_goals = g_away

                goal_events = [e for e in events
                               if e["type"] in ("goal", "own goal", "penalty goal")]

                if scoring_tid:
                    # Conta quanti goal ha quella squadra negli eventi
                    # per trovare quello appena segnato (l'ennesimo)
                    team_goals = [e for e in goal_events if e["type"] != "own goal" and e["team_id"] == scoring_tid]
                    own_goals_vs = [e for e in goal_events if e["type"] == "own goal" and e["team_id"] != scoring_tid]
                    candidates = sorted(team_goals + own_goals_vs, key=lambda x: x["minute"])

                    # Numero di goal attesi per questa squadra
                    expected_count = g_home if scoring_tid == home_id else g_away

                    # Prendi il goal corrispondente all'indice atteso (es. 1° goal = index 0)
                    last = candidates[expected_count - 1] if len(candidates) >= expected_count else (candidates[-1] if candidates else None)

                    if not last:
                        time.sleep(sleep_time)
                        continue

                    if not last["player_name"]:
                        time.sleep(sleep_time)
                        continue

                    ps = fmt_player(last["player_name"])
                    actual_scoring_tid = scoring_tid
                    if last["type"] == "own goal":
                        ps += " (Autogol)"
                        actual_scoring_tid = away_id if last["team_id"] == home_id else home_id
                    elif last["type"] == "penalty goal":
                        ps += " (Rig.)"
                    scorer_line = f"{E_BALL} <i>{last['minute']}' {ps}</i>\n"

                    if actual_scoring_tid == home_id:
                        goal_score = f"<b>{home_name} {g_home}</b>-{g_away} {away_name}"
                    else:
                        goal_score = f"{home_name} {g_home}-<b>{g_away} {away_name}</b>"

                    send_telegram(f"<b>GOAL {E_MIC}</b>\n\n{goal_score}\n{scorer_line}\n{e_comp} {hashtag}")

                state["goals_detected"] = total_goals_now
                state_changed = True
                state["prev_home_goals"] = g_home
                state_changed = True
                state["prev_away_goals"] = g_away
                state_changed = True

            elif total_goals_now < state["goals_detected"]:
                send_telegram(f"<b>GOAL ANNULLATO 📺</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                state["goals_detected"] = total_goals_now
                state_changed = True
                state["prev_home_goals"] = g_home
                state_changed = True
                state["prev_away_goals"] = g_away
                state_changed = True

            # --- Cambi ---
            # ✅ FIX: se ci sono cambi nuovi, attende 30s e rilegge per raggruppare
            new_subs_check = []
            for e in events:
                if e["type"] == "substitution":
                    sub_id = e["uid"]
                    if sub_id not in state["sent_subs"]:
                        new_subs_check.append({**e, "sub_id": sub_id})

            if new_subs_check:
                print(f"🔄 Cambio rilevato, raggruppo...")
                time.sleep(30)
                # Rileggi i dati aggiornati
                data_subs = fetch_evento(event_id, league_slug) or data
                events_subs = parse_events(data_subs, home_name, away_name, home_id, away_id)

                new_subs = []
                for e in events_subs:
                    if e["type"] == "substitution":
                        sub_id = e["uid"]
                        if sub_id not in state["sent_subs"]:
                            new_subs.append({**e, "sub_id": sub_id})

                # Raggruppa: stessa squadra, minuto entro ±2
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
                    ins  = ", ".join(fmt_player(s["assist_name"]) for s in g["subs"])
                    outs = ", ".join(fmt_player(s["player_name"]) for s in g["subs"])
                    send_telegram(
                        f"<b>CAMBIO {team_title} {E_SUB}</b>\n\n"
                        f"{E_UP} {ins}\n"
                        f"{E_DOWN} {outs}\n\n"
                        f"{e_comp} {hashtag}"
                    )
                    state["sent_subs"].extend(s["sub_id"] for s in g["subs"])
                    state_changed = True

            # --- Cartellini rossi / doppio giallo ---
            for e in events:
                if e["type"] in ("red card", "second yellow card"):
                    p_name  = fmt_player(e["player_name"])
                    card_id = f"card_{e['minute']}_{e['player_name']}".replace(" ", "_")
                    if card_id not in state["sent_cards"]:
                        send_telegram(
                            f"<b>CARTELLINO ROSSO {E_RED}</b>\n\n"
                            f"🔚 <i>{e['minute']}' {p_name}</i>\n\n{e_comp} {hashtag}"
                        )
                        state["sent_cards"].append(card_id)
                        state_changed = True

            # --- Rigori sbagliati (tempo regolamentare / supplementari): esclusa lotteria ---
            for e in events:
                if e["type"] in ("penalty missed", "penalty saved"):
                    pen_id = f"failpen_{e['minute']}_{e['player_name']}".replace(" ", "_")
                    if pen_id not in state["sent_failed_penalties"]:
                        state["sent_failed_penalties"].append(pen_id)
                        state_changed = True
                        print(f"🥅 Rigore fallito: {e['player_name']} {e['minute']}'")
                        team_name = home_name if e["team_id"] == home_id else away_name
                        send_telegram(
                            f"<b>RIGORE SBAGLIATO {team_name.upper()} 🥅</b>\n\n"
                            f"{E_PEN_KO} <i>{e['minute']}' {fmt_player(e['player_name'])}</i>\n\n"
                            f"{e_comp} {hashtag}"
                        )

        except Exception as e:
            print(f"❌ Errore ciclo live: {e}")
            sleep_time = 6

        finally:
            if isinstance(state, dict) and not state.get("_reset_done") and state_changed:
                salva_stato_su_gist(state)

        time.sleep(sleep_time)

# ==============================================================================
# MAIN
# ==============================================================================
def main():
    print("🚀 Bot avviato")

    if str(os.getenv('ONLY_REFRESH_TOKEN', '')).strip().lower() == "true":
        get_valid_token()
        return

    avvia_ciclo_partita()

if __name__ == "__main__":
    main()
