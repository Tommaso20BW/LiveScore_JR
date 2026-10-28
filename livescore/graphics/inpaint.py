"""Cancella una persona dallo sfondo e ricostruisce quello che c'era dietro.

Serve quando la persona viene spostata: senza questo passaggio, la sagoma
originale resterebbe nella foto di sfondo e la persona comparirebbe due volte.

Motore: LaMa (modello ONNX, gira su CPU con onnxruntime, gia' usato da rembg).
Se il modello non e' disponibile (download fallito, memoria, ecc.) si ripiega su
OpenCV: meno bello su buchi grandi, ma la grafica esce comunque e non si blocca.

image: PIL RGB/RGBA  |  mask: PIL "L", 255 = da cancellare. Stessa dimensione.
"""
import os
from pathlib import Path

import numpy as np
from PIL import Image

LAMA_URL = os.getenv(
    'PHASE_LAMA_URL',
    'https://huggingface.co/Carve/LaMa-ONNX/resolve/main/lama_fp32.onnx',
)
LAMA_PATH = Path(os.getenv('PHASE_LAMA_PATH', Path.home() / '.cache' / 'jr_lama' / 'lama_fp32.onnx'))
LAMA_SIZE = 512            # ingresso fisso del modello
CROP_MARGIN = 0.18         # aria attorno al buco, in frazione del lato del ritaglio
GROW = 0.012               # quanto allargare la sagoma (alone, ombre), frazione del lato lungo
FEATHER = 0.006            # sfumatura del bordo della zona ricostruita

_session = None
_session_failed = False
last_engine = ''           # 'lama' / 'opencv' / '' : per log e test


def _download(url: str, dest: Path) -> None:
    import requests
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_suffix('.part')
    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with open(temp, 'wb') as out:
            for chunk in response.iter_content(1 << 20):
                out.write(chunk)
    if temp.stat().st_size < 10_000_000:
        temp.unlink(missing_ok=True)
        raise RuntimeError('Modello LaMa incompleto.')
    os.replace(temp, dest)


def _lama():
    """Sessione onnx di LaMa, o None se non c'e' (si usa il ripiego)."""
    global _session, _session_failed
    if _session is not None or _session_failed:
        return _session
    try:
        import onnxruntime
        if not LAMA_PATH.is_file():
            _download(LAMA_URL, LAMA_PATH)
        _session = onnxruntime.InferenceSession(str(LAMA_PATH), providers=['CPUExecutionProvider'])
    except Exception:
        _session_failed = True
        _session = None
    return _session


def _odd(value: float) -> int:
    value = max(3, round(value))
    return value if value % 2 else value + 1


def _grow(mask: np.ndarray, size: int) -> np.ndarray:
    import cv2
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
    return cv2.dilate(mask, kernel)


def _run_lama(session, rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """rgb HxWx3 uint8, mask HxW uint8 (0/255) -> rgb uint8, tutti LAMA_SIZE x LAMA_SIZE."""
    names = {i.name: i for i in session.get_inputs()}
    image_name = 'image' if 'image' in names else session.get_inputs()[0].name
    mask_name = 'mask' if 'mask' in names else session.get_inputs()[1].name
    image = (rgb.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
    binary = (mask > 127).astype(np.float32)[None, None]
    out = session.run(None, {image_name: image, mask_name: binary})[0]
    out = np.asarray(out, dtype=np.float32)[0].transpose(1, 2, 0)
    if out.max() <= 1.5:                    # alcune esportazioni escono in 0..1
        out = out * 255.0
    return np.clip(out, 0, 255).astype(np.uint8)


def _fallback(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    import cv2
    radius = max(3, round(max(rgb.shape[:2]) * 0.01))
    filled = cv2.cvtColor(
        cv2.inpaint(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), mask, radius, cv2.INPAINT_TELEA),
        cv2.COLOR_BGR2RGB,
    )
    # Sul buco OpenCV lascia giunzioni nette dove i bordi si incontrano: lo ammorbidisco.
    soft = cv2.GaussianBlur(filled, (0, 0), max(6, rgb.shape[1] * 0.03))
    inside = (mask > 0)[..., None]
    return np.where(inside, soft, filled)


def remove(image: Image.Image, mask: Image.Image, *, engine=None) -> Image.Image:
    """Stessa immagine, senza le zone di `mask` (255). Mai piu' grande dell'originale.

    engine: solo per i test, funzione (rgb 512x512, mask 512x512) -> rgb.
    """
    global last_engine
    import cv2

    rgb = np.asarray(image.convert('RGB'))
    h, w = rgb.shape[:2]
    hole = np.asarray(mask.convert('L').resize((w, h)))
    hole = (hole > 24).astype(np.uint8) * 255
    if not hole.any():
        last_engine = ''
        return image.convert('RGB')
    hole = _grow(hole, _odd(max(w, h) * GROW))

    # Ritaglio quadrato attorno al buco: il modello lavora a 512 px, cosi' il
    # dettaglio resta il piu' alto possibile.
    ys, xs = np.where(hole > 0)
    side = max(xs.max() - xs.min(), ys.max() - ys.min()) * (1 + 2 * CROP_MARGIN)
    side = int(min(max(side, 64), min(w, h)))
    cx, cy = (xs.min() + xs.max()) // 2, (ys.min() + ys.max()) // 2
    x0 = int(min(max(0, cx - side // 2), max(0, w - side)))
    y0 = int(min(max(0, cy - side // 2), max(0, h - side)))
    x1, y1 = min(w, x0 + side), min(h, y0 + side)

    crop = rgb[y0:y1, x0:x1]
    crop_mask = hole[y0:y1, x0:x1]
    small = cv2.resize(crop, (LAMA_SIZE, LAMA_SIZE), interpolation=cv2.INTER_AREA)
    small_mask = cv2.resize(crop_mask, (LAMA_SIZE, LAMA_SIZE), interpolation=cv2.INTER_NEAREST)

    filled = None
    if engine is not None:
        filled, last_engine = engine(small, small_mask), 'test'
    else:
        session = _lama()
        if session is not None:
            try:
                filled, last_engine = _run_lama(session, small, small_mask), 'lama'
            except Exception:
                filled = None
        if filled is None:
            filled, last_engine = _fallback(small, small_mask), 'opencv'

    filled = cv2.resize(filled, (crop.shape[1], crop.shape[0]), interpolation=cv2.INTER_CUBIC)
    # Solo il buco viene sostituito, con un bordo morbido: il resto resta pixel per pixel.
    soft = cv2.GaussianBlur(crop_mask.astype(np.float32) / 255.0,
                            (_odd(max(w, h) * FEATHER * 2), _odd(max(w, h) * FEATHER * 2)), 0)
    alpha = np.clip(np.maximum(soft, (crop_mask > 0) * 1.0), 0, 1)[..., None]
    merged = (filled.astype(np.float32) * alpha + crop.astype(np.float32) * (1 - alpha)).round()
    out = rgb.copy()
    out[y0:y1, x0:x1] = merged.astype(np.uint8)
    return Image.fromarray(out, 'RGB')
