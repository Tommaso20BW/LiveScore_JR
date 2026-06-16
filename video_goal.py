#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Goal Video Bot (cartella goal/ del repo LiveScore_JR)
=====================================================
NON gira in polling: viene avviato da LiveScore_JR tramite repository_dispatch
ESCLUSIVAMENTE quando viene segnato un gol. Riceve marcatore e punteggio nel
client_payload (passati come variabili d'ambiente dal workflow), cerca il video
del gol su Reddit (r/soccer), scarica l'mp4 e lo invia COME VIDEO a un CANALE
DIVERSO da quello del live score.

Variabili d'ambiente (dal workflow):
  TELEGRAM_TOKEN       token del bot (stesso bot del live score)
  TELEGRAM_TO_GOALS    chat id del canale DEDICATO ai video dei gol
  SCORER               marcatore
  HOME_N, AWAY_N       nomi (brevi) delle due squadre
  G_HOME, G_AWAY       punteggio dopo il gol
  MINUTE               minuto del gol
  GOAL_SEARCH_TIMEOUT  secondi max di ricerca video (default 480)
  SEND_TEXT_FALLBACK   "1"/"0": se non trova il video manda comunque il testo
"""

import os
import re
import sys
import time
import html
import tempfile
import unicodedata

import requests

# --------------------------------------------------------------------------- #
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_TO = os.environ.get("TELEGRAM_TO_GOALS", "").strip()   # canale gol!

SCORER = os.environ.get("SCORER", "").strip()
HOME_N = os.environ.get("HOME_N", "").strip()
AWAY_N = os.environ.get("AWAY_N", "").strip()
HOME_RAW = os.environ.get("HOME_RAW", "").strip()   # nomi originali ESPN (match)
AWAY_RAW = os.environ.get("AWAY_RAW", "").strip()
G_HOME = os.environ.get("G_HOME", "").strip()
G_AWAY = os.environ.get("G_AWAY", "").strip()
MINUTE = os.environ.get("MINUTE", "").strip()

GOAL_SEARCH_TIMEOUT = int(os.environ.get("GOAL_SEARCH_TIMEOUT", "480"))  # 8 min
SEND_TEXT_FALLBACK = os.environ.get("SEND_TEXT_FALLBACK", "1").strip() != "0"

REDDIT_RETRY_SECONDS = 25
TELEGRAM_MAX_BYTES = 49 * 1024 * 1024

# Reddit OAuth (app-only): da GitHub Actions le chiamate anonime vengono spesso
# bloccate (403/429). Con un'app "script" gratuita l'accesso è affidabile.
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "").strip()
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "").strip()

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
REDDIT_UA = "juve-goal-video-bot/1.0 (by u/anonymous)"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": BROWSER_UA})


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# --------------------------------------------------------------------------- #
# Normalizzazione testo
# --------------------------------------------------------------------------- #
_TRANS = str.maketrans({
    "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
    "ø": "o", "Ø": "o", "ł": "l", "Ł": "l", "đ": "d", "Đ": "d", "ð": "d",
    "ß": "ss", "æ": "ae", "œ": "oe",
})


def deaccent(s: str) -> str:
    s = (s or "").translate(_TRANS)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


# --------------------------------------------------------------------------- #
# Telegram
# --------------------------------------------------------------------------- #
def tg_api(method):
    return f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"


def tg_send_message(text):
    try:
        r = SESSION.post(tg_api("sendMessage"),
                         data={"chat_id": TELEGRAM_TO, "text": text,
                               "parse_mode": "HTML"}, timeout=30)
        log("sendMessage:", r.status_code)
        return r.ok
    except Exception as e:
        log("sendMessage error:", e)
        return False


def tg_send_video(file_path, caption):
    try:
        with open(file_path, "rb") as f:
            r = SESSION.post(tg_api("sendVideo"),
                             data={"chat_id": TELEGRAM_TO, "caption": caption,
                                   "parse_mode": "HTML", "supports_streaming": "true"},
                             files={"video": ("goal.mp4", f, "video/mp4")},
                             timeout=300)
        log("sendVideo:", r.status_code, r.text[:200])
        return r.ok
    except Exception as e:
        log("sendVideo error:", e)
        return False


# --------------------------------------------------------------------------- #
# Reddit -> trova post del gol
# --------------------------------------------------------------------------- #
VIDEO_HOST_HINTS = (
    "streamff", "streamin", "streamja", "streamye", "streamgg", "streamvi",
    "dubz", "streamable", "juststream", "clippituser", "streamwo", "streamon",
    "v.redd.it", "imgur",
)


_REDDIT_TOKEN = None


def reddit_token():
    """Token app-only di Reddit (se sono configurati i secret). In cache."""
    global _REDDIT_TOKEN
    if _REDDIT_TOKEN:
        return _REDDIT_TOKEN
    if not (REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET):
        return None
    try:
        r = requests.post("https://www.reddit.com/api/v1/access_token",
                          auth=(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET),
                          data={"grant_type": "client_credentials"},
                          headers={"User-Agent": REDDIT_UA}, timeout=20)
        if r.ok:
            _REDDIT_TOKEN = r.json().get("access_token")
            log("Reddit OAuth: token ottenuto ✅")
            return _REDDIT_TOKEN
        log(f"Reddit OAuth fallito: {r.status_code} {r.text[:120]}")
    except Exception as e:
        log("Reddit OAuth error:", e)
    return None


def _reddit_fetch(path, params):
    """GET su Reddit: usa oauth.reddit.com se c'è il token, altrimenti
    www.reddit.com (anonimo, spesso bloccato dai server). Logga stato e conteggio."""
    tok = reddit_token()
    headers = {"User-Agent": REDDIT_UA}
    if tok:
        headers["Authorization"] = f"bearer {tok}"
        url = "https://oauth.reddit.com" + path
    else:
        url = "https://www.reddit.com" + path + ".json"
    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        if not r.ok:
            log(f"  reddit {path} -> HTTP {r.status_code}: {r.text[:120]}")
            return []
        children = r.json().get("data", {}).get("children", [])
        log(f"  reddit {path} -> {r.status_code}, {len(children)} post")
        return children
    except Exception as e:
        log(f"  reddit {path} error:", e)
        return []


def reddit_new_posts(limit=80):
    return _reddit_fetch("/r/soccer/new", {"limit": limit})


def reddit_search(query, limit=40):
    return _reddit_fetch("/r/soccer/search",
                         {"q": query, "restrict_sr": 1, "sort": "new",
                          "t": "hour", "limit": limit})


def candidate_video_url(post):
    d = post.get("data", {})
    media = d.get("secure_media") or d.get("media") or {}
    rv = (media or {}).get("reddit_video")
    if rv and rv.get("fallback_url"):
        return rv["fallback_url"]
    url = d.get("url_overridden_by_dest") or d.get("url") or ""
    return url or None


def _title_score_matches(title):
    """True se nel titolo compare il punteggio del nostro gol (immune dalla
    lingua: sono solo numeri, es. '[2] - 1'). Confronto come insieme così
    l'ordine casa/trasferta non conta."""
    if not (G_HOME.isdigit() and G_AWAY.isdigit()):
        return None  # punteggio non disponibile -> non filtrare
    want = {int(G_HOME), int(G_AWAY)}
    for a, b in re.findall(r"\[?(\d{1,2})\]?\s*[-–]\s*\[?(\d{1,2})\]?", title):
        if {int(a), int(b)} == want:
            return True
    return False


def _title_has_team(title_norm):
    """True se nel titolo (normalizzato) compare un token significativo di una
    delle due squadre, usando i nomi ORIGINALI (non tradotti)."""
    tokens = []
    for raw in (HOME_RAW, AWAY_RAW):
        tokens += [t for t in deaccent(raw).split() if len(t) >= 4]
    if not tokens:
        return None  # nomi non disponibili -> non filtrare
    return any(t in title_norm for t in tokens)


def find_goal_post(scorer, since_ts):
    surname = deaccent(scorer).split()[-1] if scorer.strip() else ""
    tokens = [t for t in deaccent(scorer).split() if len(t) >= 4]
    if not surname:
        return

    posts = reddit_new_posts(limit=80) + reddit_search(surname, limit=40)

    matched, seen = [], set()
    for p in posts:
        d = p.get("data", {})
        pid = d.get("id")
        if pid in seen:
            continue
        seen.add(pid)

        title = d.get("title", "")
        title_norm = deaccent(title)
        created = d.get("created_utc", 0)
        if created < since_ts - 150:
            continue
        # marcatore nel titolo
        if surname not in title_norm and not any(t in title_norm for t in tokens):
            continue
        # sembra un post-gol con video
        url = (d.get("url_overridden_by_dest") or d.get("url") or "").lower()
        looks_goal = bool(re.search(r"\[\d+\]|\d+\s*-\s*\d+", title))
        has_host = any(h in url for h in VIDEO_HOST_HINTS) or bool(
            (d.get("secure_media") or d.get("media") or {}).get("reddit_video"))
        if not (looks_goal or has_host):
            continue

        # punteggio: se disponibile, distingue il gol esatto (es. doppietta)
        score_ok = _title_score_matches(title)
        # squadra: se disponibile, evita clip da altre partite (omonimia)
        team_ok = _title_has_team(title_norm)

        # punteggio del nostro gol = 2 punti forti; squadra = 1 punto.
        # None significa "informazione non disponibile" -> non penalizza.
        score = 0
        score += 2 if score_ok else (-3 if score_ok is False else 0)
        score += 1 if team_ok else (-1 if team_ok is False else 0)

        matched.append((score, created, p))

    # prima il match più affidabile (punteggio+squadra), poi il più recente.
    # Scarta i candidati chiaramente sbagliati (score negativo) se ne resta
    # almeno uno valido.
    if not matched:
        log("  nessun post r/soccer corrispondente (marcatore/recency)")
        return
    best = max(m[0] for m in matched)
    valid = [m for m in matched if m[0] >= 0] or matched
    if best >= 0:
        valid = [m for m in matched if m[0] == best]
    valid.sort(key=lambda x: (x[0], x[1]), reverse=True)

    for _, _, p in valid:
        cand = candidate_video_url(p)
        if cand:
            log("  candidato reddit:", p["data"].get("title", "")[:80])
            yield cand


# --------------------------------------------------------------------------- #
# Estrazione mp4
# --------------------------------------------------------------------------- #
MP4_RE = re.compile(r"https?://[^\s\"'<>\\]+?\.mp4[^\s\"'<>\\]*", re.I)
OGVIDEO_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\']og:video(?::url|:secure_url)?["\']'
    r'[^>]+content=["\']([^"\']+)["\']', re.I)
