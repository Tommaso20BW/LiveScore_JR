"""
ESPN Match Events Extractor
============================
Estrae TUTTI gli eventi di una partita calcistica dall'API pubblica ESPN,
inclusi i rigori uno per uno (shootout), supplementari, cambi di periodo.

Uso:
    python espn_match_events.py                    # event id di default
    python espn_match_events.py 401862897
    python espn_match_events.py 401862897 --debug  # mostra struttura JSON grezza

Zero dipendenze esterne — solo stdlib Python 3.8+
"""

import sys
import json
import urllib.request
import urllib.error
from datetime import datetime

# ─────────────────────────────────────────────
DEFAULT_EVENT_ID = "401862897"   # PSG vs Arsenal, UCL, 30/05/2026

LEAGUE_SLUGS = [
    "uefa.champions",
    "uefa.europa",
    "all",
    "eng.1", "esp.1", "ger.1", "fra.1", "ita.1", "usa.1",
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
    "goal":                "⚽  GOAL",
    "own-goal":            "⚽  AUTORETE",
    "own goal":            "⚽  AUTORETE",
    "penalty-goal":        "⚽  RIGORE SEGNATO",
    "penalty goal":        "⚽  RIGORE SEGNATO",
    "penalty-missed":      "❌  RIGORE SBAGLIATO",
    "penalty missed":      "❌  RIGORE SBAGLIATO",
    "penalty-saved":       "🧤  RIGORE PARATO",
    "penalty saved":       "🧤  RIGORE PARATO",
    "yellow-card":         "🟨  CARTELLINO GIALLO",
    "yellow card":         "🟨  CARTELLINO GIALLO",
    "red-card":            "🟥  CARTELLINO ROSSO",
    "red card":            "🟥  CARTELLINO ROSSO",
    "yellow-red-card":     "🟥  DOPPIO GIALLO → ROSSO",
    "second yellow":       "🟥  DOPPIO GIALLO → ROSSO",
    "substitution":        "🔄  SOSTITUZIONE",
    "var":                 "📺  VAR REVIEW",
    "var-review":          "📺  VAR REVIEW",
    "offside":             "🚩  FUORIGIOCO",
    "injury":              "🚑  INFORTUNIO",
    "injury time":         "⏱️  RECUPERO ANNUNCIATO",
    "kickoff":             "🏁  CALCIO D'INIZIO",
    "kick-off":            "🏁  CALCIO D'INIZIO",
    "kick off":            "🏁  CALCIO D'INIZIO",
    "halftime":            "🔔  FINE 1° TEMPO",
    "half-time":           "🔔  FINE 1° TEMPO",
    "half time":           "🔔  FINE 1° TEMPO",
    "end period":          "🔔  FINE PERIODO",
    "end of period":       "🔔  FINE PERIODO",
    "second half":         "▶️  INIZIO 2° TEMPO",
    "full-time":           "🏆  FINE PARTITA (90')",
    "full time":           "🏆  FINE PARTITA (90')",
    "final":               "🏆  FINE PARTITA",
    "extra-time-start":    "⏱️  INIZIO SUPPLEMENTARI",
    "extra time":          "⏱️  SUPPLEMENTARI",
    "extra-time-halftime": "🔔  FINE 1° TEMPO SUPPL.",
    "extra-time-end":      "🏆  FINE SUPPLEMENTARI",
    "penalty-shootout":    "🎯  INIZIO CALCI DI RIGORE",
    "penalty shootout":    "🎯  INIZIO CALCI DI RIGORE",
    "shootout goal":       "⚽  RIGORE SEGNATO (shoot-out)",
    "shootout miss":       "❌  RIGORE SBAGLIATO (shoot-out)",
    "shootout saved":      "🧤  RIGORE PARATO (shoot-out)",
}

def icon(type_id: str, type_text: str = "") -> str:
    for key in [type_id.lower(), type_text.lower()]:
        if key in EVENT_ICONS:
            return EVENT_ICONS[key]
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
    base = "https://site.api.espn.com/apis/site/v2/sports/soccer"
    for slug in LEAGUE_SLUGS:
        url = f"{base}/{slug}/summary?event={event_id}"
        data = get(url, debug)
        if data:
            return data, slug
    return {}, ""


