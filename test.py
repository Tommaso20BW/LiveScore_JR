"""
ESPN Match Events Extractor — v3
=================================
Estrae TUTTI gli eventi di una partita da ESPN API pubblica.
Struttura testata su PSG vs Arsenal UCL Final 30/05/2026 (ID: 401862897).

Struttura ESPN reale (da reverse engineering):
  - key_events[]:  tipo, minuto, team, score → eventi principali
  - team_stats{}:  statistiche aggregate per squadra
  - lineups{}:     formazioni
  - score_change a minuto 120 ripetuti → calci di rigore (shootout)

Uso:
    python espn_match_events.py                    # default 401862897
    python espn_match_events.py 401862897
    python espn_match_events.py 401862897 --debug  # dump JSON grezzo
"""

import sys
import json
import urllib.request
import urllib.error
from datetime import datetime

# ─────────────────────────────────────────────────────────
DEFAULT_EVENT_ID = "401862897"

LEAGUE_SLUGS = [
    "uefa.champions", "uefa.europa", "all",
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
}

# Mappa tipo-evento ESPN → emoji + label italiano
EVENT_MAP = {
    # ── Gol ──────────────────────────────────
    "score_change":        ("⚽",  "GOAL"),
    "goal":                ("⚽",  "GOAL"),
    "own_goal":            ("⚽",  "AUTORETE"),
    "own-goal":            ("⚽",  "AUTORETE"),
    "penalty_goal":        ("⚽",  "RIGORE SEGNATO"),
    "penalty-goal":        ("⚽",  "RIGORE SEGNATO"),
    "penalty_missed":      ("❌",  "RIGORE SBAGLIATO"),
    "penalty-missed":      ("❌",  "RIGORE SBAGLIATO"),
    "penalty_saved":       ("🧤",  "RIGORE PARATO"),
    # ── Cartellini ───────────────────────────
    "yellow_card":         ("🟨",  "CARTELLINO GIALLO"),
    "yellow-card":         ("🟨",  "CARTELLINO GIALLO"),
    "red_card":            ("🟥",  "CARTELLINO ROSSO"),
    "red-card":            ("🟥",  "CARTELLINO ROSSO"),
    "yellow_red_card":     ("🟥",  "DOPPIO GIALLO → ROSSO"),
    "second_yellow":       ("🟥",  "DOPPIO GIALLO → ROSSO"),
    # ── Sostituzioni ─────────────────────────
    "substitution":        ("🔄",  "SOSTITUZIONE"),
    # ── VAR ──────────────────────────────────
    "var":                 ("📺",  "VAR REVIEW"),
    "var_review":          ("📺",  "VAR REVIEW"),
    # ── Infortuni ────────────────────────────
    "injury":              ("🚑",  "INFORTUNIO"),
    # ── Stato partita ────────────────────────
    "kickoff":             ("🏁",  "CALCIO D'INIZIO"),
    "kick_off":            ("🏁",  "CALCIO D'INIZIO"),
    "halftime":            ("🔔",  "FINE 1° TEMPO"),
    "half_time":           ("🔔",  "FINE 1° TEMPO"),
    "second_half_start":   ("▶️",   "INIZIO 2° TEMPO"),
    "full_time":           ("🏆",  "FINE PARTITA (90')"),
    "end_period":          ("🔔",  "FINE PERIODO"),
    "extra_time_start":    ("⏱️",   "INIZIO SUPPLEMENTARI"),
    "extra_time_half":     ("🔔",  "FINE 1° SUPPL."),
    "extra_time_end":      ("🏆",  "FINE SUPPLEMENTARI"),
    "shootout_start":      ("🎯",  "INIZIO CALCI DI RIGORE"),
    # ── Rigori shootout ──────────────────────
    "shootout_goal":       ("⚽",  "RIGORE SEGNATO"),
    "shootout_miss":       ("❌",  "RIGORE SBAGLIATO"),
    "shootout_saved":      ("🧤",  "RIGORE PARATO"),
}

def fmt(type_id) -> tuple[str, str]:
    # ESPN a volte restituisce type come dict {"id": "...", "text": "..."}
    if isinstance(type_id, dict):
        type_id = type_id.get("id") or type_id.get("text") or ""
    type_id = str(type_id) if type_id else ""
    k = type_id.lower().replace("-", "_")
    return EVENT_MAP.get(k, ("📌", type_id.upper() or "EVENTO"))


