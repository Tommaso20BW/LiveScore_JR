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
import goal_graphics
import fclogo_sync
import diretta_logos
from live_logging import MatchProgressLog, log_line
from telegram_autodelete import enqueue_response, should_enqueue

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
    log_line("DEBUG", "SETUP", "pynacl non installata; aggiornamento Secrets GitHub non disponibile")

# ==============================================================================
# CONFIGURAZIONE
# ==============================================================================
BOT_TOKEN           = os.getenv('TELEGRAM_TOKEN')
CHAT_ID             = os.getenv('TELEGRAM_TO')
BOT_JR_CHAT_ID      = os.getenv('TELEGRAM_TO_BOT')
TEAM_ID             = os.getenv('TEAM_ID', '111')
GH_PAT              = os.getenv('GH_PAT')
GITHUB_REPOSITORY   = os.getenv('GITHUB_REPOSITORY')
GIST_ID             = os.getenv('GIST_ID')
CLIENT_ID           = os.getenv('CANVA_CLIENT_ID')
CLIENT_SECRET       = os.getenv('CANVA_CLIENT_SECRET')
CANVA_REFRESH_TOKEN = os.getenv('CANVA_REFRESH_TOKEN')
GOAL_GRAPHICS_ENABLED = os.getenv('GOAL_GRAPHICS_ENABLED', '0').strip().lower() in (
    '1', 'true', 'yes', 'on'
)

try:
    LIVE_LOG_HEARTBEAT_MINUTES = max(
        1, int(os.getenv('LIVE_LOG_HEARTBEAT_MINUTES', '5'))
    )
except ValueError:
    LIVE_LOG_HEARTBEAT_MINUTES = 5

try:
    TELEGRAM_AUTO_DELETE_SECONDS = max(
        0, int(os.getenv('TELEGRAM_AUTO_DELETE_SECONDS', '0'))
    )
except ValueError:
    TELEGRAM_AUTO_DELETE_SECONDS = 0

CANVA_DESIGN_ID = "DAHI3ytu6yQ"
PAGINA_TARGET   = 2  # fallback / kit non determinato

# Pagina del design Canva da esportare in base al kit indossato dalla Juve
PAGINA_PER_KIT = {
    "home":  2,
    "away":  6,
    "third": 10,
}

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
        log_line("WARN", "SETUP", "leagues.json non trovato; emoji leghe disabilitate")
        return {}
    except Exception as e:
        log_line("ERROR", "SETUP", f"Caricamento leagues.json fallito: {e}")
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
                 # Juve resta sul kit 'default' e usa i loghi squadra standard,
                 # senza applicare l'override grafico Juventus.

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


def rileva_kit_juve(data_espn: dict, home_id: str, away_id: str,
                    home_name: str, away_name: str,
                    league_slug: str = "", league_name: str = "") -> str:
    """Restituisce il kit realmente indossato usando la stessa cascata ESPN
    gia usata dalle stats. La funzione e separata per poterla riusare al gol."""
    try:
        competitors = data_espn["header"]["competitions"][0]["competitors"]
    except Exception:
        competitors = []
    boxscore_teams = (data_espn.get("boxscore") or {}).get("teams", [])
    fallback_kit = determina_kit(home_id, away_id, league_slug, league_name)
    result = kit_analyzer.analizza(
        home_name=home_name,
        away_name=away_name,
        home_id=home_id,
        away_id=away_id,
        league_name=league_name,
        competitors=competitors,
        boxscore_teams=boxscore_teams,
        fallback_kit=fallback_kit,
    )
    return result["kit"] if result["kit"] in ("home", "away", "third") else fallback_kit

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

STATS_DELAY_SECONDS = 5 * 60

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


def goal_scoring_team_id(event: dict, home_id: str, away_id: str) -> str:
    """Restituisce la squadra a cui va assegnato il gol, invertendo l'autogol."""
    event_team_id = str(event.get("team_id", ""))
    if event.get("type") == "own goal":
        if event_team_id == str(home_id):
            return str(away_id)
        if event_team_id == str(away_id):
            return str(home_id)
    return event_team_id


def goal_player_lines(
    player_name: str,
    assist_name: str,
    goal_type: str,
    scoring_team_id: str,
) -> tuple[str, str]:
    """Formatta marcatore/assist applicando il fallback speciale solo alla Juve."""
    if not player_name:
        return "", ""

    player_text = fmt_player(player_name)
    if goal_type == "own goal":
        player_text += " (Autogol)"
    elif goal_type == "penalty goal":
        player_text += " (Rig.)"

    scorer_line = f"{E_BALL} <i>{player_text}</i>\n"
    registered = goal_graphics.find_player(html.unescape(player_name)) is not None
    juventus_name_only = (
        str(scoring_team_id) == JUVE_ID
        and (goal_type == "own goal" or not registered)
    )
    if juventus_name_only:
        return scorer_line, ""

    assist_line = ""
    if assist_name and _norm_name(assist_name) != _norm_name(player_name):
        assist_line = f"{E_ASSIST} <i>{fmt_player(assist_name)}</i>\n"
    return scorer_line, assist_line

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
            target_chat_id = (payload or {}).get("chat_id") or (data or {}).get("chat_id")
            if should_enqueue(
                method,
                target_chat_id,
                BOT_JR_CHAT_ID,
                TELEGRAM_AUTO_DELETE_SECONDS,
            ):
                try:
                    enqueue_response(
                        SESSION,
                        r,
                        GH_PAT,
                        GIST_ID,
                        target_chat_id,
                        TELEGRAM_AUTO_DELETE_SECONDS,
                    )
                except Exception as e:
                    log_line("WARN", "TELEGRAM", f"Coda auto-delete Bot JR non aggiornata: {e}")
            return r
        try:
            retry_after = int(r.json().get("parameters", {}).get("retry_after", 3))
        except Exception:
            retry_after = 3
        log_line("WAIT", "TELEGRAM", f"Rate limit 429; nuovo tentativo tra {retry_after}s")
        time.sleep(min(retry_after, 30))
    return r

