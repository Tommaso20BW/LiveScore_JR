"""Riepilogo del run su GitHub Actions: ogni messaggio Telegram inviato/modificato/cancellato
viene aggiunto, man mano, a $GITHUB_STEP_SUMMARY (la pagina "Summary" del run).

Non fa nulla fuori da GitHub Actions, nei test e nella simulazione (che scrive il suo report).
Non puo' mai far fallire l'invio: ogni errore viene ignorato.
"""

from __future__ import annotations

import html
import json
import os
import re
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

TRACKED = {
    "sendMessage": "📨 Invio",
    "sendPhoto": "🖼️ Invio foto",
    "sendMediaGroup": "🖼️ Invio album",
    "sendDocument": "📎 Invio file",
    "sendAnimation": "🎞️ Invio animazione",
    "editMessageText": "✏️ Modifica testo",
    "editMessageCaption": "✏️ Modifica didascalia",
    "editMessageMedia": "✏️ Modifica foto",
    "deleteMessage": "🗑️ Cancellato",
}
# GitHub accetta max 1 MiB per step: ci si ferma prima.
MAX_BYTES = 900_000
MAX_TEXT = 1500

_lock = threading.Lock()
_state = {"bytes": 0, "started": False, "full": False}


def _target() -> str | None:
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("STEP_SUMMARY_DISABLED"):
        return None
    return os.getenv("GITHUB_STEP_SUMMARY") or None


def _write(path: str, text: str) -> None:
    data = text.encode("utf-8")
    if _state["bytes"] + len(data) > MAX_BYTES:
        if not _state["full"]:
            _state["full"] = True
            data = "\n> ⚠️ Riepilogo troncato: limite di GitHub raggiunto.\n".encode("utf-8")
        else:
            return
    with open(path, "ab") as handle:
        handle.write(data)
    _state["bytes"] += len(data)


def _text_of(body: dict) -> str:
    text = body.get("text") or body.get("caption") or ""
    media = body.get("media")
    if not text and isinstance(media, str):
        try:
            text = json.loads(media).get("caption", "")
        except Exception:
            text = ""
    text = re.sub(r"<[^>]+>", "", html.unescape(str(text))).strip()
    return text[:MAX_TEXT] + ("…" if len(text) > MAX_TEXT else "")


def record(method: str, body: dict | None, *, has_image: bool = False, ok: bool = True,
           title: str = "Live Score JR", message_id=None) -> None:
    """Aggiunge una voce al riepilogo. ``body`` e' il payload/data della chiamata Telegram."""
    label = TRACKED.get(method)
    path = _target()
    if not label or not path:
        return
    try:
        body = dict(body or {})
        now = datetime.now(ZoneInfo("Europe/Rome")).strftime("%H:%M:%S")
        mid = message_id or body.get("message_id")
        head = f"**{now}** · {label}" + (" · con immagine" if has_image else "")
        if mid:
            head += f" · id `{mid}`"
        if not ok:
            head += " · ⚠️ **non riuscito**"
        text = _text_of(body)
        entry = head + "\n" + (("\n> " + text.replace("\n", "\n> ") + "\n") if text else "")
        with _lock:
            if not _state["started"]:
                _state["started"] = True
                _write(path, f"# {title}\n\nMessaggi Telegram di questo run, in ordine.\n\n")
            _write(path, entry + "\n")
    except Exception:
        pass