# ─────────────────────────────────────────────────────────
# HTTP
# ─────────────────────────────────────────────────────────
def get_json(url: str, debug=False) -> dict | None:
    if debug:
        print(f"  GET {url}")
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if debug:
            print(f"      → HTTP {e.code}")
        return None
    except Exception as e:
        if debug:
            print(f"      → ERR {e}")
        return None

def fetch_summary(event_id: str, debug=False) -> tuple[dict, str]:
    base = "https://site.api.espn.com/apis/site/v2/sports/soccer"
    for slug in LEAGUE_SLUGS:
        data = get_json(f"{base}/{slug}/summary?event={event_id}", debug)
        if data:
            return data, slug
    return {}, ""


# ─────────────────────────────────────────────────────────
# Determina i "periodi" dalla sequenza dei minuti
# ─────────────────────────────────────────────────────────
def classify_period(minute: int, has_extra: bool, has_shootout: bool) -> str:
    """
    Dato il minuto di un evento, restituisce il nome del periodo.
    ESPN non invia sempre esplicitamente il periodo negli eventi key_events,
    quindi lo deduciamo dal minuto.
    """
    if has_shootout and minute >= 120:
        return "shootout"
    if minute <= 45:
        return "first_half"
    if minute <= 90:
        return "second_half"
    if minute <= 105:
        return "extra_first"
    if minute <= 120:
        return "extra_second"
    return "shootout"


