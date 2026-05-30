"""
ESPN Match Events Extractor
============================
Estrae TUTTI gli eventi di una partita calcistica dall'API pubblica ESPN.

Uso:
    python espn_match_events.py                    # usa event id di default
    python espn_match_events.py 401862897          # specifica event id
    python espn_match_events.py 401862897 --debug  # mostra anche JSON grezzo

Zero dipendenze esterne — solo stdlib Python 3.8+
"""

import sys
import json
import urllib.request
import urllib.error
from datetime import datetime

# ─────────────────────────────────────────────
DEFAULT_EVENT_ID = "401862897"   # PSG vs Arsenal, UCL, 30/05/2026

# ESPN cerca la lega dall'event id.
# Proviamo questi slug in ordine finché uno risponde 200.
LEAGUE_SLUGS = [
    "uefa.champions",
    "uefa.europa",
    "all",
    "eng.1",
    "esp.1",
    "ger.1",
    "fra.1",
    "ita.1",
    "usa.1",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.espn.com/",
    "Origin":          "https://www.espn.com",
    "DNT":             "1",
}

EVENT_ICONS = {
    "goal":                 "⚽  GOAL",
    "own-goal":             "⚽  AUTORETE",
    "own goal":             "⚽  AUTORETE",
    "penalty-goal":         "⚽  RIGORE SEGNATO",
    "penalty goal":         "⚽  RIGORE SEGNATO",
    "penalty-missed":       "❌  RIGORE SBAGLIATO",
    "penalty-saved":        "🧤  RIGORE PARATO",
    "yellow-card":          "🟨  CARTELLINO GIALLO",
    "yellow card":          "🟨  CARTELLINO GIALLO",
    "red-card":             "🟥  CARTELLINO ROSSO",
    "red card":             "🟥  CARTELLINO ROSSO",
    "yellow-red-card":      "🟥  DOPPIO GIALLO → ROSSO",
    "second yellow":        "🟥  DOPPIO GIALLO → ROSSO",
    "substitution":         "🔄  SOSTITUZIONE",
    "var":                  "📺  VAR REVIEW",
    "var-review":           "📺  VAR REVIEW",
    "offside":              "🚩  FUORIGIOCO",
    "injury":               "🚑  INFORTUNIO",
    "injury time":          "⏱️  RECUPERO ANNUNCIATO",
    "kickoff":              "🏁  CALCIO D'INIZIO",
    "kick-off":             "🏁  CALCIO D'INIZIO",
    "kick off":             "🏁  CALCIO D'INIZIO",
    "halftime":             "🔔  FINE 1° TEMPO",
    "half-time":            "🔔  FINE 1° TEMPO",
    "half time":            "🔔  FINE 1° TEMPO",
    "end period":           "🔔  FINE PERIODO",
    "end of period":        "🔔  FINE PERIODO",
    "second half":          "▶️  INIZIO 2° TEMPO",
    "full-time":            "🏆  FINE PARTITA",
    "full time":            "🏆  FINE PARTITA",
    "final":                "🏆  FINE PARTITA",
    "extra-time-start":     "⏱️  INIZIO SUPPLEMENTARI",
    "extra time":           "⏱️  SUPPLEMENTARI",
    "extra-time-halftime":  "🔔  FINE 1° TEMPO SUPPL.",
    "extra-time-end":       "🏆  FINE SUPPLEMENTARI",
    "penalty-shootout":     "🎯  CALCIO DI RIGORE (shoot-out)",
    "penalty shootout":     "🎯  CALCIO DI RIGORE (shoot-out)",
    "shootout goal":        "⚽  GOAL SUI RIGORI",
    "shootout miss":        "❌  RIGORE SBAGLIATO (shoot-out)",
}

def icon(type_id: str, type_text: str = "") -> str:
    for key in [type_id.lower(), type_text.lower()]:
        if key in EVENT_ICONS:
            return EVENT_ICONS[key]
    # partial match
    for key, val in EVENT_ICONS.items():
        if key and key in type_id.lower():
            return val
    return f"📌  {(type_text or type_id).upper()}"


