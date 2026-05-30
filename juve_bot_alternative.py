import os
import requests
import json
import time
import sys
import base64
from PIL import Image
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

try:
    from nacl import encoding, public
except ImportError:
    print("⚠️ pynacl non installata. Aggiornamento Secrets GitHub non disponibile.")

# ==============================================================================
# CONFIGURAZIONE
# ==============================================================================
BOT_TOKEN         = os.getenv('TELEGRAM_TOKEN')
CHAT_ID           = os.getenv('TELEGRAM_TO')
TEAM_ID           = '18206'
GH_PAT            = os.getenv('GH_PAT')
GITHUB_REPOSITORY = os.getenv('GITHUB_REPOSITORY')
GIST_ID           = os.getenv('GIST_ID')
CLIENT_ID         = os.getenv('CANVA_CLIENT_ID')
CLIENT_SECRET     = os.getenv('CANVA_CLIENT_SECRET')
CANVA_REFRESH_TOKEN = os.getenv('CANVA_REFRESH_TOKEN')

CANVA_DESIGN_ID = "DAHI3ytu6yQ"
PAGINA_TARGET   = 11

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

LEAGUE_SLUGS = [
    # --- ITALIA ---
    "ita.1", "ita.coppa_italia", "ita.super_cup", "ita.2",

    # --- EUROPA (CLUB & COPPE CONTINENTALI) ---
    "uefa.champions", "uefa.europa", "uefa.europa_conf", "uefa.super_cup",

    # --- INGHILTERRA ---
    "eng.1", "eng.fa", "eng.league_cup", "eng.community", "eng.2", "eng.3", "eng.4",

    # --- SPAGNA ---
    "esp.1", "esp.copa_del_rey", "esp.super_cup", "esp.2",

    # --- GERMANIA ---
    "ger.1", "ger.dfb_pokal", "ger.2",

    # --- FRANCIA ---
    "fra.1", "fra.coupe_de_france", "fra.2",

    # --- ALTRI CAMPIONATI EUROPEI ---
    "por.1", "ned.1", "bel.1", "tur.1", "sco.1",
    "rus.1", "ukr.1", "gre.1", "aut.1", "sui.1", "den.1", "nor.1", "swe.1",

    # --- NORD & CENTRO AMERICA ---
    "usa.1", "usa.open", "usa.leagues_cup", "usa.mls.is.back",
    "mex.1", "mex.copa_mx", "mex.campeon_campeones",
    "concacaf.champions",

    # --- SUDAMERICA (CLUB & COPPE) ---
    "bra.1", "arg.1", "col.1", "chi.1", "ecu.1", "per.1", "uru.1",
    "conmebol.libertadores", "conmebol.sudamericana",

    # --- ASIA & OCEANIA ---
    "aus.1", "jpn.1", "chn.1", "sau.1", "afc.champions",

    # --- AFRICA ---
    "caf.champions",

    # --- AMICHEVOLI ---
    "friendly.club",

    # --- CALCIO FEMMINILE (CLUB & TORNEI) ---
    "usa.nwsl", "eng.w.1", "fra.w.1", "ger.w.1", "esp.w.1",
    "uefa.w.champions", "fifa.w.world", "fifa.w.world.q", 
    "uefa.w.euro", "uefa.w.nations", "olympics.w.soccer",

    # --- NAZIONALI MASCHILI (MONDIALI & QUALIFICAZIONI) ---
    "fifa.world", "fifa.world.q", "fifa.confed", "fifa.friendly", "olympics.m.soccer",

    # --- TORNEI CONTINENTALI NAZIONALI ---
    "uefa.euro", "uefa.euro.q", "uefa.nations",
    "conmebol.america", "conmebol.america.q",
    "concacaf.gold", "concacaf.nations",
    "caf.nations", "caf.nations.q",
    "afc.asian_cup", "afc.asian_cup.q"
]