# ─────────────────────────────────────────────
# Parser eventi normali
# ─────────────────────────────────────────────
def parse_participant(part: dict) -> str:
    ath  = part.get("athlete") or {}
    name = ath.get("displayName") or ath.get("shortName") or ath.get("fullName", "")
    role = (part.get("type") or {}).get("text", "")
    return f"{name} ({role})" if (name and role) else name


def play_to_event(p: dict) -> dict:
    clock  = p.get("clock") or {}
    period = p.get("period") or {}
    type_  = p.get("type") or {}
    team   = p.get("team") or {}
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
# Parser rigori (shootout)
# ─────────────────────────────────────────────
def parse_shootout(data: dict, home_name: str, away_name: str) -> list[dict]:
    """
    ESPN può mettere i rigori in posti diversi:
    1. data['shootout']            — lista diretta
    2. data['header']['competitions'][0]['shootout']
    3. dentro data['plays'] con type.id contenente 'shootout'
    4. data['penaltyShootout']
    
    Li cerchiamo tutti e restituiamo una lista ordinata di calci.
    """
    kicks = []

    # ── Fonte 1: chiave 'shootout' radice ─────
    raw = data.get("shootout") or data.get("penaltyShootout") or []
    if isinstance(raw, dict):
        raw = raw.get("plays") or raw.get("kicks") or []

    # ── Fonte 2: dentro header > competitions ─
    if not raw:
        comp = (data.get("header", {}).get("competitions") or [{}])[0]
        raw  = comp.get("shootout") or comp.get("penaltyShootout") or []

    # ── Fonte 3: dentro plays con tipo shootout
    shootout_plays = []
    for p in data.get("plays", []):
        tid = (p.get("type") or {}).get("id", "").lower()
        if "shootout" in tid or "penalty shoot" in tid:
            shootout_plays.append(p)
    if not raw and shootout_plays:
        raw = shootout_plays

    # ── Fonte 4: competitors[].shootout ───────
    if not raw:
        comp = (data.get("header", {}).get("competitions") or [{}])[0]
        for competitor in comp.get("competitors", []):
            for kick in competitor.get("shootout", []):
                team_obj = competitor.get("team") or {}
                kick["_team_name"] = team_obj.get("displayName", "")
                kick["_team_abbr"] = team_obj.get("abbreviation", "")
                raw.append(kick)

    if not raw:
        return []

    for i, kick in enumerate(raw, 1):
        # Normalizza formato — ESPN usa campi diversi a seconda della versione API
        athlete    = kick.get("athlete") or {}
        team_obj   = kick.get("team") or {}
        type_obj   = kick.get("type") or {}
        result_obj = kick.get("result") or {}

        player = (
            athlete.get("displayName")
            or athlete.get("shortName")
            or kick.get("athleteName", "")
            or kick.get("_player", "")
        )
        team = (
            team_obj.get("displayName")
            or kick.get("_team_name", "")
            or kick.get("teamName", "")
        )
        scored = (
            kick.get("scored")
            or kick.get("good")
            or result_obj.get("id", "").lower() in ("goal", "scored", "good")
            or type_obj.get("id", "").lower() in ("shootout-goal", "shootout goal", "goal")
        )
        saved  = result_obj.get("id", "").lower() in ("saved", "save")
        missed = result_obj.get("id", "").lower() in ("missed", "miss", "wide", "post")

        if scored:
            result_icon = "⚽ SEGNATO"
        elif saved:
            result_icon = "🧤 PARATO"
        elif missed:
            result_icon = "❌ SBAGLIATO (fuori)"
        else:
            result_icon = "❓ " + (result_obj.get("text") or type_obj.get("text") or "?")

        kicks.append({
            "order":       i,
            "team":        team,
            "player":      player,
            "scored":      bool(scored),
            "saved":       saved,
            "missed":      missed,
            "result_icon": result_icon,
            "result_text": result_obj.get("text") or type_obj.get("text", ""),
            "score_after": kick.get("homeScore", "") or kick.get("score", ""),
        })

    return kicks


