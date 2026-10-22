"""Invio, modifica e cancellazione messaggi Telegram."""

import json
import time

from livescore import settings
from livescore.constants import MOMENTI_CONFIG
from livescore.core import http as net
from livescore.core.log import log_line
from livescore.graphics import goal as goal_graphics
from livescore.telegram.autodelete import enqueue_response, should_enqueue


# ==============================================================================
# TELEGRAM
# ==============================================================================
def _tg_post(method: str, payload: dict | None = None, data: dict | None = None,
             files: dict | None = None, timeout: int = 10):
    """POST verso l'API Telegram con gestione manuale del rate limit (429,
    rispettando retry_after). Nessun retry automatico su altri errori per
    evitare invii duplicati."""
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/{method}"
    r = None
    for _ in range(3):
        r = net.SESSION.post(url, json=payload, data=data, files=files, timeout=timeout)
        if r.status_code != 429:
            target_chat_id = (payload or {}).get("chat_id") or (data or {}).get("chat_id")
            if should_enqueue(
                method,
                target_chat_id,
                settings.BOT_JR_CHAT_ID,
                settings.TELEGRAM_AUTO_DELETE_SECONDS,
            ):
                try:
                    enqueue_response(
                        net.SESSION,
                        r,
                        settings.GH_PAT,
                        settings.GIST_ID,
                        target_chat_id,
                        settings.TELEGRAM_AUTO_DELETE_SECONDS,
                    )
                except Exception as e:
                    log_line("WARN", "TELEGRAM", f"Coda auto-delete Bot JR non aggiornata: {e}")
            return r
        try:
            retry_after = int(r.json().get("parameters", {}).get("retry_after", 3))
        except Exception:
            retry_after = 3
        log_line("WAIT", "TELEGRAM", f"Rate limit 429; nuovo tentativo tra {retry_after}s")
        time.sleep(min(retry_after, 30))
    return r


def send_telegram(text: str):
    if not settings.BOT_TOKEN or not settings.CHAT_ID:
        log_line("WARN", "TELEGRAM", "BOT_TOKEN o CHAT_ID mancanti")
        return
    try:
        r = _tg_post("sendMessage", payload={"chat_id": settings.CHAT_ID, "text": text, "parse_mode": "HTML"})
        r.raise_for_status()
    except Exception as e:
        log_line("ERROR", "TELEGRAM", f"sendMessage fallito: {e}")


def send_telegram_edit(message_id: int, text: str) -> bool:
    """Modifica un messaggio esistente. Ritorna True solo se l'edit è
    andato a buon fine, così chi chiama può evitare di salvare lo stato
    come 'fatto' e ritentare al ciclo successivo in caso di errore."""
    if not settings.BOT_TOKEN or not settings.CHAT_ID or not message_id:
        return False
    try:
        r = _tg_post("editMessageText", payload={
            "chat_id": settings.CHAT_ID, "message_id": message_id,
            "text": text, "parse_mode": "HTML"
        })
        r.raise_for_status()
        return True
    except Exception as e:
        log_line("ERROR", "TELEGRAM", f"editMessageText fallito: {e}")
        return False


def send_telegram_get_id(text: str) -> int | None:
    if not settings.BOT_TOKEN or not settings.CHAT_ID:
        log_line("WARN", "TELEGRAM", "BOT_TOKEN o CHAT_ID mancanti")
        return None
    try:
        r = _tg_post("sendMessage", payload={"chat_id": settings.CHAT_ID, "text": text, "parse_mode": "HTML"})
        r.raise_for_status()
        msg_id = r.json().get("result", {}).get("message_id")
        return msg_id
    except Exception as e:
        log_line("ERROR", "TELEGRAM", f"sendMessage fallito: {e}")
        return None


def _send_telegram_event_photo_get_id(
    text: str,
    photo_bytes: bytes | None,
    *,
    filename: str,
    label: str,
    retry_factory=None,
) -> tuple[int | None, bool]:
    """Invia una card come foto+caption e restituisce anche il message_id.

    Se Telegram rifiuta la foto, il messaggio testuale viene comunque inviato:
    il booleano indica se il messaggio salvato e realmente una foto.
    """
    if not photo_bytes:
        return _retry_graphic_on_text(send_telegram_get_id(text), text, retry_factory, label)
    try:
        r = _tg_post(
            "sendPhoto",
            data={"chat_id": settings.CHAT_ID, "caption": text, "parse_mode": "HTML"},
            files={"photo": (filename, photo_bytes, "image/png")},
            timeout=25,
        )
        if r is not None and r.status_code == 200:
            msg_id = r.json().get("result", {}).get("message_id")
            return msg_id, bool(msg_id)
        log_line("WARN", "TELEGRAM", f"Foto {label} rifiutata; fallback testo")
    except Exception as e:
        log_line("WARN", "TELEGRAM", f"Invio foto {label} fallito: {e}; fallback testo")
    factory = retry_factory or (lambda: photo_bytes)
    return _retry_graphic_on_text(send_telegram_get_id(text), text, factory, label)


def _retry_graphic_on_text(message_id, text, factory, label):
    """Five additional attempts; never delete or resend the fallback message."""
    if not message_id or factory is None:
        return message_id, False
    for attempt in range(1, 6):
        try:
            result = factory()
            photo = getattr(result, 'png', result)
            if photo and edit_telegram_goal_photo(message_id, text, photo):
                log_line('OK', 'GRAPHICS', f'{label} recuperata | tentativo {attempt}/5 | stesso messaggio')
                return message_id, True
        except Exception as exc:
            log_line('WARN', 'GRAPHICS', f'{label} | tentativo {attempt}/5 | {type(exc).__name__}')
    log_line('WARN', 'GRAPHICS', f'{label} | 5 tentativi esauriti; resta il testo')
    return message_id, False


