"""Utilita' sui testi: escape HTML e formato nomi giocatori."""

import html
import unicodedata
from datetime import datetime

from livescore.constants import ITALY_TZ


def now_it(): return datetime.now(ITALY_TZ).strftime('%H:%M:%S')


def esc(s) -> str:
    """Escape HTML: protegge i messaggi Telegram (parse_mode=HTML) e il
    template stats da nomi contenenti '<', '>' o '&'."""
    return html.escape(str(s), quote=False)


def _norm_name(s: str) -> str:
    """Confronto nomi tollerante agli accenti (es. 'Erik' == 'Érik').
    Usata nel dedup di parse_events e nel loop correzione marcatori."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', (s or '').strip())
        if unicodedata.category(c) != 'Mn'
    ).lower()


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