# ─────────────────────────────────────────────
# Inferisci eventi di stato dal cambio periodo
# ─────────────────────────────────────────────
PERIOD_LABELS = {
    1: ("🏁  CALCIO D'INIZIO (1° TEMPO)",   "🔔  FINE 1° TEMPO"),
    2: ("▶️  INIZIO 2° TEMPO",              "🏆  FINE PARTITA (90')"),
    3: ("⏱️  INIZIO 1° TEMPO SUPPLEMENTARE","🔔  FINE 1° SUPPL."),
    4: ("⏱️  INIZIO 2° TEMPO SUPPLEMENTARE","🏆  FINE SUPPLEMENTARI"),
    5: ("🎯  INIZIO CALCI DI RIGORE",       "🏆  FINE RIGORI"),
}

def inject_period_markers(events: list[dict]) -> list[dict]:
    """
    Se ESPN non include eventi kick-off/halftime nei plays,
    li inseriamo noi inferendoli dal cambio di periodo.
    """
    if not events:
        return events

    result       = []
    seen_periods = set()
    prev_period  = None

    for ev in events:
        p = ev.get("period")
        if p and p not in seen_periods:
            seen_periods.add(p)
            # Chiudi il periodo precedente se non già chiuso
            if prev_period and prev_period in PERIOD_LABELS:
                _, end_label = PERIOD_LABELS[prev_period]
                # Solo se l'ultimo evento non è già un end-period
                if result and "FINE" not in result[-1]["icon"] and "🏆" not in result[-1]["icon"]:
                    result.append({
                        "minute": "", "period": prev_period, "period_text": "",
                        "type_id": "end-period", "type_text": "End Period",
                        "icon": end_label, "team": "", "team_abbr": "",
                        "players": [], "description": "(inferito)",
                        "score_home": "", "score_away": "", "_synthetic": True,
                    })
            # Apri nuovo periodo
            if p in PERIOD_LABELS:
                start_label, _ = PERIOD_LABELS[p]
                result.append({
                    "minute": "", "period": p, "period_text": "",
                    "type_id": "kickoff", "type_text": "Kick Off",
                    "icon": start_label, "team": "", "team_abbr": "",
                    "players": [], "description": "(inferito)",
                    "score_home": "", "score_away": "", "_synthetic": True,
                })
            prev_period = p
        result.append(ev)

    # Chiudi l'ultimo periodo
    if prev_period and prev_period in PERIOD_LABELS:
        _, end_label = PERIOD_LABELS[prev_period]
        if result and "FINE" not in result[-1]["icon"] and "🏆" not in result[-1]["icon"]:
            result.append({
                "minute": "", "period": prev_period, "period_text": "",
                "type_id": "end-period", "type_text": "End Period",
                "icon": end_label, "team": "", "team_abbr": "",
                "players": [], "description": "(inferito)",
                "score_home": "", "score_away": "", "_synthetic": True,
            })

    return result


# ─────────────────────────────────────────────
# Stampa
# ─────────────────────────────────────────────
def print_events(evlist: list, title: str) -> None:
    if not evlist:
        return
    print(f"\n{'─'*62}")
    print(f"  {title}  [{len(evlist)} eventi]")
    print(f"{'─'*62}")
    for ev in evlist:
        min_str    = f"{ev['minute']:>6}" if ev.get('minute') else "      "
        period_str = f" [T{ev['period']}]" if ev.get('period') else ""
        score_str  = ""
        sh, sa = str(ev.get('score_home','')), str(ev.get('score_away',''))
        if sh or sa:
            score_str = f"  [{sh}-{sa}]"
        synth = "  *(inferito)*" if ev.get("_synthetic") else ""
        print(f"\n  {min_str}{period_str}  {ev['icon']}{score_str}{synth}")
        if ev.get('team'):
            print(f"           ▸ {ev['team']}")
        if ev.get('players'):
            print(f"           👤 {', '.join(ev['players'])}")
        if ev.get('description') and ev['description'] != "(inferito)":
            print(f"           💬 {ev['description']}")


