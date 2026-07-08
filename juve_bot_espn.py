import os
import re
import html
import unicodedata
import requests
import json
import time
import sys
import base64
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import kit_analyzer

ITALY_TZ = ZoneInfo('Europe/Rome')
ESPN_TZ  = ZoneInfo('America/New_York')  # ESPN indicizza gli eventi in orario US Eastern

def now_it(): return datetime.now(ITALY_TZ).strftime('%H:%M:%S')

# ── Sessione HTTP condivisa ───────────────────────────────────────────────────
# Retry automatici SOLO sui GET (idempotenti): i POST Telegram non vengono
# ritentati in automatico per evitare doppi invii; il rate limit 429 di
# Telegram è gestito manualmente in _tg_post().
SESSION = requests.Session()
_retry = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset({"GET"}),
)
SESSION.mount("https://", HTTPAdapter(max_retries=_retry, pool_maxsize=10))

def esc(s) -> str:
    """Escape HTML: protegge i messaggi Telegram (parse_mode=HTML) e il
    template stats da nomi contenenti '<', '>' o '&'."""
    return html.escape(str(s), quote=False)

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
PAGINA_TARGET   = 2

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
#   default → partita senza la Juve  /  amichevole
# ==============================================================================
JUVE_ID = '111'  # ID ESPN reale della Juventus — usato SOLO per il branding
                 # (logo + tema kit). NON legato a TEAM_ID (la squadra monitorata,
                 # che in test potrebbe essere un'altra): così una partita senza la
                 # Juve resta sul kit 'default' e usa i loghi ESPN, niente logo Juve.

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

# Parole chiave di fallback per riconoscere un'amichevole dal nome/slug
# (slug ESPN tipici: 'friendly.club', 'fifa.friendly')
_FRIENDLY_KEYWORDS = ("friendly", "amichev")

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

def is_friendly_competition(league_slug: str, league_name: str = "") -> bool:
    """Determina se la competizione è un'amichevole.
    Priorità: override esplicito in leagues.json ({"slug": {"type": "friendly"}})
    → keyword di fallback."""
    slug = (league_slug or "").lower()
    name = (league_name or "").lower()

    # 1) override esplicito da leagues.json
    tipo = str(LEAGUE_MAP.get(league_slug, {}).get("type", "")).lower()
    if tipo in ("friendly", "amichevole"):
        return True

    # 2) fallback per keyword
    return any(k in slug or k in name for k in _FRIENDLY_KEYWORDS)

def determina_kit(home_id, away_id, league_slug: str = "", league_name: str = "") -> str:
    """Restituisce il tema della maglia da applicare alla grafica stats."""
    # Amichevoli → sempre kit 'default' (anche se gioca la Juve)
    if is_friendly_competition(league_slug, league_name):
        return "default"
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
E_CLOCK  = '⏱'

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

def _norm_name(s: str) -> str:
    """Confronto nomi tollerante agli accenti (es. 'Erik' == 'Érik').
    Usata nel dedup di parse_events e nel loop correzione marcatori."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', (s or '').strip())
        if unicodedata.category(c) != 'Mn'
    ).lower()

# ── Regex FONTE 0: estrazione eventi dal testo del commentary (senza play) ──
# ESPN pubblica il testo commentato MOLTO prima dei dati strutturati (play,
# participants). Queste regex pescano il nome del marcatore/ammonito direttamente
# dal testo, garantendo notifiche immediate. Il dedup normalizzato in add_event
# impedisce qualsiasi duplicato quando arrivano poi i dati strutturati.

_CT_GOAL_RX   = re.compile(
    r"Goal!\s*[^.]+?\.\s*(?P<player>[^(\n]+?)\s*\((?P<team>[^)]+)\)",
    re.IGNORECASE | re.UNICODE,
)
_CT_ASSIST_RX = re.compile(
    r"[Aa]ssisted by\s+(?P<assist>[^.]+?)(?=\s+with\b|\s+following\b|\.|$)",
    re.UNICODE,
)
_CT_YELLOW_RX = re.compile(
    r"(?P<player>[^(\n]+?)\s*\((?P<team>[^)]+)\)\s+is shown\s+(?:a\s+)?(?P<second>second\s+)?(?:yellow|the yellow)\s+card",
    re.IGNORECASE | re.UNICODE,
)
_CT_RED_RX    = re.compile(
    r"(?P<player>[^(\n]+?)\s*\((?P<team>[^)]+)\)\s+is shown\s+(?:a\s+)?(?:red|the red)\s+card",
    re.IGNORECASE | re.UNICODE,
)

# Cache displayName.strip().lower() -> shortName ufficiale ESPN.
# Popolata da extract_athlete() in parse_events() e usata da fmt_player()
# cosi anche i nomi estratti da testo (FONTE 0) ricevono la forma corretta.
_ESPN_SHORT_NAMES: dict[str, str] = {}

def fmt_player(full_name: str) -> str:
    if not full_name:
        return "N/A"
    # Controlla prima il cache ESPN: se presente usa la forma ufficiale
    # (es. "Viniciius Junior" resta tale, "Ismael Saibari" -> "I. Saibari")
    cached = _ESPN_SHORT_NAMES.get(full_name.strip().lower())
    if cached:
        return esc(cached)
    parts = full_name.strip().split()
    if len(parts) == 1:
        return esc(parts[0])
    # Se il primo token e' gia' un'iniziale (es. "I. Saibari"), non ri-abbreviare
    if parts[0].endswith("."):
        return esc(full_name.strip())
    return esc(parts[0][0].upper() + ". " + " ".join(parts[1:]))

# ==============================================================================
# TELEGRAM
# ==============================================================================
def _tg_post(method: str, payload: dict | None = None, data: dict | None = None,
             files: dict | None = None, timeout: int = 10):
    """POST verso l'API Telegram con gestione manuale del rate limit (429,
    rispettando retry_after). Nessun retry automatico su altri errori per
    evitare invii duplicati."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    r = None
    for _ in range(3):
        r = SESSION.post(url, json=payload, data=data, files=files, timeout=timeout)
        if r.status_code != 429:
            return r
        try:
            retry_after = int(r.json().get("parameters", {}).get("retry_after", 3))
        except Exception:
            retry_after = 3
        print(f"[{now_it()}] ⏳ Telegram rate limit (429) — attendo {retry_after}s")
        time.sleep(min(retry_after, 30))
    return r