# ─────────────────────────────────────────────────────────
# Analisi key_events ESPN
# ─────────────────────────────────────────────────────────
def analyze_key_events(raw_events: list, home_name: str, away_name: str) -> dict:
    """
    Analizza i key_events grezzi ESPN e restituisce una struttura
    pronta per il bot livescore:

    {
      "periods_detected": ["first_half","second_half","extra_first","extra_second","shootout"],
      "has_extra_time":   bool,
      "has_shootout":     bool,
      "goals":            [...],
      "cards":            [...],
      "substitutions":    [...],
      "shootout_kicks":   [...],
      "timeline":         [...],   ← tutti gli eventi in ordine cronologico
    }
    """
    goals         = []
    cards         = []
    substitutions = []
    other         = []
    shootout_raw  = []  # score_change a minuto altissimo = rigori

    # Primo passaggio: capisci se ci sono supplementari/rigori
    max_minute   = max((e.get("time", 0) for e in raw_events), default=0)
    has_extra    = max_minute > 90
    # I rigori ESPN li codifica come score_change multipli allo stesso minuto (120)
    # Contiamo quanti score_change ci sono a minuto >= 115
    sc_at_end    = [e for e in raw_events
                    if e.get("type") == "score_change" and e.get("time", 0) >= 115]
    has_shootout = len(sc_at_end) >= 4   # almeno 4 calci = sicuramente shootout

    # Secondo passaggio: categorizza ogni evento
    for ev in raw_events:
        t        = ev.get("type", "")
        minute   = ev.get("time", 0)
        team_id  = ev.get("team", "")  # "home" o "away"
        team     = home_name if team_id == "home" else away_name
        h_score  = ev.get("home_score")
        a_score  = ev.get("away_score")
        period   = classify_period(minute, has_extra, has_shootout)

        base = {
            "type":    t,
            "minute":  minute,
            "period":  period,
            "team":    team,
            "team_id": team_id,
        }
        if h_score is not None:
            base["score_home"] = h_score
            base["score_away"] = a_score

        if t == "score_change":
            if has_shootout and minute >= 115:
                shootout_raw.append(base)
            else:
                goals.append(base)
        elif t in ("yellow_card", "red_card", "yellow_red_card"):
            cards.append(base)
        elif t == "substitution":
            substitutions.append(base)
        else:
            other.append(base)

    # ── Ricostruisci calci di rigore ──────────────────────
    # ESPN manda score_change alternati home/away man mano che si tirano.
    # Li convertiamo in "calcio #N — team — risultato"
    shootout_kicks = []
    home_pen   = 0
    away_pen   = 0
    prev_home  = goals[-1]["score_home"] if goals else 1  # score all'inizio rigori
    prev_away  = goals[-1]["score_away"] if goals else 1

    for i, kick in enumerate(shootout_raw, 1):
        sh = kick.get("score_home", prev_home)
        sa = kick.get("score_away", prev_away)
        if kick["team_id"] == "home":
            scored = sh > prev_home
            prev_home = sh
        else:
            scored = sa > prev_away
            prev_away = sa

        shootout_kicks.append({
            "order":      i,
            "team":       kick["team"],
            "team_id":    kick["team_id"],
            "scored":     scored,
            "result":     "SEGNATO" if scored else "SBAGLIATO/PARATO",
            "icon":       "⚽" if scored else "❌",
            "score_home": sh,
            "score_away": sa,
        })

    # ── Periodi rilevati ──────────────────────────────────
    periods = ["first_half", "second_half"]
    if has_extra:
        periods += ["extra_first", "extra_second"]
    if has_shootout:
        periods += ["shootout"]

    # ── Timeline unificata ────────────────────────────────
    # Aggiunge marcatori di inizio/fine periodo + tutti gli eventi in ordine
    PERIOD_MARKERS = {
        "first_half":    {"start": (0,   "🏁", "CALCIO D'INIZIO"),
                          "end":   (45,  "🔔", "FINE 1° TEMPO")},
        "second_half":   {"start": (45,  "▶️",  "INIZIO 2° TEMPO"),
                          "end":   (90,  "🏆", "FINE PARTITA (90')")},
        "extra_first":   {"start": (90,  "⏱️",  "INIZIO 1° SUPPL."),
                          "end":   (105, "🔔", "FINE 1° SUPPL.")},
        "extra_second":  {"start": (105, "⏱️",  "INIZIO 2° SUPPL."),
                          "end":   (120, "🏆", "FINE SUPPLEMENTARI")},
        "shootout":      {"start": (120, "🎯", "INIZIO CALCI DI RIGORE"),
                          "end":   (999, "🏆", "FINE RIGORI")},
    }

    timeline = []
    all_events = sorted(
        goals + cards + substitutions + other,
        key=lambda e: e["minute"]
    )
    prev_period = None

    for ev in all_events:
        p = ev["period"]
        if p != prev_period:
            # Chiudi periodo precedente
            if prev_period and prev_period in PERIOD_MARKERS:
                m = PERIOD_MARKERS[prev_period]
                timeline.append({
                    "minute": m["end"][0], "period": prev_period,
                    "icon": m["end"][1], "label": m["end"][2],
                    "team": "", "score_home": None, "score_away": None,
                    "_marker": True,
                })
            # Apri nuovo periodo
            if p in PERIOD_MARKERS:
                m = PERIOD_MARKERS[p]
                timeline.append({
                    "minute": m["start"][0], "period": p,
                    "icon": m["start"][1], "label": m["start"][2],
                    "team": "", "score_home": None, "score_away": None,
                    "_marker": True,
                })
            prev_period = p

        emoji, label = fmt(ev["type"])
        entry = {
            "minute":     ev["minute"],
            "period":     p,
            "icon":       emoji,
            "label":      label,
            "team":       ev.get("team", ""),
            "score_home": ev.get("score_home"),
            "score_away": ev.get("score_away"),
            "_marker":    False,
        }
        timeline.append(entry)

    # Chiudi ultimo periodo
    if prev_period and prev_period in PERIOD_MARKERS:
        m = PERIOD_MARKERS[prev_period]
        if not has_shootout or prev_period != "shootout":
            timeline.append({
                "minute": m["end"][0], "period": prev_period,
                "icon": m["end"][1], "label": m["end"][2],
                "team": "", "score_home": None, "score_away": None,
                "_marker": True,
            })

    # Aggiungi i rigori in coda alla timeline
    if shootout_kicks:
        timeline.append({
            "minute": 120, "period": "shootout",
            "icon": "🎯", "label": "INIZIO CALCI DI RIGORE",
            "team": "", "score_home": None, "score_away": None,
            "_marker": True,
        })
        for k in shootout_kicks:
            timeline.append({
                "minute":     120,
                "period":     "shootout",
                "icon":       k["icon"],
                "label":      f"RIGORE #{k['order']} — {k['result']}",
                "team":       k["team"],
                "score_home": k["score_home"],
                "score_away": k["score_away"],
                "_marker":    False,
                "_kick":      k,
            })
        timeline.append({
            "minute": 999, "period": "shootout",
            "icon": "🏆", "label": "FINE RIGORI",
            "team": "", "score_home": None, "score_away": None,
            "_marker": True,
        })

    return {
        "periods_detected": periods,
        "has_extra_time":   has_extra,
        "has_shootout":     has_shootout,
        "goals":            goals,
        "cards":            cards,
        "substitutions":    substitutions,
        "shootout_kicks":   shootout_kicks,
        "timeline":         timeline,
    }


