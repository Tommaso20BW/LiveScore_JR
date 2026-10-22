"""Stato del bot salvato su GitHub Gist (anti-duplicati)."""

import atexit
import contextlib
import json
import threading
import time

from livescore import settings
from livescore.core import http as net
from livescore.core.log import log_line


# ==============================================================================
# GIST
# ==============================================================================
def _gist_headers():
    return {"Authorization": f"Bearer {settings.GH_PAT}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


def leggi_stato_da_gist():
    """Legge lo stato dal Gist.

    Ritorna una tupla (ok, state):
      ok=True,  state=dict  → stato letto correttamente
      ok=True,  state=None  → Gist vuoto/non configurato (stato vergine legittimo)
      ok=False, state=None  → ERRORE di rete/API dopo i retry: NON va trattato
                              come stato vergine, altrimenti il bot rimanderebbe
                              tutti i messaggi già inviati.
    """
    if not settings.GH_PAT or not settings.GIST_ID:
        return True, None
    for attempt in range(3):
        try:
            r = net.SESSION.get(f"https://api.github.com/gists/{settings.GIST_ID}", headers=_gist_headers(), timeout=10)
            if r.status_code == 200:
                content = r.json()["files"]["match_state.json"]["content"].strip()
                if not content or content == "{}":
                    return True, None
                return True, json.loads(content)
            log_line("RETRY", "STATE", f"Lettura Gist HTTP {r.status_code} | tentativo {attempt + 1}/3")
        except Exception as e:
            log_line("RETRY", "STATE", f"Lettura Gist fallita: {e} | tentativo {attempt + 1}/3")
        time.sleep(3)
    return False, None


def _gist_retry_delay(response=None, attempt: int = 0) -> int:
    """Attesa breve tra i retry Gist, rispettando Retry-After quando presente."""
    retry_after = None
    try:
        if response is not None:
            retry_after = int(response.headers.get("Retry-After", ""))
    except (TypeError, ValueError):
        retry_after = None
    if retry_after is not None:
        return max(1, min(retry_after, 30))
    return min(2 * (attempt + 1), 6)


def _push(payload: dict) -> tuple[bool, str]:
    """PATCH del Gist con 3 tentativi. Ritorna (riuscito, dettaglio_errore)."""
    last_detail = ""
    for attempt in range(3):
        response = None
        try:
            response = net.SESSION.patch(
                f"https://api.github.com/gists/{settings.GIST_ID}",
                headers=_gist_headers(),
                json=payload,
                timeout=10,
            )
            if response.status_code == 200:
                return True, ""

            last_detail = f"HTTP {response.status_code}"
            log_line("RETRY", "STATE", f"Salvataggio Gist {last_detail} | tentativo {attempt + 1}/3")
        except Exception as e:
            last_detail = str(e)
            log_line("RETRY", "STATE", f"Salvataggio Gist fallito: {e} | tentativo {attempt + 1}/3")

        if attempt < 2:
            time.sleep(_gist_retry_delay(response, attempt))
    return False, last_detail


# ── Salvataggio in background ─────────────────────────────────────────────────
# Il salvataggio di fine ciclo non deve fermare il polling: lo stato (copia) va a un
# thread che scrive sempre l'ULTIMA versione. Se fallisce, il ciclo dopo se ne accorge
# (`take_async_failure`) e riprova in modo sincrono, sospendendo gli invii come prima.
_write_lock = threading.Lock()     # una sola scrittura alla volta, in ordine
_queue_lock = threading.Lock()
_pending: dict | None = None
_failed = False
_wake = threading.Event()
_idle = threading.Event()
_idle.set()
_worker: threading.Thread | None = None
_local = threading.local()


@contextlib.contextmanager
def background():
    """Dentro questo blocco `salva_stato_su_gist` accoda e torna subito."""
    _local.background = True
    try:
        yield
    finally:
        _local.background = False


def _worker_loop() -> None:
    global _pending, _failed
    while True:
        _wake.wait()
        _wake.clear()
        with _write_lock:
            with _queue_lock:
                payload, _pending = _pending, None
            if payload is None:
                with _queue_lock:
                    if _pending is None:
                        _idle.set()
                continue
            ok, detail = _push(payload)
            if not ok:
                _failed = True
                log_line("ERROR", "STATE", "Stato Gist non salvato dopo 3 tentativi"
                         + (f" | {detail}" if detail else ""))
            with _queue_lock:
                if _pending is None:
                    _idle.set()


def _enqueue(payload: dict) -> None:
    global _pending, _worker
    with _queue_lock:
        _pending = payload
        _idle.clear()
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_worker_loop, name="gist-writer", daemon=True)
            _worker.start()
            atexit.register(flush)
    _wake.set()


