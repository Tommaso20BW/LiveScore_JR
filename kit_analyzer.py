"""
kit_analyzer.py
───────────────
Modulo standalone per:
  1. Determinare il kit della Juventus (home / away / third) dai dati ESPN.
  2. Estrarre i colori principali delle maglie di entrambe le squadre.

Fonte dati: il campo `uniform` dell'API ESPN (endpoint summary →
boxscore.teams[].team.uniform), che riporta per ogni squadra il tipo di
kit effettivamente indossato e il suo colore:

    "uniform": { "type": "home|away|third", "color": "RRGGBB" }

Cascata fallback kit:
    uniform.type (ESPN)  →  logica classica determina_kit()

Cascata fallback colori:
    uniform.color (ESPN)  →  team.color / alternateColor (ESPN)  →  hardcoded

Viene importato da juve_bot_espn.py e chiamato prima di generare
la grafica stats, dentro recupera_e_genera_stats_html().

Nessuna variabile d'ambiente richiesta.
"""

# ── Configurazione ────────────────────────────────────────────────────────────
JUVE_ID  = "111"

# Colori di ultima istanza (se uniform ed ESPN team color falliscono entrambi)
_FALLBACK_HOME_COLOR = "#1e3a8a"  # blu
_FALLBACK_AWAY_COLOR = "#7c3aed"  # viola

_VALID_KITS = ("home", "away", "third")


# ── Utilities interne ─────────────────────────────────────────────────────────
def darken(hex_color: str, factor: float = 0.65) -> str:
    """Restituisce una versione più scura del colore hex fornito."""
    try:
        h = hex_color.lstrip("#")
        r = int(int(h[0:2], 16) * factor)
        g = int(int(h[2:4], 16) * factor)
        b = int(int(h[4:6], 16) * factor)
        return f"#{r:02X}{g:02X}{b:02X}"
    except Exception:
        return hex_color


def _norm_hex(raw: str | None) -> str | None:
    """Normalizza un colore ESPN ('RRGGBB' o '#RRGGBB') in '#RRGGBB'.

    Restituisce None se il valore è assente o non è un hex a 6 cifre valido.
    """
    if not raw:
        return None
    h = raw.lstrip("#").strip()
    if len(h) != 6:
        return None
    try:
        int(h, 16)
    except ValueError:
        return None
    return f"#{h.upper()}"


def _espn_uniforms(
    boxscore_teams: list,
) -> dict:
    """Estrae il kit (type) e il colore (color) di ciascuna squadra dai dati
    boxscore ESPN.

    Ogni elemento di boxscore.teams contiene:
        - "homeAway": "home" | "away"
        - "team": { ..., "uniform": { "type": ..., "color": ... } }

    Ritorna: {"home": {"type": str|None, "color": str|None},
              "away": {"type": str|None, "color": str|None}}
    """
    out = {"home": {"type": None, "color": None},
           "away": {"type": None, "color": None}}
    for t in boxscore_teams:
        side    = "home" if t.get("homeAway") == "home" else "away"
        uniform = (t.get("team") or {}).get("uniform") or {}
        out[side] = {
            "type":  uniform.get("type"),
            "color": uniform.get("color"),
        }
    return out


def _espn_colors(
    competitors: list,
    home_id: str,
    away_id: str,
) -> tuple[str | None, str | None]:
    """Legge i colori ufficiali della squadra (brand) dai dati ESPN.

    Usato come fallback quando il campo uniform non è disponibile.
    """
    hc = ac = None
    for comp in competitors:
        team = comp.get("team", {})
        tid  = str(team.get("id", ""))
        raw  = team.get("color") or team.get("alternateColor") or ""
        col  = _norm_hex(raw)
        if col:
            if tid == str(home_id):
                hc = col
            elif tid == str(away_id):
                ac = col
    return hc, ac


# ── API pubblica ──────────────────────────────────────────────────────────────
def analizza(
    home_name:      str,
    away_name:      str,
    home_id:        str,
    away_id:        str,
    league_name:    str        = "",
    competitors:    list | None = None,
    boxscore_teams: list | None = None,
    fallback_kit:   str        = "default",
) -> dict:
    """
    Determina il kit della Juventus (se gioca) e i colori delle maglie
    di entrambe le squadre, usando il campo `uniform` dell'API ESPN.

    Parametri
    ─────────
    home_name / away_name : nomi visualizzati delle squadre
    home_id / away_id     : ID ESPN delle squadre
    league_name           : nome della lega (es. "Serie A")
    competitors           : lista competitors da ESPN (header) — fallback colori
    boxscore_teams        : lista boxscore.teams da ESPN — fonte primaria uniform
    fallback_kit          : kit calcolato con la logica classica, usato se
                            il campo uniform non è disponibile

    Ritorna
    ───────
    {
        "kit":        "home" | "away" | "third" | "default",
        "home_color": "#RRGGBB",   # colore maglia squadra di casa
        "away_color": "#RRGGBB",   # colore maglia squadra in trasferta
    }
    """
    competitors    = competitors or []
    boxscore_teams = boxscore_teams or []
    is_juve_home  = str(home_id) == JUVE_ID
    is_juve_away  = str(away_id) == JUVE_ID
    is_juve_match = is_juve_home or is_juve_away

    # Uniform (type + color) per home/away dai dati ESPN
    uni = _espn_uniforms(boxscore_teams)

    # ── STEP 1: kit Juve da uniform.type (fallback: logica classica) ──────
    kit = fallback_kit

    if is_juve_match:
        juve_side = "home" if is_juve_home else "away"
        juve_type = uni.get(juve_side, {}).get("type")
        if juve_type in _VALID_KITS:
            kit = juve_type

    # ── STEP 2: colori maglie da uniform.color ────────────────────────────
    home_color = _norm_hex(uni.get("home", {}).get("color"))
    away_color = _norm_hex(uni.get("away", {}).get("color"))

    # Fallback 1: colori ufficiali ESPN (team.color / alternateColor)
    espn_h, espn_a = _espn_colors(competitors, home_id, away_id)
    if not home_color:
        home_color = espn_h
    if not away_color:
        away_color = espn_a

    # Fallback 2: costanti hardcoded
    if not home_color:
        home_color = _FALLBACK_HOME_COLOR
    if not away_color:
        away_color = _FALLBACK_AWAY_COLOR

    return {
        "kit":        kit,
        "home_color": home_color,
        "away_color": away_color,
    }