# ─────────────────────────────────────────────
# HTTP
# ─────────────────────────────────────────────
def get(url: str, debug: bool = False) -> dict | None:
    if debug:
        print(f"     → GET {url}")
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if debug:
            print(f"        HTTP {e.code}")
        return None
    except Exception as e:
        if debug:
            print(f"        ERR {e}")
        return None


def fetch_summary(event_id: str, debug: bool = False) -> tuple[dict, str]:
    """
    Prova ogni slug di lega finché ESPN risponde 200.
    Ritorna (dati, league_slug) oppure ({}, '').
    """
    base = "https://site.api.espn.com/apis/site/v2/sports/soccer"
    for slug in LEAGUE_SLUGS:
        url = f"{base}/{slug}/summary?event={event_id}"
        data = get(url, debug)
        if data:
            return data, slug
    return {}, ""


# ─────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────
def parse_participant(part: dict) -> str:
    ath  = part.get("athlete") or {}
    name = ath.get("displayName") or ath.get("shortName") or ath.get("fullName", "")
    role = (part.get("type") or {}).get("text", "")
    return f"{name} ({role})" if (name and role) else name


def play_to_event(p: dict) -> dict:
    clock   = p.get("clock") or {}
    period  = p.get("period") or {}
    type_   = p.get("type") or {}
    team    = p.get("team") or {}
    return {
        "minute":      clock.get("displayValue", ""),
        "period":      period.get("number"),
        "period_text": period.get("displayValue", ""),
        "type_id":     type_.get("id", ""),
        "type_text":   type_.get("text", ""),
        "icon":        icon(type_.get("id",""), type_.get("text","")),
        "team":        team.get("displayName", ""),
        "team_abbr":   team.get("abbreviation", ""),
        "players":     [parse_participant(x) for x in p.get("participants", []) if parse_participant(x)],
        "description": p.get("text", ""),
        "score_home":  p.get("homeScore", ""),
        "score_away":  p.get("awayScore", ""),
    }


