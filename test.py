#!/usr/bin/env python3
"""
test_stats_telegram.py — TEST STANDALONE (tutto in un unico file)
─────────────────────────────────────────────────────────────────
Analizza una partita ESPN scelta da te (anche vecchia/finita), genera SOLO
la grafica delle statistiche e la invia su Telegram. Usa le stesse logiche
del bot: campo `uniform` ESPN per kit/colori, template stats.html, texture,
render Playwright.

Niente loop live, niente Gist, niente Canva: solo fetch → grafica → Telegram.

──────────────────────────────────────────────────────────────────
COME TROVARE event_id e league
──────────────────────────────────────────────────────────────────
Apri la pagina ESPN della partita, es.:
    https://www.espn.com/soccer/match/_/gameId/401870630/italy-greece
                                                ^^^^^^^^^  = event_id
La lega è lo slug ESPN (ita.1, eng.1, fifa.friendly, uefa.champions, ...).

──────────────────────────────────────────────────────────────────
USO
──────────────────────────────────────────────────────────────────
    export TELEGRAM_TOKEN="123:ABC"      # stesso bot del progetto
    export TELEGRAM_TO="-100123456789"   # stessa chat

    python test_stats_telegram.py --event 401870630 --league fifa.friendly
    python test_stats_telegram.py --event 401870630 --league fifa.friendly --momento FT

Opzioni:
    --momento {HT,2H_END,FT}   default FT
    --pen-home N --pen-away N   rigori (opzionale, mostra "d.c.r.")
    --no-send                  genera solo il PNG (non invia su Telegram)

Esegui dalla cartella del progetto: servono stats.html, texture_black.png,
texture_white.png, texture_gold.png (leagues.json è opzionale, migliora il rilevamento lega).
PNG generato: /tmp/stats_final.png
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image
from playwright.sync_api import sync_playwright

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURAZIONE (stessa del bot)
# ══════════════════════════════════════════════════════════════════════════════
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_TO")

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
ITALY_TZ  = ZoneInfo("Europe/Rome")
JUVE_ID   = "111"

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def now_it() -> str:
    return datetime.now(ITALY_TZ).strftime("%H:%M:%S")


# ── leagues.json (opzionale: override tipo lega) ──────────────────────────────
def _load_leagues() -> dict:
    try:
        with open(os.path.join(_BASE_DIR, "leagues.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

LEAGUE_MAP = _load_leagues()

_CUP_KEYWORDS = (
    "copp", "cup", "champions", "europa", "conference", "super",
    "supercoppa", "mondiale", "club world", "cwc", "shield",
    "playoff", "play-off",
)
_FRIENDLY_KEYWORDS = ("friendly", "amichev")


def _is_league_slug(slug: str) -> bool:
    parts = (slug or "").split(".")
    return (len(parts) == 2 and len(parts[0]) == 3
            and parts[0].isalpha() and parts[1].isdigit())


def is_cup_competition(league_slug: str, league_name: str = "") -> bool:
    slug = (league_slug or "").lower()
    name = (league_name or "").lower()
    tipo = str(LEAGUE_MAP.get(league_slug, {}).get("type", "")).lower()
    if tipo in ("cup", "coppa"):
        return True
    if tipo in ("league", "campionato"):
        return False
    if _is_league_slug(slug):
        return False
    return any(k in slug or k in name for k in _CUP_KEYWORDS)


def is_friendly_competition(league_slug: str, league_name: str = "") -> bool:
    slug = (league_slug or "").lower()
    name = (league_name or "").lower()
    tipo = str(LEAGUE_MAP.get(league_slug, {}).get("type", "")).lower()
    if tipo in ("friendly", "amichevole"):
        return True
    return any(k in slug or k in name for k in _FRIENDLY_KEYWORDS)


def determina_kit(home_id, away_id, league_slug: str = "", league_name: str = "") -> str:
    if is_friendly_competition(league_slug, league_name):
        return "default"
    juve_in_casa      = str(home_id) == JUVE_ID
    juve_in_trasferta = str(away_id) == JUVE_ID
    if not (juve_in_casa or juve_in_trasferta):
        return "default"
    if is_cup_competition(league_slug, league_name):
        return "third"
    return "home" if juve_in_casa else "away"


# ══════════════════════════════════════════════════════════════════════════════
# KIT / COLORI dal campo `uniform` ESPN  (logica di kit_analyzer)
# ══════════════════════════════════════════════════════════════════════════════
_FALLBACK_HOME_COLOR = "#1e3a8a"
_FALLBACK_AWAY_COLOR = "#7c3aed"
_VALID_KITS = ("home", "away", "third")


def darken(hex_color: str, factor: float = 0.65) -> str:
    try:
        h = hex_color.lstrip("#")
        r = int(int(h[0:2], 16) * factor)
        g = int(int(h[2:4], 16) * factor)
        b = int(int(h[4:6], 16) * factor)
        return f"#{r:02X}{g:02X}{b:02X}"
    except Exception:
        return hex_color


def _norm_hex(raw):
    if not raw:
        return None
    h = str(raw).lstrip("#").strip()
    if len(h) != 6:
        return None
    try:
        int(h, 16)
    except ValueError:
        return None
    return f"#{h.upper()}"


def _espn_uniforms(boxscore_teams: list) -> dict:
    out = {"home": {"type": None, "color": None},
           "away": {"type": None, "color": None}}
    for t in boxscore_teams:
        side    = "home" if t.get("homeAway") == "home" else "away"
        uniform = (t.get("team") or {}).get("uniform") or {}
        out[side] = {"type": uniform.get("type"), "color": uniform.get("color")}
    return out


def _espn_colors(competitors, home_id, away_id):
    hc = ac = None
    for comp in competitors:
        team = comp.get("team", {})
        tid  = str(team.get("id", ""))
        col  = _norm_hex(team.get("color") or team.get("alternateColor") or "")
        if col:
            if tid == str(home_id):
                hc = col
            elif tid == str(away_id):
                ac = col
    return hc, ac


def analizza_kit(home_name, away_name, home_id, away_id,
                 competitors, boxscore_teams, fallback_kit):
    is_juve_home  = str(home_id) == JUVE_ID
    is_juve_away  = str(away_id) == JUVE_ID
    is_juve_match = is_juve_home or is_juve_away

    uni = _espn_uniforms(boxscore_teams)

    kit = fallback_kit
    if is_juve_match:
        juve_side = "home" if is_juve_home else "away"
        juve_type = uni.get(juve_side, {}).get("type")
        if juve_type in _VALID_KITS:
            kit = juve_type
            print(f"[{now_it()}] ✅ Kit ESPN uniform: {kit!r}")
        else:
            print(f"[{now_it()}] ⚠️  uniform.type assente → fallback: {fallback_kit!r}")

    home_color = _norm_hex(uni.get("home", {}).get("color"))
    away_color = _norm_hex(uni.get("away", {}).get("color"))
    if home_color:
        print(f"[{now_it()}] 🎨 {home_name} uniform: {home_color}")
    if away_color:
        print(f"[{now_it()}] 🎨 {away_name} uniform: {away_color}")

    espn_h, espn_a = _espn_colors(competitors, home_id, away_id)
    home_color = home_color or espn_h or _FALLBACK_HOME_COLOR
    away_color = away_color or espn_a or _FALLBACK_AWAY_COLOR
    return {"kit": kit, "home_color": home_color, "away_color": away_color}


# ══════════════════════════════════════════════════════════════════════════════
# STATISTICHE + GRAFICA
# ══════════════════════════════════════════════════════════════════════════════
E_STATS = "📊"
MOMENTI_CONFIG = {
    "HT":     {"titolo": f"<b>STATS PRIMO TEMPO</b> {E_STATS}",   "badge": "FINE PRIMO TEMPO"},
    "2H_END": {"titolo": f"<b>STATS SECONDO TEMPO</b> {E_STATS}", "badge": "FINE SECONDO TEMPO"},
    "FT":     {"titolo": f"<b>STATS FINE PARTITA</b> {E_STATS}",  "badge": "FINE PARTITA"},
}


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


def genera_stats_html(data_espn, home_id, away_id, home_name, away_name,
                      home_goals, away_goals, momento,
                      league_name="SERIE A", league_slug="",
                      pen_home=0, pen_away=0):
    # Kit + colori dal campo uniform ESPN (fallback: logica classica / team.color)
    try:
        _competitors = data_espn["header"]["competitions"][0]["competitors"]
    except Exception:
        _competitors = []
    _boxscore_teams = (data_espn.get("boxscore") or {}).get("teams", [])
    _fallback_kit = determina_kit(home_id, away_id, league_slug, league_name)

    _kit = analizza_kit(home_name, away_name, home_id, away_id,
                        _competitors, _boxscore_teams, _fallback_kit)
    juve_kit   = _kit["kit"]
    home_color = _kit["home_color"]
    away_color = _kit["away_color"]
    print(f"[{now_it()}] 🎨 Tema: {juve_kit} | {home_name}: {home_color} / {away_name}: {away_color}")

    JUVE_LOGO_BLACK = "https://upload.wikimedia.org/wikipedia/commons/e/ed/Juventus_FC_-_logo_black_%28Italy%2C_2020%29.svg"
    JUVE_LOGO_WHITE = "https://upload.wikimedia.org/wikipedia/commons/9/99/Juventus_FC_2017_squared_icon_%28white%29.png"
    JUVE_LOGO_GOLD  = "https://gist.githubusercontent.com/Tommaso20BW/86db1c7a3581f15150f157c1fa572047/raw/fcb8706fea43a1e015da2d5ae4ff3e8b651ec235/juve_thid.png"
    juve_logo = {
        "home":  JUVE_LOGO_BLACK,
        "away":  JUVE_LOGO_BLACK,
        "third": JUVE_LOGO_GOLD,
    }.get(juve_kit, JUVE_LOGO_WHITE)

    h_logo = juve_logo if str(home_id) == JUVE_ID else f"https://a.espncdn.com/i/teamlogos/soccer/500/{home_id}.png"
    a_logo = juve_logo if str(away_id) == JUVE_ID else f"https://a.espncdn.com/i/teamlogos/soccer/500/{away_id}.png"

    badge_label = MOMENTI_CONFIG[momento]["badge"]
    if momento == "FT" and (pen_home > 0 or pen_away > 0):
        badge_label = "FINE PARTITA d.c.r."

    raw = _estrai_stats_espn(data_espn)

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
            return f"{int(v*100)}%" if v <= 1.0 else f"{int(v)}%"
        except Exception:
            return str(val)

    pos_h_raw = g("home", "possessionPct", "possessionpct", "possession", fallback="50")
    pos_a_raw = g("away", "possessionPct", "possessionpct", "possession", fallback="50")
    pos_h, pos_a = fmt_pct(pos_h_raw), fmt_pct(pos_a_raw)
    try:
        bp_perc = int(float(str(pos_h_raw).replace("%", "")))
        if bp_perc <= 1:
            bp_perc = int(bp_perc * 100)
    except Exception:
        bp_perc = 50

    sot_h   = g("home", "shotsOnTarget", "shotsontarget", fallback="0")
    sot_a   = g("away", "shotsOnTarget", "shotsontarget", fallback="0")
    shots_h = g("home", "totalShots", "totalshots", fallback="0")
    shots_a = g("away", "totalShots", "totalshots", fallback="0")
    falli_h = g("home", "foulsCommitted", "foulscommitted", "fouls", fallback="0")
    falli_a = g("away", "foulsCommitted", "foulscommitted", "fouls", fallback="0")
    gialli_h = g("home", "yellowCards", "yellowcards", fallback="0")
    gialli_a = g("away", "yellowCards", "yellowcards", fallback="0")
    rossi_h = g("home", "redCards", "redcards", fallback="0")
    rossi_a = g("away", "redCards", "redcards", fallback="0")
    corner_h = g("home", "wonCorners", "woncorners", "cornerKicks", "cornerkicks", "corners", "corner", fallback="0")
    corner_a = g("away", "wonCorners", "woncorners", "cornerKicks", "cornerkicks", "corners", "corner", fallback="0")
    saves_h = g("home", "saves", fallback="0")
    saves_a = g("away", "saves", fallback="0")
    offside_h = g("home", "offsides", fallback="0")
    offside_a = g("away", "offsides", fallback="0")
    blk_h   = g("home", "blockedShots", "blockedshots", fallback="0")
    blk_a   = g("away", "blockedShots", "blockedshots", fallback="0")
    pass_h  = g("home", "totalPasses", "totalpasses", fallback="0")
    pass_a  = g("away", "totalPasses", "totalpasses", fallback="0")
    passpct_h = fmt_pct(g("home", "passPct", "passpct", fallback="0"))
    passpct_a = fmt_pct(g("away", "passPct", "passpct", fallback="0"))

    stats_mappate = [
        ("Possesso palla",      pos_h,     pos_a,     bp_perc),
        ("Tiri in porta",       sot_h,     sot_a,     perc(sot_h, sot_a)),
        ("Tiri totali",         shots_h,   shots_a,   perc(shots_h, shots_a)),
        ("Tiri bloccati",       blk_h,     blk_a,     perc(blk_h, blk_a)),
        ("Corner",              corner_h,  corner_a,  perc(corner_h, corner_a)),
        ("Fuorigioco",          offside_h, offside_a, perc(offside_h, offside_a)),
        ("Falli",               falli_h,   falli_a,   perc(falli_h, falli_a)),
        ("Ammoniti",            gialli_h,  gialli_a,  perc(gialli_h, gialli_a)),
        ("Espulsi",             rossi_h,   rossi_a,   perc(rossi_h, rossi_a)),
        ("Parate",              saves_h,   saves_a,   perc(saves_h, saves_a)),
        ("Passaggi totali",     pass_h,    pass_a,    perc(pass_h, pass_a)),
        ("Precisione passaggi", passpct_h, passpct_a, perc(
            str(passpct_h).replace("%", ""), str(passpct_a).replace("%", ""))),
    ]

    rows_html = "".join([
        f'<div class="stat-row"><div class="stat-top">'
        f'<div class="val home-val">{h}</div><div class="stat-label">{label}</div>'
        f'<div class="val away-val">{a}</div></div>'
        f'<div class="bar-track"><div class="bar-home" style="width:{hp}%"></div>'
        f'<div class="bar-away" style="width:{100-hp}%"></div></div></div>'
        for label, h, a, hp in stats_mappate
    ])

    if pen_home > 0 or pen_away > 0:
        score_block_html = (f'<div class="score">{home_goals} \u2013 {away_goals}</div>'
                            f'<div class="pen-score">({pen_home} - {pen_away})</div>')
    else:
        score_block_html = f'<div class="score">{home_goals} \u2013 {away_goals}</div>'

    template_path = os.path.join(_BASE_DIR, "stats.html")
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            template = f.read()
    except FileNotFoundError:
        print(f"[{now_it()}] ❌ stats.html non trovato in {template_path}")
        return None

    if juve_kit == "default":
        _home_dark = darken(home_color)
        _away_dark = darken(away_color)
        _dynamic_style = (
            f"\nbody.kit-default {{\n"
            f"  --body-bg1:   {darken(home_color, 0.25)};\n"
            f"  --body-bg2:   {darken(away_color, 0.25)};\n"
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

    html_content = (
        template
        .replace("{JUVE_KIT}",      juve_kit)
        .replace("{DYNAMIC_STYLE}", _dynamic_style)
        .replace("{LEAGUE_NAME}",   league_name.upper())
        .replace("{BADGE_LABEL}",   badge_label)
        .replace("{H_LOGO}",        h_logo)
        .replace("{HOME_NAME}",     home_name)
        .replace("{SCORE_BLOCK}",   score_block_html)
        .replace("{A_LOGO}",        a_logo)
        .replace("{AWAY_NAME}",     away_name)
        .replace("{ROWS_HTML}",     rows_html)
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

    texture_file = os.path.join(_BASE_DIR, {
        "home":  "texture_black.png",
        "away":  "texture_black.png",
        "third": "texture_gold.png",
    }.get(juve_kit, "texture_white.png"))
    if os.path.exists(texture_file):
        try:
            base_img = Image.open(path_raw_png).convert("RGBA")
            texture  = Image.open(texture_file).convert("RGBA").resize(base_img.size, Image.Resampling.LANCZOS)
            Image.alpha_composite(base_img, texture).convert("RGB").save(path_final_png, "PNG")
            print(f"[{now_it()}] 🎨 Texture applicata: {os.path.basename(texture_file)}")
            return path_final_png
        except Exception as e:
            print(f"[{now_it()}] ⚠️  Errore texture: {e}")
    return path_raw_png


# ══════════════════════════════════════════════════════════════════════════════
# ESPN + TELEGRAM
# ══════════════════════════════════════════════════════════════════════════════
def fetch_evento(event_id: str, league_slug: str):
    try:
        r = requests.get(f"{ESPN_BASE}/{league_slug}/summary",
                         params={"event": event_id}, timeout=20)
        if r.status_code == 200:
            return r.json()
        print(f"[{now_it()}] ❌ ESPN HTTP {r.status_code}")
    except Exception as e:
        print(f"[{now_it()}] ❌ Errore fetch evento: {e}")
    return None


def estrai_intestazione(data: dict):
    """Ricava id, nome e gol di casa/trasferta + nome lega dal summary."""
    comp = data["header"]["competitions"][0]
    competitors = comp["competitors"]
    home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
    away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
    league_name = (data.get("header", {}).get("league", {}).get("name")
                   or data.get("header", {}).get("season", {}).get("name") or "")
    return (
        str(home.get("team", {}).get("id", "")),
        str(away.get("team", {}).get("id", "")),
        home.get("team", {}).get("displayName", "Home"),
        away.get("team", {}).get("displayName", "Away"),
        int(home.get("score", 0) or 0),
        int(away.get("score", 0) or 0),
        league_name,
    )


def invia_foto_telegram(png_path: str, caption: str):
    if not BOT_TOKEN or not CHAT_ID:
        print(f"[{now_it()}] ❌ TELEGRAM_TOKEN / TELEGRAM_TO non impostati — impossibile inviare")
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(png_path, "rb") as f:
            r = requests.post(url, data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "HTML"},
                              files={"photo": ("stats.png", f, "image/png")}, timeout=30)
        if r.status_code == 200:
            print(f"[{now_it()}] ✅ Foto inviata su Telegram")
            return True
        print(f"[{now_it()}] ❌ Telegram HTTP {r.status_code}: {r.text[:160]}")
    except Exception as e:
        print(f"[{now_it()}] ❌ Errore invio Telegram: {e}")
    return False


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(description="Genera e invia su Telegram la sola grafica stats di una partita ESPN.")
    ap.add_argument("--event",  required=True, help="event_id ESPN (gameId nell'URL della partita)")
    ap.add_argument("--league", required=True, help="slug lega ESPN (es. ita.1, fifa.friendly, uefa.champions)")
    ap.add_argument("--momento", default="FT", choices=["HT", "2H_END", "FT"], help="default: FT")
    ap.add_argument("--pen-home", type=int, default=0)
    ap.add_argument("--pen-away", type=int, default=0)
    ap.add_argument("--no-send", action="store_true", help="genera solo il PNG, non invia su Telegram")
    args = ap.parse_args()

    print(f"[{now_it()}] 📥 Scarico evento {args.event} ({args.league}) da ESPN...")
    data = fetch_evento(args.event, args.league)
    if not data:
        print(f"[{now_it()}] ❌ Evento non trovato. Controlla event_id e slug lega.")
        sys.exit(1)

    h_id, a_id, h_name, a_name, gh, ga, league_name = estrai_intestazione(data)
    league_name = league_name or args.league
    print(f"[{now_it()}] ⚽ {h_name} {gh}-{ga} {a_name}  ({league_name})")

    png = genera_stats_html(
        data, h_id, a_id, h_name, a_name, gh, ga, args.momento,
        league_name=league_name, league_slug=args.league,
        pen_home=args.pen_home, pen_away=args.pen_away,
    )
    if not png or not os.path.exists(png):
        print(f"[{now_it()}] ❌ Generazione grafica fallita.")
        sys.exit(1)
    print(f"[{now_it()}] 🖼  PNG: {png}")

    if args.no_send:
        print(f"[{now_it()}] ⏭  --no-send: foto NON inviata.")
        return

    score = f"{gh}-{ga}"
    if args.pen_home or args.pen_away:
        score += f" (d.c.r. {args.pen_home}-{args.pen_away})"
    caption = (f"{MOMENTI_CONFIG[args.momento]['titolo']}\n\n"
               f"{h_name} {score} {a_name} · {league_name}\n#TEST")
    invia_foto_telegram(png, caption)


if __name__ == "__main__":
    main()
