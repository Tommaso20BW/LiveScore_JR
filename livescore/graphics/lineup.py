"""STARTING XI dell'Italia: la grafica delle probabili formazioni, adattata.

Stessa impaginazione della PROBABILE XI di ImageGEN (campo in 3D, titolo su una riga,
etichette coi nomi in Poppins), in versione "solo nomi" e con i colori dell'Italia:

- maglia home: sfondo azzurro, campo bianco, etichette azzurre con scritte bianche;
- maglia away: sfondo bianco, campo azzurro, etichette bianche con scritte azzurre.

Sotto il campo, al posto degli stemmi, i nomi delle squadre per esteso. Campo ed
etichetta delle probabili (in grigio) stanno negli asset in `overlays/` e qui vengono
ricolorati.

I posti in campo arrivano da ESPN: ogni titolare ha un `formationPlace` (1-11) che, a
parità di modulo, indica sempre lo stesso ruolo (es. nel 4-2-3-1 il 4 e l'8 sono i due
mediani). Per i moduli più comuni c'è la tabella `FORMATIONS`; per gli altri si usa il
ruolo (`position.abbreviation`) e si riempiono le linee del modulo dal basso.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from livescore.graphics import goal as g
from livescore.graphics import portrait as p

W, H = 1920, 2560
K = W / 1080                    # misure Canva (pagina 1080x1440) -> pixel
PITCH_TOP = 350                 # overlays/starting_xi_pitch.png va a (0, PITCH_TOP)
SLAB_FROM = 1958                # nel campo: da qui in giù è il bordo (lastra), non il prato
# Titolo dove le probabili hanno "probabile XI": riga di base e altezza x della parola, box dell'XI.
TITLE_BASELINE, TITLE_XHEIGHT, TITLE_CENTER = 222, 99, 970
XI_TOP, XI_HEIGHT, XI_OVERLAP = 39, 248, 15
# Etichetta del nome (misure Canva della PROBABILE XI).
LABEL_BOX_W, LABEL_BOX_H = 233.92 * K, 58.88 * K
NAME_FONT, NAME_SIZE, NAME_SPACING = 'fonts/Poppins-Medium.ttf', 26.17 * K, 1.26 * K
NAME_BASE, NAME_MAX_W = 37.76 * K, 214 * K
LABEL_GAP, PAGE_MARGIN = 12 * K, 12 * K
# Centri delle etichette: portiere, prima linea, ultima linea (le altre in mezzo).
KEEPER_Y, BACK_Y, FRONT_Y = 2075, 1640, 560
ROW_SPACING = {2: 277 * K, 3: 315 * K, 4: 277 * K}   # distanza fra etichette, come nei moduli Canva
TEAMS_CENTER_Y, TEAMS_HEIGHT = 2440, 70

BLUE, WHITE = (31, 95, 180), (255, 255, 255)
THEMES = {
    'ita_home': dict(surface=(245, 248, 252), line=BLUE, slab=((143, 165, 196), (189, 204, 224)),
                     label=BLUE, text=WHITE, title=WHITE, xi=WHITE,
                     page=((86, 150, 222), (16, 66, 146))),
    'ita_away': dict(surface=(37, 101, 184), line=WHITE, slab=((14, 52, 110), (24, 72, 140)),
                     label=WHITE, text=BLUE, title=BLUE, xi=BLUE,
                     page=((255, 255, 255), (196, 216, 240))),
}

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
# Disegno
# --------------------------------------------------------------------------------------
def _hex(color):
    return '#%02x%02x%02x' % tuple(color)


def _page(kit, assets):
    """Sfondo a tutta pagina: sfumatura morbida (più chiara in alto al centro) con una
    leggera nuvolatura e grana. Azzurro con la maglia home, bianco-azzurro con la away."""
    c = THEMES[kit]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    # distanza dal punto di luce (in alto, poco a destra del centro), ellisse allungata in verticale
    d = np.sqrt(((xx - W * 0.56) / (W * 0.95)) ** 2 + ((yy - H * 0.30) / (H * 0.85)) ** 2)
    t = np.clip(d, 0, 1) ** 1.3
    rng = np.random.default_rng(7)                       # sempre la stessa texture
    clouds = Image.fromarray((rng.random((12, 9)) * 255).astype(np.uint8), 'L').resize((W, H), Image.Resampling.BICUBIC)
    t = np.clip(t + (np.asarray(clouds, np.float32) / 255 - 0.5) * 0.16, 0, 1)[..., None]
    light, dark = (np.array(v, np.float32) for v in c['page'])
    rgb = light + (dark - light) * t
    rgb += rng.normal(0, 2.2, (H, W, 1)).astype(np.float32)   # grana fine, uguale sui tre canali
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), 'RGB').convert('RGBA')


def _pitch(kit, assets):
    """Campo delle probabili (grigio) ricolorato: prato, linee e bordo nei colori del tema."""
    c = THEMES[kit]
    src = Image.open(Path(assets) / 'overlays' / 'starting_xi_pitch.png').convert('LA')
    lum = np.asarray(src.getchannel('L'), dtype=np.float32)
    # prato e linee: dal nero delle linee (30) al grigio del prato (222); la grana resta
    t = np.clip((lum - 30) / (222 - 30), 0, 1.04)[..., None]
    line, surface = np.array(c['line'], np.float32), np.array(c['surface'], np.float32)
    rgb = line + (surface - line) * t
    # bordo (lastra): dal tono scuro al chiaro secondo il grigio originale (110..155)
    dark, light = (np.array(v, np.float32) for v in c['slab'])
    u = np.clip((lum[SLAB_FROM:] - 110) / (155 - 110), 0, 1)[..., None]
    rgb[SLAB_FROM:] = dark + (light - dark) * u
    out = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), 'RGB').convert('RGBA')
    out.putalpha(src.getchannel('A'))
    return out


def _title(kit, assets):
    """'starting' + 'XI' su una riga, dove le probabili hanno 'probabile XI'."""
    c = THEMES[kit]
    word = Image.open(Path(assets) / 'overlays' / 'starting.png').convert('RGBA')
    xi = Image.open(Path(assets) / 'overlays' / 'xi.png').convert('RGBA')
    # altezza x e riga di base di "starting": la fascia di righe più piene
    counts = (np.asarray(word.getchannel('A')) > 100).sum(1)
    dense = np.nonzero(counts > 0.35 * counts.max())[0]
    x_top, base = int(dense[0]), int(dense[-1])
    scale = TITLE_XHEIGHT / (base - x_top)
    word = word.resize((round(word.width * scale), round(word.height * scale)), Image.Resampling.LANCZOS)
    xi = xi.resize((round(xi.width * XI_HEIGHT / xi.height), XI_HEIGHT), Image.Resampling.LANCZOS)
    total = word.width - XI_OVERLAP + xi.width
    left = round(TITLE_CENTER - total / 2)
    layer = Image.new('RGBA', (W, H))
    layer.alpha_composite(p.flat_color(word, _hex(c['title'])), (left, round(TITLE_BASELINE - base * scale)))
    layer.alpha_composite(p.flat_color(xi, _hex(c['xi'])), (left + word.width - XI_OVERLAP, XI_TOP))
    return layer


def _label(kit, assets, scale):
    """Etichetta delle probabili (rettangolo con ombra) nel colore del tema."""
    c = THEMES[kit]
    src = Image.open(Path(assets) / 'overlays' / 'starting_xi_label.png').convert('RGBA')
    alpha = np.asarray(src.getchannel('A'))
    ys, xs = np.nonzero(alpha >= 250)
    box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)          # rettangolo pieno
    rgba = np.zeros((*alpha.shape, 4), np.uint8)
    rgba[..., :3] = (4, 18, 43)                                      # ombra blu notte
    rgba[..., 3] = alpha
    rgba[box[1]:box[3], box[0]:box[2], :3] = c['label']
    img = Image.fromarray(rgba, 'RGBA')
    k = LABEL_BOX_W * scale / (box[2] - box[0])
    img = img.resize((round(img.width * k), round(img.height * k)), Image.Resampling.LANCZOS)
    return img, (box[0] * k, box[1] * k)


def _name(draw, text, cx, top, kit, assets, scale):
    """Nome in Poppins con spaziatura, centrato; si stringe se è troppo lungo."""
    size = NAME_SIZE * scale
    spacing = NAME_SPACING * scale
    font = ImageFont.truetype(str(Path(assets) / NAME_FONT), round(size))
    widths = [font.getlength(ch) for ch in text]
    total = sum(widths) + spacing * (len(text) - 1)
    max_w = NAME_MAX_W * scale
    if total > max_w:                      # come textLength nelle probabili: si stringe tutto
        squeeze = max_w / total
        font = ImageFont.truetype(str(Path(assets) / NAME_FONT), max(1, round(size * squeeze)))
        widths = [font.getlength(ch) for ch in text]
        spacing *= squeeze
        total = sum(widths) + spacing * (len(text) - 1)
    x = cx - total / 2
    base = top + NAME_BASE * scale
    for ch, w in zip(text, widths):
        draw.text((x, base), ch, font=font, fill=THEMES[kit]['text'], anchor='ls')
        x += w + spacing


def _layout(lines):
    """Centro di ogni etichetta e scala comune (con 5 in linea le etichette si rimpiccioliscono)."""
    widest = max(len(line) for line in lines)
    room = W - 2 * PAGE_MARGIN
    scale = min(1.0, (room + LABEL_GAP) / (widest * (LABEL_BOX_W + LABEL_GAP)))
    out = []
    rows = len(lines) - 1
    for r, line in enumerate(lines):
        y = KEEPER_Y if r == 0 else BACK_Y - (r - 1) * (BACK_Y - FRONT_Y) / max(1, rows - 1)
        n = len(line)
        step = 0
        if n > 1:
            fit = (room - LABEL_BOX_W * scale) / (n - 1)
            step = min(ROW_SPACING.get(n, fit), fit)
        for i, pl in enumerate(line):
            out.append((pl, W / 2 + (i - (n - 1) / 2) * step, y))
    return out, scale


def build_image(*, kit, formation, players, home_name, away_name, assets=g.DEFAULT_ASSET_DIR) -> Image.Image:
    """Grafica STARTING XI dell'Italia (1920x2560). `kit`: 'ita_home' o 'ita_away'."""
    if kit not in THEMES:
        raise ValueError('Tema non valido: solo ita_home / ita_away')
    assets = Path(assets)
    lines = arrange(formation, players)
    names = display_names(players)

    card = _page(kit, assets)
    card.alpha_composite(_pitch(kit, assets), (0, PITCH_TOP))
    card.alpha_composite(_title(kit, assets))
    # JR in contrasto con la pagina: bianco sull'azzurro, azzurro sul bianco
    card = p.brand(card, 'ita_away' if kit == 'ita_home' else 'ita_home', assets)

    placed, scale = _layout(lines)
    label, (bx, by) = _label(kit, assets, scale)
    for _, cx, cy in placed:
        top = cy - LABEL_BOX_H * scale / 2
        card.alpha_composite(label, (round(cx - LABEL_BOX_W * scale / 2 - bx), round(top - by)))
    draw = ImageDraw.Draw(card)
    for pl, cx, cy in placed:
        _name(draw, names[id(pl)], cx, cy - LABEL_BOX_H * scale / 2, kit, assets, scale)

    teams = p.match_name_mark(home_name, away_name, kit, assets, TEAMS_HEIGHT)
    card.alpha_composite(teams, (round((W - teams.width) / 2), round(TEAMS_CENTER_Y - teams.height / 2)))
    return card.convert('RGB')


def render_png(**kwargs) -> bytes:
    stream = io.BytesIO()
    build_image(**kwargs).save(stream, format='PNG', optimize=True)
    return stream.getvalue()