LEAGUE_EMOJIS = {
    # --- ITALIA ---
    "ita.1": "🇮🇹", "ita.coppa_italia": "🇮🇹", "ita.super_cup": "🇮🇹", "ita.2": "🇮🇹",

    # --- EUROPA ---
    "uefa.champions": "🇪🇺", "uefa.europa": "🇪🇺", "uefa.europa_conf": "🇪🇺", "uefa.super_cup": "🇪🇺",
    "eng.1": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "eng.fa": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "eng.league_cup": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "eng.community": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", 
    "eng.2": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "eng.3": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "eng.4": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "esp.1": "🇪🇸", "esp.copa_del_rey": "🇪🇸", "esp.super_cup": "🇪🇸", "esp.2": "🇪🇸",
    "ger.1": "🇩🇪", "ger.dfb_pokal": "🇩🇪", "ger.2": "🇩🇪",
    "fra.1": "🇫🇷", "fra.coupe_de_france": "🇫🇷", "fra.2": "🇫🇷",
    "por.1": "🇵🇹", "ned.1": "🇳🇱", "bel.1": "🇧🇪", "tur.1": "🇹🇷", "sco.1": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "rus.1": "🇷🇺", "ukr.1": "🇺🇦", "gre.1": "🇬🇷", "aut.1": "🇦🇹", "sui.1": "🇨🇭", 
    "den.1": "🇩🇰", "nor.1": "🇳🇴", "swe.1": "🇸🇪",

    # --- AMERICHE ---
    "usa.1": "🇺🇸", "usa.open": "🇺🇸", "usa.leagues_cup": "🌎", "usa.mls.is.back": "🇺🇸",
    "mex.1": "🇲🇽", "mex.copa_mx": "🇲🇽", "mex.campeon_campeones": "🇲🇽",
    "concacaf.champions": "🌎",
    "bra.1": "🇧🇷", "arg.1": "🇦🇷", "col.1": "🇨🇴", "chi.1": "🇨🇱", "ecu.1": "🇪🇨", 
    "per.1": "🇵🇪", "uru.1": "🇺🇾", "conmebol.libertadores": "🌎", "conmebol.sudamericana": "🌎",

    # --- ASIA & AFRICA ---
    "aus.1": "🇦🇺", "jpn.1": "🇯🇵", "chn.1": "🇨🇳", "sau.1": "🇸🇦", "afc.champions": "🌏",
    "caf.champions": "🌍",

    # --- AMICHEVOLI ---
    "friendly.club": "🤝",

    # --- FEMMINILE ---
    "usa.nwsl": "🇺🇸", "eng.w.1": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "fra.w.1": "🇫🇷", "ger.w.1": "🇩🇪", "esp.w.1": "🇪🇸",
    "uefa.w.champions": "🇪🇺", "fifa.w.world": "🏆", "fifa.w.world.q": "🌍", 
    "uefa.w.euro": "🇪🇺", "uefa.w.nations": "🇪🇺", "olympics.w.soccer": "🏅",

    # --- NAZIONALI MASCHILI & TORNEI INTERCONTINENTALI ---
    "fifa.world": "🏆", "fifa.world.q": "🌍", "fifa.confed": "🏆", "fifa.friendly": "🌍", "olympics.m.soccer": "🏅",
    "uefa.euro": "🇪🇺", "uefa.euro.q": "🇪🇺", "uefa.nations": "🇪🇺",
    "conmebol.america": "🌎", "conmebol.america.q": "🌎",
    "concacaf.gold": "🌎", "concacaf.nations": "🌎",
    "caf.nations": "🌍", "caf.nations.q": "🌍",
    "afc.asian_cup": "🌏", "afc.asian_cup.q": "🌏"
}

def get_league_emoji(slug): return LEAGUE_EMOJIS.get(slug, "⚽️")

