"""Filtri cromatici UEFA sulle foto dei giocatori (stile EA Sports FC).

Solo il giocatore scontornato: sfondo, scritte e loghi restano come sono. Trasparenza e dimensioni non
cambiano. Le competizioni senza preset (campionato, coppe nazionali, Italia, ...) restituiscono la
stessa immagine, intatta.

Passaggi:
1. tinta: curva per canale (3 tabelle da 256 valori, Image.point), pelle riportata in parte al tono naturale;
2. chiarezza (contrasto locale ampio) e nitidezza fine;
3. vivacità sui colori poco saturi, pelle esclusa, e pelle leggermente meno calda;
4. luce da set: volto un po' più chiaro, corpo che scende verso il buio (relight=False per i ritagli);
5. bordo luminoso sottile lungo il contorno, nel colore della competizione.
"""
import numpy as np
from PIL import Image, ImageFilter

# Chiavi di portrait.theme().
# contrast: curva a S (0 = niente). deep: ombre più profonde. lift: luce generale.
# shadow/high: spinta per canale (R, G, B) nelle ombre e nelle luci (0.10 = +10%).
# skin_keep: quanto la pelle resta com'era nella tinta. clarity/sharp: forza (%) di contrasto locale e nitidezza.
# vib: vivacità. face/body: luce sul volto e sul fondo della sagoma. rim/rim_a: colore e forza del bordo.
PRESETS = {
    'ucl': dict(contrast=.45, deep=.16, lift=.02, shadow=(-.07, .0, .15), high=(-.05, .02, .11), skin_keep=.45,
                clarity=20, sharp=18, vib=1.10, face=1.05, body=.74, rim=(150, 205, 255), rim_a=.30),
    # Supercoppa UEFA: stessa resa blu della Champions, più leggera.
    'usc': dict(contrast=.32, deep=.10, lift=.015, shadow=(-.035, .0, .07), high=(-.02, .012, .05), skin_keep=.65,
                clarity=15, sharp=15, vib=1.06, face=1.03, body=.82, rim=(150, 205, 255), rim_a=.20),
    'uel': dict(contrast=.42, deep=.12, lift=.015, shadow=(.09, .025, -.09), high=(.10, .04, -.09), skin_keep=.42,
                clarity=20, sharp=18, vib=1.08, face=1.05, body=.74, rim=(255, 196, 130), rim_a=.28),
    'conference': dict(contrast=.42, deep=.17, lift=.0, shadow=(-.10, .07, .05), high=(-.04, .07, .0), skin_keep=.42,
                       clarity=20, sharp=18, vib=1.06, face=1.05, body=.74, rim=(130, 255, 215), rim_a=.28),
}
SKIN_COOL = (.965, 1.0, 1.02)      # pelle: un filo meno rossa/arancio, per non scaldarla sotto la tinta

_LUTS = {}
_LUMA = np.array([.299, .587, .114], dtype=np.float32)


def _lut(key):
    if key not in _LUTS:
        p = PRESETS[key]
        x = np.linspace(0, 1, 256)
        y = x + p['contrast'] * (x * x * (3 - 2 * x) - x)
        ws, wh = (1 - x) ** 2, x ** 2                 # pesi di ombre e luci
        y = y * (1 - p['deep'] * ws) + p['lift'] * (1 - ws)
        _LUTS[key] = np.concatenate([
            np.clip(np.round((y + p['shadow'][c] * ws * 1.6 + p['high'][c] * wh) * 255), 0, 255).astype(np.uint8)
            for c in range(3)]).tolist()
    return _LUTS[key]


def _skin(a):
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return ((r > 70) & (g > 35) & (b > 15) & (r > g) & (r > b) & (r - np.minimum(g, b) > 12)
            & (a.max(-1) - a.min(-1) > 12) & (np.abs(r - g) > 8)).astype(np.float32)[..., None]


def grade(image, key, relight=True):
    """Foto del giocatore (RGBA) con il filtro della competizione; senza preset torna invariata."""
    p = PRESETS.get(key)
    if p is None:
        return image
    rgba = image.convert('RGBA')
    alpha = rgba.getchannel('A')
    rgb = rgba.convert('RGB')
    src = np.asarray(rgb, dtype=np.float32)
    skin = _skin(src)
    # 1) tinta
    a = np.asarray(rgb.point(_lut(key)), dtype=np.float32)
    keep = p['skin_keep'] * skin
    a = a * (1 - keep) + src * keep
    # 2) chiarezza + nitidezza
    tinted = Image.fromarray(np.clip(a + .5, 0, 255).astype(np.uint8), 'RGB')
    tinted = tinted.filter(ImageFilter.UnsharpMask(radius=24, percent=p['clarity'], threshold=2))
    tinted = tinted.filter(ImageFilter.UnsharpMask(radius=1.4, percent=p['sharp'], threshold=1))
    a = np.asarray(tinted, dtype=np.float32)
    # 3) vivacità (pelle esclusa) e pelle un filo più fredda
    lum = (a @ _LUMA)[..., None]
    sat = (a.max(-1) - a.min(-1))[..., None] / 255
    a = lum + (a - lum) * (1 + (p['vib'] - 1) * (1 - sat) * (1 - skin))
    a = a * (1 + skin * (np.array(SKIN_COOL, np.float32) - 1))
    # 4) luce da set, lungo l'altezza della sagoma
    bb = alpha.getbbox() or (0, 0, *rgba.size)
    y = (np.arange(rgba.height, dtype=np.float32) - bb[1]) / max(1, bb[3] - bb[1])
    if relight:
        light = p['face'] + (p['body'] - p['face']) * np.clip((y - .3) / .7, 0, 1) ** 1.3
        a *= light[:, None, None]
    # 5) bordo luminoso: solo dentro la sagoma, più forte in alto ("schiarisci" verso il colore)
    al = np.asarray(alpha, np.float32) / 255
    inner = np.asarray(alpha.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.GaussianBlur(2.5)), np.float32) / 255
    edge = np.clip(al - inner, 0, 1) * np.clip(1.2 - y, .2, 1)[:, None]
    k = (edge * p['rim_a'])[..., None]
    a = 255 - (255 - a) * (1 - k * np.array(p['rim'], np.float32) / 255)
    graded = Image.fromarray(np.clip(a + .5, 0, 255).astype(np.uint8), 'RGB').convert('RGBA')
    graded.putalpha(alpha)
    return graded
