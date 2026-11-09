"""STARTING XI dell'Italia: bandiere e scritta STARTING XI in alto, sotto il campo visto
dall'alto con le etichette dei cognomi (attacco in alto). Disegno in livescore/graphics/italy.py.

I posti in campo arrivano da ESPN: ogni titolare ha un `formationPlace` (1-11) che, a
parità di modulo, indica sempre lo stesso ruolo (es. nel 4-2-3-1 il 4 e l'8 sono i due
mediani). Per i moduli più comuni c'è la tabella `FORMATIONS`; per gli altri si usa il
ruolo (`position.abbreviation`) e si riempiono le linee del modulo dal basso.
"""

from __future__ import annotations

import io
import re

from PIL import Image

from livescore.graphics import goal as g

W, H = 1920, 2560

# formationPlace -> linee del modulo, dalla difesa all'attacco, ognuna da sinistra a destra
# (Italia che attacca verso l'alto). Ricavate dalle partite ESPN.
FORMATIONS = {
    '4-4-2': [[3, 6, 5, 2], [11, 8, 4, 7], [9, 10]],
    '4-3-3': [[3, 6, 5, 2], [8, 4, 7], [11, 9, 10]],
    '4-2-3-1': [[3, 6, 5, 2], [4, 8], [11, 10, 7], [9]],
    '4-1-4-1': [[3, 6, 5, 2], [4], [11, 10, 8, 7], [9]],
    '4-5-1': [[3, 6, 5, 2], [11, 10, 4, 8, 7], [9]],
    '4-4-1-1': [[3, 6, 5, 2], [11, 8, 4, 7], [10], [9]],
    '3-4-2-1': [[4, 5, 6], [3, 8, 7, 2], [11, 10], [9]],
    '3-4-3': [[4, 5, 6], [3, 8, 7, 2], [11, 9, 10]],
    '3-4-1-2': [[4, 5, 6], [3, 8, 7, 2], [9], [11, 10]],
    '3-5-2': [[4, 5, 6], [3, 8, 11, 7, 2], [9, 10]],
    '3-1-4-2': [[6, 4, 5], [8], [3, 11, 7, 2], [10, 9]],
    '5-4-1': [[3, 4, 5, 6, 2], [11, 10, 8, 7], [9]],
    '5-3-2': [[3, 4, 5, 6, 2], [11, 8, 7], [9, 10]],
}

# Profondità del ruolo ESPN (moduli fuori tabella): più alto = più avanzato.
DEPTH = {'G': 0, 'GK': 0, 'SW': 2, 'CD': 1, 'CB': 1, 'LB': 1, 'RB': 1, 'LWB': 2, 'RWB': 2,
         'DM': 2, 'CDM': 2, 'CM': 3, 'LM': 3, 'RM': 3, 'AM': 4, 'CAM': 4, 'LW': 5, 'RW': 5,
         'CF': 5, 'F': 5, 'ST': 5, 'LF': 5, 'RF': 5}


class LineupUnavailable(ValueError):
    """Formazione incompleta o non leggibile."""


def _side(abbr: str) -> float:
    """-1 esterno sinistro, -0.5 centro-sinistra, 0 centro, 0.5 centro-destra, 1 esterno destro
    (iniziale L/R = fascia, suffisso -L/-R = lato di un ruolo centrale)."""
    abbr = abbr.upper()
    if abbr.endswith('-L'):
        return -0.5
    if abbr.endswith('-R'):
        return 0.5
    if abbr in ('LB', 'LM', 'LF', 'LW', 'LWB'):
        return -1
    if abbr in ('RB', 'RM', 'RF', 'RW', 'RWB'):
        return 1
    return 0


def _depth(abbr: str) -> float:
    base = abbr.upper().split('-')[0]
    return DEPTH.get(base, 3)


def module_rows(formation: str) -> list[int]:
    """'4-2-3-1' -> [4, 2, 3, 1]; vuoto se il modulo non somma a 10."""
    rows = [int(n) for n in re.findall(r'\d', str(formation or ''))]
    return rows if sum(rows) == 10 else []


def arrange(formation: str, players: list[dict]) -> list[list[dict]]:
    """Titolari divisi in linee: [portiere], difesa, ..., attacco; ogni linea da sinistra a destra.

    `players`: 11 dict con 'place' (formationPlace), 'pos' (ruolo ESPN) e 'name'."""
    if len(players) != 11:
        raise LineupUnavailable('Servono 11 titolari')
    by_place = {pl.get('place'): pl for pl in players}
    table = FORMATIONS.get(str(formation or '').strip())
    if table and set(by_place) == set(range(1, 12)):
        return [[by_place[1]]] + [[by_place[n] for n in row] for row in table]

    keeper = [pl for pl in players if _depth(pl['pos']) == 0][:1] or [
        min(players, key=lambda pl: pl.get('place') or 99)]
    outfield = [pl for pl in players if pl is not keeper[0]]
    sizes = module_rows(formation)
    if not sizes:
        # Modulo sconosciuto: linee dal ruolo.
        depths = sorted({_depth(pl['pos']) for pl in outfield})
        lines = [[pl for pl in outfield if _depth(pl['pos']) == d] for d in depths]
    else:
        # Dal più arretrato al più avanzato; a parità, prima chi sta al centro
        # (il mediano centrale sta dietro agli esterni, il trequartista largo dietro la punta).
        ordered = sorted(outfield, key=lambda pl: (_depth(pl['pos']),
                                                   0 if _depth(pl['pos']) >= 5 and _side(pl['pos']) else 1
                                                   if _depth(pl['pos']) >= 5 else abs(_side(pl['pos'])),
                                                   pl.get('place') or 0))
        lines, start = [], 0
        for size in sizes:
            lines.append(ordered[start:start + size])
            start += size
    return [keeper] + [sorted(line, key=lambda pl: (_side(pl['pos']), pl.get('place') or 0)) for line in lines]


def display_names(players: list[dict]) -> dict[int, str]:
    """Cognome in maiuscolo; con due cognomi uguali si aggiunge l'iniziale (P. ESPOSITO)."""
    surnames = {}
    for pl in players:
        surnames.setdefault(pl['last'].upper(), []).append(pl)
    names = {}
    for pl in players:
        last = pl['last'].upper()
        if len(surnames[last]) > 1 and pl.get('first'):
            names[id(pl)] = f"{pl['first'][0].upper()}. {last}"
        else:
            names[id(pl)] = last
    return names


# --------------------------------------------------------------------------------------
# Disegno: livescore/graphics/italy.py (stesso stile delle altre grafiche dell'Italia)
# --------------------------------------------------------------------------------------
def build_html(*, kit, formation, players, home_name, away_name, assets=g.DEFAULT_ASSET_DIR) -> str:
    from livescore.graphics import italy

    if kit not in italy.THEMES:
        raise ValueError('Tema non valido: solo ita_home / ita_away')
    names = display_names(players)
    lines = [[names[id(pl)] for pl in line] for line in arrange(formation, players)]
    return italy.xi_html(kit=kit, lines=lines, home_name=home_name, away_name=away_name, assets=assets)


def render_png(**kwargs) -> bytes:
    """Grafica STARTING XI dell'Italia (PNG 1920x2560). `kit`: 'ita_home' o 'ita_away'."""
    from livescore.graphics import italy

    return italy.render(build_html(**kwargs))


def build_image(**kwargs) -> Image.Image:
    return Image.open(io.BytesIO(render_png(**kwargs))).convert('RGB')
