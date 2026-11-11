"""Fumo nel riquadro dietro al giocatore (GOAL / SAVED).

Tutto disegnato dal codice, senza immagini: una nuvola al centro del riquadro, dietro al
giocatore, che sfuma verso i bordi (non segue la sagoma). I banchi di fumo cambiano a ogni
grafica, ma la quantità di fumo resta sempre la stessa. Il fumo si somma alla luce del
riquadro (schiarisce), non lo copre.
"""
import numpy as np
from PIL import Image, ImageChops, ImageColor, ImageFilter, ImageStat

STRENGTH = .70      # luce massima del fumo (0 = niente)
# Nuvola: centro e raggi in frazioni del riquadro.
CENTER = (.5, .40)
RADIUS = (.46, .36)


def _cloud(size, rng, cells=(2, 4, 8, 16, 32), stretch=1.7):
    """Rumore a più scale, con valori distribuiti in modo uniforme fra 0 e 1: banchi larghi
    con dentro i dettagli fini, e sempre la stessa quantità di parti dense e rade."""
    w, h = size
    total = np.zeros((h, w), dtype=np.float32)
    weight = 1.0
    for c in cells:
        grid = np.asarray([[rng.random() for _ in range(max(2, round(c * stretch)))]
                           for _ in range(max(2, round(c * h / w)))], dtype=np.float32)
        layer = Image.fromarray(grid, 'F').resize((w, h), Image.Resampling.BICUBIC)
        total += np.asarray(layer) * weight
        weight *= .55
    # Per ranghi: senza questo una grafica può uscire molto più fumosa di un'altra.
    ranks = np.empty(total.size, dtype=np.float32)
    ranks[np.argsort(total, axis=None)] = np.linspace(0, 1, total.size, dtype=np.float32)
    return ranks.reshape(total.shape)


def _fog(size, rng):
    w, h = size
    y = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    x = np.linspace(0, 1, w, dtype=np.float32)[None, :]
    d = ((x - CENTER[0]) / RADIUS[0]) ** 2 + ((y - CENTER[1]) / RADIUS[1]) ** 2
    near = np.exp(-d * 1.6)                                        # piena al centro, sfuma ai bordi
    wisps = np.clip((_cloud(size, rng) - .22) / .5, 0, 1) ** 1.3
    return np.clip(near ** 1.25 * (.38 + .80 * wisps), 0, 1)


def apply(panel, color, rng):
    """Somma il fumo al riquadro. `color`: colore del tema, `rng`: random.Random."""
    size = panel.size
    # Tinta: il colore del riquadro stesso, schiarito (blu sul blu, grigio sul nero), con un
    # po' del colore del tema.
    mean = ImageStat.Stat(panel.convert('RGB')).mean
    top = max(max(mean), 1)
    base = [min(255, m / top * 255 * .8 + 255 * .2) for m in mean]
    tint = tuple(round(m * .72 + c * .28) for m, c in zip(base, ImageColor.getrgb(color)))
    fog = Image.fromarray((_fog(size, rng) * 255 * STRENGTH).astype(np.uint8), 'L')
    fog = fog.filter(ImageFilter.GaussianBlur(5))
    light = Image.merge('RGB', [fog.point(lambda v, c=c: round(v * c / 255)) for c in tint])
    lit = ImageChops.screen(panel.convert('RGB'), light)
    lit.putalpha(panel.getchannel('A'))
    return lit