# ─────────────────────────────────────────────────────────
# Stampa
# ─────────────────────────────────────────────────────────
def print_timeline(timeline: list, home: str, away: str) -> None:
    period_headers = {
        "first_half":   "━━━  1° TEMPO  ━━━",
        "second_half":  "━━━  2° TEMPO  ━━━",
        "extra_first":  "━━━  SUPPLEMENTARI — 1° TEMPO  ━━━",
        "extra_second": "━━━  SUPPLEMENTARI — 2° TEMPO  ━━━",
        "shootout":     "━━━  CALCI DI RIGORE  ━━━",
    }
    prev_period = None

    for ev in timeline:
        p = ev["period"]
        if p != prev_period:
            prev_period = p
            print(f"\n  {period_headers.get(p, p)}")

        min_str = f"{ev['minute']:>4}'" if ev["minute"] not in (0, 999) else "    "

        if ev.get("_marker"):
            print(f"\n  {min_str}  {ev['icon']}  {ev['label']}")
        else:
            score_str = ""
            sh, sa = ev.get("score_home"), ev.get("score_away")
            if sh is not None:
                score_str = f"  [{sh}–{sa}]"
            team_str = f"  ▸ {ev['team']}" if ev.get("team") else ""
            # Rigori: mostra anche chi ha segnato/sbagliato
            kick = ev.get("_kick")
            if kick:
                print(f"  {min_str}  {ev['icon']}  {ev['label']}{team_str}{score_str}")
            else:
                print(f"  {min_str}  {ev['icon']}  {ev['label']}{team_str}{score_str}")


def print_shootout_table(kicks: list, home: str, away: str) -> None:
    if not kicks:
        return
    print(f"\n{'═'*60}")
    print(f"  🎯  CALCI DI RIGORE — dettaglio")
    print(f"  {'#':<4} {'SQUADRA':<28} {'ESITO':<20} {'PARZIALE'}")
    print(f"{'─'*60}")
    for k in kicks:
        parz = f"{home} {k['score_home']} – {k['score_away']} {away}" if k['scored'] else ""
        print(f"  {k['order']:<4} {k['team']:<28} {k['icon']} {k['result']:<18} {parz}")
    # Risultato finale
    last = kicks[-1]
    print(f"{'─'*60}")
    print(f"  🏆  Risultato rigori: {home} {last['score_home']} – {last['score_away']} {away}")
    print(f"{'═'*60}")