def flush(timeout: float = 45.0) -> bool:
    """Aspetta che tutto cio' che e' in coda sia scritto (prima di uscire o di azzerare)."""
    return _idle.wait(timeout)


def take_async_failure() -> bool:
    """True (una sola volta) se l'ultimo salvataggio in background e' fallito."""
    global _failed
    failed, _failed = _failed, False
    return failed


def _supersede_pending() -> None:
    """Un salvataggio sincrono e' piu' recente di qualunque cosa sia in coda."""
    global _pending
    with _queue_lock:
        _pending = None


def salva_stato_su_gist(state: dict) -> bool:
    """Salva lo stato con retry e marca lo stato come dirty finché non persiste.

    In caso di errore non viene perso lo stato in memoria: `_gist_dirty` forza
    un nuovo tentativo prima che il live elabori altri eventi nel ciclo seguente.
    Dentro `background()` accoda soltanto (vedi sopra).
    """
    if not settings.GH_PAT or not settings.GIST_ID:
        state.pop("_gist_dirty", None)
        return True

    # Le chiavi con underscore sono flag interni di sessione (log, reset):
    # non vanno persistite nel Gist.
    clean = {k: v for k, v in state.items() if not str(k).startswith("_")}
    payload = {
        "files": {
            "match_state.json": {
                "content": json.dumps(clean, ensure_ascii=False, indent=2)
            }
        }
    }

    if getattr(_local, "background", False):
        _enqueue(payload)
        return True

    global _failed
    with _write_lock:
        _supersede_pending()
        ok, last_detail = _push(payload)
    if ok:
        _failed = False
        was_dirty = bool(state.pop("_gist_dirty", None))
        if was_dirty:
            log_line("OK", "STATE", "Stato Gist recuperato e sincronizzato")
        return True

    state["_gist_dirty"] = True
    log_line(
        "ERROR",
        "STATE",
        f"Stato Gist non salvato dopo 3 tentativi"
        + (f" | {last_detail}" if last_detail else ""),
    )
    return False


def resetta_gist() -> bool:
    """Azzera il Gist con retry e verifica esplicita della risposta GitHub."""
    if not settings.GH_PAT or not settings.GIST_ID:
        return True

    payload = {"files": {"match_state.json": {"content": "{}"}}}
    last_detail = ""
    flush()                      # niente scrittura in coda che possa riempire il Gist dopo il reset

    for attempt in range(3):
        response = None
        try:
            response = net.SESSION.patch(
                f"https://api.github.com/gists/{settings.GIST_ID}",
                headers=_gist_headers(),
                json=payload,
                timeout=10,
            )
            if response.status_code == 200:
                return True

            last_detail = f"HTTP {response.status_code}"
            log_line(
                "RETRY",
                "STATE",
                f"Reset Gist {last_detail} | tentativo {attempt + 1}/3",
            )
        except Exception as e:
            last_detail = str(e)
            log_line(
                "RETRY",
                "STATE",
                f"Reset Gist fallito: {e} | tentativo {attempt + 1}/3",
            )

        if attempt < 2:
            time.sleep(_gist_retry_delay(response, attempt))

    log_line(
        "ERROR",
        "STATE",
        f"Reset Gist non riuscito dopo 3 tentativi"
        + (f" | {last_detail}" if last_detail else ""),
    )
    return False