def send_telegram(text: str):
    if not BOT_TOKEN or not CHAT_ID:
        log_line("WARN", "TELEGRAM", "BOT_TOKEN o CHAT_ID mancanti")
        return
    try:
        r = _tg_post("sendMessage", payload={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"})
        r.raise_for_status()
    except Exception as e:
        log_line("ERROR", "TELEGRAM", f"sendMessage fallito: {e}")

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
        log_line("ERROR", "TELEGRAM", f"editMessageText fallito: {e}")
        return False

def send_telegram_get_id(text: str) -> int | None:
    if not BOT_TOKEN or not CHAT_ID:
        log_line("WARN", "TELEGRAM", "BOT_TOKEN o CHAT_ID mancanti")
        return None
    try:
        r = _tg_post("sendMessage", payload={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"})
        r.raise_for_status()
        msg_id = r.json().get("result", {}).get("message_id")
        return msg_id
    except Exception as e:
        log_line("ERROR", "TELEGRAM", f"sendMessage fallito: {e}")
        return None


def _send_telegram_event_photo_get_id(
    text: str,
    photo_bytes: bytes | None,
    *,
    filename: str,
    label: str,
) -> tuple[int | None, bool]:
    """Invia una card come foto+caption e restituisce anche il message_id.

    Se Telegram rifiuta la foto, il messaggio testuale viene comunque inviato:
    il booleano indica se il messaggio salvato e realmente una foto.
    """
    if not photo_bytes:
        return send_telegram_get_id(text), False
    try:
        r = _tg_post(
            "sendPhoto",
            data={"chat_id": CHAT_ID, "caption": text, "parse_mode": "HTML"},
            files={"photo": (filename, photo_bytes, "image/png")},
            timeout=25,
        )
        if r is not None and r.status_code == 200:
            msg_id = r.json().get("result", {}).get("message_id")
            return msg_id, bool(msg_id)
        log_line("WARN", "TELEGRAM", f"Foto {label} rifiutata; fallback testo")
    except Exception as e:
        log_line("WARN", "TELEGRAM", f"Invio foto {label} fallito: {e}; fallback testo")
    return send_telegram_get_id(text), False


def send_telegram_goal_get_id(text: str, photo_bytes: bytes | None) -> tuple[int | None, bool]:
    return _send_telegram_event_photo_get_id(
        text, photo_bytes, filename="goal.png", label="GOAL"
    )


def send_telegram_saved_get_id(text: str, photo_bytes: bytes | None) -> tuple[int | None, bool]:
    return _send_telegram_event_photo_get_id(
        text, photo_bytes, filename="saved.png", label="SAVED"
    )


def edit_telegram_goal_photo(message_id: int, text: str, photo_bytes: bytes) -> bool:
    """Aggiunge/sostituisce foto e caption quando ESPN corregge il marcatore.

    Da Bot API 7.11 editMessageMedia puo anche convertire direttamente un
    messaggio di testo in un messaggio media, conservando il message_id.
    """
    if not BOT_TOKEN or not CHAT_ID or not message_id or not photo_bytes:
        return False
    media = json.dumps({
        "type": "photo",
        "media": "attach://photo",
        "caption": text,
        "parse_mode": "HTML",
    })
    try:
        r = _tg_post(
            "editMessageMedia",
            data={"chat_id": CHAT_ID, "message_id": message_id, "media": media},
            files={"photo": ("goal.png", photo_bytes, "image/png")},
            timeout=25,
        )
        return r is not None and r.status_code == 200
    except Exception as e:
        log_line("ERROR", "TELEGRAM", f"editMessageMedia GOAL fallito: {e}")
        return False


def edit_telegram_goal_caption(message_id: int, text: str) -> bool:
    if not BOT_TOKEN or not CHAT_ID or not message_id:
        return False
    try:
        r = _tg_post("editMessageCaption", payload={
            "chat_id": CHAT_ID,
            "message_id": message_id,
            "caption": text,
            "parse_mode": "HTML",
        })
        return r is not None and r.status_code == 200
    except Exception as e:
        log_line("ERROR", "TELEGRAM", f"editMessageCaption GOAL fallito: {e}")
        return False

def delete_telegram_message(message_id: int):
    if not BOT_TOKEN or not CHAT_ID or not message_id:
        return
    try:
        _tg_post("deleteMessage", payload={"chat_id": CHAT_ID, "message_id": message_id})
    except Exception as e:
        log_line("WARN", "TELEGRAM", f"deleteMessage fallito: {e}")


def replace_corrected_goal_message(
    message_id: int,
    was_photo: bool,
    text: str,
    rendered_goal: goal_graphics.RenderedGoal | None,
) -> tuple[bool, int, bool]:
    """Aggiorna testo e media di un GOAL corretto senza lasciare la foto errata."""
    if was_photo and rendered_goal:
        edited = edit_telegram_goal_photo(message_id, text, rendered_goal.png)
        return edited, message_id, True

    if was_photo and not rendered_goal:
        replacement_id = send_telegram_get_id(text)
        if replacement_id:
            delete_telegram_message(message_id)
            return True, replacement_id, False
        return False, message_id, True

    if not was_photo and rendered_goal:
        # Bot API 7.11: conversione testo -> foto sullo stesso message_id.
        edited = edit_telegram_goal_photo(message_id, text, rendered_goal.png)
        return edited, message_id, edited

    return send_telegram_edit(message_id, text), message_id, False

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


def prepara_grafica_goal(*, data_espn: dict, scorer_name: str,
                         goal_type: str, scoring_team_id: str,
                         minute: str | int, home_name: str, away_name: str,
                         home_id: str, away_id: str,
                         home_goals: int, away_goals: int,
                         league_slug: str, league_name: str,
                         event_key: str) -> goal_graphics.RenderedGoal | None:
    """Crea la card solo per un gol assegnato alla Juventus.

    I marcatori senza asset e gli autogol a favore della Juventus ricevono la
    stessa card, ma senza la sagoma del calciatore. Se manca anche il nome, il
    bot invia il testo e lo converte nella card sullo stesso message_id quando
    ESPN comunica il marcatore. Marcatori avversari e lotteria restano testuali.
    """
    if not GOAL_GRAPHICS_ENABLED:
        return None
    if is_friendly_competition(league_slug, league_name):
        return None
    if (
        str(scoring_team_id) != JUVE_ID
        or goal_type not in ("goal", "penalty goal", "own goal")
        or not scorer_name
    ):
        return None
    try:
        juve_kit = rileva_kit_juve(
            data_espn,
            home_id,
            away_id,
            home_name,
            away_name,
            league_slug,
            league_name,
        )
        if juve_kit not in ("home", "away", "third"):
            juve_kit = "home" if str(home_id) == JUVE_ID else "away"
        rendered = goal_graphics.render_goal_card(
            scorer_name=scorer_name,
            minute=minute,
            home_name=home_name,
            away_name=away_name,
            home_id=home_id,
            away_id=away_id,
            home_goals=home_goals,
            away_goals=away_goals,
            kit=juve_kit,
            goal_type=goal_type,
            event_key=event_key,
        )
        rendered_name = (
            rendered.player.name if rendered.player else rendered.scorer_name
        )
        log_line(
            "DEBUG",
            "GRAPHICS",
            f"GOAL pronta | {rendered_name} | kit={rendered.kit} | "
            f"posa={rendered.pose} | sagoma={'sì' if rendered.player else 'no'}",
        )
        return rendered
    except goal_graphics.GoalGraphicUnavailable as e:
        log_line("WARN", "GRAPHICS", f"GOAL non disponibile: {e}; invio testo")
        return None
    except Exception as e:
        log_line("WARN", "GRAPHICS", f"Composizione GOAL fallita: {e}; invio testo")
        return None


def _nome_portiere_registrato(name: str) -> str:
    player = goal_graphics.find_player(html.unescape(name or ""))
    return player.name if player and player.role == "goalkeeper" else ""


def trova_portiere_juve(data_espn: dict, event_candidate: str = "") -> str:
    """Trova il portiere Juventus nei partecipanti evento o nelle formazioni ESPN."""
    direct = _nome_portiere_registrato(event_candidate)
    if direct:
        return direct

    candidates: list[tuple[int, str]] = []

    def add_candidate(entry: dict, base_priority: int) -> None:
        athlete = entry.get("athlete") or entry.get("player") or entry
        if not isinstance(athlete, dict):
            return
        name = (
            athlete.get("displayName") or athlete.get("fullName")
            or athlete.get("shortName") or ""
        )
        canonical = _nome_portiere_registrato(name)
        if not canonical:
            return
        position = entry.get("position") or athlete.get("position") or {}
        if isinstance(position, dict):
            position_text = " ".join(str(position.get(key, "")) for key in (
                "abbreviation", "name", "displayName"
            )).lower()
        else:
            position_text = str(position).lower()
        is_goalkeeper = any(token in position_text for token in (
            "gk", "goalkeeper", "portiere", "keeper"
        ))
        priority = base_priority
        if is_goalkeeper:
            priority += 30
        if entry.get("starter") is True:
            priority += 20
        if entry.get("active") is True or entry.get("didPlay") is True:
            priority += 10
        candidates.append((priority, canonical))

    # Summary ESPN: rosters[].roster[]
    for team_block in data_espn.get("rosters") or []:
        team = team_block.get("team") or {}
        if str(team.get("id", team_block.get("id", ""))) != JUVE_ID:
            continue
        for entry in team_block.get("roster") or team_block.get("athletes") or []:
            if isinstance(entry, dict):
                add_candidate(entry, 200)

    # Summary ESPN: boxscore.players[].statistics[].athletes[]
    for team_block in ((data_espn.get("boxscore") or {}).get("players") or []):
        team = team_block.get("team") or {}
        if str(team.get("id", "")) != JUVE_ID:
            continue
        for category in team_block.get("statistics") or []:
            for entry in category.get("athletes") or []:
                if isinstance(entry, dict):
                    add_candidate(entry, 100)

    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def prepara_grafica_parata_rigore(
    *,
    data_espn: dict,
    penalty_event: dict,
    goalkeeper_name: str,
    minute: str | int,
    home_name: str,
    away_name: str,
    home_id: str,
    away_id: str,
    home_goals: int,
    away_goals: int,
    event_key: str,
    league_slug: str = "",
    league_name: str = "",
) -> goal_graphics.RenderedGoal | None:
    """Crea SAVED solo per un rigore avversario realmente parato dalla Juve."""
    if not GOAL_GRAPHICS_ENABLED or is_friendly_competition(
        league_slug, league_name
    ) or penalty_event.get("type") not in (
        "penalty saved", "shootout saved"
    ):
        return None
    opponent_id = away_id if str(home_id) == JUVE_ID else (
        home_id if str(away_id) == JUVE_ID else ""
    )
    if not opponent_id or str(penalty_event.get("team_id", "")) != str(opponent_id):
        return None
    if not _nome_portiere_registrato(goalkeeper_name):
        return None
    try:
        rendered = goal_graphics.render_saved_card(
            goalkeeper_name=goalkeeper_name,
            minute=minute,
            home_name=home_name,
            away_name=away_name,
            home_id=home_id,
            away_id=away_id,
            home_goals=home_goals,
            away_goals=away_goals,
            event_key=event_key,
        )
        log_line(
            "DEBUG", "GRAPHICS", f"SAVED pronta | {rendered.player.name} | posa={rendered.pose}"
        )
        return rendered
    except goal_graphics.GoalGraphicUnavailable as e:
        log_line("WARN", "GRAPHICS", f"SAVED non disponibile: {e}; invio testo")
        return None
    except Exception as e:
        log_line("WARN", "GRAPHICS", f"Composizione SAVED fallita: {e}; invio testo")
        return None

def send_telegram_stats_photo(png_path: str, momento: str, hashtag: str,
                              min_long_side: int = 2000) -> bool:
    """Invia la foto delle statistiche. Ritorna True solo se l'invio è
    andato davvero a buon fine, così chi chiama può ritentare invece di
    segnare l'evento come fatto e perderlo silenziosamente."""
    if not png_path:
        log_line("WARN", "STATS", f"{momento} | immagine non generata; invio saltato")
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
        if min_long_side:
            photo_sizes = r.json().get("result", {}).get("photo", [])
            largest = max(
                photo_sizes,
                key=lambda item: item.get("width", 0) * item.get("height", 0),
                default={},
            )
            sent_w = largest.get("width", 0)
            sent_h = largest.get("height", 0)
            if max(sent_w, sent_h) >= min_long_side:
                log_line("OK", "STATS", f"Variante Telegram HD | {sent_w}x{sent_h}")
            else:
                log_line("WARN", "STATS", f"Telegram ha restituito solo {sent_w}x{sent_h}")
        return True
    except Exception as e:
        log_line("ERROR", "STATS", f"Invio foto fallito: {e}")
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
        if "key" not in pk or "key_id" not in pk:
            log_line("ERROR", "GITHUB", f"Update secret, risposta inattesa: {pk.get('message', pk)}")
            return False
        pub_key = public.PublicKey(pk["key"].encode("utf-8"), encoding.Base64Encoder)
        encrypted = base64.b64encode(public.SealedBox(pub_key).encrypt(new_value.encode())).decode()
        r = SESSION.put(f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/secrets/{secret_name}",
                        headers=headers, json={"encrypted_value": encrypted, "key_id": pk["key_id"]}, timeout=10)
        if r.status_code in [201, 204]:
            return True
    except Exception as e:
        log_line("ERROR", "GITHUB", f"Update secret fallito: {e}")
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
            log_line("RETRY", "STATE", f"Lettura Gist HTTP {r.status_code} | tentativo {attempt + 1}/3")
        except Exception as e:
            log_line("RETRY", "STATE", f"Lettura Gist fallita: {e} | tentativo {attempt + 1}/3")
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
        log_line("ERROR", "STATE", f"Salvataggio Gist fallito: {e}")

def resetta_gist():
    if not GH_PAT or not GIST_ID:
        return
    try:
        payload = {"files": {"match_state.json": {"content": "{}"}}}
        SESSION.patch(f"https://api.github.com/gists/{GIST_ID}", headers=_gist_headers(),
                      json=payload, timeout=10)
    except Exception as e:
        log_line("ERROR", "STATE", f"Reset Gist fallito: {e}")

# ==============================================================================
# CANVA
# ==============================================================================
def get_valid_token():
    if not CANVA_REFRESH_TOKEN:
        log_line("ERROR", "CANVA", "CANVA_REFRESH_TOKEN mancante")
        return None
    try:
        log_line("DEBUG", "CANVA", "Richiesta access token tramite refresh token")
        r = SESSION.post("https://api.canva.com/rest/v1/oauth/token", data={
            "grant_type": "refresh_token", "refresh_token": CANVA_REFRESH_TOKEN,
            "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET
        }, timeout=15)
        if r.status_code == 200:
            tokens = r.json()
            if "refresh_token" in tokens and tokens["refresh_token"] != CANVA_REFRESH_TOKEN:
                log_line("DEBUG", "CANVA", "Nuovo refresh token; aggiorno GitHub Secret")
                if update_github_secret("CANVA_REFRESH_TOKEN", tokens["refresh_token"]):
                    log_line("DEBUG", "CANVA", "GitHub Secret CANVA_REFRESH_TOKEN aggiornato")
                else:
                    # Il vecchio refresh token è stato invalidato da Canva ma il
                    # nuovo NON è stato salvato: senza intervento manuale tutti i
                    # run futuri falliranno. Avviso subito su Telegram.
                    log_line("ERROR", "CANVA", "Update GitHub Secret fallito; salvare il refresh token manualmente")
            else:
                log_line("DEBUG", "CANVA", "Access token ottenuto | refresh token invariato")
            return tokens["access_token"]
        log_line("ERROR", "CANVA", f"Richiesta token fallita: {r.text}")
    except Exception as e:
        log_line("ERROR", "CANVA", f"Connessione fallita: {e}")
    return None

def get_canva_image(access_token: str, pagina: int = PAGINA_TARGET):
    if not access_token:
        return None
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    try:
        log_line("DEBUG", "CANVA", f"Avvio export | design={CANVA_DESIGN_ID} | pagina={pagina}")
        r = SESSION.post("https://api.canva.com/rest/v1/exports", headers=headers, json={
            "design_id": CANVA_DESIGN_ID,
            "format": {
                "type": "png",
                "pages": [pagina],
                "export_quality": "pro",
                "lossless": True,
            },
        }, timeout=15)
        if r.status_code not in [200, 201]:
            log_line("ERROR", "CANVA", f"Avvio export HTTP {r.status_code}: {r.text}")
            return None
        job_data = r.json()
        job_id = job_data.get("id") or job_data.get("job", {}).get("id")
        if not job_id:
            log_line("ERROR", "CANVA", "Export senza job_id nella risposta")
            return None
        log_line("DEBUG", "CANVA", f"Export in corso | job_id={job_id}")
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
                        log_line("DEBUG", "CANVA", "Export completato; scarico immagine")
                        img = SESSION.get(url_dl, timeout=30).content
                        log_line("DEBUG", "CANVA", f"Immagine scaricata | {len(img) // 1024} KB")
                        return img
                elif stato == "failed":
                    log_line("ERROR", "CANVA", f"Export fallito | job_id={job_id}")
                    return None
    except Exception as e:
        log_line("ERROR", "CANVA", f"Export fallito: {e}")
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

    def add_event(ev_type, minute, team_id, player_name, assist_name, uid, minute_disp="", period=0):
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
                # Aggiorna period se prima non era noto (period=0/mancante)
                if period and not existing.get("period"):
                    existing["period"] = period
                return
        # Dedup specifico sostituzioni: la stessa sostituzione può arrivare da più
        # feed ESPN (commentary + keyEvents) con uid diversi, minuto leggermente
        # diverso e participant in ordine invertito (in/out scambiati). La
        # identifico dalla COPPIA di giocatori coinvolti, indipendente dall'ordine.
        # Confronto normalizzato per tollerare differenze di accenti tra le fonti.
        # IMPORTANTE: il confronto include anche il PERIODO (tempo di gioco), non
        # solo il minuto: senza questo controllo un cambio al 44' di 1° tempo e uno
        # al 45' di 2° tempo (minuti "vicini" ma tempi diversi, separati
        # dall'intervallo) venivano erroneamente considerati lo stesso evento/slot
        # e raggruppati insieme in un unico messaggio.
        if norm == "substitution":
            pair = frozenset((_norm_name(player_name), _norm_name(assist_name)))
            for existing in events:
                if (existing["type"] == "substitution"
                        and existing["team_id"] == str(team_id)
                        and existing.get("period", 0) == period
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
            "period":      period,        # 1=1°T, 2=2°T, 3/4=supplementari, 5=rigori
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
            log_line("DEBUG", "ESPN", f"Parsing commentary testuale fallito: {e}")

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
            add_event(ev_type, minute, team_id, player, assist, uid, minute_disp=_mdisp, period=period_num)
        except Exception as e:
            log_line("DEBUG", "ESPN", f"Parsing commentary fallito: {e}")

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

            add_event(ev_type, minute, t_id, player, assist, uid, minute_disp=_mdisp, period=period_num_ke)
        except Exception as e:
            log_line("DEBUG", "ESPN", f"Parsing keyEvent fallito: {e}")

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
            log_line("DEBUG", "ESPN", f"Parsing scoringPlay fallito: {e}")

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
            log_line("DEBUG", "ESPN", f"Parsing shootout fallito: {e}")

    return events

# ==============================================================================
# STATISTICHE
# ==============================================================================
_DIRETTA_LOGO_CACHE: dict[tuple[str, ...], tuple[str, str]] = {}


def _team_logo_aliases(data_espn: dict, team_id: str, display_name: str) -> list[str]:
    """Nomi utili a collegare una squadra ESPN al risultato di Diretta.it."""
    aliases = [html.unescape(str(display_name or ""))]
    team_id = str(team_id)
    blocks = []
    try:
        blocks.extend(data_espn["header"]["competitions"][0].get("competitors", []))
    except Exception:
        pass
    blocks.extend((data_espn.get("boxscore") or {}).get("teams", []))
    for block in blocks:
        team = block.get("team") or {}
        if str(team.get("id", "")) != team_id:
            continue
        aliases.extend(
            team.get(field, "")
            for field in ("displayName", "name", "shortDisplayName", "location")
        )
    result, seen = [], set()
    for alias in aliases:
        alias = str(alias or "").strip()
        key = alias.casefold()
        if alias and key not in seen:
            seen.add(key)
            result.append(alias)
    return result


def _diretta_stats_logo(data_espn: dict, team_id: str, display_name: str) -> str | None:
    aliases = _team_logo_aliases(data_espn, team_id, display_name)
    cache_key = (str(team_id), *(alias.casefold() for alias in aliases))
    cached = _DIRETTA_LOGO_CACHE.get(cache_key)
    if cached is not None:
        return cached[0]
    try:
        resolved = diretta_logos.resolve_team_logo(aliases, SESSION)
    except Exception as exc:
        log_line("DEBUG", "GRAPHICS", f"Logo Diretta non disponibile | {display_name}: {exc}")
        return None
    if resolved is None:
        log_line("DEBUG", "GRAPHICS", f"Logo Diretta non univoco | {display_name}")
        return None
    logo, diretta_name = resolved
    _DIRETTA_LOGO_CACHE[cache_key] = resolved
    log_line("DEBUG", "GRAPHICS", f"Logo Diretta | {display_name} -> {diretta_name}")
    return logo


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
        log_line("DEBUG", "ESPN", f"Parsing boxscore.teams fallito: {e}")

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
        log_line("DEBUG", "ESPN", f"Parsing header competitors fallito: {e}")

    return raw


def _estrai_xg_mtchstatsgraph(payload: dict, home_id: str, away_id: str):
    """Estrae gli xG aggregati di entrambe le squadre da ``mtchStatsGrph``.

    ESPN espone questo dato nella pagina Team Stats, ma non nel ``summary``
    usato dal resto del bot. Le celle vengono associate tramite l'ID squadra:
    l'ordine ``teamOne``/``teamTwo`` non e garantito. ``0`` e un valore valido;
    ritorniamo ``None`` solo se il record o una delle due squadre e assente.
    """
    try:
        gamepackage = payload["page"]["content"]["gamepackage"]
        graph = gamepackage.get("mtchStatsGrph") or {}
        teams = graph.get("teams") or {}

        expected_goals = None
        for group in graph.get("stats") or []:
            for record in group.get("data") or []:
                if str(record.get("name", "")).strip().lower() == "expected goals":
                    expected_goals = record
                    break
            if expected_goals is not None:
                break

        if expected_goals is None:
            return None

        by_team_id = {}
        for team_key in ("teamOne", "teamTwo"):
            team_id = str((teams.get(team_key) or {}).get("id", ""))
            cell = expected_goals.get(team_key) or {}
            value = cell.get("value")
            display_value = cell.get("displayValue")

            # Non usare un controllo di truthiness: xG=0 e un dato reale.
            if not team_id or (value is None and display_value in (None, "")):
                continue

            numeric_value = value if value is not None else display_value
            try:
                by_team_id[team_id] = f"{float(numeric_value):.2f}"
            except (TypeError, ValueError):
                continue

        home_key = str(home_id)
        away_key = str(away_id)
        if home_key not in by_team_id or away_key not in by_team_id:
            return None

        return by_team_id[home_key], by_team_id[away_key]
    except (KeyError, TypeError, AttributeError):
        return None


def recupera_xg_espn(event_id: str, home_id: str, away_id: str):
    """Recupera gli xG dalla pagina ESPN Team Stats tramite Playwright.

    Qualsiasi errore e non bloccante: la grafica viene comunque generata senza
    la riga xG, come richiesto per le competizioni che non forniscono il dato.
    """
    if not event_id:
        log_line("DEBUG", "STATS", "Event ID assente; riga xG omessa")
        return None

    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    url = f"https://www.espn.co.uk/football/team-stats/_/gameId/{event_id}"
    browser = None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(
                viewport={"width": 1440, "height": 1100},
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
                ),
                locale="en-GB",
            )
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            except PlaywrightTimeoutError:
                # Il payload spesso e gia presente anche se una risorsa accessoria
                # mantiene aperto il caricamento fino al timeout.
                log_line("DEBUG", "STATS", "Timeout pagina Team Stats; uso il DOM disponibile")

            page.wait_for_timeout(3_000)
            marker = "window['__espnfitt__']="
            payload = None
            for script_text in page.locator("script").all_text_contents():
                marker_index = script_text.find(marker)
                if marker_index < 0:
                    continue
                json_text = script_text[marker_index + len(marker):].lstrip()
                payload, _ = json.JSONDecoder().raw_decode(json_text)
                break

            if payload is None:
                log_line("DEBUG", "STATS", "Payload ESPN Team Stats assente; riga xG omessa")
                return None

            result = _estrai_xg_mtchstatsgraph(payload, home_id, away_id)
            if result is None:
                log_line("DEBUG", "STATS", "xG non disponibili; riga omessa")
                return None

            log_line("DEBUG", "STATS", f"xG ESPN | home={result[0]} | away={result[1]}")
            return result
    except Exception as e:
        log_line("DEBUG", "STATS", f"Recupero xG ESPN fallito: {e}; riga omessa")
        return None
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass


def recupera_e_genera_stats_html(data_espn: dict, home_id: str, away_id: str,
                                  home_name: str, away_name: str,
                                  home_goals: int, away_goals: int,
                                  momento: str, league_name: str = "SERIE A",
                                  league_slug: str = "",
                                  pen_home: int = 0, pen_away: int = 0,
                                  event_id: str = "",
                                  hd_output: bool = True):
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
    log_line(
        "DEBUG",
        "STATS",
        f"Kit={juve_kit} | {home_name}={home_color} | {away_name}={away_color} "
        f"| lega={league_name}/{league_slug or 'n.d.'}",
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
    # L'override Juventus dipendente dal kit resta intenzionale. Per tutte le
    # altre squadre la fonte primaria e' Diretta.it; ESPN interviene soltanto
    # se la ricerca non e' disponibile o non produce un match univoco.
    h_logo = juve_logo if str(home_id) == JUVE_ID else (
        _diretta_stats_logo(data_espn, home_id, home_name)
        or f"https://a.espncdn.com/i/teamlogos/soccer/500/{home_id}.png"
    )
    a_logo = juve_logo if str(away_id) == JUVE_ID else (
        _diretta_stats_logo(data_espn, away_id, away_name)
        or f"https://a.espncdn.com/i/teamlogos/soccer/500/{away_id}.png"
    )
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
            total = h + a
            return None if total == 0 else int(h / total * 100)
        except Exception:
            return None

    def fmt_pct(val):
        try:
            v = float(str(val).replace("%", "").strip())
            if v <= 1.0:
                return f"{int(round(v*100))}%"
            return f"{int(round(v))}%"
        except Exception:
            return str(val)

    pos_h_raw = g("home", "possessionPct", "possessionpct", "possession", fallback="50")
    pos_a_raw = g("away", "possessionPct", "possessionpct", "possession", fallback="50")
    pos_h     = fmt_pct(pos_h_raw)
    pos_a     = fmt_pct(pos_a_raw)
    try:
        bp_perc = float(str(pos_h_raw).replace("%", ""))
        if bp_perc <= 1:
            bp_perc *= 100
        bp_perc = max(0.0, min(100.0, bp_perc))
    except Exception:
        bp_perc = 50.0
    pos_right_pct = f"{100.0 - bp_perc:.2f}%"
    pos_ring_class = " has-split" if 0.0 < bp_perc < 100.0 else ""

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

    stats_mappate = []
    xg = recupera_xg_espn(event_id, home_id, away_id)
    if xg is not None:
        xg_h, xg_a = xg
        stats_mappate.append(
            ("Expected Goals (xG)", xg_h, xg_a, perc(xg_h, xg_a))
        )

    stats_mappate.extend([
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
    ])

    def render_stat_row(label, h, a, hp):
        if hp is None:
            track_html = '<div class="track is-empty"></div>'
        else:
            hp = max(0, min(100, hp))
            split_class = " has-split" if 0 < hp < 100 else ""
            track_html = (
                f'<div class="track{split_class}" style="--split:{hp}%">'
                f'<div class="bar-left" style="width:{hp}%"></div>'
                f'<div class="bar-right" style="width:{100-hp}%"></div>'
                f'</div>'
            )
        return (
            f'<div class="row">'
            f'<div class="row-top">'
            f'<div class="value">{h}</div>'
            f'<div class="label">{label}</div>'
            f'<div class="value right">{a}</div>'
            f'</div>'
            f'{track_html}'
            f'</div>'
        )

    rows_html = "".join(
        render_stat_row(label, h, a, hp)
        for label, h, a, hp in stats_mappate
    )

    if pen_home > 0 or pen_away > 0:
        score_block_html = (
            f'<div class="score"><span>{home_goals}</span>'
            f'<span class="score-separator">-</span><span>{away_goals}</span></div>'
            f'<div class="pen-score">({pen_home} - {pen_away})</div>'
        )
    else:
        score_block_html = (
            f'<div class="score"><span>{home_goals}</span>'
            f'<span class="score-separator">-</span><span>{away_goals}</span></div>'
        )

    # Carica il template HTML esterno
    _template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats.html")
    try:
        with open(_template_path, "r", encoding="utf-8") as f:
            template = f.read()
    except FileNotFoundError:
        log_line("ERROR", "STATS", f"Template stats.html non trovato | {_template_path}")
        return None

    # Il colore principale dei temi Juventus segue il lato reale della squadra.
    if str(home_id) == JUVE_ID:
        _juve_side_class = "juve-home"
    elif str(away_id) == JUVE_ID:
        _juve_side_class = "juve-away"
    else:
        _juve_side_class = "no-juve"

    # Data del rendering in italiano, mostrata nel footer.
    _mesi_it = (
        "GENNAIO", "FEBBRAIO", "MARZO", "APRILE", "MAGGIO", "GIUGNO",
        "LUGLIO", "AGOSTO", "SETTEMBRE", "OTTOBRE", "NOVEMBRE", "DICEMBRE",
    )
    _now_match = datetime.now(ITALY_TZ)
    _match_date = f"{_now_match.day:02d} {_mesi_it[_now_match.month - 1]} {_now_match.year}"

    # Nel tema default i colori delle barre e dei bagliori arrivano dalle
    # uniform reali ESPN. Home/away/third mantengono la palette del bot.
    if juve_kit == "default":
        _home_dark = kit_analyzer.darken(home_color)
        _away_dark = kit_analyzer.darken(away_color)
        _dynamic_style = (
            f"\nbody.kit-default {{\n"
            f"  --body-glow1: {home_color}4D;\n"
            f"  --body-glow2: {away_color}38;\n"
            f"  --left:       {home_color};\n"
            f"  --left-dark:  {_home_dark};\n"
            f"  --right:      {away_color};\n"
            f"  --right-soft: {_away_dark};\n"
            f"  --left-text:  #ffffff;\n"
            f"  --right-text: #ffffff;\n"
            f"}}"
        )
    else:
        _dynamic_style = ""

    # Determina il tema maglia (home / away / third / default)
    html_content = (
        template
        .replace("{JUVE_KIT}",       juve_kit)
        .replace("{JUVE_SIDE_CLASS}", _juve_side_class)
        .replace("{DYNAMIC_STYLE}",  _dynamic_style)
        .replace("{LEAGUE_NAME}",    esc(league_name.upper()))
        .replace("{BADGE_LABEL}",    badge_label)
        .replace("{H_LOGO}",         h_logo)
        .replace("{HOME_NAME}",      home_name)
        .replace("{SCORE_BLOCK}",    score_block_html)
        .replace("{A_LOGO}",         a_logo)
        .replace("{AWAY_NAME}",      away_name)
        .replace("{POS_H}",          pos_h)
        .replace("{POS_A}",          pos_a)
        .replace("{POS_RIGHT_PCT}",  pos_right_pct)
        .replace("{POS_RING_CLASS}", pos_ring_class)
        .replace("{ROWS_HTML}",      rows_html)
        .replace("{MATCH_DATE}",     _match_date)
    )

    path_html      = "/tmp/stats.html"
    path_raw_png   = "/tmp/stats_raw.png"
    path_final_png = "/tmp/stats_final.png"

    with open(path_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-web-security", "--allow-running-insecure-content"])
        render_scale = 2.0 if hd_output else 1.0
        page = browser.new_page(
            viewport={"width": 1620, "height": 4000},
            device_scale_factor=render_scale,
        )
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
    try:
        base_img = Image.open(path_raw_png).convert("RGBA")
        if hd_output:
            raw_size = base_img.size
            base_img = base_img.resize((1920, 2560), Image.Resampling.LANCZOS)
            log_line(
                "DEBUG", "STATS", f"Output HD | {raw_size[0]}x{raw_size[1]} -> 1920x2560 (LANCZOS)"
            )

        if os.path.exists(texture_file):
            texture  = Image.open(texture_file).convert("RGBA").resize(base_img.size, Image.Resampling.LANCZOS)
            Image.alpha_composite(base_img, texture).convert("RGB").save(path_final_png, "PNG")
            log_line(
                "DEBUG", "STATS", f"Texture applicata | {texture_file} | {base_img.width}x{base_img.height}"
            )
            return path_final_png
        if hd_output:
            raise FileNotFoundError(
                f"Texture finale obbligatoria non trovata: {texture_file}"
            )
    except Exception as e:
        if hd_output:
            raise RuntimeError(f"Errore output HD/texture stats: {e}") from e
        log_line("DEBUG", "STATS", f"Texture non applicata: {e}")

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
    log_line("DEBUG", "ESPN", f"Ricerca partita | team_id={team_id}")

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
                        return {
                            "event_id":    event["id"],
                            "league_slug": slug,
                            "league_name": league_name,
                            "competitors": competitors,
                            "competition": competitions[0],
                            "date": event.get("date", ""),
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
        log_line("ERROR", "ESPN", f"Lettura evento fallita: {e}")
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
        log_line("WARN", "ESPN", f"Parsing stato partita fallito: {e}")
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
            log_line("DEBUG", "ESPN", f"Lettura shootout strutturato fallita: {e}")

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
        log_line("WARN", "SETUP", f"teams.json non trovato | {_TEAMS_JSON_PATH}; nomi non tradotti")
        return {}
    except Exception as e:
        log_line("ERROR", "SETUP", f"Caricamento teams.json fallito: {e}")
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
def _schedule_stats(state: dict, momento: str, delay: int = STATS_DELAY_SECONDS) -> bool:
    """Programma l'invio della grafica stats `delay` secondi dopo il cambio di
    stato (HT / 2H_END / FT), senza bloccare il ciclo live. Ritorna True se è
    stata aggiunta una nuova programmazione."""
    if momento in state.get("sent_stats", []):
        return False
    pend = state.setdefault("pending_stats", [])
    if any(p.get("momento") == momento for p in pend):
        return False
    pend.append({"momento": momento, "due": int(time.time()) + delay})
    log_line("WAIT", "STATS", f"{momento} programmate tra {delay}s")
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
        if rec.get("uid") and e.get("uid"):
            if rec["uid"] == e["uid"]:
                return True
            continue
        if (rec.get("player") == e["player_name"]
                and rec.get("type") == e["type"]
                and abs(int(rec.get("minute", 0)) - e["minute"]) <= 3):
            return True
    return False


def avvia_ciclo_partita():
    team_id = str(TEAM_ID).strip()
    progress_log = MatchProgressLog(
        heartbeat_minutes=LIVE_LOG_HEARTBEAT_MINUTES,
        heartbeat_seconds=LIVE_LOG_HEARTBEAT_MINUTES * 60,
    )

    try:
        test_r = SESSION.get(f"{ESPN_BASE}/ita.1/scoreboard",
                              params={"dates": datetime.now(ESPN_TZ).strftime("%Y%m%d")}, timeout=10)
    except Exception as e:
        log_line("WARN", "ESPN", f"Test connettività fallito: {e}")

    partita = trova_partita_oggi(team_id)
    if not partita:
        log_line("INFO", "MATCH", f"Nessuna partita trovata | team_id={team_id}")
        return

    event_id    = partita["event_id"]
    league_slug = partita["league_slug"]
    league_name = partita["league_name"]

    gist_ok, state = leggi_stato_da_gist()
    if not gist_ok:
        # Stato illeggibile per errore di rete/API: partire con uno stato
        # vergine rimanderebbe tutti i messaggi già pubblicati. Meglio uscire.
        log_line("ERROR", "STATE", "Gist illeggibile dopo i retry; arresto anti-duplicati")
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
                log_line(
                    "STOP",
                    "MATCH",
                    f"Partita già conclusa | {home_name} {g_home}-{g_away} {away_name}; nessun invio",
                )
                sys.exit(0)

            events = parse_events(data, home_name_raw, away_name_raw, home_id, away_id)

            if "_intro_logged" not in state:
                log_line(
                    "EVENT",
                    "MATCH",
                    f"Partita trovata | {league_name} | {home_name} vs {away_name} | event_id={event_id}",
                )
                for raw, translated in ((home_name_raw, home_name), (away_name_raw, away_name)):
                    t = translate_team(raw)
                    in_map = bool(TEAM_MAP.get(raw) or any(k.lower() == raw.lower() for k in TEAM_MAP))
                    if raw != t:
                        log_line("DEBUG", "TEAMS", f"Traduzione | {raw} -> {esc(t)}")
                    elif not in_map:
                        log_line("DEBUG", "TEAMS", f"Nome ESPN non mappato | {raw}")
                state["_intro_logged"] = True


            _now_ts = int(time.time())
            if status != "NS" and progress_log.should_emit(
                status, elapsed, g_home, g_away, _now_ts
            ):
                log_line(
                    "LIVE",
                    "MATCH",
                    f"{status} {elapsed}' | {home_name} {g_home}-{g_away} {away_name}",
                )

            # --- Invio stats programmato (5 min dopo il cambio di stato) ---
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
                                                         _momento, league_name, league_slug=league_slug,
                                                         event_id=event_id)
                if send_telegram_stats_photo(png_path, _momento, f"{e_comp} {hashtag}"):
                    log_line("OK", "STATS", f"{_momento} | foto Telegram inviata")
                    state["sent_stats"].append(_momento)
                    salva_stato_su_gist(state)
                else:
                    # Invio non riuscito: rimetto in coda per un nuovo tentativo
                    # a breve, invece di segnare le stats come inviate e perderle.
                    log_line("RETRY", "STATS", f"{_momento} non inviata; nuovo tentativo tra 30s")
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
                            log_line("STOP", "MATCH", f"Kickoff tra {minutes_to_kickoff:.0f} min; avvio troppo anticipato")
                            sys.exit(0)
                        if "_ns_logged" not in state:
                            log_line("WAIT", "MATCH", f"Calcio d'inizio tra {minutes_to_kickoff:.0f} min")
                            state["_ns_logged"] = True
                except Exception as e:
                    log_line("WARN", "MATCH", f"Orario partita non leggibile: {e}")
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
                    log_line("OK", "TELEGRAM", "GOAL ANNULLATO inviato | retry riuscito")
                    state["cancel_msg_id"] = _retry_cancel_id
                    state["pending_goal_annullato"] = None
                    state_changed = True
                else:
                    log_line("RETRY", "TELEGRAM", "GOAL ANNULLATO non inviato; nuovo tentativo al prossimo ciclo")

            # --- Inizio primo tempo ---
            if status == "1H" and "1H" not in state["sent_periods"]:
                msg_id = send_telegram_get_id(f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{home_name} - {away_name}\n\n{e_comp} {hashtag}")
                if msg_id:
                    log_line("EVENT", "MATCH", "INIZIO PARTITA | Telegram inviato")
                    state["sent_periods"].append("1H")
                    salva_stato_su_gist(state)
                    state_changed = True
                else:
                    log_line("RETRY", "TELEGRAM", "INIZIO PARTITA non inviato; nuovo tentativo al prossimo ciclo")

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
                    actual_tid = goal_scoring_team_id(ge, home_id, away_id)
                    if actual_tid == home_id:
                        ch += 1
                    else:
                        ca += 1

                    p_name = ge.get("player_name", "")
                    a_name = ge.get("assist_name", "")
                    scorer_line, assist_line = goal_player_lines(
                        p_name, a_name, ge["type"], actual_tid
                    )

                    if actual_tid == home_id:
                        goal_score = f"<b>{home_name} {ch}</b>-{ca} {away_name}"
                    else:
                        goal_score = f"{home_name} {ch}-<b>{ca} {away_name}</b>"

                    goal_text = f"<b>GOAL · {ge['minute']}\' {E_MIC}</b>\n\n{goal_score}\n{scorer_line}{assist_line}\n{e_comp} {hashtag}"
                    goal_key  = f"{ch}_{ca}"

                    rendered_goal = prepara_grafica_goal(
                        data_espn=data,
                        scorer_name=p_name,
                        goal_type=ge["type"],
                        scoring_team_id=actual_tid,
                        minute=ge["minute"],
                        home_name=home_name_raw,
                        away_name=away_name_raw,
                        home_id=home_id,
                        away_id=away_id,
                        home_goals=ch,
                        away_goals=ca,
                        league_slug=league_slug,
                        league_name=league_name,
                        event_key=f"{event_id}|{goal_key}",
                    )
                    msg_id, sent_as_photo = send_telegram_goal_get_id(
                        goal_text,
                        rendered_goal.png if rendered_goal else None,
                    )
                    if not msg_id:
                        # Invio non riuscito: interrompo il recupero. Annullo
                        # l'incremento di questo gol (non annunciato) e lascio che sia
                        # il rilevamento live a riprovare i gol rimanenti.
                        log_line("RETRY", "TELEGRAM", f"GOAL {ge['minute']}' non inviato | {home_name} {ch}-{ca} {away_name}")
                        if actual_tid == home_id:
                            ch -= 1
                        else:
                            ca -= 1
                        break
                    log_line("EVENT", "MATCH", f"GOAL {ge['minute']}' | {home_name} {ch}-{ca} {away_name} | Telegram inviato")
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
                        "is_photo":  sent_as_photo,
                        "graphic_kit": rendered_goal.kit if rendered_goal and sent_as_photo else None,
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
                        log_line("EVENT", "MATCH", f"FINE 1° TEMPO | {home_name} {g_home}-{g_away} {away_name} | Telegram inviato")
                        state["sent_periods"].append("HT")
                        _schedule_stats(state, "HT")
                        salva_stato_su_gist(state)
                        state_changed = True
                    else:
                        log_line("RETRY", "TELEGRAM", "FINE 1° TEMPO non inviato; nuovo tentativo al prossimo ciclo")
                elif "HT" not in state["sent_stats"]:
                    # Recovery: messaggio HT già inviato in un run precedente ma
                    # stats mai partite (es. crash) → riprogramma
                    if _schedule_stats(state, "HT"):
                        state_changed = True

            # --- Inizio secondo tempo ---
            if status == "2H" and "2H" not in state["sent_periods"]:
                msg_id = send_telegram_get_id(f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                if msg_id:
                    log_line("EVENT", "MATCH", "INIZIO 2° TEMPO | Telegram inviato")
                    state["sent_periods"].append("2H")
                    salva_stato_su_gist(state)
                    state_changed = True
                else:
                    log_line("RETRY", "TELEGRAM", "INIZIO 2° TEMPO non inviato; nuovo tentativo al prossimo ciclo")

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
                        log_line("EVENT", "MATCH", f"FINE REGOLAMENTARI | {home_name} {g_home}-{g_away} {away_name} | Telegram inviato")
                        state["sent_periods"].append("2H_END")
                        _schedule_stats(state, "2H_END")
                        salva_stato_su_gist(state)
                        state_changed = True
                    else:
                        log_line("RETRY", "TELEGRAM", "FINE REGOLAMENTARI non inviato; nuovo tentativo al prossimo ciclo")
            elif status != "BREAK_ET":
                state["_break_et_seen"] = 0

            # Recovery: ESPN non ha mai esposto la pausa (o il bot era giù) e lo
            # status è già ET/PEN/AET → invia ora. L'INIZIO 1T SUPPLEMENTARE
            # partirà comunque al ciclo successivo grazie a _2h_end_gia_inviato.
            if status in ("ET", "PEN", "AET") and "2H_END" not in state["sent_periods"] and "FT" not in state["sent_periods"]:
                msg_id = send_telegram_get_id(f"<b>FINE REGOLAMENTARI {E_FLAG}</b>\n\n{score_str}\n\n{e_comp} {hashtag}")
                if msg_id:
                    log_line("EVENT", "MATCH", f"FINE REGOLAMENTARI | {home_name} {g_home}-{g_away} {away_name} | Telegram inviato")
                    state["sent_periods"].append("2H_END")
                    if status == "ET":
                        _schedule_stats(state, "2H_END")
                    salva_stato_su_gist(state)
                    state_changed = True
                else:
                    log_line("RETRY", "TELEGRAM", "FINE REGOLAMENTARI non inviato; nuovo tentativo al prossimo ciclo")
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
                    log_line("WAIT", "MATCH", f"Punteggio instabile | {g_home}-{g_away} -> {g_home_c}-{g_away_c}; attendo conferma")
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
                        scoring_tid = goal_scoring_team_id(
                            _last_ev, home_id, away_id
                        )
                    else:
                        scoring_tid = home_id if g_home >= g_away else away_id
                    log_line("WARN", "MATCH", f"Punteggio incoerente | prima={prev_home}-{prev_away} | ora={g_home}-{g_away}; marcatore dedotto dal feed")

                # Flag: True solo se il gol è stato realmente annunciato (ora o in passato).
                # Il contatore avanzerà SOLO in quel caso.
                goal_announced = False

                if scoring_tid:
                    candidates = sorted(
                        [
                            e for e in goal_events
                            if goal_scoring_team_id(e, home_id, away_id) == scoring_tid
                        ],
                        key=lambda x: (x["minute"], x.get("seq", 0)),
                    )

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
                        log_line("WARN", "ESPN", "GOAL rilevato senza marcatore; invio provvisorio")
                        player_name = ""
                        assist_name = ""
                        goal_minute = elapsed
                        goal_type   = "goal"

                    actual_scoring_tid = scoring_tid
                    scorer_line, assist_line = goal_player_lines(
                        player_name,
                        assist_name,
                        goal_type,
                        actual_scoring_tid,
                    )

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
                        rendered_goal = prepara_grafica_goal(
                            data_espn=data,
                            scorer_name=player_name,
                            goal_type=goal_type,
                            scoring_team_id=actual_scoring_tid,
                            minute=goal_minute,
                            home_name=home_name_raw,
                            away_name=away_name_raw,
                            home_id=home_id,
                            away_id=away_id,
                            home_goals=g_home,
                            away_goals=g_away,
                            league_slug=league_slug,
                            league_name=league_name,
                            event_key=f"{event_id}|{goal_key}",
                        )
                        msg_id, sent_as_photo = send_telegram_goal_get_id(
                            goal_text,
                            rendered_goal.png if rendered_goal else None,
                        )
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
                                "is_photo":  sent_as_photo,
                                "graphic_kit": rendered_goal.kit if rendered_goal and sent_as_photo else None,
                            }
                            state_changed = True
                            goal_announced = True
                            log_line("EVENT", "MATCH", f"GOAL{_scorer_log}{_assist_log} | {home_name} {g_home}-{g_away} {away_name} | Telegram inviato")
                        else:
                            # Invio NON riuscito: non avanzo il contatore così al ciclo
                            # successivo il bot rientra qui e riprova (il gol non si perde).
                            log_line("RETRY", "TELEGRAM", f"GOAL non inviato | {home_name} {g_home}-{g_away} {away_name}; nuovo tentativo al prossimo ciclo")

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
                log_line("WAIT", "MATCH", "Possibile GOAL ANNULLATO; conferma tra 120s")
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
                        log_line("EVENT", "MATCH", "GOAL ANNULLATO | Telegram inviato")
                        state["cancel_msg_id"] = cancel_msg_id
                    else:
                        # Invio non riuscito: lo score sotto va comunque aggiornato (è
                        # già confermato), ma il messaggio resta in coda e viene
                        # ritentato a ogni ciclo finché non va a buon fine.
                        log_line("RETRY", "TELEGRAM", "GOAL ANNULLATO non inviato; nuovo tentativo al prossimo ciclo")
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
                    log_line("INFO", "MATCH", f"Punteggio stabile | {g_home_c}-{g_away_c}; aggiorno gli eventi")

                    # Se avevamo già inviato un "GOAL ANNULLATO" per errore, cancellalo
                    if state.get("cancel_msg_id"):
                        log_line("INFO", "TELEGRAM", "Rimuovo GOAL ANNULLATO falso positivo")
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
                        log_line(
                            "EVENT",
                            "MATCH",
                            f"Rigori decisi | {_hp_check.count(E_PEN_OK)}-{_ap_check.count(E_PEN_OK)}; "
                            "non attendo lo stato post di ESPN",
                        )
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
                        log_line(
                            "RETRY",
                            "MATCH",
                            f"Partita finita con GOAL in sospeso | "
                            f"{state.get('goals_detected', 0)}/{g_home + g_away} | tentativo {_retries + 1}/5",
                        )
                        time.sleep(sleep_time)
                        continue
                    log_line("ERROR", "MATCH", "GOAL in sospeso non inviato dopo 5 tentativi; chiusura forzata")

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
                            if goal_scoring_team_id(e, home_id, away_id) != team_id:
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

                    # Foto Canva solo per le partite ufficiali della Juve:
                    # nelle amichevoli il messaggio finale parte come solo testo.
                    is_juve_match = home_id == JUVE_ID or away_id == JUVE_ID
                    is_friendly   = is_friendly_competition(league_slug, league_name)
                    if is_juve_match and not is_friendly:
                        # Kit Juve (home/away/third) dagli stessi dati ESPN già
                        # disponibili, per scegliere la pagina Canva corretta.
                        try:
                            _competitors = data["header"]["competitions"][0]["competitors"]
                        except Exception:
                            _competitors = []
                        _boxscore_teams = (data.get("boxscore") or {}).get("teams", [])
                        _fallback_kit = determina_kit(home_id, away_id, league_slug, league_name)
                        _kit_result = kit_analyzer.analizza(
                            home_name=home_name, away_name=away_name,
                            home_id=home_id, away_id=away_id,
                            league_name=league_name,
                            competitors=_competitors, boxscore_teams=_boxscore_teams,
                            fallback_kit=_fallback_kit,
                        )
                        juve_kit_finale = _kit_result["kit"]
                        pagina_canva = PAGINA_PER_KIT.get(juve_kit_finale, PAGINA_TARGET)
                        log_line("DEBUG", "CANVA", f"Kit finale={juve_kit_finale} | pagina={pagina_canva}")

                        canva_token = get_valid_token()
                        foto = get_canva_image(canva_token, pagina_canva) if canva_token else None
                        ft_sent = send_telegram_with_photo(msg_finale, foto)
                    else:
                        if is_juve_match and is_friendly:
                            log_line("DEBUG", "CANVA", "Amichevole; foto finale saltata")
                        ft_sent = send_telegram_get_id(msg_finale) is not None

                    if not ft_sent:
                        log_line("RETRY", "TELEGRAM", "FINE PARTITA non inviata; nuovo tentativo al prossimo ciclo")
                        time.sleep(sleep_time)
                        continue

                    log_line("EVENT", "MATCH", f"FINE PARTITA | {home_name} {g_home}-{g_away} {away_name} | Telegram inviato")
                    # Persisti SUBITO: se il bot muore durante l'attesa delle stats,
                    # al riavvio il messaggio finale non verrà reinviato.
                    state["sent_periods"].append("FT")
                    salva_stato_su_gist(state)
                    state_changed = True

                # --- Stats fine partita: 5 minuti dopo il messaggio finale ---
                # (attesa "a fette": la partita è finita, non c'è altro da monitorare)
                if "FT" not in state["sent_stats"]:
                    log_line("WAIT", "STATS", f"FINE PARTITA | generazione tra {STATS_DELAY_SECONDS}s")
                    for _ in range(STATS_DELAY_SECONDS // 5):
                        time.sleep(5)
                    data_fresh = fetch_evento(event_id, league_slug) or data
                    _ftp_h, _ftp_a = _rigori_icone(data_fresh, events, home_id, away_id,
                                                   home_name_raw, away_name_raw)
                    ft_pen_home = _ftp_h.count(E_PEN_OK)
                    ft_pen_away = _ftp_a.count(E_PEN_OK)
                    png_path = recupera_e_genera_stats_html(data_fresh, home_id, away_id,
                                                             home_name, away_name, g_home, g_away,
                                                             "FT", league_name, league_slug=league_slug,
                                                             pen_home=ft_pen_home, pen_away=ft_pen_away,
                                                             event_id=event_id)
                    # Il bot sta per spegnersi: niente "prossimo ciclo" che possa
                    # ritentare da solo, quindi ritento qui sul posto prima di
                    # rinunciare, invece di segnare le stats come inviate a prescindere.
                    ft_stats_ok = False
                    for _attempt in range(5):
                        if send_telegram_stats_photo(png_path, "FT", f"{e_comp} {hashtag}"):
                            ft_stats_ok = True
                            break
                        log_line("RETRY", "STATS", f"FINE PARTITA non inviate | tentativo {_attempt + 1}/5 | attesa 10s")
                        time.sleep(10)
                    if ft_stats_ok:
                        log_line("OK", "STATS", "FINE PARTITA | foto Telegram inviata")
                        state["sent_stats"].append("FT")
                    else:
                        log_line("ERROR", "STATS", "FINE PARTITA non inviate dopo 5 tentativi; proseguo con lo spegnimento")
                    salva_stato_su_gist(state)
                    state_changed = True

                state["_reset_done"] = True
                resetta_gist()
                log_line("STOP", "SYSTEM", f"Live Score terminato | {home_name} {g_home}-{g_away} {away_name}")
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
                    idx = gh - 1
                else:
                    idx = ga - 1

                candidates = sorted(
                    [
                        e for e in goal_events_all
                        if goal_scoring_team_id(e, s_home_id, s_away_id) == s_tid
                    ],
                    key=lambda x: (x["minute"], x.get("seq", 0)),
                )

                if idx < 0 or idx >= len(candidates):
                    continue

                current = candidates[idx]
                current_scorer = current.get("player_name", "")
                current_assist = current.get("assist_name", "")
                current_type = current.get("type", saved.get("type", "goal"))

                if (_norm_name(current_scorer) != _norm_name(saved.get("scorer", ""))) or \
                   (_norm_name(current_assist) != _norm_name(saved.get("assist", ""))) or \
                   (current_type != saved.get("type", "goal")):

                    actual_tid = s_tid
                    scorer_line_new, assist_line_new = goal_player_lines(
                        current_scorer,
                        current_assist,
                        current_type,
                        actual_tid,
                    )

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

                    rendered_correction = prepara_grafica_goal(
                        data_espn=data,
                        scorer_name=current_scorer,
                        goal_type=current_type,
                        scoring_team_id=actual_tid,
                        minute=_min_disp_new,
                        home_name=home_name_raw,
                        away_name=away_name_raw,
                        home_id=s_home_id,
                        away_id=s_away_id,
                        home_goals=gh,
                        away_goals=ga,
                        league_slug=league_slug,
                        league_name=league_name,
                        event_key=f"{event_id}|{goal_key}",
                    )
                    was_photo = bool(saved.get("is_photo"))
                    edit_ok, new_msg_id, new_is_photo = replace_corrected_goal_message(
                        msg_id,
                        was_photo,
                        goal_text_new,
                        rendered_correction,
                    )

                    if edit_ok:
                        log_line("EDIT", "MATCH", f"GOAL {goal_key} corretto | {', '.join(changes)}")
                        state["goal_messages"][goal_key]["msg_id"]     = new_msg_id
                        state["goal_messages"][goal_key]["scorer"]    = current_scorer
                        state["goal_messages"][goal_key]["assist"]    = current_assist
                        state["goal_messages"][goal_key]["type"]      = current_type
                        state["goal_messages"][goal_key]["score_tid"] = actual_tid
                        state["goal_messages"][goal_key]["is_photo"]  = new_is_photo
                        state["goal_messages"][goal_key]["graphic_kit"] = (
                            rendered_correction.kit
                            if rendered_correction and new_is_photo else None
                        )
                        state_changed = True
                    else:
                        log_line("RETRY", "TELEGRAM", f"Correzione GOAL {goal_key} fallita | {', '.join(changes)}")

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

                # Cerca slot già inviato per questo team + stesso periodo (tempo di
                # gioco) + minuto compatibile (±2'). Il controllo sul periodo evita
                # che un cambio al 44' di un tempo venga unito a uno al 45' del tempo
                # successivo, separati dall'intervallo.
                slot_key = None
                for k, slot in state["sent_subs"].items():
                    if (k.split(":")[0] == e["team_id"]
                            and slot.get("period", 1) == e.get("period", 1)
                            and abs(slot["minute"] - e["minute"]) <= 2):
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
                    log_line("EDIT", "MATCH", f"CAMBIO {team_title} {slot['minute']}' corretto | {log_dir}")
                    state_changed = True
                else:
                    log_line("RETRY", "TELEGRAM", f"Correzione CAMBIO {team_title} {slot['minute']}' fallita | {log_dir}")

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
                    log_line("EDIT", "MATCH", f"CAMBIO {team_title} {slot['minute']}' | entra: {ins_str} | esce: {outs_str}")
                    state_changed = True
                else:
                    log_line("RETRY", "TELEGRAM", f"Edit CAMBIO {team_title} {slot['minute']}' fallito | entra: {_e_in} | esce: {_e_out}")

            if new_subs_fresh:
                log_line("WAIT", "MATCH", "CAMBIO rilevato; raggruppamento per 10s")
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
                        if (k.split(":")[0] == e["team_id"]
                                and slot.get("period", 1) == e.get("period", 1)
                                and abs(slot["minute"] - e["minute"]) <= 2):
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
                            log_line("EDIT", "MATCH", f"CAMBIO raggruppato {team_title} {slot['minute']}' | entra: {ins_str} | esce: {outs_str}")
                            state_changed = True
                        else:
                            log_line("RETRY", "TELEGRAM", f"Edit CAMBIO raggruppato {team_title} {slot['minute']}' fallito | entra: {_in_p} | esce: {_out_p}")
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
                        if (g["team_id"] == sub["team_id"]
                                and g.get("period", 1) == sub.get("period", 1)
                                and abs(g["minute"] - sub["minute"]) <= 2):
                            g["subs"].append(sub)
                            placed = True
                            break
                    if not placed:
                        groups.append({"team_id": sub["team_id"], "minute": sub["minute"],
                                        "period": sub.get("period", 1), "subs": [sub]})

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
                        log_line("EVENT", "MATCH", f"CAMBIO {team_title} {_min_ref}' | entra: {ins_str} | esce: {outs_str} | Telegram inviato")
                        # La chiave include il periodo per evitare collisioni tra
                        # cambi allo stesso minuto "nominale" ma in tempi diversi.
                        new_key = f"{g['team_id']}:{g.get('period', 1)}:{_min_ref}"
                        state["sent_subs"][new_key] = {
                            "msg_id":  msg_id,
                            "minute":  _min_ref,
                            "period":  g.get("period", 1),
                            "ins":     [fmt_player(s["assist_name"]) for s in g["subs"]],
                            "outs":    [fmt_player(s["player_name"]) for s in g["subs"]],
                            "sub_ids": [s["uid"] for s in g["subs"]],
                        }
                        state_changed = True
                    else:
                        # Invio NON riuscito: non salvo lo slot né i sub_ids, così
                        # al ciclo successivo il cambio viene rilevato come nuovo
                        # e ritentato, esattamente come per i gol.
                        log_line("RETRY", "TELEGRAM", f"CAMBIO {team_title} {_min_ref}' non inviato | entra: {ins_str} | esce: {outs_str}")

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
                            log_line("EVENT", "MATCH", f"{label} {e['minute']}' | {p_name} | Telegram inviato")
                            state["sent_cards"].append(card_id)
                            state_changed = True

            # --- Rigori sbagliati (solo durante il gioco: nella lotteria dei
            # rigori l'esito di ogni calcio lo annuncia già il blocco RIGORI) ---
            for e in events:
                regular_penalty = (
                    status not in ("PEN", "BREAK_PEN")
                    and e["type"] in ("penalty missed", "penalty saved")
                )
                shootout_save = e["type"] == "shootout saved"
                if regular_penalty or shootout_save:
                    if _failpen_gia_inviato(state, e):
                        continue
                    team_name = home_name if e["team_id"] == home_id else away_name
                    opponent_id = away_id if str(home_id) == JUVE_ID else (
                        home_id if str(away_id) == JUVE_ID else ""
                    )
                    is_juve_save = (
                        e["type"] in ("penalty saved", "shootout saved")
                        and bool(opponent_id)
                        and str(e["team_id"]) == str(opponent_id)
                    )
                    goalkeeper_name = (
                        trova_portiere_juve(data, e.get("assist_name", ""))
                        if is_juve_save else ""
                    )
                    rendered_saved = None
                    if goalkeeper_name:
                        rendered_saved = prepara_grafica_parata_rigore(
                            data_espn=data,
                            penalty_event=e,
                            goalkeeper_name=goalkeeper_name,
                            minute=e.get("minute_disp", e["minute"]),
                            home_name=home_name_raw,
                            away_name=away_name_raw,
                            home_id=home_id,
                            away_id=away_id,
                            home_goals=g_home,
                            away_goals=g_away,
                            event_key=f"{event_id}|saved|{e.get('uid', '')}",
                            league_slug=league_slug,
                            league_name=league_name,
                        )
                        penalty_text = (
                            f"<b>RIGORE PARATO · {e['minute']}' {E_KICK}</b>\n\n"
                            f"🧤 <i>{fmt_player(goalkeeper_name)}</i>\n"
                            f"{E_PEN_KO} <i>{fmt_player(e['player_name'])}</i>\n\n"
                            f"{e_comp} {hashtag}"
                        )
                        msg_id, _ = send_telegram_saved_get_id(
                            penalty_text,
                            rendered_saved.png if rendered_saved else None,
                        )
                    else:
                        # Nella lotteria il mancato riconoscimento del portiere
                        # non crea un doppione: resta il messaggio RIGORI aggregato.
                        if shootout_save:
                            continue
                        msg_id = send_telegram_get_id(
                            f"<b>RIGORE SBAGLIATO {team_name.upper()} · {e['minute']}' {E_KICK}</b>\n\n"
                            f"{E_PEN_KO} <i>{fmt_player(e['player_name'])}</i>\n\n"
                            f"{e_comp} {hashtag}"
                        )
                    if msg_id:
                        label = "RIGORE PARATO" if goalkeeper_name else "RIGORE SBAGLIATO"
                        log_line("EVENT", "MATCH", f"{label} {team_name.upper()} {e['minute']}' | {fmt_player(e['player_name'])} | Telegram inviato")
                        state["sent_failed_penalties"].append({
                            "player": e["player_name"],
                            "type":   e["type"],
                            "minute": e["minute"],
                            "uid":    e.get("uid", ""),
                        })
                        state_changed = True

        except Exception as e:
            log_line("ERROR", "SYSTEM", f"Ciclo live fallito: {e}")
            sleep_time = 6

        finally:
            if isinstance(state, dict) and not state.get("_reset_done") and state_changed:
                salva_stato_su_gist(state)

        time.sleep(sleep_time)

# ==============================================================================
# MAIN
# ==============================================================================
def main():
    channel = os.getenv("LIVE_SCORE_CHANNEL_NAME", "Juventus Reborn")
    graphics = "on" if GOAL_GRAPHICS_ENABLED else "off"
    log_line(
        "START",
        "SYSTEM",
        f"Live Score avviato | team_id={TEAM_ID} | canale={channel} | grafiche={graphics}",
    )

    if str(os.getenv('ONLY_REFRESH_TOKEN', '')).strip().lower() == "true":
        get_valid_token()
        return

    # Il workflow può aver già sincronizzato i loghi prima di pubblicarli.
    # L'avvio diretto, o un primo tentativo fallito, mantiene il sync interno.
    if GOAL_GRAPHICS_ENABLED and os.getenv('FCLOGO_SYNC_DONE', '').strip().lower() != 'true':
        try:
            report = fclogo_sync.sync_current_season()
            log_line("DEBUG", "GRAPHICS", report.summary())
            for warning in report.errors:
                log_line("WARN", "GRAPHICS", f"FCLogo: {warning}")
        except Exception as exc:
            # Un problema del catalogo grafico non deve mai bloccare il live.
            log_line("WARN", "GRAPHICS", f"FCLogo non sincronizzato: {exc}")

    avvia_ciclo_partita()

if __name__ == "__main__":
    main()
