"""CAMBIO: il pannello diventa lo schermo a led del quarto uomo (solo cambi Juventus).

- Tutto il pannello è uno schermo a puntini (si vedono anche i puntini spenti).
- Sopra chi entra (verde), sotto chi esce (rosso), in tutti i temi; divisi da una riga di puntini.
- Numero di maglia a puntini (Dharma) e solo il cognome a puntini (Bebas), anche con un cambio.
- 1-2 cambi: colonne, numero sopra il cognome. 3 o più: una riga per giocatore
  (triangolo, numero allineato a destra, cognome), blocco centrato.
- Stemmi in fondo. Niente scritte, minuto o risultato: il minuto resta nel testo del messaggio.

Nessun effetto su Telegram: restituisce solo il PNG.
"""

from __future__ import annotations

import math
import unicodedata
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageStat

from livescore.graphics import goal as g
from livescore.graphics import portrait as P

W, H = P.W, P.H
X0, Y0, X1, Y1 = P.M, P.M, P.W - P.M, P.H - P.M
DOT = 5                         # passo dei puntini accesi
BG = 3 * DOT                    # passo dei puntini spenti dello sfondo (visibili, come uno schermo vero)
GX0 = X0 + ((X1 - X0) % BG) // 2
GY0 = Y0 + ((Y1 - Y0) % BG) // 2
IN_LED = '#14FF55'              # chi entra: verde acceso, come il tabellone del quarto uomo (in ogni tema)
OUT_LED = '#FF2222'             # chi esce: rosso acceso
GLOW = ((16, .55), (4, .9))     # bagliore dei puntini accesi: (sfocatura, intensità), largo e stretto
NUMBER_FONT = 'fonts/DharmaGothicEBold.otf'
NAME_FONT = 'fonts/BebasNeue2014-Regular.ttf'
CREST_HEIGHT = 52
OFF_MIX = .02                   # puntino spento: colore del pannello schiarito appena
DIM_MIX = .214                  # riga che divide entra / esce
LIGHT_PANEL = 110               # pannelli chiari (Away rosa): lo schermo diventa scuro
DARK_SCREEN_MIX = .06           # schermo scuro: ombra del tema con un po' del colore del pannello


class SubstitutionGraphicUnavailable(RuntimeError):
    """Mancano numero o cognome: il bot invia solo il testo."""


@lru_cache(maxsize=64)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _mix(color, other, k):
    return tuple(round(a + (b - a) * k) for a, b in zip(color, other))


def printable(text: str, font_path: str) -> str:
    """Testo in maiuscolo con i soli caratteri che il font sa disegnare
    (una lettera mancante perde l'accento; se manca anche quella, salta)."""
    font = _font(font_path, 100)
    missing = bytes(font.getmask(''))

    def has(ch):
        return ch == ' ' or bytes(font.getmask(ch)) != missing

    out = []
    for ch in str(text or '').upper():
        if has(ch):
            out.append(ch)
            continue
        base = ''.join(c for c in unicodedata.normalize('NFKD', ch) if unicodedata.category(c) != 'Mn')
        out.extend(c for c in base if has(c))
    return ' '.join(''.join(out).split())


# ───────────────────────────── testo a puntini ─────────────────────────────
def cells(t, capd, cell, font_path, track=1, thr=115):
    """Puntini accesi del testo: maiuscole alte `capd` puntini, riga di base fissa (accenti e Ç
    non spostano nulla). Ritorna (insieme di (riga, colonna), colonne, righe, riga delle maiuscole)."""
    big = _font(font_path, 400)
    ch = big.getbbox('H')
    cap = capd * cell
    f = _font(font_path, max(8, round(400 * cap / (ch[3] - ch[1]))))
    top = math.ceil(capd * .34)
    bot = math.ceil(capd * .26)
    cols = math.ceil((f.getlength(t) + (len(t) * track + 4) * cell) / cell)
    rows = top + capd + bot
    m = Image.new('L', (cols * cell, rows * cell))
    d = ImageDraw.Draw(m)
    x = 2 * cell
    for c in t:
        d.text((x, (top + capd) * cell), c, font=f, fill=255, anchor='ls')
        x += f.getlength(c) + track * cell
    px = m.resize((cols, rows), Image.Resampling.BOX).load()
    on = {(r, q) for r in range(rows) for q in range(cols) if px[q, r] > thr}
    if not on:
        raise SubstitutionGraphicUnavailable(f'Testo vuoto: {t!r}')
    c0 = min(q for _, q in on)
    c1 = max(q for _, q in on)
    return {(r, q - c0) for r, q in on}, c1 - c0 + 1, rows, top


