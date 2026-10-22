"""Costanti fisse: emoji dei messaggi, fusi orari, tabelle ESPN."""

import re
from zoneinfo import ZoneInfo


ITALY_TZ = ZoneInfo('Europe/Rome')


ESPN_TZ  = ZoneInfo('America/New_York')  # ESPN indicizza gli eventi in orario US Eastern


ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"


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