MOMENTI_CONFIG = {
    "HT":    {"titolo": "<b>STATS PRIMO TEMPO</b> 📊",   "badge": "FINE PRIMO TEMPO"},
    "2H_END":{"titolo": "<b>STATS SECONDO TEMPO</b> 📊", "badge": "FINE SECONDO TEMPO"},
    "FT":    {"titolo": "<b>STATS FINE PARTITA</b> 📊",  "badge": "FINE PARTITA"},
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
        print(f"📨 Telegram inviato: {text[:60]}...")
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
            print("💾 Stato salvato sul Gist.")
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
        time.sleep(8)
        for i in range(60):
            time.sleep(5)
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
def parse_events(data: dict) -> list:
    events = []
    seen_ids = set()

    def safe_minute(clock_str):
        try:
            return int(str(clock_str).split(":")[0])
        except Exception:
            return 0

    def extract_athlete(participants, index=0):
        try:
            return participants[index].get("athlete", {}).get("displayName", "")
        except Exception:
            return ""

    def add_event(ev_type, minute, team_id, player_name, assist_name, uid=None):
        key = uid or f"{ev_type}_{minute}_{player_name}"
        if key in seen_ids:
            return
        seen_ids.add(key)
        events.append({
            "type": ev_type.lower(),
            "minute": minute,
            "team_id": str(team_id),
            "player_name": player_name,
            "assist_name": assist_name,
        })

    for item in data.get("scoringPlays", []):
        try:
            ev_type    = item.get("type", {}).get("text", "goal")
            clock      = item.get("clock", {}).get("displayValue", "0:00")
            minute     = safe_minute(clock)
            team_id    = item.get("team", {}).get("id", "")
            parts      = item.get("participants", [])
            player     = extract_athlete(parts, 0)
            assist     = extract_athlete(parts, 1)
            uid        = item.get("id", f"sp_{minute}_{player}")
            add_event(ev_type, minute, team_id, player, assist, uid)
        except Exception as e:
            print(f"⚠️ Errore parsing scoringPlay: {e}")

    for item in data.get("keyPlays", []):
        try:
            ev_type = item.get("type", {}).get("text", "")
            if not ev_type:
                continue
            clock   = item.get("clock", {}).get("displayValue", "0:00")
            minute  = safe_minute(clock)
            team_id = item.get("team", {}).get("id", "")
            parts   = item.get("participants", [])
            player  = extract_athlete(parts, 0)
            assist  = extract_athlete(parts, 1)
            uid     = item.get("id", f"kp_{minute}_{player}_{ev_type}")
            add_event(ev_type, minute, team_id, player, assist, uid)
        except Exception as e:
            print(f"⚠️ Errore parsing keyPlay: {e}")

    for item in data.get("plays", []):
        try:
            ev_type = item.get("type", {}).get("text", "")
            if not ev_type:
                continue
            clock   = item.get("clock", {}).get("displayValue", "0:00")
            minute  = safe_minute(clock)
            team_id = item.get("team", {}).get("id", "")
            parts   = item.get("participants", [])
            player  = extract_athlete(parts, 0)
            assist  = extract_athlete(parts, 1)
            uid     = item.get("id", f"p_{minute}_{player}_{ev_type}")
            add_event(ev_type, minute, team_id, player, assist, uid)
        except Exception as e:
            print(f"⚠️ Errore parsing play: {e}")

    try:
        for comp in data.get("header", {}).get("competitions", []):
            for item in comp.get("plays", []):
                try:
                    ev_type = item.get("type", {}).get("text", "")
                    if not ev_type:
                        continue
                    clock   = item.get("clock", {}).get("displayValue", "0:00")
                    minute  = safe_minute(clock)
                    team_id = item.get("team", {}).get("id", "")
                    parts   = item.get("participants", [])
                    player  = extract_athlete(parts, 0)
                    assist  = extract_athlete(parts, 1)
                    uid     = item.get("id", f"hp_{minute}_{player}_{ev_type}")
                    add_event(ev_type, minute, team_id, player, assist, uid)
                except Exception:
                    pass
    except Exception:
        pass

    if events:
        print(f"📋 Eventi totali trovati: {len(events)} — tipi: {list(set(e['type'] for e in events))}")
    else:
        print("⚠️ Nessun evento trovato in scoringPlays/keyPlays/plays.")

    return events

# ==============================================================================
# STATISTICHE
# ==============================================================================
def _estrai_stats_espn(data: dict) -> dict:
    raw = {"home": {}, "away": {}}

    # --- Fonte A: boxscore ---
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

    # --- Fonte B: header.competitions.competitors (LIVE) ---
    try:
        comps = data.get("header", {}).get("competitions", [{}])
        for comp in comps:
            for competitor in comp.get("competitors", []):
                side = "home" if competitor.get("homeAway") == "home" else "away"
                for s in competitor.get("statistics", []):
                    key = s.get("name", "").lower()
                    val = s.get("displayValue", s.get("value", "0"))
                    if key and key not in raw[side]:
                        raw[side][key] = str(val)
    except Exception as e:
        print(f"⚠️ Errore parsing header competitors stats: {e}")

    # Debug: mostra TUTTE le chiavi trovate
    print(f"📊 Stats home keys ({len(raw['home'])}): {list(raw['home'].keys())}")
    print(f"📊 Stats away keys ({len(raw['away'])}): {list(raw['away'].keys())}")

    return raw


def recupera_e_genera_stats_html(data_espn: dict, home_id: str, away_id: str,
                                  home_name: str, away_name: str,
                                  home_goals: int, away_goals: int,
                                  momento: str, league_name: str = "SERIE A"):
    print(f"📊 Generazione stats HTML per momento {momento}...")

    def logo_url(competitor_id):
        return f"https://a.espncdn.com/i/teamlogos/soccer/500/{competitor_id}.png"

    h_logo = logo_url(home_id)
    a_logo = logo_url(away_id)
    badge_label = MOMENTI_CONFIG[momento]["badge"]

    raw = _estrai_stats_espn(data_espn)

    def g(side, *keys, fallback="0"):
        for key in keys:
            val = raw[side].get(key.lower(), None)
            if val is not None and val not in ("0", "", "0.0", "0%"):
                return val
        for key in keys:
            val = raw[side].get(key.lower(), None)
            if val is not None:
                return val
        return fallback

    def calcola_perc(h_val, a_val, tipo="int"):
        try:
            clean = lambda v: str(v).replace("%", "").strip()
            if tipo == "float":
                h, a = float(clean(h_val)), float(clean(a_val))
            else:
                h, a = int(float(clean(h_val))), int(float(clean(a_val)))
            return 50 if (h + a) == 0 else int(h / (h + a) * 100)
        except Exception:
            return 50

    # Possesso
    pos_h = g("home", "possessionPct", "possessionpct", "possession", fallback="50%")
    pos_a = g("away", "possessionPct", "possessionpct", "possession", fallback="50%")
    try:
        bp_perc = int(float(str(pos_h).replace("%", "")))
    except Exception:
        bp_perc = 50

    # Tiri in porta
    sot_h    = g("home", "shotsOnTarget", "shotsontarget", fallback="0")
    sot_a    = g("away", "shotsOnTarget", "shotsontarget", fallback="0")
    # Tiri totali
    shots_h  = g("home", "totalShots", "totalshots", fallback="0")
    shots_a  = g("away", "totalShots", "totalshots", fallback="0")
    # Falli
    falli_h  = g("home", "foulsCommitted", "foulscommitted", "fouls", fallback="0")
    falli_a  = g("away", "foulsCommitted", "foulscommitted", "fouls", fallback="0")
    # Cartellini gialli
    gialli_h = g("home", "yellowCards", "yellowcards", fallback="0")
    gialli_a = g("away", "yellowCards", "yellowcards", fallback="0")
    # Cartellini rossi
    rossi_h  = g("home", "redCards", "redcards", fallback="0")
    rossi_a  = g("away", "redCards", "redcards", fallback="0")
    # Corner — tutte le varianti ESPN note
    corner_h = g("home", "cornerKicks", "cornerkicks", "cornerKick", "cornerkick", "corners", "corner", fallback="0")
    corner_a = g("away", "cornerKicks", "cornerkicks", "cornerKick", "cornerkick", "corners", "corner", fallback="0")
    # Parate
    saves_h  = g("home", "saves", fallback="0")
    saves_a  = g("away", "saves", fallback="0")

    stats_mappate = [
        ("Possesso palla",  pos_h,   pos_a,   bp_perc),
        ("Tiri in porta",   sot_h,   sot_a,   calcola_perc(sot_h,   sot_a)),
        ("Tiri totali",     shots_h, shots_a, calcola_perc(shots_h, shots_a)),
        ("Falli",           falli_h, falli_a, calcola_perc(falli_h, falli_a)),
        ("Ammoniti",        gialli_h,gialli_a,calcola_perc(gialli_h,gialli_a)),
        ("Espulsi",         rossi_h, rossi_a, calcola_perc(rossi_h, rossi_a)),
        ("Corner",          corner_h,corner_a,calcola_perc(corner_h,corner_a)),
        ("Parate",          saves_h, saves_a, calcola_perc(saves_h, saves_a)),
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
  padding: 50px 60px; overflow: hidden;
}}
.card {{
  width: 1500px; height: 1880px; margin: 0 auto;
  background: linear-gradient(180deg, rgba(17,24,39,0.96), rgba(10,14,28,0.96));
  border-radius: 70px; overflow: hidden;
  border: 3px solid rgba(255,255,255,0.08);
  box-shadow: 0 50px 100px rgba(0,0,0,0.6), inset 0 2px 0 rgba(255,255,255,0.04);
  display: flex; flex-direction: column;
}}
.header {{ position: relative; padding: 75px 80px 55px; border-bottom: 3px solid rgba(255,255,255,0.06); }}
.league-row {{ text-align: center; color: #7c8cb5; font-size: 28px; letter-spacing: 5px; text-transform: uppercase; font-weight: 700; margin-bottom: 35px; }}
.badge {{ width: fit-content; margin: 0 auto 40px; padding: 14px 40px; border-radius: 999px; background: linear-gradient(135deg, #facc15, #f59e0b); color: #111827; font-size: 22px; font-weight: 900; letter-spacing: 3px; text-transform: uppercase; }}
.teams-row {{ display: flex; align-items: center; justify-content: space-between; padding: 0 30px; }}
.team {{ width: 350px; text-align: center; }}
.logo {{ width: 170px; height: 170px; object-fit: contain; display: block; margin: 0 auto 25px; }}
.team-name {{ color: white; font-weight: 800; font-size: 40px; }}
.score-wrap {{ text-align: center; }}
.score {{ font-family: 'Barlow Condensed', sans-serif; font-size: 195px; line-height: 0.85; font-weight: 900; color: white; letter-spacing: -4px; }}
.match-status {{ margin-top: 20px; color: #8fa1c7; font-size: 26px; font-weight: 600; text-transform: uppercase; letter-spacing: 2px; }}
.stats-body {{ padding: 50px 80px 65px; flex: 1; display: flex; flex-direction: column; justify-content: space-between; }}
.stats-title {{ text-align: center; color: #91a4d0; font-size: 26px; font-weight: 800; letter-spacing: 4px; text-transform: uppercase; margin-bottom: 15px; }}
.stat-row {{ padding: 15px 0; border-bottom: 2px solid rgba(255,255,255,0.05); }}
.stat-row:last-child {{ border-bottom: none; }}
.stat-top {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }}
.val {{ width: 120px; color: white; font-weight: 900; font-size: 46px; font-family: 'Barlow Condensed', sans-serif; }}
.home-val {{ text-align: left; }}
.away-val {{ text-align: right; }}
.stat-label {{ color: #b4c0df; font-size: 30px; font-weight: 700; }}
.bar-track {{ position: relative; height: 22px; border-radius: 999px; overflow: hidden; background: rgba(255,255,255,0.06); }}
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

    print("📸 Rendering con Playwright (1620×1980)...")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-web-security", "--allow-running-insecure-content"])
        page = browser.new_page(viewport={"width": 1620, "height": 1980}, device_scale_factor=1.0)
        page.goto(f"file://{path_html}")
        page.wait_for_timeout(3000)
        page.screenshot(path=path_raw_png, omit_background=False)
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
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    for slug in LEAGUE_SLUGS:
        url = f"{ESPN_BASE}/{slug}/scoreboard"
        try:
            r = requests.get(url, params={"dates": today}, timeout=10)
            if r.status_code != 200:
                continue
            data = r.json()
            league_name = data.get("leagues", [{}])[0].get("name", slug)
            for event in data.get("events", []):
                competitions = event.get("competitions", [])
                if not competitions:
                    continue
                competitors = competitions[0].get("competitors", [])
                ids = [c.get("team", {}).get("id", "") for c in competitors]
                if team_id in ids:
                    return {"event_id": event["id"], "league_slug": slug,
                            "league_name": league_name, "competitors": competitors}
        except Exception as e:
            print(f"⚠️ Errore fetch slug {slug}: {e}")
    return None

def fetch_evento(event_id: str, league_slug: str):
    try:
        r = requests.get(f"{ESPN_BASE}/{league_slug}/summary",
                         params={"event": event_id}, timeout=15)
        if r.status_code == 200:
            d = r.json()
            print(f"🔍 Chiavi ESPN summary: {list(d.keys())}")
            return d
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

    partita = trova_partita_oggi(team_id)
    if not partita:
        print(f"📭 Nessun evento trovato oggi per team_id={team_id}.")
        return

    event_id    = partita["event_id"]
    league_slug = partita["league_slug"]
    league_name = partita["league_name"]
    print(f"✅ Partita trovata: event_id={event_id} ({league_name})")

    state = leggi_stato_da_gist()
    if state is None or state.get("event_id") != event_id:
        state = {
            "event_id": event_id, "sent_periods": [], "goals_detected": 0,
            "sent_subs": [], "sent_cards": [], "penalties_count": 0, "sent_stats": []
        }

    while True:
        sleep_time = 90
        try:
            data = fetch_evento(event_id, league_slug)
            if not data:
                time.sleep(30)
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
            events    = parse_events(data)

            print(f"[{status}] {home_name} {g_home}-{g_away} {away_name} | min {elapsed} | eventi: {len(events)}")

            if status == "NS":
                time.sleep(60)
                continue

            sleep_time = 60 if status == "PEN" else 90

            if status == "1H" and "1H" not in state["sent_periods"]:
                send_telegram(f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{home_name} - {away_name}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("1H")

            if status == "HT" and "HT" not in state["sent_periods"]:
                send_telegram(f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("HT")
                time.sleep(120)
                data_fresh = fetch_evento(event_id, league_slug) or data
                png_path = recupera_e_genera_stats_html(data_fresh, home_id, away_id,
                                                         home_name, away_name, g_home, g_away,
                                                         "HT", league_name)
                send_telegram_stats_photo(png_path, "HT", f"{e_comp} {hashtag}")
                state["sent_stats"].append("HT")

            if status == "2H" and "2H" not in state["sent_periods"]:
                send_telegram(f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("2H")

            if status == "ET" and "2H_END" not in state["sent_periods"]:
                send_telegram(f"<b>FINE REGOLAMENTARI {E_FLAG}</b>\n\nSi va ai supplementari!\n\n{score_str}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("2H_END")
                time.sleep(120)
                data_fresh = fetch_evento(event_id, league_slug) or data
                png_path = recupera_e_genera_stats_html(data_fresh, home_id, away_id,
                                                         home_name, away_name, g_home, g_away,
                                                         "2H_END", league_name)
                send_telegram_stats_photo(png_path, "2H_END", f"{e_comp} {hashtag}")
                state["sent_stats"].append("2H_END")

            if status == "ET":
                if elapsed >= 91 and elapsed < 105 and "1ET_START" not in state["sent_periods"]:
                    send_telegram(f"<b>INIZIO 1° TEMPO SUPPLEMENTARE {E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("1ET_START")
                elif elapsed >= 105 and "1ET_END" not in state["sent_periods"]:
                    send_telegram(f"<b>FINE 1° TEMPO SUPPLEMENTARE {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("1ET_END")
                elif elapsed >= 106 and "2ET_START" not in state["sent_periods"]:
                    send_telegram(f"<b>INIZIO 2° TEMPO SUPPLEMENTARE {E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("2ET_START")

            if status == "PEN":
                if "ET_END_PENS" not in state["sent_periods"]:
                    send_telegram(f"<b>FINE SUPPLEMENTARI {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                    state["sent_periods"].append("ET_END_PENS")

                home_pen_icons, away_pen_icons = [], []
                for e in events:
                    if "penalty" in e["type"] or "shootout" in e["type"]:
                        icon = E_PEN_KO if ("miss" in e["type"] or "saved" in e["type"]) else E_PEN_OK
                        (home_pen_icons if e["team_id"] == home_id else away_pen_icons).append(icon)

                total_kicks = len(home_pen_icons) + len(away_pen_icons)
                if total_kicks > state["penalties_count"]:
                    send_telegram(
                        f"{home_name}: " + "".join(home_pen_icons) + "\n"
                        f"{away_name}: " + "".join(away_pen_icons) + f"\n\n{e_comp} {hashtag}"
                    )
                    state["penalties_count"] = total_kicks

            is_finished = (
                status in ["FT", "AET"] or
                (status == "PEN" and
                 data.get("header", {}).get("competitions", [{}])[0]
                     .get("status", {}).get("type", {}).get("state") == "post")
            )
            if is_finished and "FT" not in state["sent_periods"]:
                home_scorers, away_scorers = [], []
                for e in events:
                    if "goal" in e["type"] and "shootout" not in e["type"]:
                        ps = fmt_player(e["player_name"])
                        if "own" in e["type"]:
                            ps += " (Autogol)"
                        elif "penalty" in e["type"]:
                            ps += " (Rig.)"
                        entry = f"{e['minute']}' {ps}"
                        (home_scorers if e["team_id"] == home_id else away_scorers).append(entry)

                if home_scorers and away_scorers:
                    scorers_line = f"{E_BALL} <i>" + ", ".join(home_scorers) + " // " + ", ".join(away_scorers) + "</i>\n"
                elif home_scorers:
                    scorers_line = f"{E_BALL} <i>" + ", ".join(home_scorers) + "</i>\n"
                elif away_scorers:
                    scorers_line = f"{E_BALL} <i>" + ", ".join(away_scorers) + "</i>\n"
                else:
                    scorers_line = ""

                msg_finale = f"<b>FINE PARTITA {E_FLAG}</b>\n\n{score_str}\n{scorers_line}\n{e_comp} {hashtag}"

                canva_token = get_valid_token()
                if canva_token:
                    foto = get_canva_image(canva_token)
                    send_telegram_with_photo(msg_finale, foto)
                else:
                    send_telegram(msg_finale)

                time.sleep(120)
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

            total_goals_now = g_home + g_away
            if total_goals_now > state["goals_detected"]:
                goal_events = [e for e in events if "goal" in e["type"] and "shootout" not in e["type"]]
                if goal_events:
                    last = sorted(goal_events, key=lambda x: x["minute"])[-1]
                    if not last["player_name"]:
                        print("⏳ Nome marcatore non ancora disponibile. Riprovo...")
                        time.sleep(sleep_time)
                        continue
                    ps = fmt_player(last["player_name"])
                    if "own" in last["type"]:
                        ps += " (Autogol)"
                    elif "penalty" in last["type"]:
                        ps += " (Rig.)"
                    scorer_line = f"{E_BALL} <i>{last['minute']}' {ps}</i>\n"

                    scoring_tid = last["team_id"]
                    if "own" in last["type"]:
                        scoring_tid = away_id if scoring_tid == home_id else home_id

                    if scoring_tid == home_id:
                        goal_score = f"<b>{home_name} {g_home}</b>-{g_away} {away_name}"
                    else:
                        goal_score = f"{home_name} {g_home}-<b>{g_away} {away_name}</b>"

                    send_telegram(f"<b>GOAL {E_MIC}</b>\n\n{goal_score}\n{scorer_line}\n{e_comp} {hashtag}")
                    state["goals_detected"] = total_goals_now

            elif total_goals_now < state["goals_detected"]:
                send_telegram(f"<b>GOAL ANNULLATO 📺</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                state["goals_detected"] = total_goals_now

            subs_by_bucket: dict = {}
            for e in events:
                ev_type = e["type"]
                if "substitut" in ev_type:
                    p_out  = fmt_player(e["player_name"])
                    p_in   = fmt_player(e["assist_name"])
                    sub_id = f"sub_{e['minute']}_{e['player_name']}_{e['assist_name']}".replace(" ", "_")
                    if sub_id not in state["sent_subs"]:
                        bucket = f"{e['team_id']}_{e['minute'] // 2}"
                        if bucket not in subs_by_bucket:
                            subs_by_bucket[bucket] = {"minute": e["minute"], "team_id": e["team_id"],
                                                       "in": [], "out": [], "ids": []}
                        subs_by_bucket[bucket]["in"].append(p_in)
                        subs_by_bucket[bucket]["out"].append(p_out)
                        subs_by_bucket[bucket]["ids"].append(sub_id)

                elif "red card" in ev_type or "second yellow" in ev_type:
                    p_name  = fmt_player(e["player_name"])
                    card_id = f"card_{e['minute']}_{e['player_name']}".replace(" ", "_")
                    if card_id not in state["sent_cards"]:
                        send_telegram(f"<b>CARTELLINO ROSSO {E_RED}</b>\n\n🔚 <i>{e['minute']}' {p_name}</i>\n\n{e_comp} {hashtag}")
                        state["sent_cards"].append(card_id)

            for bucket, sub in subs_by_bucket.items():
                team_title = home_name.upper() if sub["team_id"] == home_id else away_name.upper()
                send_telegram(
                    f"<b>CAMBIO {team_title} {E_SUB}</b>\n\n"
                    f"{E_UP} {', '.join(sub['in'])}\n"
                    f"{E_DOWN} {', '.join(sub['out'])}\n\n"
                    f"{e_comp} {hashtag}"
                )
                state["sent_subs"].extend(sub["ids"])

        except Exception as e:
            print(f"❌ Errore ciclo live: {e}")
            sleep_time = 30

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
