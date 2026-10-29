"""Livelli HALF TIME / END OF 90' / FULL TIME da foto caricate (al posto di Canva).

Produce la stessa cartella di prima (background.png + player.png, 1086x1448),
così portrait.phase() resta identico: sfondo sotto, scritta di fase in mezzo,
persona scontornata sopra.

frame = {'x', 'y', 'zoom'} come nella Mini App: x/y spostamento del centro in
frazione della pagina, zoom >= 1 rispetto a "riempi la pagina".

Lo SFONDO e' sempre fermo e riempie la pagina (FIXED_FRAME): nessuno lo sposta.
La PERSONA e' libera (x, y, zoom, anche fuori dalla pagina). Se la persona e'
scontornata dalla stessa foto dello sfondo e viene spostata, viene cancellata dallo
sfondo e la zona e' ricostruita (inpaint.py), cosi' non compare due volte.
"""
import hashlib
import io
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageOps

SIZE = (1086, 1448)
MAX_ZOOM = 6
FIXED_FRAME = {'x': 0.0, 'y': 0.0, 'zoom': 1.0}   # sfondo: sempre "riempi pagina"
MOVED_EPS = 0.0005
_clean_cache = {}
# La grafica e' 1086x1448 con 76 px di cornice: la pagina dei livelli (1086x1448) e' ridotta
# a 0,895 dentro il riquadro, quindi la cornice in alto vale 85 px di pagina. La persona
# puo' uscire dal riquadro solo verso l'alto, dentro quella cornice (player_top.png).
TOP_BLEED = 85
# Provato sulla pagina 1 Canva: 99,3% uguale alla sagoma Canva, ~1,5 s a foto.
CUTOUT_MODEL = os.getenv('PHASE_CUTOUT_MODEL', 'isnet-general-use')

_session = None
_people_session = None
# Tutte le figure umane (anche dietro, tagliate dal bordo): servono per ripulire lo sfondo.
PEOPLE_MODEL = os.getenv('PHASE_PEOPLE_MODEL', 'u2net_human_seg')


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


def place(image, frame, *, cover=True, bleed=0):
    """Immagine sulla pagina. bleed > 0: restituisce anche la striscia sopra la pagina
    (altezza `bleed`), cioe' (pagina, striscia): la parte che esce dal bordo in alto."""
    left, top, width, height = box(image.size, frame, cover=cover)
    canvas = Image.new('RGBA', (SIZE[0], SIZE[1] + bleed))
    layer = image.resize((max(1, round(width)), max(1, round(height))), Image.Resampling.LANCZOS)
    # Tela vuota: copia diretta (le parti fuori pagina vengono tagliate).
    canvas.paste(layer, (round(left), round(top) + bleed))
    page = canvas.crop((0, bleed, SIZE[0], SIZE[1] + bleed))
    if not bleed:
        return page
    return page, canvas.crop((0, 0, SIZE[0], bleed))


def _quiet_onnxruntime():
    """Solo errori nel log di onnxruntime.

    Su GitHub, quando onnxruntime si prepara cerca le schede video e avvisa che
    non le trova (GetPciBusId): normale e innocuo, lo scontorno usa la CPU.
    L'avviso esce proprio mentre si prepara, prima che si possa abbassare il
    log: per quell'istante lo stderr del processo va a /dev/null, poi torna.
    Gli errori Python (eccezioni) restano visibili.
    """
    import os
    import sys

    sys.stderr.flush()
    saved = os.dup(2)
    try:
        with open(os.devnull, 'w') as null:
            os.dup2(null.fileno(), 2)
            import onnxruntime
            onnxruntime.set_default_logger_severity(3)
    finally:
        os.dup2(saved, 2)
        os.close(saved)


# Rifinitura del bordo dello scontorno (vedi refine_cutout). Valori in frazione del lato lungo
# della foto, cosi' l'effetto e' lo stesso a 1000 px come a 4000 px.
EDGE_CHOKE = 0.0016       # quanto il bordo rientra verso la persona (toglie l'alone dello sfondo)
EDGE_FEATHER = 0.0012     # sfumatura del bordo (sigma)
EDGE_SOLID = (0.30, 0.92)  # alpha del modello: sotto = trasparente, sopra = pieno


