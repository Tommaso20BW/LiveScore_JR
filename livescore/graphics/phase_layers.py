"""Livelli HALF TIME / END OF 90' / FULL TIME da foto caricate (al posto di Canva).

Produce la stessa cartella di prima (background.png + player.png, 1086x1448),
così portrait.phase() resta identico: sfondo sotto, scritta di fase in mezzo,
persona scontornata sopra.

frame = {'x', 'y', 'zoom'} come nella Mini App: x/y spostamento del centro in
frazione della pagina, zoom >= 1 rispetto a "riempi la pagina".
"""
import io
import json
import os
from pathlib import Path

from PIL import Image, ImageOps

SIZE = (1086, 1448)
MAX_ZOOM = 6
# Provato sulla pagina 1 Canva: 99,3% uguale alla sagoma Canva, ~1,5 s a foto.
CUTOUT_MODEL = os.getenv('PHASE_CUTOUT_MODEL', 'isnet-general-use')

_session = None


def open_photo(raw):
    try:
        with Image.open(io.BytesIO(raw)) as image:
            image = ImageOps.exif_transpose(image)
            return image.convert('RGBA')
    except Exception:
        raise ValueError('Foto non valida: usa JPG o PNG.') from None


def box(size, frame, *, cover=True):
    """Posizione e dimensione dell'immagine nella pagina 1086x1448.

    cover=True (sfondo): mai bordi vuoti, la foto copre sempre la pagina.
    cover=False (persona): può uscire o restare dentro la pagina liberamente.
    """
    frame = frame or {}
    w, h = size
    W, H = SIZE
    fit = max(W / w, H / h)
    zoom = min(max(float(frame.get('zoom', 1)), 1 if cover else .2), MAX_ZOOM)
    width, height = w * fit * zoom, h * fit * zoom
    left = (W - width) / 2 + float(frame.get('x', 0)) * W
    top = (H - height) / 2 + float(frame.get('y', 0)) * H
    if cover:
        left = min(0, max(W - width, left))
        top = min(0, max(H - height, top))
    return left, top, width, height


def place(image, frame, *, cover=True):
    left, top, width, height = box(image.size, frame, cover=cover)
    canvas = Image.new('RGBA', SIZE)
    layer = image.resize((max(1, round(width)), max(1, round(height))), Image.Resampling.LANCZOS)
    # Tela vuota: copia diretta (le parti fuori pagina vengono tagliate).
    canvas.paste(layer, (round(left), round(top)))
    return canvas


def cutout(image):
    """Persona scontornata (stesse dimensioni della foto, sfondo trasparente)."""
    global _session
    from rembg import new_session, remove
    if _session is None:
        # Solo errori nel log: su GitHub onnxruntime avvisa che non trova schede
        # video (GetPciBusId), cosa normale e innocua: lo scontorno usa la CPU.
        import onnxruntime
        onnxruntime.set_default_logger_severity(3)
        _session = new_session(CUTOUT_MODEL)
    return remove(image.convert('RGB'), session=_session).convert('RGBA')


def has_transparency(image):
    alpha = image.getchannel('A')
    return alpha.getextrema()[0] < 250


def ghost(render, width=543):
    """Grafica senza foto, trasparente dove va la foto: placeholder per l'editor.

    render(cartella_livelli) -> PNG della grafica completa. Si disegna due volte,
    con sfondo nero e con sfondo bianco: dalla differenza si ricavano colore e
    trasparenza esatti di tutto quello che sta sopra la foto (cornice, scritta,
    sfumatura, risultato, stemmi), senza ripetere il codice della grafica.
    """
    import tempfile

    import numpy as np

    shots = []
    with tempfile.TemporaryDirectory(prefix='jr_ghost_') as tmp:
        for value in (0, 255):
            folder = Path(tmp) / str(value)
            folder.mkdir()
            Image.new('RGBA', SIZE, (value, value, value, 255)).save(folder / 'background.png')
            Image.new('RGBA', SIZE).save(folder / 'player.png')
            with Image.open(io.BytesIO(render(folder))) as shot:
                shots.append(np.asarray(shot.convert('RGB'), dtype=np.float32))
    black, white = shots
    alpha = np.clip(1 - (white - black).mean(axis=2) / 255, 0, 1)
    color = np.clip(black / np.maximum(alpha, 1 / 255)[..., None], 0, 255)
    rgba = np.dstack([color, alpha * 255]).round().astype(np.uint8)
    image = Image.fromarray(rgba, 'RGBA')
    image = image.resize((width, round(width * image.height / image.width)), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, 'PNG', optimize=True)
    return out.getvalue()


def build_layers(destination, *, background, person=None, background_frame=None, person_frame=None):
    """Scrive background.png, player.png e manifest.json in `destination`.

    background / person: byte dell'immagine caricata. Senza `person` la persona
    viene scontornata dallo sfondo stesso. Un PNG già trasparente caricato come
    persona viene usato così com'è.
    person_frame=None: la persona segue la posizione dello sfondo (stessa foto,
    combacia esattamente); altrimenti si muove per conto suo.
    """
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    bg = open_photo(background)
    if person is None:
        person_image = cutout(bg)
    else:
        person_image = open_photo(person)
        if not has_transparency(person_image):
            person_image = cutout(person_image)
    follow = person_frame is None
    layers = {
        'background': place(bg, background_frame, cover=True),
        'player': place(person_image, background_frame if follow else person_frame, cover=follow),
    }
    for role, image in layers.items():
        temp = destination / f'{role}.tmp.png'
        image.save(temp)
        os.replace(temp, destination / f'{role}.png')
    (destination / 'manifest.json').write_text(json.dumps({
        'source': 'upload',
        'size': list(SIZE),
        'background_frame': background_frame or {},
        'person_frame': (background_frame if follow else person_frame) or {},
        'person_follows_background': follow,
        'person_uploaded': person is not None,
    }))
    return destination
