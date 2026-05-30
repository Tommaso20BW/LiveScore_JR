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
TEAM_ID             = '160'
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
    "penalty shootout - miss":  "shootout miss",
    "penalty shootout - saved": "shootout saved",
}

def normalize_event_type(raw: str) -> str:
    if not raw:
        return ""
    low = raw.strip().lower()
    for k, v in EVENT_TYPE_MAP.items():
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
        print(f"📨 Telegram inviato: {text[:80]}...")
    except Exception as e:
        print(f"❌ Errore Telegram: {e}")

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
        print(f"✅ Statistiche ({momento}) inviate su Telegram!")
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
            print(f"✅ Secret '{secret_name}' aggiornato.")
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
        print("🔄 Gist resettato.")
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
                print(f"   [Controllo {i+1}/60] Canva: {stato}")
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
            s = str(clock_val).replace("'", "").strip()
            return int(float(s.split(":")[0]))
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
            if not t_id:
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

    if not events:
        print("⚠️ Nessun evento trovato.")

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
                                  momento: str, league_name: str = "SERIE A"):
    print(f"📊 Generazione stats HTML per momento {momento}...")

    JUVE_ID     = '111'
    JUVE_LOGO   = "https://upload.wikimedia.org/wikipedia/commons/9/99/Juventus_FC_2017_squared_icon_%28white%29.png"
    h_logo      = JUVE_LOGO if str(home_id) == JUVE_ID else f"https://a.espncdn.com/i/teamlogos/soccer/500/{home_id}.png"
    a_logo      = JUVE_LOGO if str(away_id) == JUVE_ID else f"https://a.espncdn.com/i/teamlogos/soccer/500/{away_id}.png"
    badge_label = MOMENTI_CONFIG[momento]["badge"]
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
      <div class="score-wrap"><div class="score">{home_goals}–{away_goals}</div><div class="match-status">LIVE STATS</div></div>
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

    print("📸 Rendering con Playwright...")
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
    print(f"🔍 Ricerca partita per team_id={team_id} nelle date: {dates_to_try}")

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
                        print(f"✅ Trovata: slug={slug} data={date_str} event_id={event['id']}")
                        return {
                            "event_id":    event["id"],
                            "league_slug": slug,
                            "league_name": league_name,
                            "competitors": competitors,
                        }
            except Exception as e:
                print(f"⚠️ Errore fetch slug={slug} data={date_str}: {e}")

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
        state  = status.get("type", {}).get("state", "pre")
        desc   = status.get("type", {}).get("description", "").lower()
        clock  = status.get("displayClock", "0:00")
        period = status.get("period", 1)
        try:
            elapsed = int(clock.split(":")[0])
        except Exception:
            elapsed = 0

        if state == "pre":
            return "NS", 0
        if state == "post":
            if "pen" in desc:
                return "PEN", 120
            if "extra" in desc or "aet" in desc:
                return "AET", 120
            return "FT", 90
        if "halftime" in desc or desc == "half time":
            return "HT", 45
        if "first" in desc and "half" in desc:
            return "1H", elapsed
        if "second" in desc and "half" in desc:
            return "2H", elapsed
        if "extra" in desc:
            return "ET", elapsed
        if "penalty" in desc or "penalties" in desc:
            return "PEN", elapsed
        return ("1H" if period == 1 else "2H"), elapsed
    except Exception:
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
    print(f"🚀 Avvio bot ESPN per team_id={team_id}")

    # Test connettività API
    try:
        test_r = requests.get(f"{ESPN_BASE}/ita.1/scoreboard",
                               params={"dates": datetime.now(timezone.utc).strftime("%Y%m%d")}, timeout=10)
        print(f"🔍 Test API ita.1: status={test_r.status_code}, eventi={len(test_r.json().get('events', []))}")
    except Exception as e:
        print(f"⚠️ Test API fallito: {e}")

    partita = trova_partita_oggi(team_id)
    if not partita:
        print(f"📭 Nessun evento trovato per team_id={team_id}.")
        return

    event_id    = partita["event_id"]
    league_slug = partita["league_slug"]
    league_name = partita["league_name"]
    print(f"✅ Partita trovata: event_id={event_id} ({league_name})")

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
        }

    while True:
        sleep_time = 10
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

            print(f"[{status}] {home_name} {g_home}-{g_away} {away_name} | min {elapsed} | eventi: {len(events)}")

            # --- Non ancora iniziata ---
            if status == "NS":
                try:
                    comp       = data["header"]["competitions"][0]
                    start_str  = comp.get("date", "")
                    if start_str:
                        start_time         = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                        now_utc            = datetime.now(timezone.utc)
                        minutes_to_kickoff = (start_time - now_utc).total_seconds() / 60
                        print(f"⏳ Partita non ancora iniziata. Inizio tra {minutes_to_kickoff:.0f} min.")
                        if minutes_to_kickoff > 30:
                            print(f"🛑 Mancano più di 30 minuti all'inizio ({minutes_to_kickoff:.0f} min). Bot spento.")
                            sys.exit(0)
                except Exception as e:
                    print(f"⚠️ Impossibile leggere orario partita: {e}")
                time.sleep(10)
                continue

            # Rigori: polling ancora più rapido
            if status == "PEN":
                sleep_time = 8

            # --- Inizio primo tempo ---
            if status == "1H" and "1H" not in state["sent_periods"]:
                send_telegram(f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{home_name} - {away_name}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("1H")

            # --- Fine primo tempo ---
            if status == "HT" and "HT" not in state["sent_periods"]:
                send_telegram(f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("HT")
                time.sleep(60)
                data_fresh = fetch_evento(event_id, league_slug) or data
                png_path = recupera_e_genera_stats_html(data_fresh, home_id, away_id,
                                                         home_name, away_name, g_home, g_away,
                                                         "HT", league_name)
                send_telegram_stats_photo(png_path, "HT", f"{e_comp} {hashtag}")
                state["sent_stats"].append("HT")

            # --- Inizio secondo tempo ---
            if status == "2H" and "2H" not in state["sent_periods"]:
                send_telegram(f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("2H")

            # --- Fine regolamentari → supplementari ---
            if status == "ET" and "2H_END" not in state["sent_periods"]:
                send_telegram(f"<b>FINE REGOLAMENTARI {E_FLAG}</b>\n\nSi va ai supplementari!\n\n{score_str}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("2H_END")
                time.sleep(60)
                data_fresh = fetch_evento(event_id, league_slug) or data
                png_path = recupera_e_genera_stats_html(data_fresh, home_id, away_id,
                                                         home_name, away_name, g_home, g_away,
                                                         "2H_END", league_name)
                send_telegram_stats_photo(png_path, "2H_END", f"{e_comp} {hashtag}")
                state["sent_stats"].append("2H_END")

            # --- Supplementari ---
            if status == "ET":
                if elapsed >= 91 and "1ET_START" not in state["sent_periods"]:
                    send_telegram(f"<b>INIZIO 1° TEMPO SUPPLEMENTARE {E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("1ET_START")
                if elapsed >= 105 and "1ET_END" not in state["sent_periods"]:
                    send_telegram(f"<b>FINE 1° TEMPO SUPPLEMENTARE {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("1ET_END")
                if elapsed >= 106 and "2ET_START" not in state["sent_periods"]:
                    send_telegram(f"<b>INIZIO 2° TEMPO SUPPLEMENTARE {E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("2ET_START")

            # --- Rigori ---
            if status == "PEN":
                if "ET_END_PENS" not in state["sent_periods"]:
                    send_telegram(f"<b>FINE SUPPLEMENTARI {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("ET_END_PENS")

                home_pen_icons, away_pen_icons = [], []
                for e in events:
                    if e["type"] in ("shootout goal", "shootout miss", "shootout saved"):
                        icon = E_PEN_OK if e["type"] == "shootout goal" else E_PEN_KO
                        (home_pen_icons if e["team_id"] == home_id else away_pen_icons).append(icon)

                total_kicks = len(home_pen_icons) + len(away_pen_icons)
                if total_kicks > state["penalties_count"]:
                    send_telegram(
                        f"<b>RIGORI {E_MIC}</b>\n\n"
                        f"{home_name}: " + "".join(home_pen_icons or ["-"]) + "\n"
                        f"{away_name}: " + "".join(away_pen_icons or ["-"]) + f"\n\n{e_comp} {hashtag}"
                    )
                    state["penalties_count"] = total_kicks

            # --- Fine partita ---
            is_finished = (
                status in ["FT", "AET"] or
                (status == "PEN" and
                 data.get("header", {}).get("competitions", [{}])[0]
                     .get("status", {}).get("type", {}).get("state") == "post")
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
                png_path = recupera_e_genera_stats_html(data_fresh, home_id, away_id,
                                                         home_name, away_name, g_home, g_away,
                                                         "FT", league_name)
                send_telegram_stats_photo(png_path, "FT", f"{e_comp} {hashtag}")
                state["sent_stats"].append("FT")
                state["_reset_done"] = True
                resetta_gist()
                print("🏁 Partita terminata. Bot spento.")
                sys.exit(0)

            # --- Rilevamento goal ---
            total_goals_now = g_home + g_away
            prev_home = state.get("prev_home_goals", 0)
            prev_away = state.get("prev_away_goals", 0)

            if total_goals_now > state["goals_detected"]:
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
                state["prev_home_goals"] = g_home
                state["prev_away_goals"] = g_away

            elif total_goals_now < state["goals_detected"]:
                send_telegram(f"<b>GOAL ANNULLATO 📺</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                state["goals_detected"] = total_goals_now
                state["prev_home_goals"] = g_home
                state["prev_away_goals"] = g_away

            # --- Cambi ---
            # ✅ FIX: se ci sono cambi nuovi, attende 30s e rilegge per raggruppare
            new_subs_check = []
            for e in events:
                if e["type"] == "substitution":
                    sub_id = f"sub_{e['minute']}_{e['player_name']}_{e['assist_name']}".replace(" ", "_")
                    if sub_id not in state["sent_subs"]:
                        new_subs_check.append({**e, "sub_id": sub_id})

            if new_subs_check:
                print(f"🔄 Cambio rilevato, attendo 30s per raggruppare...")
                time.sleep(30)
                # Rileggi i dati aggiornati
                data_subs = fetch_evento(event_id, league_slug) or data
                events_subs = parse_events(data_subs, home_name, away_name, home_id, away_id)

                new_subs = []
                for e in events_subs:
                    if e["type"] == "substitution":
                        sub_id = f"sub_{e['minute']}_{e['player_name']}_{e['assist_name']}".replace(" ", "_")
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

            # --- Rigori sbagliati (tempo regolamentare / supplementari) ---
            for e in events:
                if e["type"] in ("penalty missed", "penalty saved"):
                    p_name = fmt_player(e["player_name"])
                    pen_id = f"failpen_{e['minute']}_{e['player_name']}".replace(" ", "_")
                    if pen_id not in state["sent_failed_penalties"]:
                        team_name_pen = home_name if e["team_id"] == home_id else away_name
                        send_telegram(
                            f"<b>RIGORE SBAGLIATO {team_name_pen.upper()} {E_PEN_KO}</b>\n\n"
                            f"🥅 <i>{e['minute']}' {p_name}</i>\n\n{e_comp} {hashtag}"
                        )
                        state["sent_failed_penalties"].append(pen_id)

        except Exception as e:
            print(f"❌ Errore ciclo live: {e}")
            sleep_time = 10

        finally:
            if isinstance(state, dict) and not state.get("_reset_done"):
                salva_stato_su_gist(state)

        time.sleep(sleep_time)

# ==============================================================================
# MAIN
# ==============================================================================
def main():
    print("🚀 ESPN Live Score Bot avviato...")

    if str(os.getenv('ONLY_REFRESH_TOKEN', '')).strip().lower() == "true":
        get_valid_token()
        return

    avvia_ciclo_partita()

if __name__ == "__main__":
    main()