def refine_cutout(image):
    """Bordo della persona pulito: niente "contorno" visibile quando sta sopra la scritta.

    Il modello restituisce una maschera con bordo duro/seghettato e, sul bordo, pixel che
    hanno ancora il colore dello sfondo originale (alone chiaro o scuro). Tre passi:
    1) la maschera si leviga e si restringe di un soffio (la sagoma entra nella persona);
    2) il bordo si sfuma in modo morbido, a pixel interi e senza gradini;
    3) il colore dei pixel di bordo si rimpiazza con quello della persona subito dentro
       (decontaminazione), cosi' sulla scritta non resta nessuna linea di sfondo.
    Sagoma e dimensioni restano quelle della foto: cambia solo il bordo.
    """
    import cv2

    rgba = np.asarray(image.convert('RGBA'))
    rgb = rgba[..., :3].astype(np.float32)
    alpha = rgba[..., 3].astype(np.float32) / 255.0
    side = max(alpha.shape)
    choke = max(1, round(side * EDGE_CHOKE))
    sigma = max(0.8, side * EDGE_FEATHER)

    # 1) sagoma levigata e ristretta: soglia morbida sull'alpha del modello, poi erosione.
    smooth = cv2.GaussianBlur(alpha, (0, 0), sigma)
    lo, hi = EDGE_SOLID
    core = np.clip((smooth - lo) / (hi - lo), 0, 1)
    core = core * core * (3 - 2 * core)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * choke + 1, 2 * choke + 1))
    core = cv2.erode(core, kernel)

    # 2) bordo sfumato.
    out_alpha = np.clip(cv2.GaussianBlur(core, (0, 0), sigma), 0, 1)
    out_alpha = np.minimum(out_alpha, np.maximum(alpha, cv2.dilate(alpha, kernel)))  # mai oltre il modello

    # 3) colore dell'interno, steso verso il bordo (media pesata, solo pixel sicuri).
    inner = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * choke + 3, 2 * choke + 3))
    sure = (cv2.erode((alpha > 0.97).astype(np.uint8), inner) > 0).astype(np.float32)
    colour = np.zeros_like(rgb)
    weight = np.zeros_like(sure)
    for scale in (1, 3, 9):
        k = (0, 0)
        s = max(1.0, choke * 2.0) * scale
        num = cv2.GaussianBlur(rgb * sure[..., None], k, s)
        den = cv2.GaussianBlur(sure, k, s)
        fresh = (weight < 0.05) & (den > 0.05)
        colour[fresh] = num[fresh] / den[fresh, None]
        weight[fresh] = den[fresh]
    band = np.clip((0.999 - out_alpha) * 8, 0, 1) + (1 - sure) * (out_alpha > 0)
    band = np.clip(band, 0, 1)[..., None]
    have = (weight > 0.05)[..., None]
    rgb = np.where(have, rgb * (1 - band) + colour * band, rgb)

    result = np.dstack([np.clip(rgb, 0, 255), out_alpha * 255]).round().astype(np.uint8)
    return Image.fromarray(result, 'RGBA')


def cutout(image):
    """Persona scontornata (stesse dimensioni della foto, sfondo trasparente)."""
    global _session
    if _session is None:
        _quiet_onnxruntime()            # prima di rembg, che carica onnxruntime
    from rembg import new_session, remove
    if _session is None:
        _session = new_session(CUTOUT_MODEL)
    return refine_cutout(remove(image.convert('RGB'), session=_session).convert('RGBA'))


def people_mask(image):
    """Maschera "L" di tutte le persone nella foto (255 = persona), o None se non disponibile."""
    global _people_session
    try:
        if _people_session is None and _session is None:
            _quiet_onnxruntime()
        from rembg import new_session, remove
        if _people_session is None:
            _people_session = new_session(PEOPLE_MODEL)
        return remove(image.convert('RGB'), session=_people_session, only_mask=True).convert('L')
    except Exception:
        return None


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


