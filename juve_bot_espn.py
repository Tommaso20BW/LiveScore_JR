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
    "uefa.w.champions": "🇪🇺", "fifa.w.world": "🌍", "fifa.w.world.q": "🌍",
    "uefa.w.euro": "🇪🇺", "uefa.w.nations": "🇪🇺", "olympics.w.soccer": "🏅",
    "fifa.world": "🌍", "fifa.world.q": "🌍", "fifa.confed": "🌍", "fifa.friendly": "🤝", "olympics.m.soccer": "🏅",
    "uefa.euro": "🇪🇺", "uefa.euro.q": "🇪🇺", "uefa.nations": "🇪🇺",
    "conmebol.america": "🌎", "conmebol.america.q": "🌎",
    "concacaf.gold": "🌎", "concacaf.nations": "🌎",
    "caf.nations": "🌍", "caf.nations.q": "🌍",
    "afc.asian_cup": "🌏", "afc.asian_cup.q": "🌏"
}

def get_league_emoji(slug): return LEAGUE_EMOJIS.get(slug, "⚽️")

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
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  BOT_TOKEN o CHAT_ID mancanti")
        return None
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
        r.raise_for_status()
        msg_id = r.json().get("result", {}).get("message_id")
        return msg_id
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
        if r.status_code in [201, 204]:
            return True
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
        payload = {"files": {"match_state.json": {"content": json.dumps(state, ensure_ascii=False)}}}
        r = requests.patch(f"https://api.github.com/gists/{GIST_ID}", headers=_gist_headers(),
                           json=payload, timeout=10)
        if r.status_code == 200:
            pass
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
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Errore export Canva: {e}")
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
        events.append({
            "type":        norm,
            "minute":      minute,
            "team_id":     str(team_id),
            "player_name": player_name,
            "assist_name": assist_name,
            "uid":         uid,
        })

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
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Errore parsing commentary: {e}")

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
                t_id = home_id if t_name.lower() == home_name.lower() else away_id
            add_event(ev_type, minute, t_id, player, assist, uid)
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Errore parsing keyEvent: {e}")

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
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Errore parsing scoringPlay: {e}")

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
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Errore parsing shootout: {e}")

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
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Errore parsing boxscore.teams: {e}")

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
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Errore parsing header competitors: {e}")
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
    corner_h = g("home", "wonCorners",      "woncorners", "cornerKicks", "cornerkicks", "corners", "corner", fallback="0")
    corner_a = g("away", "wonCorners",      "woncorners", "cornerKicks", "cornerkicks", "corners", "corner", fallback="0")
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
        ("Precisione passaggi", passpct_h, passpct_a, perc(str(passpct_h).replace("%",""), str(passpct_a).replace("%",""))),
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
body {{ width: 1620px; height: 1980px; background: radial-gradient(circle at top left, #1e3a8a 0%, transparent 40%), radial-gradient(circle at bottom right, #7c3aed 0%, transparent 40%), #060816; font-family: 'Inter', sans-serif; display: flex; align-items: center; justify-content: center; }}
.card {{ width: 1500px; height: 1900px; background: linear-gradient(180deg, rgba(17,24,39,0.96), rgba(10,14,28,0.96)); border-radius: 50px; overflow: hidden; border: 3px solid rgba(255,255,255,0.08); box-shadow: 0 50px 100px rgba(0,0,0,0.6), inset 0 2px 0 rgba(255,255,255,0.04); display: flex; flex-direction: column; }}
.header {{ padding: 55px 80px 40px; border-bottom: 2px solid rgba(255,255,255,0.06); background: rgba(255,255,255,0.01); position: relative; }}
.league-row {{ font-family: 'Barlow Condensed', sans-serif; font-weight: 900; font-size: 38px; color: #60a5fa; letter-spacing: 4px; text-transform: uppercase; margin-bottom: 15px; }}
.badge {{ position: absolute; top: 55px; right: 80px; background: rgba(96,165,250,0.15); border: 1.5px solid rgba(96,165,250,0.3); color: #93c5fd; padding: 10px 24px; border-radius: 999px; font-weight: 700; font-size: 24px; letter-spacing: 1px; }}
.teams-row {{ display: flex; align-items: center; justify-content: space-between; margin-top: 25px; }}
.team {{ display: flex; align-items: center; gap: 35px; width: 42%; }}
.team:last-child {{ justify-content: flex-end; text-align: right; flex-direction: row-reverse; }}
.logo {{ width: 140px; height: 140px; object-fit: contain; filter: drop-shadow(0 15px 25px rgba(0,0,0,0.4)); }}
.team-name {{ font-size: 48px; font-weight: 800; color: #ffffff; letter-spacing: -1px; line-height: 1.1; }}
.score-wrap {{ display: flex; flex-direction: column; align-items: center; justify-content: center; width: 16%; }}
.score {{ font-family: 'Barlow Condensed', sans-serif; font-weight: 900; font-size: 90px; color: #ffffff; line-height: 1; letter-spacing: -2px; }}
.pen-score {{ font-size: 28px; font-weight: 700; color: #9ca3af; margin-top: 4px; }}
.match-status {{ font-size: 20px; font-weight: 800; color: #ef4444; letter-spacing: 3px; margin-top: 15px; background: rgba(239,68,68,0.1); padding: 6px 16px; border-radius: 6px; border: 1px solid rgba(239,68,68,0.2); }}
.stats-body {{ flex: 1; padding: 50px 80px; display: flex; flex-direction: column; gap: 32px; justify-content: center; }}
.stats-title {{ font-size: 26px; font-weight: 800; color: #9ca3af; letter-spacing: 2px; margin-bottom: 5px; text-transform: uppercase; }}
.stat-row {{ display: flex; flex-direction: column; gap: 14px; }}
.stat-top {{ display: flex; justify-content: space-between; align-items: center; }}
.val {{ font-size: 34px; font-weight: 700; color: #ffffff; width: 80px; }}
.home-val {{ text-align: left; }}
.away-val {{ text-align: right; }}
.stat-label {{ font-size: 28px; font-weight: 600; color: #9ca3af; text-align: center; flex: 1; }}
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
    path_html = "/tmp/stats.html"
    path_raw_png = "/tmp/stats_raw.png"
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
    if os.path.exists(path_raw_png):
        img = Image.open(path_raw_png)
        img.save(path_final_png, "PNG", quality=95)
        return path_final_png
    return None

# ==============================================================================
# HELPERS PARTITA
# ==============================================================================
def fetch_evento(event_id, league_slug):
    url = f"{ESPN_BASE}/{league_slug}/summary?event={event_id}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ Errore API ESPN ({league_slug}/{event_id}): {e}")
    return None

def parse_score(competitors):
    home_id, away_id, home_name, away_name = "", "", "", ""
    g_home, g_away = 0, 0
    for c in competitors:
        side = c.get("homeAway", "home")
        if side == "home":
            home_id   = str(c["id"])
            home_name = c["team"]["displayName"]
            g_home    = int(c.get("score", 0))
        else:
            away_id   = str(c["id"])
            away_name = c["team"]["displayName"]
            g_away    = int(c.get("score", 0))
    return home_id, away_id, home_name, away_name, g_home, g_away

def build_hashtag(home_name, away_name):
    h = "".join(x for x in home_name.title() if x.isalnum())
    a = "".join(x for x in away_name.title() if x.isalnum())
    return f"#{h}{a}"

def parse_status(data):
    try:
        status = data["header"]["competitions"][0]["status"]
        stype  = status["type"]
        state  = stype.get("state", "pre")
        name   = stype.get("name", "").upper()
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
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ Errore parse_status: {e}")
        return "NS", 0

def build_score_str(home_name, away_name, g_home, g_away):
    if g_home > g_away:
        return f"<b>{home_name} {g_home}</b>-{g_away} {away_name}"
    elif g_away > g_home:
        return f"{home_name} {g_home}-<b>{g_away} {away_name}</b>"
    return f"{home_name} {g_home}-{g_away} {away_name}"

# ==============================================================================
# PROCESSO EVENTO INDIVIDUALE
# ==============================================================================
def processa_partita_singola(event_id, league_slug, league_name, partita):
    state = leggi_stato_da_gist()
    if not state:
        state = {
            "goals_detected": 0, "prev_home_goals": 0, "prev_away_goals": 0,
            "sent_periods": [], "sent_stats": [], "sent_failed_penalties": [],
            "shootout_message_id": None, "goal_messages": {},
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
            hashtag = build_hashtag(home_name, away_name)
            e_comp = get_league_emoji(league_slug)
            events = parse_events(data, home_name, away_name, home_id, away_id)
            if "_intro_logged" not in state:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 PARTITA TROVATA: {league_name} | {home_name} vs {away_name} | event_id={event_id}")
                state["_intro_logged"] = True
            _now_ts = int(time.time())
            _log_key = f"{status}_{elapsed}_{g_home}_{g_away}"
            if status != "NS" and (state.get("_last_log_key") != _log_key or (_now_ts - state.get("_last_log_ts", 0)) >= 60):
                _ts = datetime.now().strftime("%H:%M:%S")
                print(f"[{_ts}] 📡 {status} {elapsed}' | {home_name} {g_home}-{g_away} {away_name}")
                state["_last_log_key"] = _log_key
                state["_last_log_ts"] = _now_ts

            # ==================================================================
            # CORREZIONE COMPLETA CATCHUP SUL PUNTEGGIO PROGRESSIVO
            # ==================================================================
            if state["goals_detected"] == 0 and (g_home + g_away) > 0 and not state.get("goal_messages"):
                _seen_uids = set()
                _deduped = []
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
                        actual_tid = away_id if ge["team_id"] == home_id else home_id
                    else:
                        actual_tid = ge["team_id"]

                    if actual_tid == home_id:
                        if ch < g_home:
                            ch += 1
                        else:
                            continue
                    else:
                        if ca < g_away:
                            ca += 1
                        else:
                            continue

                    p_name = ge.get("player_name", "")
                    a_name = ge.get("assist_name", "")
                    ps = fmt_player(p_name) if p_name else ""
                    if ge["type"] == "own goal" and ps:
                        ps += " (Autogol)"
                    elif ge["type"] == "penalty goal" and ps:
                        ps += " (Rig.)"

                    scorer_line = f"{E_BALL} <i>{ps}</i>\n" if ps else ""
                    assist_line = f"{E_ASSIST} <i>{fmt_player(a_name)}</i>\n" if a_name and a_name != p_name else ""

                    if actual_tid == home_id:
                        goal_score = f"<b>{home_name} {ch}</b>-{ca} {away_name}"
                    else:
                        goal_score = f"{home_name} {ch}-<b>{ca} {away_name}"

                    goal_text = f"<b>GOAL · {ge['minute']}\' {E_MIC}</b>\n\n{goal_score}\n{scorer_line}{assist_line}\n{e_comp} {hashtag}"
                    goal_key  = f"{ch}_{ca}"

                    _tipo_log = " (Autogol)" if ge["type"] == "own goal" else (" (Rig.)" if ge["type"] == "penalty goal" else "")
                    _scorer_log = f" {fmt_player(p_name)}{_tipo_log}" if p_name else " (marcatore in attesa)"
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚽️ CATCHUP GOAL {ge['minute']}\'{_scorer_log} {home_name} {ch}-{ca} {away_name} → Telegram inviato")
                    
                    msg_id = send_telegram_get_id(goal_text)
                    state.setdefault("goal_messages", {})[goal_key] = {
                        "msg_id": msg_id, "scorer": p_name, "assist": a_name, "minute": ge["minute"], "type": ge["type"],
                        "home_n": home_name, "away_n": away_name, "g_home": ch, "g_away": ca, "home_id": home_id, "away_id": away_id, "score_tid": actual_tid,
                    }
                    time.sleep(2)

                state["goals_detected"]  = g_home + g_away
                state["prev_home_goals"] = g_home
                state["prev_away_goals"] = g_away
                state_changed = True

            # ==================================================================
            # CICLO LIVE STANDARD
            # ==================================================================
            elif (g_home + g_away) > (state["prev_home_goals"] + state["prev_away_goals"]):
                prev_home, prev_away = state["prev_home_goals"], state["prev_away_goals"]
                total_goals_now = g_home + g_away
                time.sleep(15)
                data_confirm = fetch_evento(event_id, league_slug) or data
                try:
                    competitors_confirm = data_confirm["header"]["competitions"][0]["competitors"]
                except Exception:
                    competitors_confirm = competitors
                _, _, _, _, g_home_c, g_away_c = parse_score(competitors_confirm)
                if g_home_c + g_away_c != total_goals_now:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ Punteggio instabile ({g_home}-{g_away} → {g_home_c}-{g_away_c}), attendo conferma...")
                    time.sleep(sleep_time)
                    continue
                data = data_confirm
                g_home, g_away = g_home_c, g_away_c
                events = parse_events(data, home_name, away_name, home_id, away_id)
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
                goal_events = [e for e in events if e["type"] in ("goal", "own goal", "penalty goal")]
                if scoring_tid:
                    team_goals = [e for e in goal_events if e["team_id"] == scoring_tid or (e["type"] == "own goal" and e["team_id"] != scoring_tid)]
                    idx = (expected_home_goals - 1) if scoring_tid == home_id else (expected_away_goals - 1)
                    if 0 <= idx < len(team_goals):
                        last = team_goals[idx]
                    else:
                        last = {"minute": f"{elapsed}", "player_name": "", "assist_name": "", "type": "goal"}
                else:
                    last = goal_events[-1] if goal_events else {"minute": f"{elapsed}", "player_name": "", "assist_name": "", "type": "goal"}
                player_name = last.get("player_name", "")
                assist_name = last.get("assist_name", "")
                ps = fmt_player(player_name) if player_name else ""
                if last["type"] == "own goal" and ps:
                    ps += " (Autogol)"
                elif last["type"] == "penalty goal" and ps:
                    ps += " (Rig.)"
                actual_scoring_tid = scoring_tid or (away_id if last.get("team_id") == home_id and last["type"] == "own goal" else home_id)
                scorer_line = f"{E_BALL} <i>{ps}</i>\n" if ps else ""
                assist_line = f"{E_ASSIST} <i>{fmt_player(assist_name)}</i>\n" if assist_name and assist_name != player_name else ""
                if actual_scoring_tid == home_id:
                    goal_score = f"<b>{home_name} {g_home}</b>-{g_away} {away_name}"
                else:
                    goal_score = f"{home_name} {g_home}-<b>{g_away} {away_name}</b>"
                goal_text = f"<b>GOAL · {last['minute']}' {E_MIC}</b>\n\n{goal_score}\n{scorer_line}{assist_line}\n{e_comp} {hashtag}"
                goal_key = f"{g_home}_{g_away}"
                if not state.get("goal_messages", {}).get(goal_key, {}).get("msg_id"):
                    _scorer_log = f" {fmt_player(player_name)}" if player_name else " (marcatore in attesa)"
                    _assist_log = f" | assist: {fmt_player(assist_name)}" if assist_name and assist_name != player_name else ""
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚽️ GOAL{_scorer_log}{_assist_log} ({home_name} {g_home}-{g_away} {away_name}) → Telegram inviato")
                    msg_id = send_telegram_get_id(goal_text)
                    state.setdefault("goal_messages", {})[goal_key] = {
                        "msg_id": msg_id, "scorer": player_name, "assist": assist_name, "minute": last["minute"], "type": last["type"],
                        "home_n": home_name, "away_n": away_name, "g_home": g_home, "g_away": g_away, "home_id": home_id, "away_id": away_id, "score_tid": actual_scoring_tid
                    }
                state["prev_home_goals"] = g_home
                state["prev_away_goals"] = g_away
                state["goals_detected"] = g_home + g_away
                state_changed = True

            for goal_key, saved in list(state.get("goal_messages", {}).items()):
                msg_id = saved.get("msg_id")
                if not msg_id:
                    continue
                try:
                    gh, ga = map(int, goal_key.split("_"))
                except ValueError:
                    continue
                s_home_id, s_away_id, s_home_n, s_away_n, s_tid = saved.get("home_id", home_id), saved.get("away_id", away_id), saved.get("home_n", home_name), saved.get("away_n", away_name), saved.get("score_tid")
                goal_events_all = [e for e in events if e["type"] in ("goal", "own goal", "penalty goal")]
                if s_tid == s_home_id:
                    team_goals = [e for e in goal_events_all if e["team_id"] == s_home_id or (e["type"] == "own goal" and e["team_id"] != s_home_id)]
                    idx = gh - 1
                else:
                    team_goals = [e for e in goal_events_all if e["team_id"] == s_away_id or (e["type"] == "own goal" and e["team_id"] != s_away_id)]
                    idx = ga - 1
                if 0 <= idx < len(team_goals):
                    current = team_goals[idx]
                    current_scorer = current.get("player_name", "")
                    current_assist = current.get("assist_name", "")
                    current_type   = current.get("type", "goal")
                    if current_scorer != saved.get("scorer") or current_assist != saved.get("assist") or current_type != saved.get("type"):
                        saved["scorer"], saved["assist"], saved["type"] = current_scorer, current_assist, current_type
                        state_changed = True
                        if current_scorer:
                            ps_new = fmt_player(current_scorer)
                            if current_type == "own goal":
                                ps_new += " (Autogol)"
                            elif current_type == "penalty goal":
                                ps_new += " (Rig.)"
                            scorer_line_new = f"{E_BALL} <i>{ps_new}</i>\n"
                        else:
                            scorer_line_new = ""
                        assist_line_new = f"{E_ASSIST} <i>{fmt_player(current_assist)}</i>\n" if current_assist and current_assist != current_scorer else ""
                        if current_type == "own goal":
                            actual_tid = s_away_id if current.get("team_id") == s_home_id else s_home_id
                        else:
                            actual_tid = current.get("team_id") or s_tid
                        if actual_tid == s_home_id:
                            goal_score_new = f"<b>{s_home_n} {gh}</b>-{ga} {s_away_n}"
                        else:
                            goal_score_new = f"{s_home_n} {gh}-<b>{ga} {s_away_n}</b>"
                        e_comp_saved = get_league_emoji(league_slug)
                        hashtag_saved = build_hashtag(s_home_n, s_away_n)
                        goal_text_new = f"<b>GOAL · {current['minute']}' {E_MIC}</b>\n\n{goal_score_new}\n{scorer_line_new}{assist_line_new}\n{e_comp_saved} {hashtag_saved}"
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 📝 CORREZIONE GOAL {goal_key} → {current_scorer or 'In attesa'} | assist: {current_assist or 'Nessuno'}")
                        send_telegram_edit(msg_id, goal_text_new)

            if status == "1H" and elapsed >= 45 and "1H_END" not in state["sent_periods"]:
                send_telegram(f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("1H_END")
                salva_stato_su_gist(state)
                state_changed = True

            if status == "HT" and "HT" not in state["sent_stats"]:
                time.sleep(45)
                data_fresh = fetch_evento(event_id, league_slug) or data
                png_path = recupera_e_genera_stats_html(data_fresh, home_id, away_id, home_name, away_name, g_home, g_away, "HT", league_name)
                send_telegram_stats_photo(png_path, "HT", f"{e_comp} {hashtag}")
                state["sent_stats"].append("HT")
                state_changed = True

            if status == "2H" and "2H_START" not in state["sent_periods"]:
                send_telegram(f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("2H_START")
                salva_stato_su_gist(state)
                state_changed = True

            if status in ("FT", "AET", "PEN") and "2H_END" not in state["sent_periods"]:
                send_telegram(f"<b>FINE SECONDO TEMPO {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("2H_END")
                salva_stato_su_gist(state)
                state_changed = True
                if status == "ET":
                    time.sleep(120)
                    data_fresh = fetch_evento(event_id, league_slug) or data
                    png_path = recupera_e_genera_stats_html(data_fresh, home_id, away_id, home_name, away_name, g_home, g_away, "2H_END", league_name)
                    send_telegram_stats_photo(png_path, "2H_END", f"{e_comp} {hashtag}")
                    state["sent_stats"].append("2H_END")
                    state_changed = True

            if status == "ET":
                try:
                    comp_status = data["header"]["competitions"][0].get("status", {})
                    stype_name = comp_status.get("type", {}).get("name", "").upper()
                    et_period = comp_status.get("period", 1)
                except Exception:
                    stype_name = ""
                    et_period = 1
                is_et_halftime = any(kw in stype_name for kw in ("HALFTIME", "HALF_TIME", "HT_ET", "EXTRA_TIME_HALF"))
                is_second_et = (et_period >= 4 or (elapsed >= 106 and et_period >= 3))
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
                if is_second_et and "2ET_START" not in state["sent_periods"] and not is_et_halftime:
                    send_telegram(f"<b>INIZIO 2° TEMPO SUPPLEMENTARE {E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("2ET_START")
                    salva_stato_su_gist(state)
                    state_changed = True

            if status == "PEN" and "ET_END_PENS" not in state["sent_periods"]:
                send_telegram(f"<b>FINE SUPPLEMENTARI — SI VA AI RIGORI! {E_KICK}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("ET_END_PENS")
                salva_stato_su_gist(state)
                state_changed = True

            if status == "PEN":
                shootout_events = [e for e in events if "shootout" in e["type"]]
                if shootout_events:
                    lines = []
                    h_ok, a_ok = 0, 0
                    for se in shootout_events:
                        ico = E_PEN_OK if se["type"] == "shootout goal" else E_PEN_KO
                        p_fmt = fmt_player(se["player_name"])
                        t_name = home_name if se["team_id"] == home_id else away_name
                        lines.append(f"{ico} {t_name.upper()} - {p_fmt}")
                        if se["type"] == "shootout goal":
                            if se["team_id"] == home_id:
                                h_ok += 1
                            else:
                                a_ok += 1
                    shootout_text = (
                        f"<b>SEQUENZA RIGORI {E_KICK}</b>\n\n"
                        f"<b>{home_name} ({h_ok}) — ({a_ok}) {away_name}</b>\n\n"
                        f"{chr(10).join(lines)}\n\n"
                        f"{e_comp} {hashtag}"
                    )
                    old_msg_id = state.get("shootout_message_id")
                    if not old_msg_id:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🥅 Inizio sequenza rigori → Telegram inviato")
                        msg_id = send_telegram_get_id(shootout_text)
                        state["shootout_message_id"] = msg_id
                        state_changed = True
                    else:
                        state_changed = True
                        send_telegram_edit(old_msg_id, shootout_text)

            try:
                comp_state_espn = data["header"]["competitions"][0]["status"]["type"].get("state", "").lower()
            except Exception:
                comp_state_espn = ""
            is_finished = (status in ("FT", "AET") or (status == "PEN" and comp_state_espn == "post"))
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
                has_shootout = ("ET_END_PENS" in state["sent_periods"] or status == "PEN" or len(data.get("shootout", [])) > 0)
                if has_shootout:
                    home_pen_goals = sum(1 for e in events if e["type"] == "shootout goal" and e["team_id"] == home_id)
                    away_pen_goals = sum(1 for e in events if e["type"] == "shootout goal" and e["team_id"] == away_id)
                    if home_pen_goals > 0 or away_pen_goals > 0:
                        if home_pen_goals > away_pen_goals:
                            pen_score_str = f" ({home_pen_goals}-{away_pen_goals} d.c.r.)"
                        else:
                            pen_score_str = f" ({home_pen_goals}-{away_pen_goals} d.c.r.)"
                        score_str = f"{home_name} {g_home}-{g_away} {away_name}{pen_score_str}"
                final_text = f"<b>FISCHIO FINALE {E_EXIT}</b>\n\n{score_str}\n{scorers_line}\n{e_comp} {hashtag}"
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🏁 PARTITA TERMINATA: {home_name} {g_home}-{g_away} {away_name} → Telegram inviato")
                send_telegram(final_text)
                state["sent_periods"].append("FT")
                salva_stato_su_gist(state)
                state_changed = True
                time.sleep(120)
                data_fresh = fetch_evento(event_id, league_slug) or data
                if has_shootout:
                    home_pen_goals = sum(1 for e in events if e["type"] == "shootout goal" and e["team_id"] == home_id)
                    away_pen_goals = sum(1 for e in events if e["type"] == "shootout goal" and e["team_id"] == away_id)
                else:
                    home_pen_goals, away_pen_goals = 0, 0
                png_path = recupera_e_genera_stats_html(data_fresh, home_id, away_id, home_name, away_name, g_home, g_away, "FT", league_name, home_pen_goals, away_pen_goals)
                send_telegram_stats_photo(png_path, "FT", f"{e_comp} {hashtag}")
                state["sent_stats"].append("FT")
                state["_reset_done"] = False
                salva_stato_su_gist(state)
                break

            for sub in events:
                if sub["type"] == "substitution":
                    sub_id = sub["uid"]
                    if "sent_subs" not in state:
                        state["sent_subs"] = []
                    if sub_id not in state["sent_subs"]:
                        state["sent_subs"].append(sub_id)
                        state_changed = True
                        groups = []
                        for s in groups:
                            if s["minute"] == sub["minute"] and s["team_id"] == sub["team_id"]:
                                s["subs"].append(sub)
                                break
                        else:
                            groups.append({"team_id": sub["team_id"], "minute": sub["minute"], "subs": [sub]})
                        for g in groups:
                            team_title = home_name.upper() if g["team_id"] == home_id else away_name.upper()
                            ins = ", ".join(fmt_player(s["assist_name"]) for s in g["subs"])
                            outs = ", ".join(fmt_player(s["player_name"]) for s in g["subs"])
                            _min_cambio = g["subs"][0]["minute"]
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 CAMBIO {team_title} {_min_cambio}' | ↑ {ins} / ↓ {outs} → Telegram inviato")
                            send_telegram(
                                f"<b>CAMBIO {team_title} {E_SUB}</b>\n\n"
                                f"{E_UP} Entra: <i>{ins}</i>\n"
                                f"{E_DOWN} Esce: <i>{outs}</i>\n"
                                f"Al minuto {_min_cambio}'\n\n"
                                f"{e_comp} {hashtag}"
                            )

            for card in events:
                if card["type"] in ("yellow card", "red card", "second yellow card"):
                    card_id = card["uid"]
                    if "sent_cards" not in state:
                        state["sent_cards"] = []
                    if card_id not in state["sent_cards"]:
                        state["sent_cards"].append(card_id)
                        state_changed = True
                        p_fmt = fmt_player(card["player_name"])
                        t_name = home_name if card["team_id"] == home_id else away_name
                        if card["type"] == "yellow card":
                            title = "AMMONIZIONE"
                            emoji = "🟨"
                        elif card["type"] == "second yellow card":
                            title = "ESPULSIONE (DOPPIA AMMONIZIONE)"
                            emoji = "🟨 ESPULSO 🟥"
                        else:
                            title = "ESPULSIONE DIRETTA"
                            emoji = "🟥"
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] {emoji} CARTELLINO {t_name.upper()} {card['minute']}' {p_fmt} → Telegram inviato")
                        send_telegram(
                            f"<b>{title} {emoji}</b>\n\n"
                            f"👤 <i>{card['minute']}' {p_fmt} ({t_name})</i>\n\n"
                            f"{e_comp} {hashtag}"
                        )

            for e in events:
                if e["type"] in ("penalty missed", "penalty saved"):
                    pen_id = e["uid"]
                    if "sent_failed_penalties" not in state:
                        state["sent_failed_penalties"] = []
                    if pen_id not in state["sent_failed_penalties"]:
                        state["sent_failed_penalties"].append(pen_id)
                        state_changed = True
                        team_name = home_name if e["team_id"] == home_id else away_name
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🥅 RIGORE SBAGLIATO {team_name.upper()} {e['minute']}' {fmt_player(e['player_name'])} → Telegram inviato")
                        send_telegram(
                            f"<b>RIGORE SBAGLIATO {team_name.upper()} {E_KICK}</b>\n\n"
                            f"{E_PEN_KO} <i>{e['minute']}' {fmt_player(e['player_name'])}</i>\n\n"
                            f"{e_comp} {hashtag}"
                        )

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Errore ciclo live: {e}")
            sleep_time = 6
        finally:
            if isinstance(state, dict) and not state.get("_reset_done") and state_changed:
                salva_stato_su_gist(state)
        time.sleep(sleep_time)

# ==============================================================================
# MAIN
# ==============================================================================
def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Bot avviato")
    if str(os.getenv('ONLY_REFRESH_TOKEN', '')).strip().lower() == "true":
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 Modalità ONLY_REFRESH_TOKEN rilevata.")
        token = get_valid_token()
        if token:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Token Canva aggiornato nei Secrets!")
        sys.exit(0)

    url_scoreboard = f"{ESPN_BASE}/all/scoreboard"
    match_trovato = None
    league_slug_trovato = ""
    league_name_trovato = ""
    try:
        r = requests.get(url_scoreboard, timeout=12)
        if r.status_code == 200:
            sb_data = r.json()
            for ev in sb_data.get("events", []):
                for comp in ev.get("competitions", []):
                    for competitor in comp.get("competitors", []):
                        if str(competitor.get("team", {}).get("id")) == str(TEAM_ID):
                            match_trovato = ev
                            break
                if match_trovato:
                    break
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ Errore controllo iniziale scoreboard generico: {e}")

    if not match_trovato:
        for slug in LEAGUE_SLUGS:
            url_league = f"{ESPN_BASE}/{slug}/scoreboard"
            try:
                r = requests.get(url_league, timeout=10)
                if r.status_code != 200:
                    continue
                sb_data = r.json()
                league_name = sb_data.get("leagues", [{}])[0].get("name", "COMPETIZIONE")
                for ev in sb_data.get("events", []):
                    for comp in ev.get("competitions", []):
                        for competitor in comp.get("competitors", []):
                            if str(competitor.get("team", {}).get("id")) == str(TEAM_ID):
                                match_trovato = ev
                                league_slug_trovato = slug
                                league_name_trovato = league_name
                                break
                    if match_trovato:
                        break
                if match_trovato:
                    break
            except Exception:
                continue

    if match_trovato:
        event_id = match_trovato["id"]
        slug = league_slug_trovato or "all"
        name = league_name_trovato or "PARTITA"
        try:
            comp_data = match_trovato["competitions"][0]
        except Exception:
            comp_data = match_trovato
        processa_partita_singola(event_id, slug, name, comp_data)
    else:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚫 Nessun match in corso o programmato trovato per TEAM_ID={TEAM_ID}")
        state = leggi_stato_da_gist()
        if state and "sent_periods" in state and "FT" in state["sent_periods"] and not state.get("_reset_done", False):
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🧹 Partita precedente conclusa rilevata nello stato. Eseguo il reset automatico del Gist...")
            resetta_gist()
            state = {"_reset_done": True}
            salva_stato_su_gist(state)

if __name__ == "__main__":
    main()
