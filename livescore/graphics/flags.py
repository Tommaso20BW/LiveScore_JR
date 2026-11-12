"""Bandiere tonde delle nazionali (grafiche dell'Italia, livescore/graphics/italy.py).

Le bandiere sono negli asset in `flags_round/<codice>.png` (tonde, trasparenti attorno,
ricavate da `flags/<codice>.svg`, flag-icons). Il codice si trova dal nome della squadra:
nome ESPN -> nome italiano (team_names) -> `data/nations.json` (lo stesso elenco dei
Convocati di ImageGEN: nome italiano e varianti -> codice).
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from livescore.core import team_names
from livescore.paths import DATA_DIR


def _key(text: str) -> str:
    raw = unicodedata.normalize('NFKD', str(text or '')).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]', '', raw.lower())


@lru_cache(maxsize=1)
def _nations() -> dict[str, str]:
    """{nome normalizzato: codice bandiera}."""
    data = json.loads((DATA_DIR / 'nations.json').read_text(encoding='utf-8'))
    return {_key(name): code for code, names in data.items() if not code.startswith('_') for name in names}


def code_for(name: str) -> str | None:
    """'it' per "Italy" / "Italia"; None se la nazione non è nell'elenco."""
    for candidate in (team_names.translate_team(name), name):
        code = _nations().get(_key(candidate))
        if code:
            return code
    return None


_TAG_FLAGS = {'gb-eng': 'eng', 'gb-sct': 'sct', 'gb-wls': 'wls'}


def emoji_for(name: str) -> str:
    """Emoji della bandiera per una nazionale ('🇮🇹' per Italia); '' se non è una nazione."""
    code = code_for(name)
    if not code:
        return ''
    if code in _TAG_FLAGS:
        tags = ''.join(chr(0xE0000 + ord(c)) for c in _TAG_FLAGS[code])
        return '🏴' + tags + '󠁿'
    if len(code) != 2 or not code.isalpha():
        return ''
    return ''.join(chr(0x1F1E6 + ord(c) - ord('a')) for c in code.lower())


def path_for(name: str, assets) -> Path | None:
    code = code_for(name)
    if not code:
        return None
    path = Path(assets) / 'flags_round' / f'{code}.png'
    return path if path.is_file() else None