SOURCE_RE = re.compile(r'<source[^>]+src=["\']([^"\']+\.mp4[^"\']*)["\']', re.I)
CONTENTURL_RE = re.compile(r'"contentUrl"\s*:\s*"([^"]+\.mp4[^"]*)"', re.I)


def extract_mp4(page_url):
    if not page_url:
        return None
    if page_url.lower().split("?")[0].endswith(".mp4"):
        return page_url
    try:
        r = SESSION.get(page_url, timeout=25, allow_redirects=True)
    except Exception as e:
        log("  fetch host error:", e)
        return None
    if not r.ok:
        return None
    if r.url.lower().split("?")[0].endswith(".mp4"):
        return r.url

    txt = html.unescape(r.text)
    for rx in (OGVIDEO_RE, SOURCE_RE, CONTENTURL_RE):
        m = rx.search(txt)
        if m:
            u = m.group(1)
            if u.startswith("//"):
                u = "https:" + u
            elif u.startswith("/"):
                from urllib.parse import urljoin
                u = urljoin(r.url, u)
            if ".mp4" in u.lower():
                return u
    cands = MP4_RE.findall(txt)
    if cands:
        cands.sort(key=lambda u: ("thumb" in u.lower() or "preview" in u.lower()))
        return cands[0]
    return None


