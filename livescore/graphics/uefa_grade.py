"""Filtri cromatici UEFA sulle foto dei giocatori (stile EA Sports FC).

Solo il giocatore scontornato: sfondo, scritte e loghi restano come sono. Trasparenza e dimensioni non
cambiano. Le competizioni senza preset (campionato, coppe nazionali, Italia, ...) restituiscono la
stessa immagine, intatta.

Passaggi:
1. tinta leggera solo nei mezzitoni scuri (bianco e nero della maglia restano neutri): curva per canale
   (3 tabelle da 256 valori, Image.point), pelle riportata in parte al tono naturale;
2. chiarezza (contrasto locale ampio) e nitidezza fine;
3. vivacità sui colori poco saturi, pelle esclusa, e pelle leggermente meno calda;
4. luce da set: volto un po' più chiaro, corpo che scende verso il buio (relight=False per i ritagli);
"""
import numpy as np
from PIL import Image, ImageFilter

# Chiavi di portrait.theme().
# contrast: curva a S (0 = niente). deep: ombre più profonde. lift: luce generale.
# shadow: tinta per canale (R, G, B) nei mezzitoni scuri (0.05 = +5%).
# skin_keep: quanto la pelle resta com'era nella tinta. clarity/sharp: forza (%) di contrasto locale e nitidezza.
# vib: vivacità. face/body: luce sul volto e sul fondo della sagoma.
PRESETS = {
    'ucl': dict(contrast=.24, deep=.07, lift=.01, shadow=(-.035, .0, .07), skin_keep=.6,
                clarity=12, sharp=10, vib=1.04, face=1.03, body=.88),
    # Supercoppa UEFA: stessa resa blu della Champions, più leggera.
    'usc': dict(contrast=.18, deep=.04, lift=.01, shadow=(-.02, .0, .04), skin_keep=.7,
                clarity=9, sharp=8, vib=1.02, face=1.02, body=.92),
    'uel': dict(contrast=.24, deep=.06, lift=.01, shadow=(.06, .02, -.05), skin_keep=.6,
                clarity=12, sharp=10, vib=1.03, face=1.03, body=.88),
    'conference': dict(contrast=.24, deep=.08, lift=.0, shadow=(-.05, .045, .025), skin_keep=.6,
                       clarity=12, sharp=10, vib=1.03, face=1.03, body=.88),
}
SKIN_COOL = (.965, 1.0, 1.02)      # pelle: un filo meno rossa/arancio, per non scaldarla sotto la tinta

_LUTS = {}
_LUMA = np.array([.299, .587, .114], dtype=np.float32)


def _lut(key):
    if key not in _LUTS:
        p = PRESETS[key]
        x = np.linspace(0, 1, 256)
        y = x + p['contrast'] * (x * x * (3 - 2 * x) - x)
        ws = (1 - x) ** 2
        y = y * (1 - p['deep'] * ws) + p['lift'] * (1 - ws)
        # tinta solo nei mezzitoni scuri: il nero resta nero e il bianco resta bianco
        wt = 6.75 * x * (1 - x) ** 2 * np.clip(x / .2, 0, 1) ** 2
        _LUTS[key] = np.concatenate([
            np.clip(np.round((y + p['shadow'][c] * wt) * 255), 0, 255).astype(np.uint8) for c in range(3)]).tolist()
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
    graded = Image.fromarray(np.clip(a + .5, 0, 255).astype(np.uint8), 'RGB').convert('RGBA')
    graded.putalpha(alpha)
    return graded
