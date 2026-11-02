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
# Pagina dei livelli per la grafica vera: alta risoluzione (la card esce 1920x2560 come
# le altre grafiche). SIZE resta per sagome e sfondo ripulito (stesse proporzioni).
PAGE = (1920, 2560)
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


def box(size, frame, *, cover=True, page=SIZE):
    """Posizione e dimensione dell'immagine nella pagina 1086x1448.

    cover=True (sfondo): mai bordi vuoti, la foto copre sempre la pagina.
    cover=False (persona): può uscire o restare dentro la pagina liberamente.
    """
    frame = frame or {}
    w, h = size
    W, H = page
    fit = max(W / w, H / h)
    zoom = min(max(float(frame.get('zoom', 1)), 1 if cover else .2), MAX_ZOOM)
    width, height = w * fit * zoom, h * fit * zoom
    left = (W - width) / 2 + float(frame.get('x', 0)) * W
    top = (H - height) / 2 + float(frame.get('y', 0)) * H
    if cover:
        left = min(0, max(W - width, left))
        top = min(0, max(H - height, top))
    return left, top, width, height


def place(image, frame, *, cover=True, bleed=0, page=SIZE):
    """Immagine sulla pagina. bleed > 0: restituisce anche la striscia sopra la pagina
    (altezza `bleed`), cioe' (pagina, striscia): la parte che esce dal bordo in alto."""
    left, top, width, height = box(image.size, frame, cover=cover, page=page)
    canvas = Image.new('RGBA', (page[0], page[1] + bleed))
    layer = image.resize((max(1, round(width)), max(1, round(height))), Image.Resampling.LANCZOS)
    # Tela vuota: copia diretta (le parti fuori pagina vengono tagliate).
    canvas.paste(layer, (round(left), round(top) + bleed))
    out = canvas.crop((0, bleed, page[0], page[1] + bleed))
    if not bleed:
        return out
    return out, canvas.crop((0, 0, page[0], bleed))


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
EDGE_CHOKE = 0.0007       # quanto il bordo rientra verso la persona (toglie l'alone dello sfondo)
EDGE_FEATHER = 0.0004     # sfumatura finale del bordo (sigma, minimo 0,7 px)
EDGE_SOLID = (0.20, 0.85)  # alpha del modello: sotto = trasparente, sopra = pieno


def refine_cutout(image):
    """Bordo della persona pulito: niente "contorno" visibile quando sta sopra la scritta.

    Il modello restituisce una maschera con un bordo largo e morbido e, sul bordo, pixel che
    hanno ancora il colore dello sfondo originale (di solito scuro): sopra la scritta
    colorata diventano una linea attorno al soggetto. Tre passi, leggeri per non rovinare
    dita, capelli e righe della maglia:
    1) l'alpha si "stringe" (curva piu' netta) e rientra di un paio di pixel;
    2) il colore dei pixel di bordo si rimpiazza con quello della persona subito dentro,
       steso verso fuori pochi pixel alla volta (decontaminazione);
    3) un'ultima sfumatura di ~1 px toglie la seghettatura.
    Sagoma e dimensioni restano quelle della foto: cambia solo il bordo.
    """
    import cv2

    rgba = np.asarray(image.convert('RGBA'))
    rgb = rgba[..., :3].astype(np.float32)
    alpha = rgba[..., 3].astype(np.float32) / 255.0
    side = max(alpha.shape)
    choke = max(1, round(side * EDGE_CHOKE))
    sigma = max(0.7, side * EDGE_FEATHER)

    # 1) alpha piu' netta e ristretta.
    lo, hi = EDGE_SOLID
    core = np.clip((alpha - lo) / (hi - lo), 0, 1)
    core = core * core * (3 - 2 * core)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * choke + 1, 2 * choke + 1))
    core = cv2.erode(core, kernel)
    out_alpha = np.clip(cv2.GaussianBlur(core, (0, 0), sigma), 0, 1)
    out_alpha = np.minimum(out_alpha, alpha)                 # mai piu' piena del modello

    # 2) colore: parte dai pixel sicuri (piena opacita', lontani dal bordo) e si allarga
    # verso fuori a piccoli passi, sostituendo il colore sporco del bordo.
    solid = (alpha > 0.95).astype(np.uint8)
    known = (cv2.erode(solid, np.ones((3, 3), np.uint8)) > 0).astype(np.float32)
    colour = rgb * known[..., None]
    reach = max(3, 2 * choke + 3)
    for _ in range(reach):
        num = cv2.GaussianBlur(colour, (0, 0), 1.0)
        den = cv2.GaussianBlur(known, (0, 0), 1.0)
        fresh = (known == 0) & (den > 0.04)
        if not fresh.any():
            break
        colour[fresh] = num[fresh] / den[fresh, None]
        known[fresh] = 1.0
    # Solo i pixel di bordo (alpha del modello non piena): l'interno resta com'e'.
    # Piu' l'alpha e' bassa, piu' il colore e' sostituito; vicino al pieno resta quasi il proprio.
    mix = np.clip((0.95 - alpha) / 0.4, 0, 1)[..., None]
    rgb = rgb * (1 - mix) + colour * mix

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