def print_shootout(kicks: list, home_name: str, away_name: str) -> None:
    if not kicks:
        return
    print(f"\n{'═'*62}")
    print(f"  🎯  CALCI DI RIGORE  —  sequenza completa")
    print(f"{'═'*62}")

    home_score = 0
    away_score = 0
    for k in kicks:
        team   = k['team']
        player = k['player'] or "N/D"
        res    = k['result_icon']
        if k['scored']:
            if team == home_name:
                home_score += 1
            else:
                away_score += 1
        score_str = f"  →  {home_name} {home_score} – {away_score} {away_name}"
        print(f"\n  #{k['order']:>2}  {team:<25}  {player:<22}  {res}")
        if k['scored']:
            print(f"       {score_str}")
    print(f"\n  🏆  RISULTATO RIGORI: {home_name} {home_score} – {away_score} {away_name}")
    print(f"{'═'*62}")


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
        print("    • ESPN blocca IP datacenter (GitHub Actions/Codespaces)")
        print("      → esegui da PC locale oppure usa un proxy residenziale")
        return

    print(f"✅  Risposta da slug: {slug}\n")

    # ── Info partita ──────────────────────────
    header      = data.get("header", {})
    comp        = (header.get("competitions") or [{}])[0]
    competitors = comp.get("competitors", [])
    status_type = (comp.get("status") or {}).get("type", {})

    home = next((c for c in competitors if c.get("homeAway") == "home"), {})
    away = next((c for c in competitors if c.get("homeAway") == "away"), {})

    home_name  = (home.get("team") or {}).get("displayName", "Home")
    away_name  = (away.get("team") or {}).get("displayName", "Away")
    home_score = home.get("score", "?")
    away_score = away.get("score", "?")
    venue      = (comp.get("venue") or {}).get("fullName", "N/A")
    league     = (header.get("league") or {}).get("name", "N/A")
    status     = status_type.get("description", "N/A")

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
        source = "nessun evento trovato"

    ke_events = [play_to_event(ke) for ke in key_events]

    # Inietta marcatori di periodo se mancano
    events_with_markers = inject_period_markers(events)

    print(f"  📋  Fonte: {source}")
    if ke_events:
        print(f"  🔑  Key events: {len(ke_events)}")

    # ── Rigori ────────────────────────────────
    kicks = parse_shootout(data, home_name, away_name)
    if kicks:
        print(f"  🎯  Rigori trovati: {len(kicks)} calci")

    # ── Stampa ────────────────────────────────
    if not events and not ke_events:
        print("\n⚠️  Nessun evento disponibile.")
        print("   La partita potrebbe non essere iniziata o ESPN")
        print("   non ha il play-by-play per questa competizione.")
    else:
        print_events(events_with_markers, "📺  TIMELINE COMPLETA (con marcatori periodo)")
        print_events(ke_events, "🔑  KEY EVENTS ESPN")

    print_shootout(kicks, home_name, away_name)

    # ── Debug ─────────────────────────────────
    if debug:
        print(f"\n{'─'*62}")
        print("  🔍  CHIAVI JSON RADICE ESPN")
        print(f"{'─'*62}")
        for k, v in data.items():
            t = type(v).__name__
            l = f"  ({len(v)} items)" if isinstance(v, (list, dict)) else ""
            print(f"    {k:<35} {t}{l}")

    # ── Salva JSON ────────────────────────────
    out = {
        "event_id":   event_id,
        "league":     league,
        "home":       home_name,
        "away":       away_name,
        "score":      f"{home_score}-{away_score}",
        "status":     status,
        "date":       date_fmt,
        "venue":      venue,
        "events":     events_with_markers,
        "key_events": ke_events,
        "shootout":   kicks,
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