def send_telegram_goal_get_id(text: str, photo_bytes: bytes | None, *, retry_factory=None) -> tuple[int | None, bool]:
    return _send_telegram_event_photo_get_id(
        text, photo_bytes, filename="goal.png", label="GOAL", retry_factory=retry_factory
    )


def send_telegram_saved_get_id(text: str, photo_bytes: bytes | None, *, retry_factory=None) -> tuple[int | None, bool]:
    return _send_telegram_event_photo_get_id(
        text, photo_bytes, filename="saved.png", label="SAVED", retry_factory=retry_factory
    )


def edit_telegram_goal_photo(message_id: int, text: str, photo_bytes: bytes) -> bool:
    """Aggiunge/sostituisce foto e caption quando ESPN corregge il marcatore.

    Da Bot API 7.11 editMessageMedia puo anche convertire direttamente un
    messaggio di testo in un messaggio media, conservando il message_id.
    """
    if not settings.BOT_TOKEN or not settings.CHAT_ID or not message_id or not photo_bytes:
        return False
    media = json.dumps({
        "type": "photo",
        "media": "attach://photo",
        "caption": text,
        "parse_mode": "HTML",
    })
    try:
        r = _tg_post(
            "editMessageMedia",
            data={"chat_id": settings.CHAT_ID, "message_id": message_id, "media": media},
            files={"photo": ("goal.png", photo_bytes, "image/png")},
            timeout=25,
        )
        return r is not None and r.status_code == 200
    except Exception as e:
        log_line("ERROR", "TELEGRAM", f"editMessageMedia GOAL fallito: {e}")
        return False


def edit_telegram_goal_caption(message_id: int, text: str) -> bool:
    if not settings.BOT_TOKEN or not settings.CHAT_ID or not message_id:
        return False
    try:
        r = _tg_post("editMessageCaption", payload={
            "chat_id": settings.CHAT_ID,
            "message_id": message_id,
            "caption": text,
            "parse_mode": "HTML",
        })
        return r is not None and r.status_code == 200
    except Exception as e:
        log_line("ERROR", "TELEGRAM", f"editMessageCaption GOAL fallito: {e}")
        return False


def delete_telegram_message(message_id: int):
    if not settings.BOT_TOKEN or not settings.CHAT_ID or not message_id:
        return
    try:
        _tg_post("deleteMessage", payload={"chat_id": settings.CHAT_ID, "message_id": message_id})
    except Exception as e:
        log_line("WARN", "TELEGRAM", f"deleteMessage fallito: {e}")


def replace_corrected_goal_message(
    message_id: int,
    was_photo: bool,
    text: str,
    rendered_goal: goal_graphics.RenderedGoal | None,
) -> tuple[bool, int, bool]:
    """Aggiorna testo e media di un GOAL corretto senza lasciare la foto errata."""
    if was_photo and rendered_goal:
        edited = edit_telegram_goal_photo(message_id, text, rendered_goal.png)
        return edited, message_id, True

    if was_photo and not rendered_goal:
        replacement_id = send_telegram_get_id(text)
        if replacement_id:
            delete_telegram_message(message_id)
            return True, replacement_id, False
        return False, message_id, True

    if not was_photo and rendered_goal:
        # Bot API 7.11: conversione testo -> foto sullo stesso message_id.
        edited = edit_telegram_goal_photo(message_id, text, rendered_goal.png)
        return edited, message_id, edited

    return send_telegram_edit(message_id, text), message_id, False


def send_telegram_with_photo(text: str, photo_bytes) -> bool:
    """Invia foto+caption; fallback su solo testo. Ritorna True se almeno
    un messaggio è stato consegnato."""
    if not photo_bytes:
        return send_telegram_get_id(text) is not None
    try:
        r = _tg_post("sendPhoto",
                     data={"chat_id": settings.CHAT_ID, "caption": text, "parse_mode": "HTML"},
                     files={"photo": ("matchday.png", photo_bytes)}, timeout=25)
        if r is not None and r.status_code == 200:
            return True
        return send_telegram_get_id(text) is not None
    except Exception:
        return send_telegram_get_id(text) is not None


def send_telegram_stats_photo(png_path: str, momento: str, hashtag: str,
                              min_long_side: int = 2000) -> bool:
    """Invia la foto delle statistiche. Ritorna True solo se l'invio è
    andato davvero a buon fine, così chi chiama può ritentare invece di
    segnare l'evento come fatto e perderlo silenziosamente."""
    if not png_path:
        log_line("WARN", "STATS", f"{momento} | immagine non generata; invio saltato")
        return False
    caption = f"{MOMENTI_CONFIG[momento]['titolo']}\n\n{hashtag}"
    try:
        with open(png_path, "rb") as f:
            r = _tg_post("sendPhoto",
                     data={"chat_id": settings.CHAT_ID, "caption": caption, "parse_mode": "HTML"},
                     files={"photo": ("stats.png", f, "image/png")}, timeout=25)
        if r is None:
            return False
        r.raise_for_status()
        if min_long_side:
            photo_sizes = r.json().get("result", {}).get("photo", [])
            largest = max(
                photo_sizes,
                key=lambda item: item.get("width", 0) * item.get("height", 0),
                default={},
            )
            sent_w = largest.get("width", 0)
            sent_h = largest.get("height", 0)
            if max(sent_w, sent_h) >= min_long_side:
                log_line("OK", "STATS", f"Variante Telegram HD | {sent_w}x{sent_h}")
            else:
                log_line("WARN", "STATS", f"Telegram ha restituito solo {sent_w}x{sent_h}")
        return True
    except Exception as e:
        log_line("ERROR", "STATS", f"Invio foto fallito: {e}")
        return False