# Scontorno fine per la grafica finale (anteprima e invio): BiRefNet lite, più preciso di
# ISNet su capelli e buchi (es. tra mano e maglia) ma ~10 volte più lento. ISNet resta per
# l'editor (subito); il fine parte in background appena c'è la foto e resta in memoria.
# PHASE_FINE_MODEL='' = solo ISNet.
FINE_MODEL = os.getenv('PHASE_FINE_MODEL', 'birefnet-general-lite')
FINE_WAIT_SECONDS = float(os.getenv('PHASE_FINE_WAIT', '20'))   # attesa massima, poi ISNet
FINE_KEEP = 8
_fine_session = None
_fine_jobs = {}
_fine_lock = __import__('threading').Lock()
_fine_pool = None


def _fine_model():
    global _fine_session
    if _fine_session is None:
        if _session is None:
            _quiet_onnxruntime()
        from rembg import new_session
        _fine_session = new_session(FINE_MODEL)
    return _fine_session


def warm_up_fine():
    """Carica il modello fine in anticipo (all'avvio del servizio)."""
    if FINE_MODEL:
        _fine_model()


def _run_fine(job, image):
    import time

    from livescore.core.log import log_line
    started = time.time()
    try:
        from rembg import remove
        out = refine_cutout(remove(image.convert('RGB'), session=_fine_model()).convert('RGBA'))
        buffer = io.BytesIO()
        out.save(buffer, 'PNG')
        job['png'] = buffer.getvalue()
        log_line('INFO', 'PHOTO', f'Scontorno fine pronto in {time.time() - started:.1f} s')
    except Exception as exc:  # noqa: BLE001 - si ripiega sullo scontorno veloce
        log_line('WARN', 'PHOTO', f'Scontorno fine non riuscito: {type(exc).__name__}: {exc}')
    finally:
        job['event'].set()


def start_fine_cutout(key, image):
    """Scontorno fine in background (una foto alla volta), ricordato per `key`."""
    global _fine_pool
    if not FINE_MODEL or has_transparency(image.convert('RGBA')):
        return
    import threading
    from concurrent.futures import ThreadPoolExecutor
    with _fine_lock:
        if key in _fine_jobs:
            return
        job = _fine_jobs[key] = {'event': threading.Event(), 'png': None}
        while len(_fine_jobs) > FINE_KEEP:
            _fine_jobs.pop(next(iter(_fine_jobs)))
        if _fine_pool is None:
            _fine_pool = ThreadPoolExecutor(1, thread_name_prefix='fine-cutout')
    _fine_pool.submit(_run_fine, job, image.copy())


def fine_cutout(key, wait=FINE_WAIT_SECONDS):
    """PNG dello scontorno fine se pronto entro `wait` secondi, altrimenti None."""
    job = _fine_jobs.get(key)
    if job is None:
        return None
    job['event'].wait(max(0, wait))
    return job['png']


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

    from concurrent.futures import ThreadPoolExecutor

    def shot(tmp, value):
        folder = Path(tmp) / str(value)
        folder.mkdir()
        Image.new('RGBA', SIZE, (value, value, value, 255)).save(folder / 'background.png')
        Image.new('RGBA', SIZE).save(folder / 'player.png')
        with Image.open(io.BytesIO(render(folder))) as image:
            return np.asarray(image.convert('RGB'), dtype=np.float32)

    # I due disegni (fondo nero e fondo bianco) insieme: la sagoma arriva prima.
    with tempfile.TemporaryDirectory(prefix='jr_ghost_') as tmp, ThreadPoolExecutor(2) as pool:
        black, white = pool.map(lambda v: shot(tmp, v), (0, 255))
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


def _clean_page(background, person, bg_image, page, bg_look=None):
    """Sfondo ripulito alla misura `page`. La ricostruzione si fa a SIZE (più veloce, in
    memoria per anteprima e invio); fuori dalla zona ricostruita resta la foto a piena
    risoluzione, così lo sfondo non perde nitidezza."""
    from PIL import ImageFilter

    low = clean_background(background, person)
    original = place(bg_image, FIXED_FRAME, cover=True)
    diff = ImageChops.difference(low.convert('RGB'), original.convert('RGB')).convert('L')
    mask = diff.point(lambda v: 255 if v > 6 else 0).filter(ImageFilter.MaxFilter(5))
    mask = mask.filter(ImageFilter.GaussianBlur(1.5)).resize(page, Image.Resampling.LANCZOS)
    hi = place(bg_look if bg_look is not None else bg_image, FIXED_FRAME, cover=True, page=page)
    hi.paste(look(low.resize(page, Image.Resampling.LANCZOS)), (0, 0), mask)
    return hi


# Ritocco automatico delle foto (come i cursori "Texture" di Canva, 0-100):
# sfondo e persona in primo piano, sempre uguali, così combaciano.
LOOK = {'sharpness': 15, 'clarity': 20, 'vignette': 15}