def moved(frame):
    """True se la persona non e' piu' dov'e' stata scontornata (sopra se' stessa nello sfondo)."""
    if not frame:
        return False
    return (abs(float(frame.get('x', 0))) > MOVED_EPS or abs(float(frame.get('y', 0))) > MOVED_EPS
            or abs(float(frame.get('zoom', 1)) - 1) > MOVED_EPS)


def clean_background(background, person):
    """Sfondo a pagina intera (RGBA) senza la persona scontornata, che ricostruisce il dietro.

    background / person: byte come in build_layers. La persona e' cancellata nella
    posizione originale (FIXED_FRAME), dove combacia con lo sfondo. Il risultato e'
    tenuto in memoria: anteprima, editor e invio non ricalcolano.
    """
    from livescore.graphics import inpaint

    key = (hashlib.sha256(background).hexdigest(), hashlib.sha256(person).hexdigest())
    if key not in _clean_cache:
        photo = open_photo(background)
        page = place(photo, FIXED_FRAME, cover=True)
        mask = place(open_photo(person), FIXED_FRAME, cover=True).getchannel('A')
        # Anche le persone dietro (o tagliate dal bordo) che lo scontorno non ha preso.
        others = people_mask(photo)
        if others is not None:
            others = place(others.convert('RGBA'), FIXED_FRAME, cover=True).getchannel('R')
            mask = ImageChops.lighter(mask, others)
        clean = inpaint.remove(page.convert('RGB'), mask)
        while len(_clean_cache) >= 4:
            _clean_cache.pop(next(iter(_clean_cache)))
        _clean_cache[key] = clean.convert('RGBA')
    return _clean_cache[key].copy()


def clean_background_jpeg(background, person):
    out = io.BytesIO()
    clean_background(background, person).convert('RGB').save(out, 'JPEG', quality=90)
    return out.getvalue()


def build_layers(destination, *, background, person=None, background_frame=None, person_frame=None,
                 remove_person=False):
    """Scrive background.png, player.png e manifest.json in `destination`.

    background / person: byte dell'immagine caricata. Senza `person` la persona
    viene scontornata dallo sfondo stesso. Un PNG già trasparente caricato come
    persona viene usato così com'è.
    background_frame: ignorato. Lo sfondo e' sempre FIXED_FRAME (riempi pagina, fermo).
    person_frame=None: la persona sta ferma sopra se' stessa nello sfondo; altrimenti
    si muove per conto suo.
    remove_person=True: la persona e' ricavata dalla stessa foto dello sfondo; se
    viene spostata, nello sfondo la sua sagoma e' cancellata e ricostruita.
    """
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    bg_image = open_photo(background)
    if person is None:
        person_bytes = None
        person_image = cutout(bg_image)
    else:
        person_bytes = person
        person_image = open_photo(person)
        if not has_transparency(person_image):
            person_image = cutout(person_image)
            person_bytes = None
    follow = person_frame is None
    erase = bool(remove_person) and not follow and moved(person_frame)
    if erase:
        if person_bytes is None:
            buffer = io.BytesIO()
            person_image.save(buffer, 'PNG')
            person_bytes = buffer.getvalue()
        background_layer = clean_background(background, person_bytes)
    else:
        background_layer = place(bg_image, FIXED_FRAME, cover=True)
    player, strip = place(person_image, FIXED_FRAME if follow else person_frame, cover=follow, bleed=TOP_BLEED)
    layers = {'background': background_layer, 'player': player}
    top_file = destination / 'player_top.png'
    if strip.getchannel('A').getextrema()[1] > 0:
        layers['player_top'] = strip
    else:
        top_file.unlink(missing_ok=True)
    for role, image in layers.items():
        temp = destination / f'{role}.tmp.png'
        image.save(temp)
        os.replace(temp, destination / f'{role}.png')
    (destination / 'manifest.json').write_text(json.dumps({
        'source': 'upload',
        'size': list(SIZE),
        'background_frame': FIXED_FRAME,
        'person_frame': (FIXED_FRAME if follow else person_frame) or {},
        'person_follows_background': follow,
        'person_uploaded': person is not None,
        'person_removed_from_background': erase,
    }))
    return destination