def num_cells(t, nd, cell, font_path):
    """Numero a puntini, cifra per cifra: ogni cifra centrata sulle sue colonne (lo 0 resta simmetrico)."""
    big = _font(font_path, 400)
    ch = big.getbbox('H')
    f = _font(font_path, max(8, round(400 * nd * cell / (ch[3] - ch[1]))))
    on, x = set(), 0
    for dg in t:
        m = Image.new('L', (round(f.getlength(dg)) + 4 * cell, (nd + 2) * cell))
        ImageDraw.Draw(m).text((2 * cell, (nd + 1) * cell), dg, font=f, fill=255, anchor='ls')
        b = m.getbbox()
        if not b:
            continue
        ink = m.crop((b[0], cell, b[2], (nd + 1) * cell))
        cols = max(1, round(ink.width / cell))
        pad = Image.new('L', (cols * cell, nd * cell))
        pad.paste(ink, ((pad.width - ink.width) // 2, 0))
        px = pad.resize((cols, nd), Image.Resampling.BOX).load()
        on |= {(r, x + q) for r in range(nd) for q in range(cols) if px[q, r] > 105}
        x += cols + 1
    return on, max(1, x - 1), nd, 0


def tri_cells(w, up):
    """Triangolo a puntini largo `w` puntini (punta in su: entra, in giù: esce)."""
    h = math.ceil(w / 2)
    on = set()
    for r in range(h):
        k = r if up else h - 1 - r
        half = (k + .5) * (w / 2) / h
        for q in range(w):
            if abs(q + .5 - w / 2) <= half + .01:
                on.add((r, q))
    return on, w, h


def snap(v, o, step=DOT):
    return o + round((v - o) / step) * step


# ───────────────────────────── schermo ─────────────────────────────
class Screen:
    def __init__(self, key, assets):
        self.key, self.assets = key, assets
        self.c = Image.open(assets / 'portrait' / f'{key}_clean_1086x1448.png').convert('RGBA')
        box = (X0, Y0, X1, Y1)
        panel = self.c.crop(box).filter(ImageFilter.GaussianBlur(60))      # via le linee curve
        mean = tuple(round(v) for v in ImageStat.Stat(panel.convert('RGB')).mean)
        if sum(mean) / 3 > LIGHT_PANEL:
            # pannello chiaro: uno schermo a led è scuro
            base = _mix(ImageColor.getrgb(P.SHADOW.get(key, '#000000')), mean, DARK_SCREEN_MIX)
            panel = Image.blend(Image.new("RGBA", panel.size, base + (255,)), panel, .03)
            mean = tuple(round(v) for v in ImageStat.Stat(panel.convert('RGB')).mean)
        self.c.paste(panel, box[:2])
        self.off = _mix(mean, (255, 255, 255), OFF_MIX) + (255,)
        self.dim = _mix(mean, (255, 255, 255), DIM_MIX) + (255,)
        self.gold = Image.new('L', (W, H))
        self.white = Image.new('L', (W, H))
        d = ImageDraw.Draw(self.c)
        for y in range(GY0, Y1 - BG + 1, BG):
            for x in range(GX0, X1 - BG + 1, BG):
                d.ellipse((x + 2, y + 2, x + BG - 3, y + BG - 3), fill=self.off)

    def stamp(self, on, x, y, cell, out=None, color=None):
        """Accende i puntini (x, y: angolo in alto a sinistra, agganciato alla griglia)."""
        step = BG if cell % BG == 0 else DOT      # i numeri a puntini grossi cadono sui puntini dello sfondo
        x, y = snap(x, GX0, step), snap(y, GY0, step)
        if color:
            d = ImageDraw.Draw(self.c)
            for r, q in on:
                d.ellipse((x + q * cell + 1, y + r * cell + 1, x + (q + 1) * cell - 2, y + (r + 1) * cell - 2),
                          fill=color)
            return
        d = ImageDraw.Draw(self.white if out else self.gold)
        gap = 1 if cell > DOT else 0
        for r, q in on:
            d.ellipse((x + q * cell + 1 + gap, y + r * cell + 1 + gap,
                       x + (q + 1) * cell - 1 - gap, y + (r + 1) * cell - 1 - gap), fill=255)

    def light(self):
        base = self.c.convert('RGB')
        black = Image.new('RGB', base.size, 0)
        for mask, color in ((self.gold, IN_LED), (self.white, OUT_LED)):
            col = Image.new('RGB', mask.size, ImageColor.getrgb(color))
            for blur, k in GLOW:        # luce sommata (screen): il fondo si illumina, non si sporca
                glow = mask.filter(ImageFilter.GaussianBlur(blur)).point(lambda a, k=k: min(255, round(a * k)))
                base = ImageChops.screen(base, Image.composite(col, black, glow))
            base.paste(col, (0, 0), mask)
        self.c = base.convert('RGBA')
        return self.c


class Layout:
    """Misure e disegno dei giocatori sullo schermo."""

    def __init__(self, screen, assets):
        self.s = screen
        self.fnum = str(assets / NUMBER_FONT)
        self.fname = str(assets / NAME_FONT)

    def num(self, t, nd, cell):
        return num_cells(t, nd, cell, self.fnum)

    def name(self, t, capd):
        return cells(t, capd, DOT, self.fname)

    def name_size(self, players, width, start):
        capd = start
        while capd > 6 and max(self.name(p[1], capd)[1] for p in players) * DOT > width:
            capd -= 1
        return capd

    def fit_numbers(self, players, box_w, box_h, capd):
        """Altezza dei numeri (uguale per tutti): la più grande in cui il numero più largo sta col
        triangolo e numero + nome stanno nel riquadro. Puntini grossi se il numero è grande."""
        for cell in (3 * DOT, 2 * DOT, DOT):
            nd = int(box_h / cell)
            while nd >= 9:
                nh = nd * cell
                widest = max(self.num(p[0], nd, cell)[1] for p in players) * cell
                side = max(DOT * 3, round(nh * .08)) + max(6, round(nh * .3 / DOT)) * DOT
                if widest / 2 + side <= box_w / 2 * .94 and nh + max(18, round(nh * .1)) + capd * DOT <= box_h:
                    break
                nd -= 1
            if nd * cell >= (170 if cell == 3 * DOT else 110) or cell == DOT:
                return nd, cell
        return 9, DOT

    @staticmethod
    def num_size(nh_max):
        for cell, low in ((3 * DOT, 170), (2 * DOT, 110), (DOT, 0)):
            if nh_max >= low:
                return max(5, int(nh_max / cell)), cell

    def player(self, p, out, ax, y, nd, cell, capd):
        """Triangolo + numero centrati sull'asse ax (il triangolo fuori, a sinistra), cognome sotto."""
        on, w, _, _ = self.num(p[0], nd, cell)
        nh = nd * cell
        self.s.stamp(on, ax - w * cell / 2, y, cell, out)
        ton, tw, th = tri_cells(max(6, round(nh * .3 / DOT)), not out)
        self.s.stamp(ton, ax - w * cell / 2 - max(DOT * 3, round(nh * .08)) - tw * DOT,
                     y + (nh - th * DOT) / 2, DOT, out)
        nm, nw, _, ntop = self.name(p[1], capd)
        gap = max(18, round(nh * .1))
        self.s.stamp(nm, ax - nw * DOT / 2, y + nh + gap - ntop * DOT, DOT, out)

    def columns(self, players, out, y0, h, nd, cell, capd, inner):
        """Giocatori affiancati: numero grande e cognome sotto, centrati nella loro colonna."""
        colw = inner / len(players)
        blk = nd * cell + max(18, round(nd * cell * .1)) + capd * DOT
        for k, p in enumerate(players):
            self.player(p, out, X0 + 30 + colw * (k + .5), y0 + (h - blk) / 2, nd, cell, capd)

    def rows(self, players, out, y0, h, nd, cell, capd, x0, numw, nrows):
        """Giocatori uno sotto l'altro: triangolo, numero (allineato a destra) e cognome accanto."""
        rh = h / nrows
        nh = nd * cell
        ton, tw, th = tri_cells(max(5, round(nh * .38 / DOT)), not out)
        for k, p in enumerate(players):
            cy = y0 + (k + .5) * rh
            on, w, _, _ = self.num(p[0], nd, cell)
            xr = x0 + tw * DOT + round(nh * .12) + numw
            self.s.stamp(on, xr - w * cell, cy - nh / 2, cell, out)
            self.s.stamp(ton, xr - w * cell - round(nh * .12) - tw * DOT, cy - th * DOT / 2, DOT, out)
            nm, _, _, ntop = self.name(p[1], capd)
            self.s.stamp(nm, xr + round(nh * .22), cy - capd * DOT / 2 - ntop * DOT, DOT, out)


def _crests(card, key, assets, home, away):
    marks = [P.logo(name, tid, key, assets, CREST_HEIGHT) for name, tid in (home, away)]
    marks = [m for m in marks if m is not None]
    if not marks:
        return
    gap = 22
    x = (W - sum(m.width for m in marks) - gap * (len(marks) - 1)) // 2
    y = Y1 - 40 - CREST_HEIGHT
    for m in marks:
        card.alpha_composite(m.convert('RGBA'), (x, y + (CREST_HEIGHT - m.height) // 2))
        x += m.width + gap


def render(pairs, *, home_name, away_name, home_id, away_id, kit='home', competition='',
           assets=g.DEFAULT_ASSET_DIR) -> Image.Image:
    """pairs: [(esce, entra)], ogni giocatore (numero di maglia, cognome)."""
    if not pairs:
        raise SubstitutionGraphicUnavailable('Nessun cambio')
    assets = Path(assets)
    key = P.theme(kit, competition)
    fname = str(assets / NAME_FONT)
    clean = []
    for pair in pairs:
        row = []
        for number, surname in pair:
            digits = ''.join(ch for ch in str(number or '') if ch.isdigit())
            name = printable(surname, fname)
            if not digits or not name:
                raise SubstitutionGraphicUnavailable(f'Numero o cognome mancante: {number!r} {surname!r}')
            row.append((digits, name))
        clean.append(tuple(row))

    s = Screen(key, assets)
    lay = Layout(s, assets)
    n = len(clean)
    top = Y0 + 56
    _crests(s.c, key, assets, (home_name, home_id), (away_name, away_id))
    bottom = Y1 - 40 - CREST_HEIGHT - 40
    inner = X1 - X0 - 60
    half = (bottom - top) / 2
    mid = top + half
    s.stamp({(0, j) for j in range(round(inner * .7 / DOT))}, W / 2 - inner * .35, mid, DOT, color=s.dim)
    ins, outs = [i for _, i in clean], [o for o, _ in clean]
    everyone = ins + outs

    if n <= 2:
        capd = lay.name_size(everyone, inner / n * .9, 16 if n == 1 else 12)
        nd, cell = lay.fit_numbers(everyone, inner / n, half * .8, capd)
        lay.columns(ins, False, top, half, nd, cell, capd, inner)
        lay.columns(outs, True, mid, half, nd, cell, capd, inner)
    else:
        rh = (half - 30) / n
        nd, cell = lay.num_size(rh * .74)
        nh = nd * cell
        numw = max(lay.num(p[0], nd, cell)[1] for p in everyone) * cell
        tw = max(5, round(nh * .38 / DOT)) * DOT
        lead = tw + round(nh * .12) + numw + round(nh * .22)
        capd = lay.name_size(everyone, inner * .94 - lead,
                             min(round(rh * .55 / DOT), max(9, round(nh * .6 / DOT))))
        namew = max(lay.name(p[1], capd)[1] for p in everyone) * DOT
        x0 = W / 2 - (lead + namew) / 2
        lay.rows(ins, False, top + 10, half - 30, nd, cell, capd, x0, numw, n)
        lay.rows(outs, True, mid + 20, half - 30, nd, cell, capd, x0, numw, n)
    return P.brand(s.light(), key, assets)


def render_png(pairs, **kwargs) -> bytes:
    return P.png(render(pairs, **kwargs))
