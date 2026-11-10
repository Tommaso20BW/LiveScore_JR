"""Filtri cromatici UEFA sulle foto dei giocatori (stile EA Sports FC).

Solo il giocatore scontornato: sfondo, scritte e loghi restano come sono. Ogni preset è una curva per
canale (3 tabelle da 256 valori, applicate con Image.point) più la saturazione, con la pelle riportata
in parte al tono naturale. Trasparenza e dimensioni non cambiano. Le competizioni senza preset
(campionato, coppe nazionali, Italia, ...) restituiscono la stessa immagine, intatta.
"""
import numpy as np
from PIL import Image

# Chiavi di portrait.theme().
# contrast: curva a S (0 = niente). deep: ombre più profonde. lift: luce generale.
# shadow/high: spinta per canale (R, G, B) nelle ombre e nelle luci (0.10 = +10%).
# sat: saturazione dei colori, pelle esclusa (1 = invariata). skin_keep: quanto la pelle resta com'era.
PRESETS = {
    'ucl': dict(contrast=.45, deep=.16, lift=.02, shadow=(-.07, .0, .15), high=(-.05, .02, .11), sat=.90, skin_keep=.45),
    # Supercoppa UEFA: stessa resa blu della Champions, più leggera.
    'usc': dict(contrast=.32, deep=.10, lift=.015, shadow=(-.035, .0, .07), high=(-.02, .012, .05), sat=.94, skin_keep=.65),
    'uel': dict(contrast=.42, deep=.12, lift=.015, shadow=(.09, .025, -.09), high=(.10, .04, -.09), sat=.90, skin_keep=.42),
    'conference': dict(contrast=.42, deep=.17, lift=.0, shadow=(-.10, .07, .05), high=(-.04, .07, .0), sat=.86, skin_keep=.42),
}

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


def grade(image, key):
    """Foto del giocatore (RGBA) con il filtro della competizione; senza preset torna invariata."""
    p = PRESETS.get(key)
    if p is None:
        return image
    rgba = image.convert('RGBA')
    rgb = rgba.convert('RGB')
    src = np.asarray(rgb, dtype=np.float32)
    out = np.asarray(rgb.point(_lut(key)), dtype=np.float32)
    r, g, b = src[..., 0], src[..., 1], src[..., 2]
    skin = ((r > 70) & (g > 35) & (b > 15) & (r > g) & (r > b) & (r - np.minimum(g, b) > 12)
            & (src.max(-1) - src.min(-1) > 12) & (np.abs(r - g) > 8)).astype(np.float32)[..., None]
    lum = (out @ _LUMA)[..., None]
    out = lum + (out - lum) * (p['sat'] + (1 - p['sat']) * skin)
    keep = p['skin_keep'] * skin
    out = out * (1 - keep) + src * keep
    graded = Image.fromarray(np.clip(out + .5, 0, 255).astype(np.uint8), 'RGB').convert('RGBA')
    graded.putalpha(rgba.getchannel('A'))
    return graded
