"""
kit_analyzer.py
───────────────
Modulo standalone per:
  1. Determinare il kit della Juventus (home / away / third) tramite Gemini.
  2. Estrarre i colori principali delle maglie di entrambe le squadre.

Cascata fallback colori:
  Gemini  →  colori ESPN dall'API  →  costanti hardcoded

Viene importato da juve_bot_espn.py e chiamato prima di generare
la grafica stats, dentro recupera_e_genera_stats_html().

Variabile d'ambiente richiesta: GEMINI_API_KEY
"""

import os
import re
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

# ── Configurazione ────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
_GEMINI_MODEL  = "gemini-2.5-flash"
_GEMINI_URL    = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{_GEMINI_MODEL}:generateContent"
)

ITALY_TZ = ZoneInfo("Europe/Rome")
JUVE_ID  = "111"

# Colori di ultima istanza (se Gemini e ESPN falliscono entrambi)
_FALLBACK_HOME_COLOR = "#1e3a8a"  # blu
_FALLBACK_AWAY_COLOR = "#7c3aed"  # viola


# ── Utilities interne ─────────────────────────────────────────────────────────
def _now_it() -> str:
    return datetime.now(ITALY_TZ).strftime("%H:%M:%S")


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


def _call_gemini(prompt: str) -> str | None:
    """Invia una domanda testuale a Gemini; restituisce la risposta grezza o None."""
    if not GEMINI_API_KEY:
        print(f"[{_now_it()}] ⚠️  [kit] GEMINI_API_KEY non impostata — skip Gemini")
        return None
    try:
        r = requests.post(
            f"{_GEMINI_URL}?key={GEMINI_API_KEY}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=15,
        )
        if r.status_code == 200:
            parts = (
                r.json()
                 .get("candidates", [{}])[0]
                 .get("content", {})
                 .get("parts", [{}])
            )
            return (parts[0].get("text", "") if parts else "").strip()
        print(f"[{_now_it()}] ⚠️  [kit] Gemini HTTP {r.status_code}: {r.text[:120]}")
    except Exception as e:
        print(f"[{_now_it()}] ❌ [kit] Errore chiamata Gemini: {e}")
    return None


def _parse_hex(text: str) -> str | None:
    """Estrae il primo #RRGGBB valido dal testo."""
    if not text:
        return None
    m = re.search(r"#([0-9A-Fa-f]{6})\b", text)
    return m.group(0).upper() if m else None


def _parse_kit(text: str) -> str | None:
    """Estrae home / away / third dal testo."""
    if not text:
        return None
    low = text.lower()
    for k in ("home", "away", "third"):
        if k in low:
            return k
    return None


def _espn_colors(
    competitors: list,
    home_id: str,
    away_id: str,
) -> tuple[str | None, str | None]:
    """Legge i colori ufficiali direttamente dai dati ESPN (competitors list)."""
    hc = ac = None
    for comp in competitors:
        team = comp.get("team", {})
        tid  = str(team.get("id", ""))
        raw  = team.get("color") or team.get("alternateColor") or ""
        if raw:
            col = raw if raw.startswith("#") else f"#{raw}"
            if tid == str(home_id):
                hc = col.upper()
            elif tid == str(away_id):
                ac = col.upper()
    return hc, ac