# ─────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────
def extract(event_id: str, debug=False) -> None:
    print(f"\n{'═'*60}")
    print(f"  🏟️  ESPN Match Events Extractor  v3")
    print(f"  Event ID : {event_id}")
    print(f"{'═'*60}\n")

    print("⏳ Contatto ESPN API...")
    data, slug = fetch_summary(event_id, debug)

    if not data:
        print("❌  ESPN non ha risposto (IP datacenter bloccato).")
        print("   → Esegui da PC locale o aggiungi proxy residenziale.")
        return

    print(f"✅  Slug lega: {slug}\n")

    # ── Info partita ────────────────────────────────────────
    header      = data.get("header", {})
    comp        = (header.get("competitions") or [{}])[0]
    competitors = comp.get("competitors", [])
    status_type = (comp.get("status") or {}).get("type", {})

    home_c = next((c for c in competitors if c.get("homeAway") == "home"), {})
    away_c = next((c for c in competitors if c.get("homeAway") == "away"), {})
    home_t = home_c.get("team") or {}
    away_t = away_c.get("team") or {}

    home_name  = home_t.get("displayName", "Home")
    away_name  = away_t.get("displayName", "Away")
    home_score = home_c.get("score", "?")
    away_score = away_c.get("score", "?")
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
    print(f"  📊  Stato: {status}\n")

    # ── Analisi eventi ──────────────────────────────────────
    raw_events = data.get("keyEvents") or data.get("key_events") or []

    # Fallback: plays o scoringPlays
    if not raw_events:
        for p in data.get("plays", []):
            t = (p.get("type") or {}).get("id", "")
            raw_events.append({
                "type":       t,
                "time":       (p.get("clock") or {}).get("value", 0) // 60,
                "team":       "home" if (p.get("team") or {}).get("id") == home_t.get("id") else "away",
                "home_score": p.get("homeScore"),
                "away_score": p.get("awayScore"),
            })

    if not raw_events:
        print("⚠️  Nessun evento trovato nel feed ESPN per questa partita.")
        return

    result = analyze_key_events(raw_events, home_name, away_name)

    # ── Riepilogo struttura ─────────────────────────────────
    print(f"  📋  Periodi rilevati: {' → '.join(result['periods_detected'])}")
    print(f"  ⏱️   Supplementari:   {'Sì' if result['has_extra_time'] else 'No'}")
    print(f"  🎯  Rigori:           {'Sì (' + str(len(result['shootout_kicks'])) + ' calci)' if result['has_shootout'] else 'No'}")
    print(f"  ⚽  Goal (regolari):  {len(result['goals'])}")
    print(f"  🟨  Cartellini:       {len(result['cards'])}")
    print(f"  🔄  Sostituzioni:     {len(result['substitutions'])}")

    # ── Timeline ────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"  📺  TIMELINE COMPLETA")
    print(f"{'─'*60}")
    print_timeline(result["timeline"], home_name, away_name)

    # ── Tabella rigori ──────────────────────────────────────
    if result["shootout_kicks"]:
        print_shootout_table(result["shootout_kicks"], home_name, away_name)

    # ── Debug ───────────────────────────────────────────────
    if debug:
        print(f"\n{'─'*60}")
        print("  🔍  CHIAVI JSON RADICE ESPN")
        for k, v in data.items():
            t = type(v).__name__
            l = f" ({len(v)} items)" if isinstance(v, (list, dict)) else ""
            print(f"    {k:<35} {t}{l}")
        print()
        print("  🔍  KEY_EVENTS GREZZI ESPN")
        for i, ev in enumerate(raw_events):
            print(f"    [{i:>2}] {ev}")

    # ── Salva JSON ──────────────────────────────────────────
    out = {
        "event_id":   event_id,
        "league":     league,
        "home":       home_name,
        "away":       away_name,
        "score":      f"{home_score}–{away_score}",
        "status":     status,
        "date":       date_fmt,
        "venue":      venue,
        "analysis":   result,
    }
    fname = f"espn_events_{event_id}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n{'─'*60}")
    print(f"  💾  Salvato → {fname}")
    print(f"{'─'*60}\n")

    # ── Guida implementazione bot ───────────────────────────
    print(f"{'═'*60}")
    print("  📖  GUIDA IMPLEMENTAZIONE BOT LIVESCORE")
    print(f"{'═'*60}")
    print("""
  Il JSON prodotto ha questa struttura per il bot:

  analysis.has_extra_time   → bool: ci sono supplementari?
  analysis.has_shootout     → bool: si va ai rigori?
  analysis.periods_detected → lista periodi in ordine

  analysis.goals[]          → ogni goal con minuto, team, score
  analysis.cards[]          → cartellini con minuto e team
  analysis.substitutions[]  → cambi con minuto e team
  analysis.shootout_kicks[] → rigori con ordine, team, scored, score

  analysis.timeline[]       → TUTTO in ordine cronologico, inclusi
                               marcatori di inizio/fine periodo.
                               Usa questo per il feed del bot.

  LOGICA RIGORI ESPN:
    ESPN non manda i calci di rigore come eventi separati.
    Li manda come score_change ripetuti al minuto 120.
    Se count(score_change, minuto>=115) >= 4 → shootout.
    L'alternanza home/away nei score_change riflette
    l'ordine dei calci (home tira prima, poi away, ecc.)
    Confronta score prima/dopo per capire se segnato o no.
""")


# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    args     = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags    = [a for a in sys.argv[1:] if a.startswith("--")]
    event_id = args[0] if args else DEFAULT_EVENT_ID
    debug    = "--debug" in flags
    extract(event_id, debug)