def look(image, *, clarity=True):
    """Nitidezza + chiarezza (contrasto locale) su una foto RGB/RGBA, alpha intatto.
    Misure in proporzione al lato lungo: stesso effetto a ogni risoluzione."""
    from PIL import ImageFilter

    side = max(image.size)
    rgb = image.convert('RGB')
    if clarity and LOOK['clarity']:
        rgb = rgb.filter(ImageFilter.UnsharpMask(radius=max(2, side * 0.012),
                                                 percent=round(LOOK['clarity'] * 1.6), threshold=2))
    if LOOK['sharpness']:
        rgb = rgb.filter(ImageFilter.UnsharpMask(radius=max(0.8, side * 0.0008),
                                                 percent=round(LOOK['sharpness'] * 6), threshold=2))
    if image.mode != 'RGBA':
        return rgb.convert('RGBA')
    out = rgb.convert('RGBA')
    out.putalpha(image.getchannel('A'))
    return out


def look_like(target, original, enhanced):
    """Persona scontornata da `original`: le stesse correzioni dello sfondo (differenza
    enhanced - original), senza toccare i bordi già ripuliti dello scontorno."""
    if target.size != original.size:
        return look(target, clarity=False)
    delta = (np.asarray(enhanced.convert('RGB'), dtype=np.int16)
             - np.asarray(original.convert('RGB'), dtype=np.int16))
    rgb = np.clip(np.asarray(target.convert('RGB'), dtype=np.int16) + delta, 0, 255).astype(np.uint8)
    out = Image.fromarray(rgb, 'RGB').convert('RGBA')
    out.putalpha(target.getchannel('A'))
    return out


def vignette(layer, page, top=0):
    """Bordi più scuri della pagina (`page`). `top`: righe sopra la pagina (striscia della
    persona alzata), così la vignettatura continua senza stacchi."""
    strength = LOOK['vignette'] / 100
    if not strength:
        return layer
    w, h = page
    ys = (np.arange(layer.height, dtype=np.float32) - top + .5) / h * 2 - 1
    xs = (np.arange(layer.width, dtype=np.float32) + .5) / w * 2 - 1
    r = np.sqrt(xs[None, :] ** 2 + ys[:, None] ** 2) / np.sqrt(2)      # 0 centro, 1 angoli
    t = np.clip((r - .45) / .55, 0, None)
    factor = 1 - strength * 1.6 * t * t * (3 - 2 * np.minimum(t, 1))
    a = np.asarray(layer.convert('RGBA'), dtype=np.float32)
    a[..., :3] *= np.clip(factor, 0, 1)[..., None]
    return Image.fromarray(a.round().astype(np.uint8), 'RGBA')


def build_layers(destination, *, background, person=None, background_frame=None, person_frame=None,
                 remove_person=False, page=PAGE):
    """Scrive background.png, player.png e manifest.json in `destination`.

    background / person: byte dell'immagine caricata. Senza `person` la persona
    viene scontornata dallo sfondo stesso. Un PNG già trasparente caricato come
    persona viene usato così com'è.
    background_frame: ignorato. Lo sfondo e' sempre FIXED_FRAME (riempi pagina, fermo).
    person_frame=None: la persona sta ferma sopra se' stessa nello sfondo; altrimenti
    si muove per conto suo.
    page: misura della pagina dei livelli (PAGE: alta risoluzione).
    remove_person=True: la persona e' ricavata dalla stessa foto dello sfondo; se
    viene spostata, nello sfondo la sua sagoma e' cancellata e ricostruita.
    """
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    bg_image = open_photo(background)
    bg_look = look(bg_image)
    if person is None:
        person_bytes = None
        person_image = cutout(bg_image)
        person_look = look_like(person_image, bg_image, bg_look)
    else:
        person_bytes = person
        person_image = open_photo(person)
        if not has_transparency(person_image):
            source = person_image
            person_image = cutout(source)
            person_look = look_like(person_image, source, look(source))
            person_bytes = None
        else:
            person_look = look(person_image, clarity=False)    # PNG già scontornato: solo nitidezza
    follow = person_frame is None
    erase = bool(remove_person) and not follow and moved(person_frame)
    if erase:
        if person_bytes is None:
            buffer = io.BytesIO()
            person_image.save(buffer, 'PNG')
            person_bytes = buffer.getvalue()
        background_layer = _clean_page(background, person_bytes, bg_image, page, bg_look)
    else:
        background_layer = place(bg_look, FIXED_FRAME, cover=True, page=page)
    bleed = round(TOP_BLEED * page[0] / SIZE[0])
    player, strip = place(person_look, FIXED_FRAME if follow else person_frame, cover=follow,
                          bleed=bleed, page=page)
    background_layer = vignette(background_layer, page)
    player = vignette(player, page)
    strip = vignette(strip, page, top=bleed)
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
        'size': list(page),
        'background_frame': FIXED_FRAME,
        'person_frame': (FIXED_FRAME if follow else person_frame) or {},
        'person_follows_background': follow,
        'person_uploaded': person is not None,
        'person_removed_from_background': erase,
    }))
    return destination