# ── API pubblica ──────────────────────────────────────────────────────────────
def analizza(
    home_name:    str,
    away_name:    str,
    home_id:      str,
    away_id:      str,
    league_name:  str        = "",
    competitors:  list | None = None,
    fallback_kit: str        = "default",
) -> dict:
    """
    Determina il kit della Juventus (se gioca) e i colori delle maglie
    di entrambe le squadre.

    Parametri
    ─────────
    home_name / away_name : nomi visualizzati delle squadre
    home_id / away_id     : ID ESPN delle squadre
    league_name           : nome della lega (es. "Serie A")
    competitors           : lista competitors da ESPN (per il fallback colori)
    fallback_kit          : kit calcolato con la logica classica, usato se
                            Gemini non risponde o risponde male

    Ritorna
    ───────
    {
        "kit":        "home" | "away" | "third" | "default",
        "home_color": "#RRGGBB",   # colore maglia squadra di casa
        "away_color": "#RRGGBB",   # colore maglia squadra in trasferta
    }
    """
    competitors = competitors or []
    is_juve_home  = str(home_id) == JUVE_ID
    is_juve_away  = str(away_id) == JUVE_ID
    is_juve_match = is_juve_home or is_juve_away

    # ── STEP 1: kit Juve ──────────────────────────────────────────────────
    kit = fallback_kit

    if is_juve_match:
        opponent   = away_name if is_juve_home else home_name
        prompt_kit = (
            f"Che maglia sta indossando la Juventus oggi contro {opponent}? "
            f"Rispondi solo: home, away o third."
        )
        print(f"[{_now_it()}] 🤖 [kit] Gemini kit → Juve vs {opponent}")
        resp_kit    = _call_gemini(prompt_kit)
        parsed_kit  = _parse_kit(resp_kit)

        if parsed_kit:
            kit = parsed_kit
            print(f"[{_now_it()}] ✅ [kit] Kit Gemini: {kit!r}")
        else:
            print(
                f"[{_now_it()}] ⚠️  [kit] Risposta Gemini non valida ({resp_kit!r})"
                f" → fallback logica classica: {fallback_kit!r}"
            )

    # ── STEP 2: colori maglie ─────────────────────────────────────────────
    home_color = away_color = None

    if GEMINI_API_KEY:
        # Colore maglia squadra di casa
        prompt_h = (
            f"Che colore ha la maglia che sta indossando {home_name} oggi contro {away_name}? "
            f"Rispondi solo con il codice hex nel formato #RRGGBB, nient'altro."
        )
        print(f"[{_now_it()}] 🤖 [kit] Gemini colore maglia → {home_name} (casa)")
        resp_h     = _call_gemini(prompt_h)
        home_color = _parse_hex(resp_h)
        if home_color:
            print(f"[{_now_it()}] 🎨 [kit] {home_name} color Gemini: {home_color}")
        else:
            print(f"[{_now_it()}] ⚠️  [kit] {home_name} color non valido ({resp_h!r})")

        # Colore maglia squadra in trasferta
        prompt_a = (
            f"Che colore ha la maglia che sta indossando {away_name} oggi contro {home_name}? "
            f"Rispondi solo con il codice hex nel formato #RRGGBB, nient'altro."
        )
        print(f"[{_now_it()}] 🤖 [kit] Gemini colore maglia → {away_name} (trasferta)")
        resp_a     = _call_gemini(prompt_a)
        away_color = _parse_hex(resp_a)
        if away_color:
            print(f"[{_now_it()}] 🎨 [kit] {away_name} color Gemini: {away_color}")
        else:
            print(f"[{_now_it()}] ⚠️  [kit] {away_name} color non valido ({resp_a!r})")

    # Fallback 1: colori ESPN
    espn_h, espn_a = _espn_colors(competitors, home_id, away_id)
    if not home_color:
        home_color = espn_h
        if home_color:
            print(f"[{_now_it()}] 🔄 [kit] {home_name} color fallback ESPN: {home_color}")
    if not away_color:
        away_color = espn_a
        if away_color:
            print(f"[{_now_it()}] 🔄 [kit] {away_name} color fallback ESPN: {away_color}")

    # Fallback 2: costanti hardcoded
    if not home_color:
        home_color = _FALLBACK_HOME_COLOR
        print(f"[{_now_it()}] 🔄 [kit] {home_name} color fallback hardcoded: {home_color}")
    if not away_color:
        away_color = _FALLBACK_AWAY_COLOR
        print(f"[{_now_it()}] 🔄 [kit] {away_name} color fallback hardcoded: {away_color}")

    return {
        "kit":        kit,
        "home_color": home_color,
        "away_color": away_color,
    }