def send_telegram(text: str):
    if not BOT_TOKEN or not CHAT_ID:
        print(f"[{now_it()}] ⚠️  BOT_TOKEN o CHAT_ID mancanti")
        return
    try:
        r = _tg_post("sendMessage", payload={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"})
        r.raise_for_status()
    except Exception as e:
        print(f"[{now_it()}] ❌ Errore send_telegram: {e}")

def send_telegram_edit(message_id: int, text: str) -> bool:
    """Modifica un messaggio esistente. Ritorna True solo se l'edit è
    andato a buon fine, così chi chiama può evitare di salvare lo stato
    come 'fatto' e ritentare al ciclo successivo in caso di errore."""
    if not BOT_TOKEN or not CHAT_ID or not message_id:
        return False
    try:
        r = _tg_post("editMessageText", payload={
            "chat_id": CHAT_ID, "message_id": message_id,
            "text": text, "parse_mode": "HTML"
        })
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"[{now_it()}] ❌ Errore editMessageText: {e}")
        return False

def send_telegram_get_id(text: str) -> int | None:
    if not BOT_TOKEN or not CHAT_ID:
        print(f"[{now_it()}] ⚠️  BOT_TOKEN o CHAT_ID mancanti")
        return None
    try:
        r = _tg_post("sendMessage", payload={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"})
        r.raise_for_status()
        msg_id = r.json().get("result", {}).get("message_id")
        return msg_id
    except Exception as e:
        print(f"[{now_it()}] ❌ Errore send_telegram_get_id: {e}")
        return None

def delete_telegram_message(message_id: int):
    if not BOT_TOKEN or not CHAT_ID or not message_id:
        return
    try:
        _tg_post("deleteMessage", payload={"chat_id": CHAT_ID, "message_id": message_id})
    except Exception as e:
        print(f"[{now_it()}] ⚠️  Errore deleteMessage: {e}")

def send_telegram_with_photo(text: str, photo_bytes) -> bool:
    """Invia foto+caption; fallback su solo testo. Ritorna True se almeno
    un messaggio è stato consegnato."""
    if not photo_bytes:
        return send_telegram_get_id(text) is not None
    try:
        r = _tg_post("sendPhoto",
                     data={"chat_id": CHAT_ID, "caption": text, "parse_mode": "HTML"},
                     files={"photo": ("matchday.png", photo_bytes)}, timeout=25)
        if r is not None and r.status_code == 200:
            return True
        return send_telegram_get_id(text) is not None
    except Exception:
        return send_telegram_get_id(text) is not None

def send_telegram_stats_photo(png_path: str, momento: str, hashtag: str) -> bool:
    """Invia la foto delle statistiche. Ritorna True solo se l'invio è
    andato davvero a buon fine, così chi chiama può ritentare invece di
    segnare l'evento come fatto e perderlo silenziosamente."""
    if not png_path:
        print(f"[{now_it()}] ⚠️  Stats {momento}: nessuna immagine generata — invio saltato")
        return False
    caption = f"{MOMENTI_CONFIG[momento]['titolo']}\n\n{hashtag}"
    try:
        with open(png_path, "rb") as f:
            r = _tg_post("sendPhoto",
                     data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "HTML"},
                     files={"photo": ("stats.png", f, "image/png")}, timeout=25)
        if r is None:
            return False
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"[{now_it()}] ❌ Errore invio foto statistiche: {e}")
        return False

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
        pk = SESSION.get(f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/secrets/public-key",
                         headers=headers, timeout=10).json()
        pub_key = public.PublicKey(pk["key"].encode("utf-8"), encoding.Base64Encoder)
        encrypted = base64.b64encode(public.SealedBox(pub_key).encrypt(new_value.encode())).decode()
        r = SESSION.put(f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/secrets/{secret_name}",
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
    """Legge lo stato dal Gist.

    Ritorna una tupla (ok, state):
      ok=True,  state=dict  → stato letto correttamente
      ok=True,  state=None  → Gist vuoto/non configurato (stato vergine legittimo)
      ok=False, state=None  → ERRORE di rete/API dopo i retry: NON va trattato
                              come stato vergine, altrimenti il bot rimanderebbe
                              tutti i messaggi già inviati.
    """
    if not GH_PAT or not GIST_ID:
        return True, None
    for attempt in range(3):
        try:
            r = SESSION.get(f"https://api.github.com/gists/{GIST_ID}", headers=_gist_headers(), timeout=10)
            if r.status_code == 200:
                content = r.json()["files"]["match_state.json"]["content"].strip()
                if not content or content == "{}":
                    return True, None
                return True, json.loads(content)
            print(f"[{now_it()}] ⚠️  Lettura Gist HTTP {r.status_code} (tentativo {attempt + 1}/3)")
        except Exception as e:
            print(f"[{now_it()}] ⚠️  Errore lettura Gist (tentativo {attempt + 1}/3): {e}")
        time.sleep(3)
    return False, None

def salva_stato_su_gist(state: dict):
    if not GH_PAT or not GIST_ID:
        return
    try:
        # Le chiavi con underscore sono flag interni di sessione (log, reset):
        # non vanno persistite nel Gist.
        clean = {k: v for k, v in state.items() if not str(k).startswith("_")}
        payload = {"files": {"match_state.json": {"content": json.dumps(clean, ensure_ascii=False, indent=2)}}}
        r = SESSION.patch(f"https://api.github.com/gists/{GIST_ID}", headers=_gist_headers(),
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
        SESSION.patch(f"https://api.github.com/gists/{GIST_ID}", headers=_gist_headers(),
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
        r = SESSION.post("https://api.canva.com/rest/v1/oauth/token", data={
            "grant_type": "refresh_token", "refresh_token": CANVA_REFRESH_TOKEN,
            "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET
        }, timeout=15)
        if r.status_code == 200:
            tokens = r.json()
            if "refresh_token" in tokens and tokens["refresh_token"] != CANVA_REFRESH_TOKEN:
                print(f"[{now_it()}] 🔄 Nuovo refresh token ricevuto — aggiorno GitHub Secret...")
                if update_github_secret("CANVA_REFRESH_TOKEN", tokens["refresh_token"]):
                    print(f"[{now_it()}] ✅ GitHub Secret CANVA_REFRESH_TOKEN aggiornato")
                else:
                    # Il vecchio refresh token è stato invalidato da Canva ma il
                    # nuovo NON è stato salvato: senza intervento manuale tutti i
                    # run futuri falliranno. Avviso subito su Telegram.
                    print(f"[{now_it()}] 🚨 Aggiornamento GitHub Secret FALLITO — il nuovo refresh token va salvato A MANO")
                    send_telegram(
                        "🚨 <b>ATTENZIONE — Canva</b>\n\n"
                        "Il refresh token è stato ruotato ma il salvataggio del "
                        "GitHub Secret <code>CANVA_REFRESH_TOKEN</code> è fallito.\n"
                        "Aggiornalo manualmente o i prossimi run non potranno "
                        "generare la grafica Canva."
                    )
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
        r = SESSION.post("https://api.canva.com/rest/v1/exports", headers=headers, json={
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
            check = SESSION.get(status_url, headers=headers, timeout=15)
            if check.status_code == 200:
                d = check.json()
                stato = d.get("status") or d.get("job", {}).get("status")
                if stato == "success":
                    urls = d.get("urls") or d.get("job", {}).get("urls")
                    url_dl = urls[0] if urls else (d.get("url") or d.get("job", {}).get("url"))
                    if url_dl:
                        print(f"[{now_it()}] ✅ Export Canva completato, scarico immagine...")
                        img = SESSION.get(url_dl, timeout=30).content
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
    # I testi ESPN spesso citano ENTRAMBE le squadre (es. "Goal! Juventus 1,
    # Inter 0"): controllare solo "nome in testo" attribuirebbe sempre alla
    # squadra di casa. Si attribuisce invece al nome che compare PER PRIMO.
    text_low = text.lower()
    h_pos = text_low.find(home_name.lower()) if home_name else -1
    a_pos = text_low.find(away_name.lower()) if away_name else -1
    if h_pos >= 0 and (a_pos < 0 or h_pos < a_pos):
        return home_id
    if a_pos >= 0:
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

    def safe_minute_disp(clock_val) -> str:
        """Preserva il formato originale ESPN per la visualizzazione (es. '45+5')."""
        try:
            s = str(clock_val).strip().replace("'", "")
            if "+" in s:
                a, b = s.split("+", 1)
                return f"{int(float(a.strip()))}+{int(float(b.strip()))}"
            if ":" in s:
                return str(int(float(s.split(":")[0])))
            return str(int(float(s)))
        except Exception:
            return str(safe_minute(clock_val))

    def extract_athlete(participants, index=0) -> str:
        try:
            athlete = participants[index].get("athlete", {})
            display = (athlete.get("displayName") or "").strip()
            short   = (athlete.get("shortName")   or "").strip()
            # Popola il cache globale: displayName -> shortName
            # (es. "Ismael Saibari" -> "I. Saibari",
            #       "Vinicius Junior" -> "Vinicius Junior")
            # cosi fmt_player sa gia la forma corretta anche per i nomi
            # estratti da testo in FONTE 0.
            if display and short:
                _ESPN_SHORT_NAMES[display.lower()] = short
            return display or short or ""
        except Exception:
            return ""

    def add_event(ev_type, minute, team_id, player_name, assist_name, uid, minute_disp=""):
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
                    and _norm_name(existing["player_name"]) == _norm_name(player_name)):
                # Stesso evento: aggiorna con dati più completi (es. assist
                # arrivato dopo, o nome da fonte strutturata dopo fonte testuale).
                if not existing["assist_name"] and assist_name:
                    existing["assist_name"] = assist_name
                if not existing["player_name"] and player_name:
                    existing["player_name"] = player_name
                # Aggiorna minute_disp se il nuovo ha il formato recupero (contiene "+")
                if minute_disp and "+" in minute_disp and "+" not in existing.get("minute_disp", ""):
                    existing["minute_disp"] = minute_disp
                return
        # Dedup specifico sostituzioni: la stessa sostituzione può arrivare da più
        # feed ESPN (commentary + keyEvents) con uid diversi, minuto leggermente
        # diverso e participant in ordine invertito (in/out scambiati). La
        # identifico dalla COPPIA di giocatori coinvolti, indipendente dall'ordine.
        # Confronto normalizzato per tollerare differenze di accenti tra le fonti.
        if norm == "substitution":
            pair = frozenset((_norm_name(player_name), _norm_name(assist_name)))
            for existing in events:
                if (existing["type"] == "substitution"
                        and existing["team_id"] == str(team_id)
                        and abs(existing["minute"] - minute) <= 2
                        and frozenset((_norm_name(existing["player_name"]),
                                       _norm_name(existing["assist_name"]))) == pair):
                    return
        events.append({
            "type":        norm,
            "minute":      minute,
            "minute_disp": minute_disp or str(minute),
            "seq":         len(events),   # ordine cronologico ESPN — tiebreaker nel sort
            "team_id":     str(team_id),
            "player_name": player_name,
            "assist_name": assist_name,
            "uid":         uid,
        })

    # --- FONTE 0: commentary[] testo senza play strutturato (fonte veloce) ---
    # ESPN pubblica il testo commentato molto prima dei dati strutturati (play +
    # participants). Questa fonte estrae gol, cartellini gialli e rossi dal testo
    # libero appena disponibile. Il dedup normalizzato in add_event garantisce che
    # quando arrivano i dati strutturati (FONTE 1/2) l'evento non venga duplicato,
    # ma venga solo aggiornato con eventuali dati mancanti (es. assist).
    # Le sostituzioni NON vengono parsate qui: il loro testo ESPN è ambiguo riguardo
    # all'ordine in/out, e i dati strutturati arrivano comunque in tempi brevi.
    for item in data.get("commentary", []):
        if item.get("play"):
            continue  # ha già il play strutturato → gestita da FONTE 1
        text = item.get("text", "")
        if not text:
            continue
        seq        = str(item.get("sequence", ""))
        _clock_f0  = item.get("time", {}).get("displayValue", "0")
        minute     = safe_minute(_clock_f0)
        _mdisp_f0  = safe_minute_disp(_clock_f0)
        text_low = text.lower()

        try:
            # ── GOAL ──
            mg = _CT_GOAL_RX.search(text)
            if mg:
                player   = mg.group("player").strip()
                team_txt = mg.group("team").strip()
                tl = team_txt.lower()
                if tl == (home_name or "").lower():
                    t_id = home_id
                elif tl == (away_name or "").lower():
                    t_id = away_id
                else:
                    t_id = ""
                # Tipo gol
                if "own goal" in text_low:
                    ev_type = "own goal"
                elif "penalty" in text_low:
                    ev_type = "penalty goal"
                else:
                    ev_type = "goal"
                # Assist (può non essere ancora nel testo rapido)
                ma = _CT_ASSIST_RX.search(text)
                assist = ma.group("assist").strip() if ma else ""
                add_event(ev_type, minute, t_id, player, assist, f"txt_g_{seq}", minute_disp=_mdisp_f0)
                continue

            # ── CARTELLINO GIALLO / DOPPIO GIALLO ──
            my = _CT_YELLOW_RX.search(text)
            if my:
                player   = my.group("player").strip()
                team_txt = my.group("team").strip()
                tl = team_txt.lower()
                if tl == (home_name or "").lower():
                    t_id = home_id
                elif tl == (away_name or "").lower():
                    t_id = away_id
                else:
                    t_id = ""
                second   = bool(my.group("second"))
                ev_type  = "second yellow card" if second else "yellow card"
                add_event(ev_type, minute, t_id, player, "", f"txt_y_{seq}", minute_disp=_mdisp_f0)
                continue

            # ── CARTELLINO ROSSO ──
            mr = _CT_RED_RX.search(text)
            if mr:
                player   = mr.group("player").strip()
                team_txt = mr.group("team").strip()
                tl = team_txt.lower()
                if tl == (home_name or "").lower():
                    t_id = home_id
                elif tl == (away_name or "").lower():
                    t_id = away_id
                else:
                    t_id = ""
                add_event("red card", minute, t_id, player, "", f"txt_r_{seq}", minute_disp=_mdisp_f0)
                continue

        except Exception as e:
            print(f"[{now_it()}] ⚠️  Errore FONTE 0 commentary testo: {e}")

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
            _mdisp  = safe_minute_disp(clock)
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
            # Calcio della lotteria senza squadra attribuibile: scartato. La
            # fonte strutturata shootout[] lo fornirà comunque con la squadra
            # giusta; tenerlo qui lo farebbe contare alla squadra sbagliata.
            if period_num == 5 and not team_id:
                continue
            add_event(ev_type, minute, team_id, player, assist, uid, minute_disp=_mdisp)
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
            _mdisp  = safe_minute_disp(clock)
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

            # Periodo 5 = lotteria dei rigori. Senza questa rimappatura un calcio
            # arrivato via keyEvents diventerebbe "penalty goal" (finendo tra i
            # marcatori del risultato finale) o "penalty missed" (scatenando un
            # finto messaggio RIGORE SBAGLIATO durante la lotteria).
            period_num_ke = play.get("period", {}).get("number", 0)
            if period_num_ke == 5:
                raw_type = play.get("type", {}).get("type", "")
                ev_low = ev_type.lower()
                if "scored" in raw_type or "scored" in ev_low or "goal" in ev_low:
                    ev_type = "shootout goal"
                elif "missed" in raw_type or "missed" in ev_low or "miss" in ev_low:
                    ev_type = "shootout miss"
                elif "saved" in raw_type or "saved" in ev_low:
                    ev_type = "shootout saved"
                if not t_id:
                    continue  # calcio non attribuibile: lo fornirà shootout[]

            add_event(ev_type, minute, t_id, player, assist, uid, minute_disp=_mdisp)
        except Exception as e:
            print(f"[{now_it()}] ⚠️  Errore parsing keyEvent: {e}")

    # --- FONTE 3: scoringPlays[] (fallback) ---
    for item in data.get("scoringPlays", []):
        try:
            ev_type = item.get("type", {}).get("text", "goal")
            clock   = item.get("clock", {}).get("displayValue", "0")
            minute  = safe_minute(clock)
            _mdisp  = safe_minute_disp(clock)
            team_id = item.get("team", {}).get("id", "")
            parts   = item.get("participants", [])
            player  = extract_athlete(parts, 0)
            assist  = extract_athlete(parts, 1)
            uid     = str(item.get("id", f"sp_{minute}_{player}"))
            add_event(ev_type, minute, team_id, player, assist, uid, minute_disp=_mdisp)
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
    # Import lazy: PIL e Playwright servono solo qui. Così il workflow di
    # keep-alive Canva (ONLY_REFRESH_TOKEN) può girare senza installarli.
    from PIL import Image
    from playwright.sync_api import sync_playwright

    # ── Kit maglia + colori dal campo 'uniform' ESPN (cascata fallback) ──
    # boxscore.teams → uniform reale (kit + colore indossato in campo)
    # competitors    → fallback colori brand (team.color / alternateColor)
    try:
        _competitors = data_espn["header"]["competitions"][0]["competitors"]
    except Exception:
        _competitors = []
    _boxscore_teams = (data_espn.get("boxscore") or {}).get("teams", [])

    # La logica classica (campionato/coppa/amichevole) resta come fallback
    # nel caso in cui il campo uniform non sia disponibile.
    _fallback_kit = determina_kit(home_id, away_id, league_slug, league_name)

    _kit_result = kit_analyzer.analizza(
        home_name      = home_name,
        away_name      = away_name,
        home_id        = home_id,
        away_id        = away_id,
        league_name    = league_name,
        competitors    = _competitors,
        boxscore_teams = _boxscore_teams,
        fallback_kit   = _fallback_kit,
    )
    juve_kit   = _kit_result["kit"]
    home_color = _kit_result["home_color"]
    away_color = _kit_result["away_color"]
    print(
        f"[{now_it()}] 🎨 Kit grafica stats: {juve_kit} "
        f"| {home_name}: {home_color} / {away_name}: {away_color} "
        f"(lega: {league_name} / {league_slug or 'n.d.'})"
    )

    # Logo Juve in base al kit:
    #   home / away    → logo nero (SVG, 2020)
    #   third / default → icona bianca quadrata (PNG, 2017)
    JUVE_LOGO_BLACK = "https://upload.wikimedia.org/wikipedia/commons/e/ed/Juventus_FC_-_logo_black_%28Italy%2C_2020%29.svg"
    JUVE_LOGO_WHITE = "https://upload.wikimedia.org/wikipedia/commons/9/99/Juventus_FC_2017_squared_icon_%28white%29.png"
    JUVE_LOGO_GOLD  = "https://gist.githubusercontent.com/Tommaso20BW/86db1c7a3581f15150f157c1fa572047/raw/fcb8706fea43a1e015da2d5ae4ff3e8b651ec235/juve_thid.png"

    if juve_kit in ("home", "away"):
        juve_logo = JUVE_LOGO_BLACK
    elif juve_kit == "third":
        juve_logo = JUVE_LOGO_GOLD
    else:
        juve_logo = JUVE_LOGO_WHITE
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
    pass_h   = g("home", "totalPasses",     "totalpasses",     fallback="0")
    pass_a   = g("away", "totalPasses",     "totalpasses",     fallback="0")
    passpct_h = fmt_pct(g("home", "passPct", "passpct",        fallback="0"))
    passpct_a = fmt_pct(g("away", "passPct", "passpct",        fallback="0"))

    stats_mappate = [
        ("Possesso palla",      pos_h,      pos_a,      bp_perc),
        ("Tiri in porta",       sot_h,      sot_a,      perc(sot_h,      sot_a)),
        ("Tiri",                shots_h,    shots_a,    perc(shots_h,    shots_a)),
        ("Corner",              corner_h,   corner_a,   perc(corner_h,   corner_a)),
        ("Fuorigioco",          offside_h,  offside_a,  perc(offside_h,  offside_a)),
        ("Falli",               falli_h,    falli_a,    perc(falli_h,    falli_a)),
        ("Ammoniti",            gialli_h,   gialli_a,   perc(gialli_h,   gialli_a)),
        ("Espulsi",             rossi_h,    rossi_a,    perc(rossi_h,    rossi_a)),
        ("Parate",              saves_h,    saves_a,    perc(saves_h,    saves_a)),
        ("Passaggi totali",     pass_h,     pass_a,     perc(pass_h,     pass_a)),
        ("Precisione passaggi", passpct_h,  passpct_a,  perc(
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

    # Genera override CSS per il tema default:
    # i colori dei bagliori e delle barre diventano i colori reali delle maglie.
    # Per home/away/third i temi CSS hardcoded restano invariati.
    if juve_kit == "default":
        _home_dark = kit_analyzer.darken(home_color)
        _away_dark = kit_analyzer.darken(away_color)
        _dynamic_style = (
            f"\nbody.kit-default {{\n"
            f"  --body-bg1:   {kit_analyzer.darken(home_color, 0.25)};\n"
            f"  --body-bg2:   {kit_analyzer.darken(away_color, 0.25)};\n"
            f"  --body-glow1: {home_color}4D;\n"
            f"  --body-glow2: {away_color}38;\n"
            f"  --bar-juve1:  {home_color};\n"
            f"  --bar-juve2:  {_home_dark};\n"
            f"  --bar-opp1:   {away_color};\n"
            f"  --bar-opp2:   {_away_dark};\n"
            f"}}"
        )
    else:
        _dynamic_style = ""

    # Determina il tema maglia (home / away / third / default)
    html_content = (
        template
        .replace("{JUVE_KIT}",       juve_kit)
        .replace("{DYNAMIC_STYLE}",  _dynamic_style)
        .replace("{LEAGUE_NAME}",    esc(league_name.upper()))
        .replace("{BADGE_LABEL}",    badge_label)
        .replace("{H_LOGO}",         h_logo)
        .replace("{HOME_NAME}",      home_name)
        .replace("{SCORE_BLOCK}",    score_block_html)
        .replace("{A_LOGO}",         a_logo)
        .replace("{AWAY_NAME}",      away_name)
        .replace("{ROWS_HTML}",      rows_html)
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
        page.screenshot(path=path_raw_png, clip={"x": 0, "y": 0, "width": 1620, "height": 2160}, omit_background=False)
        browser.close()

    # home/away → texture scura; third → texture gold; default → texture chiara
    texture_file = {
        "home":  "texture_black.png",
        "away":  "texture_black.png",
        "third": "texture_gold.png",
    }.get(juve_kit, "texture_white.png")
    if os.path.exists(texture_file):
        try:
            base_img = Image.open(path_raw_png).convert("RGBA")
            texture  = Image.open(texture_file).convert("RGBA").resize(base_img.size, Image.Resampling.LANCZOS)
            Image.alpha_composite(base_img, texture).convert("RGB").save(path_final_png, "PNG")
            print(f"[{now_it()}] 🎨 Texture applicata: {texture_file}")
            return path_final_png
        except Exception as e:
            print(f"[{now_it()}] ⚠️  Errore texture stats: {e}")

    return path_raw_png

# ==============================================================================
# ESPN API
# ==============================================================================
def trova_partita_oggi(team_id: str):
    # ESPN archivia le partite secondo l'orario US Eastern, non UTC: le gare serali
    # americane (es. amichevoli "Road to 26") restano sul giorno locale anche quando
    # in UTC è gia il giorno dopo. Calcolando "oggi" sull'orologio di ESPN la partita
    # rientra sempre nella ricerca finche e in diretta — niente cuscinetto su ieri.
    now_espn      = datetime.now(ESPN_TZ)
    dates_to_try  = [
        now_espn.strftime("%Y%m%d"),                        # "oggi" secondo ESPN
        (now_espn + timedelta(days=1)).strftime("%Y%m%d"),  # "domani" secondo ESPN
    ]
    print(f"[{now_it()}] 🔍 Cerco partita per team_id={team_id}...")

    for date_str in dates_to_try:
        for slug in LEAGUE_SLUGS:
            url = f"{ESPN_BASE}/{slug}/scoreboard"
            try:
                r = SESSION.get(url, params={"dates": date_str}, timeout=10)
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
        r = SESSION.get(f"{ESPN_BASE}/{league_slug}/summary",
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

        # NB: HT_ET va controllato PRIMA dell'intervallo generico, perché
        # "STATUS_HALFTIME_ET" contiene anche la sottostringa "HALFTIME" e
        # verrebbe altrimenti scambiato per l'intervallo dei tempi regolamentari.
        if "EXTRA_TIME_HALF" in name or "HALFTIME_ET" in name:
            return "HT_ET", 105
        if "HALFTIME" in name or "HALF_TIME" in name:
            # Intervallo generico: il periodo distingue quale dei due è.
            if period >= 3:
                return "HT_ET", 105
            return "HT", 45
        if "PENALTY" in name or "SHOOTOUT" in name:
            return "PEN", elapsed
        # Pausa tra fine supplementari e rigori (es. STATUS_END_OF_EXTRATIME).
        # Va controllata PRIMA del check generico "EXTRA" qui sotto, altrimenti
        # verrebbe mappata a "ET" e il bot crederebbe che si stia ancora giocando.
        if "END_OF_EXTRATIME" in name or "END_EXTRA" in name:
            return "BREAK_PEN", 120
        # Pausa tra fine regolamentari e inizio supplementari.
        if "END_OF_REGULATION" in name:
            return "BREAK_ET", 90
        if "EXTRA" in name or "OT" in name:
            return "ET", elapsed
        if "END_PERIOD" in name:
            # END_PERIOD è generico: il periodo dice QUALE pausa è.
            if period <= 1:
                return "HT", 45          # fine 1° tempo
            if period == 2:
                return "BREAK_ET", 90    # fine regolamentari (pausa pre-supplementari)
            if period == 3:
                return "HT_ET", 105      # intervallo tra i due supplementari
            return "BREAK_PEN", 120      # fine supplementari (pausa pre-rigori)
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


def _rigori_icone(data: dict, events: list, home_id: str, away_id: str,
                  home_name_raw: str = "", away_name_raw: str = ""):
    """Restituisce (home_icons, away_icons) della lotteria dei rigori.

    Preferisce data['shootout'] (fonte strutturata ESPN): è ordinata per
    battuta e attribuisce ogni calcio alla squadra giusta. Solo se assente
    ricade sugli eventi parsati, scartando i calci senza squadra attribuita
    (che altrimenti finirebbero per errore nel conteggio della trasferta).
    """
    home_icons, away_icons = [], []

    for team_shootout in (data.get("shootout") or []):
        try:
            t_id_raw = str(team_shootout.get("id", ""))
            t_name   = team_shootout.get("team", "")
            if t_id_raw:
                t_id = t_id_raw
            elif isinstance(t_name, str) and t_name:
                t_id = home_id if t_name.lower() == (home_name_raw or "").lower() else away_id
            else:
                continue
            if t_id == str(home_id):
                target = home_icons
            elif t_id == str(away_id):
                target = away_icons
            else:
                continue
            for kick in (team_shootout.get("shots") or team_shootout.get("shootoutAttempts", [])):
                did_score = kick.get("didScore", kick.get("scored", False))
                target.append(E_PEN_OK if did_score else E_PEN_KO)
        except Exception as e:
            print(f"[{now_it()}] ⚠️  Errore lettura shootout strutturato: {e}")

    if home_icons or away_icons:
        return home_icons, away_icons

    # Fallback: eventi parsati (commentary/keyEvents), in ordine di arrivo (seq)
    for e in sorted(events, key=lambda x: x.get("seq", 0)):
        if e["type"] not in ("shootout goal", "shootout miss", "shootout saved"):
            continue
        icon = E_PEN_OK if e["type"] == "shootout goal" else E_PEN_KO
        if e["team_id"] == str(home_id):
            home_icons.append(icon)
        elif e["team_id"] == str(away_id):
            away_icons.append(icon)
        # team_id sconosciuto → scartato: meglio un calcio in meno nel widget
        # che un calcio assegnato alla squadra sbagliata.
    return home_icons, away_icons


def _shootout_deciso(home_icons: list, away_icons: list) -> bool:
    """True se la lotteria dei rigori è matematicamente decisa, anche se
    ESPN non ha ancora aggiornato status.type.state a 'post' (può volerci
    diversi minuti dopo l'ultimo tiro — visto un ritardo di 7' su Svizzera-
    Colombia 2026: rigore decisivo segnato ma state ancora 'in').

    NB sui conteggi disuguali: quando a chiudere è la squadra che batte per
    PRIMA, l'ultimo tiro dell'altra non si batte proprio e i conteggi restano
    disuguali per sempre (es. 5 tiri vs 4). Va quindi accettato uno sbilancio
    di 1 tiro; oltre 1 il feed è incompleto e non ci si può fidare della
    matematica (tiri mancanti → falsi positivi)."""
    n_home, n_away = len(home_icons), len(away_icons)
    if n_home == 0 and n_away == 0:
        return False
    if abs(n_home - n_away) > 1:
        return False  # feed incompleto: mancano tiri, matematica inaffidabile
    home_goals = home_icons.count(E_PEN_OK)
    away_goals = away_icons.count(E_PEN_OK)
    if n_home <= 5 and n_away <= 5:
        # Entro i primi 5 tiri: decisa se il margine è incolmabile con i tiri
        # rimasti (copre anche 5-5 con punteggi diversi: zero tiri rimasti).
        home_left = 5 - n_home
        away_left = 5 - n_away
        return (home_goals > away_goals + away_left) or (away_goals > home_goals + home_left)
    # Oltre il 5°: sudden death, si decide solo a coppia di tiri completata
    # (il secondo tiratore batte sempre, quindi conteggi pari) con parità rotta.
    return n_home == n_away and home_goals != away_goals


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
    return esc(f"#{abbr(home_name)}{abbr(away_name)}")

# ==============================================================================
# CICLO PRINCIPALE
# ==============================================================================
def _schedule_stats(state: dict, momento: str, delay: int = 120) -> bool:
    """Programma l'invio della grafica stats `delay` secondi dopo il cambio di
    stato (HT / 2H_END / FT), senza bloccare il ciclo live. Ritorna True se è
    stata aggiunta una nuova programmazione."""
    if momento in state.get("sent_stats", []):
        return False
    pend = state.setdefault("pending_stats", [])
    if any(p.get("momento") == momento for p in pend):
        return False
    pend.append({"momento": momento, "due": int(time.time()) + delay})
    print(f"[{now_it()}] 🕑 Stats {momento} programmate tra {delay}s")
    return True


def _failpen_gia_inviato(state: dict, e: dict) -> bool:
    """Dedup rigori sbagliati tollerante alla correzione del minuto da parte
    di ESPN (es. 44' → 45'+1): stesso giocatore + stesso esito entro ±3'."""
    for rec in state.get("sent_failed_penalties", []):
        if isinstance(rec, str):
            # Retrocompatibilità con il vecchio formato stringa
            if rec == f"failpen_{e['minute']}_{e['player_name']}".replace(" ", "_"):
                return True
            continue
        if (rec.get("player") == e["player_name"]
                and rec.get("type") == e["type"]
                and abs(int(rec.get("minute", 0)) - e["minute"]) <= 3):
            return True
    return False


def avvia_ciclo_partita():
    team_id = str(TEAM_ID).strip()

    try:
        test_r = SESSION.get(f"{ESPN_BASE}/ita.1/scoreboard",
                              params={"dates": datetime.now(ESPN_TZ).strftime("%Y%m%d")}, timeout=10)
    except Exception as e:
        print(f"[{now_it()}] ⚠️  Test connettività API fallito: {e}")

    partita = trova_partita_oggi(team_id)
    if not partita:
        print(f"[{now_it()}] 📭 Nessun evento trovato per team_id={team_id}.")
        return

    event_id    = partita["event_id"]
    league_slug = partita["league_slug"]
    league_name = partita["league_name"]

    gist_ok, state = leggi_stato_da_gist()
    if not gist_ok:
        # Stato illeggibile per errore di rete/API: partire con uno stato
        # vergine rimanderebbe tutti i messaggi già pubblicati. Meglio uscire.
        print(f"[{now_it()}] 🛑 Stato Gist illeggibile dopo i retry — esco per evitare messaggi duplicati")
        sys.exit(1)
    if state is None or state.get("event_id") != event_id:
        state = {
            "event_id":               event_id,
            "league_slug":            league_slug,
            "league_name":            league_name,
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
            "pending_stats":          [],
        }
    if isinstance(state.get("sent_subs"), list):
        state["sent_subs"] = {}
    # La lega va sempre tenuta aggiornata nel Gist (anche su stati ripresi da
    # versioni precedenti): serve ai bot esterni che leggono la partita dal Gist.
    state["league_slug"] = league_slug
    state["league_name"] = league_name
    # Retrocompatibilità con stati salvati da versioni precedenti
    state.setdefault("cancel_msg_id", None)
    state.setdefault("pending_stats", [])
    state.setdefault("sent_stats", [])
    state.setdefault("sent_failed_penalties", [])

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
            home_name = esc(translate_team(home_name_raw))
            away_name = esc(translate_team(away_name_raw))
            score_str = build_score_str(home_name, away_name, g_home, g_away)
            hashtag   = build_hashtag(home_name_raw, away_name_raw)
            e_comp    = get_league_emoji(league_slug)

            # --- Partita GIÀ conclusa all'avvio → spegni subito, non fare nulla ---
            comp_state_espn = (
                data.get("header", {}).get("competitions", [{}])[0]
                    .get("status", {}).get("type", {}).get("state", "")
            )
            match_finished  = comp_state_espn == "post" or status in ("FT", "AET")
            never_processed = (
                not state.get("sent_periods")
                and not state.get("goal_messages")
                and state.get("goals_detected", 0) == 0
            )
            if match_finished and never_processed:
                print(f"[{now_it()}] ⏹️ Partita già conclusa all'avvio "
                      f"({home_name} {g_home}-{g_away} {away_name}) — nessun messaggio inviato, bot spento")
                sys.exit(0)

            events = parse_events(data, home_name_raw, away_name_raw, home_id, away_id)

            if "_intro_logged" not in state:
                print(f"[{now_it()}] 🚀 PARTITA TROVATA: {league_name} | {home_name} vs {away_name} | event_id={event_id}")
                for raw, translated in ((home_name_raw, home_name), (away_name_raw, away_name)):
                    t = translate_team(raw)
                    in_map = bool(TEAM_MAP.get(raw) or any(k.lower() == raw.lower() for k in TEAM_MAP))
                    if raw != t:
                        print(f"[{now_it()}] 📋 Traduzione: '{raw}' → '{esc(t)}'")
                    elif not in_map:
                        print(f"[{now_it()}] 📋 '{raw}' non in teams.json — usato nome ESPN")
                state["_intro_logged"] = True


            _now_ts = int(time.time())
            _log_key = f"{status}_{elapsed}_{g_home}_{g_away}"
            if status != "NS" and (state.get("_last_log_key") != _log_key or (_now_ts - state.get("_last_log_ts", 0)) >= 60):
                print(f"[{now_it()}] 📡 {status} {elapsed}' | {home_name} {g_home}-{g_away} {away_name}")
                state["_last_log_key"] = _log_key
                state["_last_log_ts"] = _now_ts

            # --- Invio stats programmato (2 min dopo il cambio di stato) ---
            # Coda non bloccante: durante l'attesa il bot continua a rilevare
            # gol, cambi e cartellini. Persistita nel Gist → sopravvive ai crash.
            for _ps in list(state.get("pending_stats", [])):
                if _now_ts < int(_ps.get("due", 0)):
                    continue
                _momento = _ps.get("momento")
                state["pending_stats"].remove(_ps)
                state_changed = True
                if not _momento or _momento in state.get("sent_stats", []):
                    continue
                data_fresh = fetch_evento(event_id, league_slug) or data
                png_path = recupera_e_genera_stats_html(data_fresh, home_id, away_id,
                                                         home_name, away_name, g_home, g_away,
                                                         _momento, league_name, league_slug=league_slug)
                if send_telegram_stats_photo(png_path, _momento, f"{e_comp} {hashtag}"):
                    print(f"[{now_it()}] 📊 STATS {_momento} → foto Telegram inviata")
                    state["sent_stats"].append(_momento)
                    salva_stato_su_gist(state)
                else:
                    # Invio non riuscito: rimetto in coda per un nuovo tentativo
                    # a breve, invece di segnare le stats come inviate e perderle.
                    print(f"[{now_it()}] ⚠️  Invio STATS {_momento} non riuscito — riprovo tra 30s")
                    state.setdefault("pending_stats", []).append({
                        "momento": _momento,
                        "due": _now_ts + 30,
                    })
                    salva_stato_su_gist(state)

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

            # --- Retry GOAL ANNULLATO non riuscito in un ciclo precedente ---
            # Lo stato del punteggio è già stato aggiornato quando l'annullamento è
            # stato rilevato, quindi qui NON possiamo contare su una ri-rilevazione
            # naturale: il testo del messaggio resta in coda finché l'invio non va a buon fine.
            if state.get("pending_goal_annullato"):
                _retry_cancel_id = send_telegram_get_id(state["pending_goal_annullato"])
                if _retry_cancel_id:
                    print(f"[{now_it()}] 📺 GOAL ANNULLATO (retry) → Telegram inviato")
                    state["cancel_msg_id"] = _retry_cancel_id
                    state["pending_goal_annullato"] = None
                    state_changed = True
                else:
                    print(f"[{now_it()}] ⚠️  Invio GOAL ANNULLATO non riuscito — riprovo al prossimo ciclo")

            # --- Inizio primo tempo ---
            if status == "1H" and "1H" not in state["sent_periods"]:
                msg_id = send_telegram_get_id(f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{home_name} - {away_name}\n\n{e_comp} {hashtag}")
                if msg_id:
                    print(f"[{now_it()}] ⚡️ INIZIO PARTITA → Telegram inviato")
                    state["sent_periods"].append("1H")
                    salva_stato_su_gist(state)
                    state_changed = True
                else:
                    print(f"[{now_it()}] ⚠️  Invio INIZIO PARTITA non riuscito — riprovo al prossimo ciclo")

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

                    msg_id = send_telegram_get_id(goal_text)
                    if not msg_id:
                        # Invio non riuscito: interrompo il recupero. Annullo
                        # l'incremento di questo gol (non annunciato) e lascio che sia
                        # il rilevamento live a riprovare i gol rimanenti.
                        print(f"[{now_it()}] ⚠️  CATCHUP invio non riuscito {ge['minute']}\' {home_name} {ch}-{ca} {away_name} — riprovo col rilevamento live")
                        if ge["team_id"] == home_id:
                            ch -= 1
                        else:
                            ca -= 1
                        break
                    print(f"[{now_it()}] ⚽️  CATCHUP GOAL {ge['minute']}\' {home_name} {ch}-{ca} {away_name} → Telegram inviato")
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

                # Avanza solo fino ai gol realmente annunciati (ch/ca): se un invio
                # è fallito, i gol mancanti li recupera il rilevamento live.
                state["goals_detected"]  = ch + ca
                state["prev_home_goals"] = ch
                state["prev_away_goals"] = ca
                state_changed = True

            # --- Fine primo tempo ---
            if status == "HT":
                if "HT" not in state["sent_periods"]:
                    msg_id = send_telegram_get_id(f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                    if msg_id:
                        print(f"[{now_it()}] 🏁 FINE 1° TEMPO ({home_name} {g_home}-{g_away} {away_name}) → Telegram inviato")
                        state["sent_periods"].append("HT")
                        _schedule_stats(state, "HT")
                        salva_stato_su_gist(state)
                        state_changed = True
                    else:
                        print(f"[{now_it()}] ⚠️  Invio FINE 1° TEMPO non riuscito — riprovo al prossimo ciclo")
                elif "HT" not in state["sent_stats"]:
                    # Recovery: messaggio HT già inviato in un run precedente ma
                    # stats mai partite (es. crash) → riprogramma
                    if _schedule_stats(state, "HT"):
                        state_changed = True

            # --- Inizio secondo tempo ---
            if status == "2H" and "2H" not in state["sent_periods"]:
                msg_id = send_telegram_get_id(f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                if msg_id:
                    print(f"[{now_it()}] ⚡️ INIZIO 2° TEMPO → Telegram inviato")
                    state["sent_periods"].append("2H")
                    salva_stato_su_gist(state)
                    state_changed = True
                else:
                    print(f"[{now_it()}] ⚠️  Invio INIZIO 2° TEMPO non riuscito — riprovo al prossimo ciclo")

            # --- Fine regolamentari → supplementari ---
            # Fotografie dello stato PRIMA che i blocchi qui sotto lo modifichino:
            # servono a garantire che due messaggi consecutivi (es. FINE
            # REGOLAMENTARI e INIZIO 1T SUPPLEMENTARE) non partano mai nello
            # stesso ciclo di polling, ma ad almeno un ciclo (~6s) di distanza.
            _2h_end_gia_inviato  = "2H_END"  in state["sent_periods"]
            _1et_end_gia_inviato = "1ET_END" in state["sent_periods"]

            # Caso normale: ESPN espone la pausa (END_OF_REGULATION / END_PERIOD
            # con period=2) → il messaggio parte DURANTE l'intervallo, come in TV.
            # Richiede 2 avvistamenti consecutivi (~12s) per non scattare su un
            # eventuale END_PERIOD transitorio prima del fischio finale di una
            # partita senza supplementari.
            if status == "BREAK_ET" and "2H_END" not in state["sent_periods"] and "FT" not in state["sent_periods"]:
                state["_break_et_seen"] = state.get("_break_et_seen", 0) + 1
                if state["_break_et_seen"] >= 2:
                    msg_id = send_telegram_get_id(f"<b>FINE REGOLAMENTARI {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                    if msg_id:
                        print(f"[{now_it()}] 🏁 FINE REGOLAMENTARI ({home_name} {g_home}-{g_away} {away_name}) → Telegram inviato")
                        state["sent_periods"].append("2H_END")
                        _schedule_stats(state, "2H_END")
                        salva_stato_su_gist(state)
                        state_changed = True
                    else:
                        print(f"[{now_it()}] ⚠️  Invio FINE REGOLAMENTARI non riuscito — riprovo al prossimo ciclo")
            elif status != "BREAK_ET":
                state["_break_et_seen"] = 0

            # Recovery: ESPN non ha mai esposto la pausa (o il bot era giù) e lo
            # status è già ET/PEN/AET → invia ora. L'INIZIO 1T SUPPLEMENTARE
            # partirà comunque al ciclo successivo grazie a _2h_end_gia_inviato.
            if status in ("ET", "PEN", "AET") and "2H_END" not in state["sent_periods"] and "FT" not in state["sent_periods"]:
                msg_id = send_telegram_get_id(f"<b>FINE REGOLAMENTARI {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                if msg_id:
                    print(f"[{now_it()}] 🏁 FINE REGOLAMENTARI ({home_name} {g_home}-{g_away} {away_name}) → Telegram inviato")
                    state["sent_periods"].append("2H_END")
                    if status == "ET":
                        _schedule_stats(state, "2H_END")
                    salva_stato_su_gist(state)
                    state_changed = True
                else:
                    print(f"[{now_it()}] ⚠️  Invio FINE REGOLAMENTARI non riuscito — riprovo al prossimo ciclo")
            elif status == "ET" and "2H_END" in state["sent_periods"] and "2H_END" not in state["sent_stats"]:
                # Recovery: stats di fine regolamentari mai partite dopo un crash
                if _schedule_stats(state, "2H_END"):
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
                                     ("HALFTIME", "HALF_TIME", "HT_ET", "EXTRA_TIME_HALF", "END_PERIOD"))
                is_second_et = (et_period >= 4 or (elapsed >= 106 and et_period >= 3))

                # Gate _2h_end_gia_inviato: se FINE REGOLAMENTARI è partito in
                # QUESTO ciclo, l'inizio supplementari aspetta il prossimo (~6s).
                if (_2h_end_gia_inviato and "1ET_START" not in state["sent_periods"]
                        and not is_et_halftime and not is_second_et):
                    if send_telegram_get_id(f"<b>INIZIO 1T SUPPLEMENTARE {E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}"):
                        state["sent_periods"].append("1ET_START")
                        salva_stato_su_gist(state)
                        state_changed = True

                if (is_et_halftime or is_second_et) and "1ET_END" not in state["sent_periods"]:
                    if send_telegram_get_id(f"<b>FINE 1T SUPPLEMENTARE {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}"):
                        state["sent_periods"].append("1ET_END")
                        salva_stato_su_gist(state)
                        state_changed = True

                # Gate _1et_end_gia_inviato: stessa logica, FINE 1T SUPPLEMENTARE
                # e INIZIO 2T SUPPLEMENTARE non partono mai nello stesso ciclo.
                if is_second_et and _1et_end_gia_inviato and "2ET_START" not in state["sent_periods"]:
                    if send_telegram_get_id(f"<b>INIZIO 2T SUPPLEMENTARE {E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}"):
                        state["sent_periods"].append("2ET_START")
                        salva_stato_su_gist(state)
                        state_changed = True

            # --- Intervallo supplementari ---
            if status == "HT_ET":
                if "1ET_START" not in state["sent_periods"]:
                    state["sent_periods"].append("1ET_START")
                    state_changed = True
                if "1ET_END" not in state["sent_periods"]:
                    if send_telegram_get_id(f"<b>FINE 1T SUPPLEMENTARE {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}"):
                        state["sent_periods"].append("1ET_END")
                        salva_stato_su_gist(state)
                        state_changed = True

            # --- Pausa fine supplementari → rigori ---
            # ESPN espone la pausa pre-rigori (END_OF_EXTRATIME / END_PERIOD con
            # period=4): FINE 2T SUPPLEMENTARE parte QUI, durante l'intervallo,
            # invece che insieme al primo aggiornamento della lotteria.
            if status == "BREAK_PEN":
                if "1ET_END" not in state["sent_periods"]:
                    # Backfill silenzioso: se il bot non ha mai visto l'intervallo
                    # dei supplementari, non ha senso annunciarlo ora in ritardo.
                    state["sent_periods"].append("1ET_END")
                    state_changed = True
                if "ET_END_PENS" not in state["sent_periods"]:
                    _pens_intro_ok = True
                    if "2ET_START" in state["sent_periods"] or "1ET_START" in state["sent_periods"]:
                        _pens_intro_ok = send_telegram_get_id(f"<b>FINE 2T SUPPLEMENTARE {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}") is not None
                    if _pens_intro_ok:
                        state["sent_periods"].append("ET_END_PENS")
                        salva_stato_su_gist(state)
                        state_changed = True

            # --- Rigori ---
            if status == "PEN":
                if "ET_END_PENS" not in state["sent_periods"]:
                    _pens_intro_ok = True
                    if "2ET_START" in state["sent_periods"] or "1ET_START" in state["sent_periods"]:
                        _pens_intro_ok = send_telegram_get_id(f"<b>FINE 2T SUPPLEMENTARE {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}") is not None
                    if _pens_intro_ok:
                        state["sent_periods"].append("ET_END_PENS")
                        salva_stato_su_gist(state)
                        state_changed = True

                home_pen_icons, away_pen_icons = _rigori_icone(data, events, home_id, away_id,
                                                               home_name_raw, away_name_raw)

                total_kicks = len(home_pen_icons) + len(away_pen_icons)
                if total_kicks > state["penalties_count"]:
                    _pen_msg_ok = send_telegram_get_id(
                        f"<b>RIGORI {E_KICK}</b>\n\n"
                        f"{home_name}: " + ("".join(home_pen_icons) if home_pen_icons else "—") + "\n"
                        f"{away_name}: " + ("".join(away_pen_icons) if away_pen_icons else "—") + f"\n\n{e_comp} {hashtag}"
                    )
                    if _pen_msg_ok:
                        state["penalties_count"] = total_kicks
                        state_changed = True

            # --- Rilevamento goal ---
            # IMPORTANTE: questo blocco sta PRIMA di is_finished (fix applicato).
            # Se un gol arriva nello stesso ciclo in cui la partita passa a FT,
            # va annunciato qui prima che il blocco is_finished chiami sys.exit(0)
            # e spenga il bot — altrimenti il gol (es. 4-1 al 90') non parte mai.
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

                goal_events = [e for e in events
                               if e["type"] in ("goal", "own goal", "penalty goal")]

                # Quale squadra ha segnato.
                # Di norma lo si capisce dall'aumento rispetto all'ultimo punteggio
                # annunciato (prev_*). Se però lo stato salvato è incoerente
                # (prev_* gia avanti, p.es. dopo un riavvio del job), questi confronti
                # fallirebbero e il gol verrebbe perso in silenzio: in quel caso si
                # ricava il marcatore dall'ultimo evento del feed ESPN.
                if g_home > prev_home:
                    scoring_tid = home_id
                elif g_away > prev_away:
                    scoring_tid = away_id
                else:
                    _gevs = sorted(goal_events, key=lambda x: x["minute"])
                    if _gevs:
                        _last_ev = _gevs[-1]
                        scoring_tid = _last_ev["team_id"]
                        if _last_ev["type"] == "own goal":
                            scoring_tid = away_id if _last_ev["team_id"] == home_id else home_id
                    else:
                        scoring_tid = home_id if g_home >= g_away else away_id
                    print(f"[{now_it()}] ⚠️  Stato punteggio incoerente (prev {prev_home}-{prev_away}, ora {g_home}-{g_away}) — marcatore dedotto dal feed")

                # Flag: True solo se il gol è stato realmente annunciato (ora o in passato).
                # Il contatore avanzerà SOLO in quel caso.
                goal_announced = False

                if scoring_tid:
                    team_goals = [e for e in goal_events if e["type"] != "own goal" and e["team_id"] == scoring_tid]
                    own_goals_vs = [e for e in goal_events if e["type"] == "own goal" and e["team_id"] != scoring_tid]
                    candidates = sorted(team_goals + own_goals_vs, key=lambda x: (x["minute"], x.get("seq", 0)))

                    expected_count = g_home if scoring_tid == home_id else g_away

                    last = candidates[expected_count - 1] if len(candidates) >= expected_count else (candidates[-1] if candidates else None)

                    if last:
                        player_name = last.get("player_name", "")
                        assist_name = last.get("assist_name", "")
                        goal_minute = last.get("minute_disp", str(last.get("minute", elapsed)))
                        goal_type   = last.get("type", "goal")
                    else:
                        # Feed ESPN incompleto: gol rilevato dal punteggio ma nessun
                        # evento marcatore associato. Annuncio comunque per non bloccare
                        # il ciclo (altrimenti goals_detected non avanza mai).
                        print(f"[{now_it()}] ⚠️  Gol dal punteggio senza marcatore nel feed — invio senza marcatore")
                        player_name = ""
                        assist_name = ""
                        goal_minute = elapsed
                        goal_type   = "goal"

                    actual_scoring_tid = scoring_tid

                    if player_name:
                        ps = fmt_player(player_name)
                        if goal_type == "own goal":
                            ps += " (Autogol)"
                            actual_scoring_tid = away_id if last["team_id"] == home_id else home_id
                        elif goal_type == "penalty goal":
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

                    goal_text = f"<b>GOAL · {goal_minute}' {E_MIC}</b>\n\n{goal_score}\n{scorer_line}{assist_line}\n{e_comp} {hashtag}"
                    goal_key = f"{g_home}_{g_away}"

                    if state.get("goal_messages", {}).get(goal_key, {}).get("msg_id"):
                        # Gol già annunciato davvero in passato: duplicato corretto,
                        # il contatore può avanzare.
                        goal_announced = True
                    else:
                        _scorer_log = f" {fmt_player(player_name)}" if player_name else " (marcatore in attesa)"
                        _assist_log = f" | assist: {fmt_player(assist_name)}" if assist_name and assist_name != player_name else ""
                        msg_id = send_telegram_get_id(goal_text)
                        if msg_id:
                            state.setdefault("goal_messages", {})[goal_key] = {
                                "msg_id":    msg_id,
                                "scorer":    player_name,
                                "assist":    assist_name,
                                "minute":    goal_minute,
                                "type":      goal_type,
                                "home_n":    home_name,
                                "away_n":    away_name,
                                "g_home":    g_home,
                                "g_away":    g_away,
                                "home_id":   home_id,
                                "away_id":   away_id,
                                "score_tid": actual_scoring_tid,
                            }
                            state_changed = True
                            goal_announced = True
                            print(f"[{now_it()}] ⚽️  GOAL{_scorer_log}{_assist_log} ({home_name} {g_home}-{g_away} {away_name}) → Telegram inviato")
                        else:
                            # Invio NON riuscito: non avanzo il contatore così al ciclo
                            # successivo il bot rientra qui e riprova (il gol non si perde).
                            print(f"[{now_it()}] ⚠️  Invio GOAL non riuscito ({home_name} {g_home}-{g_away} {away_name}) — riprovo al prossimo ciclo")

                # Il contatore avanza SOLO se il gol è stato davvero annunciato.
                # Se l'invio è fallito (o scoring_tid assente), lo stato resta indietro
                # e il gol verrà ritentato, invece di sparire.
                if goal_announced:
                    state["goals_detected"]  = total_goals_now
                    state["prev_home_goals"] = g_home
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
                    cancel_text = f"<b>GOAL ANNULLATO {E_CANCEL}</b>\n\n{score_str}\n\n{e_comp} {hashtag}"
                    cancel_msg_id = send_telegram_get_id(cancel_text)
                    if cancel_msg_id:
                        print(f"[{now_it()}] 📺 GOAL ANNULLATO → Telegram inviato")
                        state["cancel_msg_id"] = cancel_msg_id
                    else:
                        # Invio non riuscito: lo score sotto va comunque aggiornato (è
                        # già confermato), ma il messaggio resta in coda e viene
                        # ritentato a ogni ciclo finché non va a buon fine.
                        print(f"[{now_it()}] ⚠️  Invio GOAL ANNULLATO non riuscito — riprovo al prossimo ciclo")
                        state["pending_goal_annullato"] = cancel_text

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

            # --- Fine partita ---
            comp_state_espn = (
                data.get("header", {}).get("competitions", [{}])[0]
                    .get("status", {}).get("type", {}).get("state", "")
            )
            _pen_deciso = False
            if status == "PEN" and comp_state_espn != "post":
                _hp_check, _ap_check = _rigori_icone(data, events, home_id, away_id,
                                                      home_name_raw, away_name_raw)
                _tot_check = len(_hp_check) + len(_ap_check)
                if (_shootout_deciso(_hp_check, _ap_check)
                        and state.get("penalties_count", 0) >= _tot_check):
                    # Gate penalties_count: l'ultimo messaggio RIGORI deve essere
                    # stato DAVVERO consegnato prima di chiudere (se l'invio è
                    # fallito il contatore è indietro → si riprova al prossimo
                    # ciclo, il messaggio non va perso con lo spegnimento).
                    # Doppia conferma (~12s) contro dati ESPN transitoriamente
                    # sballati: la chiusura anticipata è irreversibile.
                    state["_pen_deciso_seen"] = state.get("_pen_deciso_seen", 0) + 1
                    if state["_pen_deciso_seen"] >= 2:
                        _pen_deciso = True
                        print(f"[{now_it()}] 🏁 Rigori matematicamente decisi "
                              f"({_hp_check.count(E_PEN_OK)}-{_ap_check.count(E_PEN_OK)}) — "
                              f"non attendo lo state 'post' di ESPN")
                else:
                    state["_pen_deciso_seen"] = 0

            is_finished = (
                status in ("FT", "AET") or
                (status == "PEN" and comp_state_espn == "post") or
                (status == "PEN" and _pen_deciso)
            )
            if is_finished:
                # Se un gol è ancora in sospeso (invio fallito per timeout in
                # QUESTO ciclo, il blocco gol gira prima di qui) NON chiudere subito:
                # ritenta qualche ciclo così il messaggio del gol non si perde.
                # Cap di sicurezza per non restare appesi se Telegram è giù a lungo.
                _goal_pending = (
                    "FT" not in state["sent_periods"]
                    and state.get("goals_detected", 0) < (g_home + g_away)
                )
                if _goal_pending:
                    _retries = state.get("ft_pending_goal_retries", 0)
                    if _retries < 5:
                        state["ft_pending_goal_retries"] = _retries + 1
                        state_changed = True
                        print(f"[{now_it()}] ⏳ Partita finita ma gol in sospeso "
                              f"({state.get('goals_detected', 0)}/{g_home + g_away}) — "
                              f"ritento ({_retries + 1}/5) prima di chiudere")
                        time.sleep(sleep_time)
                        continue
                    print(f"[{now_it()}] ⚠️  Gol in sospeso non inviato dopo 5 tentativi — chiudo comunque")

                if "FT" not in state["sent_periods"]:
                    # Raggruppa i gol per squadra e per giocatore (con suffisso tipo)
                    # Struttura: { team_id: { "chiave_giocatore": {"label": str, "minutes": [int]} } }
                    from collections import OrderedDict
                    def _build_scorers_list(team_id):
                        """Restituisce lista di stringhe tipo '25', 43' B. Varga' per una squadra."""
                        grouped = OrderedDict()  # chiave: (player_name, suffix)
                        for e in events:
                            if e["type"] not in ("goal", "own goal", "penalty goal"):
                                continue
                            if e["team_id"] != team_id:
                                continue
                            ps = fmt_player(e["player_name"])
                            if e["type"] == "own goal":
                                suffix = " (Autogol)"
                            else:
                                suffix = ""          # i rigori contano come gol normali
                            key = (ps, suffix)
                            if key not in grouped:
                                grouped[key] = []
                            # Usa minute_disp per preservare il formato recupero
                            # (es. "90+6" invece di 96). Fallback all'intero.
                            grouped[key].append(e.get("minute_disp") or str(e["minute"]))
                        result = []
                        for (ps, suffix), minutes in grouped.items():
                            mins_str = ", ".join(f"{m}'" for m in minutes)
                            result.append(f"{mins_str} {ps}{suffix}")
                        return result

                    home_scorers = _build_scorers_list(home_id)
                    away_scorers = _build_scorers_list(away_id)

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
                        _hp_icons, _ap_icons = _rigori_icone(data, events, home_id, away_id,
                                                             home_name_raw, away_name_raw)
                        home_pen_goals = _hp_icons.count(E_PEN_OK)
                        away_pen_goals = _ap_icons.count(E_PEN_OK)
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
                        foto = get_canva_image(canva_token) if canva_token else None
                        ft_sent = send_telegram_with_photo(msg_finale, foto)
                    else:
                        ft_sent = send_telegram_get_id(msg_finale) is not None

                    if not ft_sent:
                        print(f"[{now_it()}] ⚠️  Invio FINE PARTITA non riuscito — riprovo al prossimo ciclo")
                        time.sleep(sleep_time)
                        continue

                    print(f"[{now_it()}] 🏁 FINE PARTITA ({home_name} {g_home}-{g_away} {away_name}) → Telegram inviato")
                    # Persisti SUBITO: se il bot muore durante l'attesa delle stats,
                    # al riavvio il messaggio finale non verrà reinviato.
                    state["sent_periods"].append("FT")
                    salva_stato_su_gist(state)
                    state_changed = True

                # --- Stats fine partita: 2 minuti dopo il messaggio finale ---
                # (attesa "a fette": la partita è finita, non c'è altro da monitorare)
                if "FT" not in state["sent_stats"]:
                    print(f"[{now_it()}] 🕑 Attendo 120s prima delle stats FT...")
                    for _ in range(24):
                        time.sleep(5)
                    data_fresh = fetch_evento(event_id, league_slug) or data
                    _ftp_h, _ftp_a = _rigori_icone(data_fresh, events, home_id, away_id,
                                                   home_name_raw, away_name_raw)
                    ft_pen_home = _ftp_h.count(E_PEN_OK)
                    ft_pen_away = _ftp_a.count(E_PEN_OK)
                    png_path = recupera_e_genera_stats_html(data_fresh, home_id, away_id,
                                                             home_name, away_name, g_home, g_away,
                                                             "FT", league_name, league_slug=league_slug,
                                                             pen_home=ft_pen_home, pen_away=ft_pen_away)
                    # Il bot sta per spegnersi: niente "prossimo ciclo" che possa
                    # ritentare da solo, quindi ritento qui sul posto prima di
                    # rinunciare, invece di segnare le stats come inviate a prescindere.
                    ft_stats_ok = False
                    for _attempt in range(5):
                        if send_telegram_stats_photo(png_path, "FT", f"{e_comp} {hashtag}"):
                            ft_stats_ok = True
                            break
                        print(f"[{now_it()}] ⚠️  Invio STATS FINE PARTITA non riuscito (tentativo {_attempt + 1}/5) — riprovo tra 10s")
                        time.sleep(10)
                    if ft_stats_ok:
                        print(f"[{now_it()}] 📊 STATS FINE PARTITA → foto Telegram inviata")
                        state["sent_stats"].append("FT")
                    else:
                        print(f"[{now_it()}] ❌ Invio STATS FINE PARTITA fallito dopo 5 tentativi — proseguo comunque con lo spegnimento")
                    salva_stato_su_gist(state)
                    state_changed = True

                state["_reset_done"] = True
                resetta_gist()
                print(f"[{now_it()}] 🏆 LIVE SCORE TERMINATO ({home_name} {g_home}-{g_away} {away_name}) — Spegnimento BOT")
                sys.exit(0)

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
                    candidates   = sorted(team_goals + own_goals_vs, key=lambda x: (x["minute"], x.get("seq", 0)))
                    idx = gh - 1
                else:
                    team_goals   = [e for e in goal_events_all if e["type"] != "own goal" and e["team_id"] == s_away_id]
                    own_goals_vs = [e for e in goal_events_all if e["type"] == "own goal" and e["team_id"] == s_away_id]
                    candidates   = sorted(team_goals + own_goals_vs, key=lambda x: (x["minute"], x.get("seq", 0)))
                    idx = ga - 1

                if idx < 0 or idx >= len(candidates):
                    continue

                current = candidates[idx]
                current_scorer = current.get("player_name", "")
                current_assist = current.get("assist_name", "")
                current_type = current.get("type", saved.get("type", "goal"))

                if (_norm_name(current_scorer) != _norm_name(saved.get("scorer", ""))) or \
                   (_norm_name(current_assist) != _norm_name(saved.get("assist", ""))) or \
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
                    _min_disp_new = current.get("minute_disp", str(current["minute"]))
                    goal_text_new = f"<b>GOAL · {_min_disp_new}' {E_MIC}</b>\n\n{goal_score_new}\n{scorer_line_new}{assist_line_new}\n{e_comp_saved} {hashtag_saved}"

                    changes = []
                    if _norm_name(current_scorer) != _norm_name(saved.get("scorer", "")):
                        changes.append(f"marcatore: {saved.get('scorer')} → {current_scorer}")
                    if _norm_name(current_assist) != _norm_name(saved.get("assist", "")):
                        old_a = saved.get("assist", "—") or "—"
                        new_a = current_assist or "—"
                        changes.append(f"assist: {old_a} → {new_a}")
                    if current_type != saved.get("type", "goal"):
                        changes.append(f"tipo: {saved.get('type', 'goal')} → {current_type}")

                    if send_telegram_edit(msg_id, goal_text_new):
                        print(f"[{now_it()}] ✏️  CORREZIONE goal {goal_key}: {', '.join(changes)} → messaggio editato")
                        state["goal_messages"][goal_key]["scorer"]    = current_scorer
                        state["goal_messages"][goal_key]["assist"]    = current_assist
                        state["goal_messages"][goal_key]["type"]      = current_type
                        state["goal_messages"][goal_key]["score_tid"] = actual_tid
                        state_changed = True
                    else:
                        print(f"[{now_it()}] ⚠️  CORREZIONE goal {goal_key} non riuscita ({', '.join(changes)}) — riprovo al prossimo ciclo")

            # --- Cambi ---
            new_subs_fresh      = []
            new_subs_edit       = []
            # Correzioni ESPN: ESPN prima manda il cambio sbagliato, poi corregge il
            # giocatore (uid diverso, una sola metà della coppia in/out cambia).
            # { slot_key, field("in"|"out"), idx, old_val, new_val, sub_id, event }
            new_subs_correction = []

            for e in events:
                if e["type"] != "substitution":
                    continue
                sub_id = e["uid"]
                # Dedup per uid: stesso evento ESPN già registrato
                already_sent = any(sub_id in slot["sub_ids"] for slot in state["sent_subs"].values())
                if already_sent:
                    continue

                _e_out = fmt_player(e["player_name"])   # giocatore che esce
                _e_in  = fmt_player(e["assist_name"])   # giocatore che entra

                # Cerca slot già inviato per questo team + minuto compatibile (±2')
                slot_key = None
                for k, slot in state["sent_subs"].items():
                    if k.split(":")[0] == e["team_id"] and abs(slot["minute"] - e["minute"]) <= 2:
                        slot_key = k
                        break

                if slot_key:
                    slot = state["sent_subs"][slot_key]
                    out_present = _e_out in slot["outs"]
                    in_present  = _e_in  in slot["ins"]

                    if out_present and in_present:
                        # Duplicato esatto (uid diverso, stessa coppia) → skip
                        continue
                    elif in_present and not out_present:
                        # L'IN è già nello slot ma l'OUT è diverso:
                        # ESPN ha corretto il giocatore che esce
                        idx = slot["ins"].index(_e_in)
                        new_subs_correction.append({
                            "slot_key": slot_key, "field": "out",
                            "idx": idx, "old_val": slot["outs"][idx],
                            "new_val": _e_out, "sub_id": sub_id, "event": e,
                        })
                    elif out_present and not in_present:
                        # L'OUT è già nello slot ma l'IN è diverso:
                        # ESPN ha corretto il giocatore che entra
                        idx = slot["outs"].index(_e_out)
                        new_subs_correction.append({
                            "slot_key": slot_key, "field": "in",
                            "idx": idx, "old_val": slot["ins"][idx],
                            "new_val": _e_in, "sub_id": sub_id, "event": e,
                        })
                    else:
                        # Nessun giocatore coincide: sub genuinamente nuovo da aggiungere allo slot
                        new_subs_edit.append((e, slot_key))
                else:
                    # Nessuno slot compatibile — controlla duplicato preciso cross-slot
                    # (Bug 1: stesso cambio, uid diverso, minuto fuori dalla finestra ±2')
                    already_sent_exact = any(
                        k.split(":")[0] == e["team_id"]
                        and _e_out in slot["outs"]
                        and _e_in  in slot["ins"]
                        for k, slot in state["sent_subs"].items()
                    )
                    if already_sent_exact:
                        continue
                    new_subs_fresh.append(e)

            # Correzioni ESPN: sostituisce solo il giocatore sbagliato nello slot e re-edita
            for corr in new_subs_correction:
                slot       = state["sent_subs"][corr["slot_key"]]
                e          = corr["event"]
                team_title = home_name.upper() if e["team_id"] == home_id else away_name.upper()
                # Calcolo il nuovo testo SENZA mutare ancora lo slot: se l'edit
                # fallisce, la correzione deve poter essere ritentata al ciclo
                # successivo, quindi lo stato va aggiornato solo dopo conferma.
                tmp_ins  = list(slot["ins"])
                tmp_outs = list(slot["outs"])
                if corr["field"] == "out":
                    tmp_outs[corr["idx"]] = corr["new_val"]
                    log_dir = f"↓ {corr['old_val']} → {corr['new_val']}"
                else:
                    tmp_ins[corr["idx"]] = corr["new_val"]
                    log_dir = f"↑ {corr['old_val']} → {corr['new_val']}"
                ins_str  = ", ".join(tmp_ins)
                outs_str = ", ".join(tmp_outs)
                new_text = (
                    f"<b>CAMBIO {team_title} · {slot['minute']}' {E_SUB}</b>\n\n"
                    f"{E_UP} {ins_str}\n"
                    f"{E_DOWN} {outs_str}\n\n"
                    f"{e_comp} {hashtag}"
                )
                if send_telegram_edit(slot["msg_id"], new_text):
                    slot["ins"]  = tmp_ins
                    slot["outs"] = tmp_outs
                    slot["sub_ids"].append(corr["sub_id"])
                    print(f"[{now_it()}] ✏️  CORREZIONE CAMBIO {team_title} {slot['minute']}' | {log_dir} → messaggio editato")
                    state_changed = True
                else:
                    print(f"[{now_it()}] ⚠️  CORREZIONE CAMBIO {team_title} {slot['minute']}' non riuscita ({log_dir}) — riprovo al prossimo ciclo")

            for e, slot_key in new_subs_edit:
                slot       = state["sent_subs"][slot_key]
                team_title = home_name.upper() if e["team_id"] == home_id else away_name.upper()
                _e_out = fmt_player(e["player_name"])
                _e_in  = fmt_player(e["assist_name"])
                # Safety: non duplicare se entrambi già presenti (non dovrebbe capitare qui)
                if _e_out in slot["outs"] and _e_in in slot["ins"]:
                    continue
                tmp_ins  = slot["ins"]  + [_e_in]
                tmp_outs = slot["outs"] + [_e_out]
                ins_str  = ", ".join(tmp_ins)
                outs_str = ", ".join(tmp_outs)
                new_text = (
                    f"<b>CAMBIO {team_title} · {slot['minute']}' {E_SUB}</b>\n\n"
                    f"{E_UP} {ins_str}\n"
                    f"{E_DOWN} {outs_str}\n\n"
                    f"{e_comp} {hashtag}"
                )
                if send_telegram_edit(slot["msg_id"], new_text):
                    slot["ins"]  = tmp_ins
                    slot["outs"] = tmp_outs
                    slot["sub_ids"].append(e["uid"])
                    print(f"[{now_it()}] ✏️  CAMBIO EDIT {team_title} {slot['minute']}' | ↑ {ins_str} / ↓ {outs_str}")
                    state_changed = True
                else:
                    print(f"[{now_it()}] ⚠️  CAMBIO EDIT {team_title} {slot['minute']}' non riuscito (↑ {_e_in} / ↓ {_e_out}) — riprovo al prossimo ciclo")

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
                    slot_key = None
                    for k, slot in state["sent_subs"].items():
                        if k.split(":")[0] == e["team_id"] and abs(slot["minute"] - e["minute"]) <= 2:
                            slot_key = k
                            break
                    if slot_key:
                        slot       = state["sent_subs"][slot_key]
                        team_title = home_name.upper() if e["team_id"] == home_id else away_name.upper()
                        # Evita duplicati esatti nello slot (stessa coppia in+out da fonti ESPN diverse).
                        # Con OR si bloccherebbero anche le correzioni; AND lascia passare
                        # solo il vero duplicato e demanda le correzioni al ciclo successivo.
                        _in_p  = fmt_player(e["assist_name"])
                        _out_p = fmt_player(e["player_name"])
                        if _out_p in slot["outs"] and _in_p in slot["ins"]:
                            continue
                        tmp_ins  = slot["ins"]  + [_in_p]
                        tmp_outs = slot["outs"] + [_out_p]
                        ins_str  = ", ".join(tmp_ins)
                        outs_str = ", ".join(tmp_outs)
                        new_text = (
                            f"<b>CAMBIO {team_title} · {slot['minute']}' {E_SUB}</b>\n\n"
                            f"{E_UP} {ins_str}\n"
                            f"{E_DOWN} {outs_str}\n\n"
                            f"{e_comp} {hashtag}"
                        )
                        if send_telegram_edit(slot["msg_id"], new_text):
                            slot["ins"]  = tmp_ins
                            slot["outs"] = tmp_outs
                            slot["sub_ids"].append(sub_id)
                            print(f"[{now_it()}] ✏️  CAMBIO EDIT (post-attesa) {team_title} {slot['minute']}' | ↑ {ins_str} / ↓ {outs_str}")
                            state_changed = True
                        else:
                            print(f"[{now_it()}] ⚠️  CAMBIO EDIT (post-attesa) {team_title} {slot['minute']}' non riuscito (↑ {_in_p} / ↓ {_out_p}) — riprovo al prossimo ciclo")
                    else:
                        pending.append(e)

                # Dedup pending: la stessa sostituzione può arrivare da più fonti
                # ESPN (commentary + keyEvents) con uid diversi e participant in
                # ordine differente. Identifico il cambio dalla COPPIA di giocatori
                # coinvolti (in + out), indipendente dall'ordine, così i doppioni
                # non finiscono nello stesso messaggio.
                _seen_pairs = set()
                _pending_dedup = []
                for sub in pending:
                    pair_key = (
                        sub["team_id"],
                        frozenset((
                            fmt_player(sub["player_name"]),
                            fmt_player(sub["assist_name"]),
                        )),
                    )
                    if pair_key in _seen_pairs:
                        continue
                    _seen_pairs.add(pair_key)
                    _pending_dedup.append(sub)
                pending = _pending_dedup

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
                    msg_id = send_telegram_get_id(new_text)
                    if msg_id:
                        print(f"[{now_it()}] 🔄 CAMBIO {team_title} {_min_ref}' | ↑ {ins_str} / ↓ {outs_str} → Telegram inviato")
                        new_key = f"{g['team_id']}:{_min_ref}"
                        state["sent_subs"][new_key] = {
                            "msg_id":  msg_id,
                            "minute":  _min_ref,
                            "ins":     [fmt_player(s["assist_name"]) for s in g["subs"]],
                            "outs":    [fmt_player(s["player_name"]) for s in g["subs"]],
                            "sub_ids": [s["uid"] for s in g["subs"]],
                        }
                        state_changed = True
                    else:
                        # Invio NON riuscito: non salvo lo slot né i sub_ids, così
                        # al ciclo successivo il cambio viene rilevato come nuovo
                        # e ritentato, esattamente come per i gol.
                        print(f"[{now_it()}] ⚠️  Invio CAMBIO non riuscito ({team_title} {_min_ref}' ↑ {ins_str} / ↓ {outs_str}) — riprovo al prossimo ciclo")

            # --- Cartellini rossi / doppio giallo ---
            for e in events:
                if e["type"] in ("red card", "second yellow card"):
                    p_name  = fmt_player(e["player_name"])
                    card_id = f"card_{e['player_name']}".replace(" ", "_")
                    if card_id not in state["sent_cards"]:
                        is_second_yellow = e["type"] == "second yellow card"
                        team_name = home_name if e["team_id"] == home_id else away_name
                        label = f"ROSSO {team_name.upper()}" if is_second_yellow else f"ROSSO {team_name.upper()}"
                        msg_id = send_telegram_get_id(
                            f"<b>{label} · {e['minute']}' {E_RED}</b>\n\n"
                            f"{E_EXIT} <i>{p_name}</i>\n\n{e_comp} {hashtag}"
                        )
                        if msg_id:
                            print(f"[{now_it()}] 🟥 {label} {e['minute']}' {p_name} → Telegram inviato")
                            state["sent_cards"].append(card_id)
                            state_changed = True

            # --- Rigori sbagliati (solo durante il gioco: nella lotteria dei
            # rigori l'esito di ogni calcio lo annuncia già il blocco RIGORI) ---
            for e in (events if status not in ("PEN", "BREAK_PEN") else []):
                if e["type"] in ("penalty missed", "penalty saved"):
                    if _failpen_gia_inviato(state, e):
                        continue
                    team_name = home_name if e["team_id"] == home_id else away_name
                    msg_id = send_telegram_get_id(
                        f"<b>RIGORE SBAGLIATO {team_name.upper()} · {e['minute']}' {E_KICK}</b>\n\n"
                        f"{E_PEN_KO} <i>{fmt_player(e['player_name'])}</i>\n\n"
                        f"{e_comp} {hashtag}"
                    )
                    if msg_id:
                        print(f"[{now_it()}] 🥅 RIGORE SBAGLIATO {team_name.upper()} {e['minute']}' {fmt_player(e['player_name'])} → Telegram inviato")
                        state["sent_failed_penalties"].append({
                            "player": e["player_name"],
                            "type":   e["type"],
                            "minute": e["minute"],
                        })
                        state_changed = True

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