def download_video(mp4_url):
    try:
        with SESSION.get(mp4_url, stream=True, timeout=60,
                         headers={"Referer": mp4_url}) as r:
            if not r.ok:
                log("  download status:", r.status_code)
                return None
            clen = r.headers.get("Content-Length")
            if clen and int(clen) > TELEGRAM_MAX_BYTES:
                log("  video troppo grande:", clen)
                return None
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            total = 0
            for chunk in r.iter_content(chunk_size=1 << 16):
                if not chunk:
                    continue
                total += len(chunk)
                if total > TELEGRAM_MAX_BYTES:
                    tmp.close(); os.unlink(tmp.name)
                    log("  video troppo grande in streaming")
                    return None
                tmp.write(chunk)
            tmp.close()
            if total < 10000:
                os.unlink(tmp.name)
                return None
            log(f"  scaricati {total/1024/1024:.1f} MB")
            return tmp.name
    except Exception as e:
        log("  download error:", e)
        return None


def try_send_goal_video(scorer, since_ts, caption):
    for host_url in find_goal_post(scorer, since_ts):
        mp4 = extract_mp4(host_url)
        if not mp4:
            continue
        path = download_video(mp4)
        if not path:
            continue
        ok = tg_send_video(path, caption)
        try:
            os.unlink(path)
        except OSError:
            pass
        if ok:
            return True
    return False


# --------------------------------------------------------------------------- #
def build_caption():
    score_line = f"{HOME_N} {G_HOME}-{G_AWAY} {AWAY_N}".strip()
    minute = f" {MINUTE}'" if MINUTE and not MINUTE.endswith("'") else (
        f" {MINUTE}" if MINUTE else "")
    scorer = SCORER or "Gol"
    return (f"⚽️ <b>{html.escape(scorer)}</b>{minute}\n"
            f"{html.escape(score_line)}")


def main():
    if not TELEGRAM_TOKEN or not TELEGRAM_TO:
        log("ERRORE: TELEGRAM_TOKEN e TELEGRAM_TO_GOALS sono obbligatori.")
        sys.exit(1)

    caption = build_caption()
    log("Gol ricevuto:", caption.replace("\n", " | "))

    if not SCORER:
        log("Nessun marcatore: impossibile cercare il video.")
        if SEND_TEXT_FALLBACK:
            tg_send_message(caption)
        return

    deadline = time.time() + GOAL_SEARCH_TIMEOUT
    since = time.time() - 240
    while time.time() < deadline:
        log(f"Cerco video per {SCORER} su r/soccer...")
        if try_send_goal_video(SCORER, since, caption):
            log("Video inviato ✅")
            return
        time.sleep(REDDIT_RETRY_SECONDS)

    log("Timeout: video non trovato.")
    if SEND_TEXT_FALLBACK:
        tg_send_message(caption + "\n\n<i>(video non trovato)</i>")


if __name__ == "__main__":
    main()
