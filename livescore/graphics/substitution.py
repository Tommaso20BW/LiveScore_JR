"""CAMBIO: "SUB" / "SUBS" grande al centro, chi entra sopra e chi esce sotto (solo cambi Juventus).

- In alto il quadrato IN (pieno, colore del tema, lato alto quanto la lista) con, accanto, numero di maglia nel suo riquadro
  e nome e cognome di ogni giocatore che entra; in basso lo stesso con OUT (grigio chiaro, con le stesse linee).
- In mezzo SUB (un cambio) o SUBS (più cambi), alto e stretto, nel colore del tema; ai lati un
  triangolo che sale (entra) e uno che scende (esce).
- 1-5 cambi (fino a 11 nelle amichevoli di ImageGen): con più giocatori righe, scritta e riquadri
  si rimpiccioliscono, il quadrato IN / OUT (lettere comprese) segue la lista; tutto resta centrato.
- Stemmi in fondo. Niente minuto o risultato: il minuto resta nel testo del messaggio.
- Pannello chiaro (Away rosa): scritta e riquadro IN scuri, OUT bianco.
- Coppa Italia, Supercoppa, Supercoppa UEFA e Champions: lettere di IN bianche sul riquadro rosso o blu.

Nessun effetto su Telegram: restituisce solo il PNG.
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps

from livescore.graphics import goal as g
from livescore.graphics import portrait as P

W, H = P.W, P.H
X0, Y0, X1, Y1 = P.M, P.M, P.W - P.M, P.H - P.M
NAME_FONT = 'fonts/DharmaGothicEBold.otf'
CREST_HEIGHT = 52
LINE = {1: 70, 2: 70, 3: 58, 4: 50, 5: 44, 6: 42, 7: 40, 8: 38, 9: 36, 10: 35, 11: 34}   # altezza di una riga
WORD_H = {1: 520, 2: 520, 3: 470, 4: 400, 5: 350,                                     # altezza di SUB / SUBS
          6: 300, 7: 260, 8: 230, 9: 205, 10: 180, 11: 160}
TAG_FILL = .8                                         # OUT occupa al massimo questa parte del lato del quadrato
TAG_SCALE = .64                                       # trama di IN / OUT sempre a questa scala: linee uguali ovunque
TAG_LINE = 52                                         # le linee staccano dal fondo di tanto (0-255), in ogni colore
WORD_SRC = 560                                        # SUB / SUBS disegnato a questa altezza e poi stretto
TEXT = '#EDEDED'
INK = '#151515'
OUT_TAG = '#CFCFCF'
OUT_NUM = '#4E4E4E'
OUT_ARROW = '#A8A8A8'
WHITE_IN = ('coppa', 'supercoppa', 'usc', 'ucl')     # riquadro IN rosso o blu: lettere bianche, non scure


class SubstitutionGraphicUnavailable(RuntimeError):
    """Mancano numero o cognome: il bot invia solo il testo."""


@lru_cache(maxsize=64)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def printable(text: str, font_path: str) -> str:
    """Testo in maiuscolo con i soli caratteri che il font sa disegnare
    (una lettera mancante perde l'accento; se manca anche quella, salta)."""
    font = _font(font_path, 100)
    missing = bytes(font.getmask(''))

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


# ───────────────────────────── pezzi ─────────────────────────────
def _sized(font_path, cap):
    ref = _font(font_path, 200).getbbox('H', anchor='ls')
    return _font(font_path, max(1, round(200 * cap / (ref[3] - ref[1]))))


def _tight_text(text, cap, font_path):
    """Testo bianco ritagliato: maiuscole alte `cap` px."""
    f = _sized(font_path, cap)
    box = f.getbbox(text)
    layer = Image.new('RGBA', (box[2] - box[0] + 20, box[3] - box[1] + 20))
    ImageDraw.Draw(layer).text((10 - box[0], 10 - box[1]), text, font=f, fill='white')
    return layer.crop(layer.getchannel('A').getbbox())


def _line_text(text, cap, font_path):
    """Testo bianco a altezza fissa: la riga di base è sempre allo stesso punto (accenti e Ç non spostano nulla)."""
    f = _sized(font_path, cap)
    up, down = round(cap * .45), round(cap * .35)
    box = f.getbbox(text, anchor='ls')
    layer = Image.new('RGBA', (box[2] - box[0] + 4, cap + up + down))
    ImageDraw.Draw(layer).text((2 - box[0], cap + up), text, font=f, fill='white', anchor='ls')
    return layer


def _flat(layer, color):
    return P.flat_color(layer, color)


def _row(parts, gap):
    """Affianca i pezzi centrandoli in verticale."""
    out = Image.new('RGBA', (sum(p.width for p in parts) + gap * (len(parts) - 1), max(p.height for p in parts)))
    x = 0
    for p in parts:
        out.alpha_composite(p, (x, (out.height - p.height) // 2))
        x += p.width + gap
    return out


def _fit(layer, width):
    if layer.width <= width:
        return layer
    return layer.resize((width, max(1, round(layer.height * width / layer.width))), Image.Resampling.LANCZOS)


def _triangle(h, up):
    w = round(h * 1.15)
    t = Image.new('RGBA', (w, h))
    ImageDraw.Draw(t).polygon([(0, h), (w / 2, 0), (w, h)] if up else [(0, 0), (w, 0), (w / 2, h)], fill='white')
    return t


class Style:
    """Colori del tema: pannello scuro (testo chiaro, tema per chi entra) o chiaro (Away rosa: tutto scuro)."""

    def __init__(self, key, assets):
        self.key, self.assets = key, assets
        self.light = key == 'away'
        self.text = P.AWAY_DARK if self.light else TEXT

    def word(self, layer):
        """SUB / SUBS, come le scritte grandi delle altre grafiche."""
        if self.light:
            return P.textured(layer, self.key, self.assets, color=P.AWAY_DARK)
        if self.key == 'ucl':
            return P.ucl_gradient(layer, self.assets)
        return P.textured(layer, self.key, self.assets)

    def fill(self, layer):
        """Riquadro IN e triangolo di chi entra: texture del tema in zoom, come nomi e stemmi."""
        if self.light:
            return P.textured(layer, self.key, self.assets, True, color=P.AWAY_DARK)
        if self.key == 'ucl':
            return P.ucl_gradient(layer, self.assets)
        return P.textured(layer, self.key, self.assets, True)

    def tag_text(self, up):
        if up and (self.light or self.key in WHITE_IN):
            return '#FFFFFF'
        return P.AWAY_DARK if self.light else INK

    def tag_color(self, up):
        """Colore del quadrato IN / OUT (None: i due blu della Champions)."""
        if not up:
            return '#FFFFFF' if self.light else OUT_TAG
        if self.light:
            return P.AWAY_DARK
        return None if self.key == 'ucl' else P.COLORS[self.key]

    def num_colors(self, up):
        """(fondo, cifre) del riquadro del numero."""
        if self.light:
            return (P.AWAY_DARK, '#FFFFFF') if up else ('#FFFFFF', P.AWAY_DARK)
        return (TEXT, INK) if up else (OUT_NUM, TEXT)

    def arrow(self, h, up):
        t = _triangle(h, up)
        if up:
            return self.fill(t)
        return _flat(t, '#FFFFFF' if self.light else OUT_ARROW)


def _num_box(num, h, up, st, font_path):
    back, ink = st.num_colors(up)
    t = _flat(_tight_text(num, round(h * .62), font_path), ink)
    box = Image.new('RGBA', (max(round(h * 1.05), t.width + 22), h), ImageColor.getrgb(back) + (255,))
    box.alpha_composite(t, ((box.width - t.width) // 2, (box.height - t.height) // 2))
    return box


@lru_cache(maxsize=4)
def _tag_texture(assets):
    """Trama a linee (la stessa per tutti i temi) divisa in sfumatura e linee, a piena risoluzione."""
    tex = Image.open(Path(assets) / 'word_textures' / 'home.png').convert('L')
    lines = ImageChops.subtract(tex, tex.filter(ImageFilter.GaussianBlur(4)))
    shade = ImageOps.autocontrast(tex.filter(ImageFilter.GaussianBlur(24)), cutoff=1)
    return shade, lines


def _tag_fill(size, up, st):
    """Fondo del quadrato IN / OUT: colore sfumato e linee chiare (scure sul bianco) sempre alla stessa
    scala e con lo stesso stacco dal fondo, qualunque sia il colore o la misura del quadrato."""
    shade, lines = _tag_texture(str(st.assets))
    w, h = size
    cw, ch = min(shade.width, round(w / TAG_SCALE)), min(shade.height, round(h / TAG_SCALE))
    x, y = (shade.width - cw) // 2, (shade.height - ch) // 2
    sh = shade.crop((x, y, x + cw, y + ch)).resize(size, Image.Resampling.LANCZOS)
    ln = lines.crop((x, y, x + cw, y + ch)).resize(size, Image.Resampling.LANCZOS)
    color = st.tag_color(up)
    if color is None:
        dark, _, light = P.UCL_GRADIENT
        base = ImageOps.colorize(sh, black=dark, white=light)
        rgb = ImageColor.getrgb(P.UCL_GRADIENT[1])
    else:
        rgb = ImageColor.getrgb(color)
        base = ImageChops.multiply(Image.new('RGB', size, rgb),
                                   sh.point(lambda v: round(255 * (.8 + .2 * v / 255))).convert('RGB'))
    lum = .9 * (.299 * rgb[0] + .587 * rgb[1] + .114 * rgb[2])
    if lum > 215:                                     # fondo bianco: linee scure
        target, alpha = (0, 0, 0), TAG_LINE / lum
    else:
        target, alpha = (255, 255, 255), min(.9, max(.22, TAG_LINE / (255 - lum)))
    mask = ln.point(lambda v: round(min(255, v * 5) * alpha))
    return Image.composite(Image.new('RGB', size, target), base, mask).convert('RGBA')


def _tag(text, h, up, st, font_path):
    """Quadrato pieno IN / OUT con il lato alto quanto la lista dei giocatori; IN e OUT con lettere della
    stessa altezza (quella con cui OUT ci sta)."""
    cap = round(h * .62)
    wide = _tight_text('OUT', cap, font_path).width
    if wide > h * TAG_FILL:
        cap = max(1, int(cap * h * TAG_FILL / wide))
    t = _tight_text(text, cap, font_path)
    box = _tag_fill((h, h), up, st)
    box.alpha_composite(_flat(t, st.tag_text(up)), ((box.width - t.width) // 2, (box.height - t.height) // 2))
    return box


def _block(players, up, line_h, st, font_path):
    """IN | numeri | nomi (chi entra) oppure nomi | numeri | OUT (chi esce)."""
    cap = round(line_h * .78)
    gap = round(line_h * .22)
    boxes = [_num_box(p[0], line_h, up, st, font_path) for p in players]
    names = [_flat(_line_text(p[2], cap, font_path), st.text) for p in players]
    height = len(players) * line_h + (len(players) - 1) * gap
    nums = Image.new('RGBA', (max(b.width for b in boxes), height))
    col = Image.new('RGBA', (max(t.width for t in names), height))
    for k, (b, t) in enumerate(zip(boxes, names)):
        y = k * (line_h + gap)
        nums.alpha_composite(b, ((nums.width - b.width) // 2, y))
        col.alpha_composite(t, (0 if up else col.width - t.width, y + (line_h - t.height) // 2))
    tag = _tag('IN' if up else 'OUT', max(height, round(line_h * 1.9)), up, st, font_path)
    return _row([tag, nums, col] if up else [col, nums, tag], round(line_h * .3))


def _crest(name, tid, key, assets, ink=None):
    """Stemma come nelle altre grafiche; sul pannello chiaro gli stemmi a un colore (Juve) diventano `ink`."""
    mark = P.logo(name, tid, key, assets, CREST_HEIGHT)
    if mark is None or ink is None or key in P.ITALY_THEMES:
        return mark
    if g.resolve_team_logo_source(name, str(tid), assets)[1] != 'FCLogo':
        return mark
    return _flat(mark.convert('RGBA'), ink)


def _crests(card, key, assets, home, away, ink=None):
    marks = [_crest(name, tid, key, assets, ink) for name, tid in (home, away)]
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
    """pairs: [(esce, entra)], ogni giocatore (numero di maglia, cognome[, nome e cognome])."""
    if not pairs:
        raise SubstitutionGraphicUnavailable('Nessun cambio')
    assets = Path(assets)
    key = P.theme(kit, competition)
    font = str(assets / NAME_FONT)
    clean = []
    for pair in pairs:
        row = []
        for player in pair:
            number, surname = player[0], player[1]
            full = player[2] if len(player) > 2 and player[2] else surname
            digits = ''.join(ch for ch in str(number or '') if ch.isdigit())
            name = printable(full, font) or printable(surname, font)
            if not digits or not printable(surname, font) or not name:
                raise SubstitutionGraphicUnavailable(f'Numero o cognome mancante: {number!r} {surname!r}')
            row.append((digits, printable(surname, font), name))
        clean.append(tuple(row))

    st = Style(key, assets)
    card = Image.open(assets / 'portrait' / f'{key}_clean_1086x1448.png').convert('RGBA')
    n = len(clean)
    line_h = LINE.get(n, 34)
    word = _tight_text('SUB' if n == 1 else 'SUBS', WORD_SRC, font)
    word_h = WORD_H.get(n, 160)
    word_w = min(word.width, 640 if n == 1 else 720, 720 if n <= 5 else round(word_h * 2.2))   # oltre 5 non si allarga
    word = st.word(word.resize((word_w, word_h), Image.Resampling.LANCZOS))
    top = _fit(_block([i for _, i in clean], True, line_h, st, font), X1 - X0 - 100)
    bot = _fit(_block([o for o, _ in clean], False, line_h, st, font), X1 - X0 - 100)
    gap = 50 if n < 4 else 38 if n <= 5 else 30 if n <= 8 else 26

    # blocco centrato tra il bordo alto e gli stemmi
    crest_top = Y1 - 40 - CREST_HEIGHT
    total = top.height + gap + word.height + gap + bot.height
    y0 = round((Y0 + 40 + crest_top - 40) / 2 - total / 2)
    wy = y0 + top.height + gap
    cy = wy + word.height / 2
    P.soft_place(card, word, (round((W - word.width) / 2), wy), key=key)
    card.alpha_composite(top, (round((W - top.width) / 2), y0))
    card.alpha_composite(bot, (round((W - bot.width) / 2), wy + word.height + gap))
    up, down = st.arrow(44, True), st.arrow(44, False)
    card.alpha_composite(up, (round(W / 2 - word.width / 2 - 34 - up.width), round(cy - up.height / 2)))
    card.alpha_composite(down, (round(W / 2 + word.width / 2 + 34), round(cy - down.height / 2)))
    _crests(card, key, assets, (home_name, home_id), (away_name, away_id), P.AWAY_DARK if st.light else None)
    return P.brand(card, key, assets)


def render_png(pairs, **kwargs) -> bytes:
    return P.png(render(pairs, **kwargs))