def scoring_to_event(sp: dict) -> dict:
    period = sp.get("period") or {}
    clock  = sp.get("clock") or {}
    type_  = sp.get("type") or {}
    team   = sp.get("team") or {}
    return {
        "minute":      clock.get("displayValue", ""),
        "period":      period.get("number"),
        "period_text": period.get("displayValue", ""),
        "type_id":     type_.get("id", "goal"),
        "type_text":   type_.get("text", "Goal"),
        "icon":        icon(type_.get("id","goal"), type_.get("text","Goal")),
        "team":        team.get("displayName", ""),
        "team_abbr":   team.get("abbreviation", ""),
        "players":     [parse_participant(x) for x in sp.get("participants", []) if parse_participant(x)],
        "description": sp.get("text", ""),
        "score_home":  sp.get("homeScore", ""),
        "score_away":  sp.get("awayScore", ""),
    }


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def extract(event_id: str, debug: bool = False) -> None:
    print(f"\n{'═'*62}")
    print(f"  🏟️  ESPN Match Events Extractor")
    print(f"  Event ID : {event_id}")
    print(f"{'═'*62}\n")

    print("⏳ Contatto ESPN API (provo vari slug lega)...")
    data, slug = fetch_summary(event_id, debug)

    if not data:
        print("\n❌  Nessun endpoint ha risposto.")
        print("    Possibili cause:")
        print("    • Event ID non valido")
        print("    • ESPN blocca le richieste da IP datacenter (GitHub Actions)")
        print("      → prova da PC locale o aggiungi un proxy residenziale")
        print("    • La partita non esiste ancora nel sistema ESPN")
        return

    print(f"✅ Risposta da slug: {slug}\n")

    # ── Info partita ──────────────────────────
    header      = data.get("header", {})
    comps       = header.get("competitions", [{}])
    comp        = comps[0] if comps else {}
    competitors = comp.get("competitors", [])
    status_obj  = comp.get("status", {})
    status_type = status_obj.get("type", {})

    home = next((c for c in competitors if c.get("homeAway") == "home"), {})
    away = next((c for c in competitors if c.get("homeAway") == "away"), {})

    def team_info(c):
        t = c.get("team") or {}
        return t.get("displayName", "?"), c.get("score", "?")

    home_name, home_score = team_info(home)
    away_name, away_score = team_info(away)

    venue  = (comp.get("venue") or {}).get("fullName", "N/A")
    league = (header.get("league") or {}).get("name", "N/A")
    status = status_type.get("description", "N/A")

    date_str = comp.get("date", "")
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        date_fmt = dt.strftime("%d %B %Y  %H:%M UTC")
    except Exception:
        date_fmt = date_str

    print(f"  🏆  {league}")
    print(f"  📅  {date_fmt}")
    print(f"  🏟️   {venue}")
    print(f"  ⚽  {home_name}  {home_score} – {away_score}  {away_name}")
    print(f"  📊  Stato: {status}")
    print()

    # ── Raccoglie eventi ──────────────────────
    # Priorità: plays > scoringPlays; aggiungi keyEvents se diversi
    plays         = data.get("plays", [])
    scoring_plays = data.get("scoringPlays", [])
    key_events    = data.get("keyEvents", [])

    if plays:
        events = [play_to_event(p) for p in plays]
        source = f"plays  ({len(events)} eventi play-by-play)"
    elif scoring_plays:
        events = [scoring_to_event(sp) for sp in scoring_plays]
        source = f"scoringPlays  ({len(events)} eventi con punteggio)"
    else:
        events = []
        source = "nessuna fonte principale trovata"

    # key events (eventi chiave ESPN — goal, cartellini, sostituzioni)
    ke_events = [play_to_event(ke) for ke in key_events]

    print(f"  📋  Fonte: {source}")
    if ke_events:
        print(f"  🔑  Key events: {len(ke_events)}")
    print()

    # ── Stampa timeline ───────────────────────
    def print_events(evlist: list, title: str) -> None:
        if not evlist:
            return
        print(f"{'─'*62}")
        print(f"  {title}  [{len(evlist)} eventi]")
        print(f"{'─'*62}")
        for ev in evlist:
            min_str    = f"{ev['minute']:>6}" if ev['minute'] else "      "
            period_str = f" [T{ev['period']}]" if ev.get('period') else ""
            score_str  = ""
            if ev.get('score_home') != "" and ev.get('score_away') != "":
                sh, sa = ev['score_home'], ev['score_away']
                if sh or sa:
                    score_str = f"  [{sh}-{sa}]"
            print(f"\n  {min_str}{period_str}  {ev['icon']}{score_str}")
            if ev['team']:
                print(f"           ▸ {ev['team']}")
            if ev['players']:
                print(f"           👤 {', '.join(ev['players'])}")
            if ev['description']:
                print(f"           💬 {ev['description']}")
        print()

    if not events and not ke_events:
        print("⚠️  Nessun evento disponibile.")
        print("   La partita potrebbe non essere iniziata o ESPN")
        print("   non ha il play-by-play per questa competizione.")
    else:
        print_events(events,    "📺  TIMELINE COMPLETA")
        print_events(ke_events, "🔑  KEY EVENTS ESPN")

    # ── Debug: struttura grezza ───────────────
    if debug:
        print(f"\n{'─'*62}")
        print("  🔍  CHIAVI JSON RADICE")
        print(f"{'─'*62}")
        for k, v in data.items():
            t = type(v).__name__
            l = f"  ({len(v)} items)" if isinstance(v, (list, dict)) else ""
            print(f"    {k:<30} {t}{l}")

    # ── Salva JSON ────────────────────────────
    out = {
        "event_id":    event_id,
        "league":      league,
        "home":        home_name,
        "away":        away_name,
        "score":       f"{home_score}-{away_score}",
        "status":      status,
        "date":        date_fmt,
        "venue":       venue,
        "events":      events,
        "key_events":  ke_events,
    }
    fname = f"espn_events_{event_id}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n{'─'*62}")
    print(f"  💾  JSON salvato → {fname}")
    print(f"{'─'*62}\n")


# ─────────────────────────────────────────────
if __name__ == "__main__":
    args     = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags    = [a for a in sys.argv[1:] if a.startswith("--")]
    event_id = args[0] if args else DEFAULT_EVENT_ID
    debug    = "--debug" in flags
    extract(event_id, debug)
