"""Foto per HALF TIME / END OF 90' / FULL TIME, scelte da te nella Mini App (al posto di Canva).

Circa 10 minuti prima della fase il bot manda in chat privata un pulsante che apre
l'editor (la Mini App di ImageGEN in modalita' live). Li' carichi la foto, sistemi
sfondo e persona, la cambi quante volte vuoi e la confermi. Al fischio la grafica
usa la foto confermata; se non c'e' ancora, il bot aspetta (al massimo
WAIT_SECONDS, poi solo testo; in simulazione senza limite).

Tre "slot", uno per ogni avviso:
- half  -> HALF TIME (avviso al 35')
- end   -> END OF 90' e FULL TIME senza supplementari (avviso all'80')
- extra -> FULL TIME dopo supplementari/rigori (avviso al 110')

La Mini App parla con un piccolo server locale, raggiunto da Telegram attraverso
un tunnel cloudflared temporaneo (come ImageGEN).
"""

from __future__ import annotations

import atexit
import hashlib
import io
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

from livescore import settings
from livescore.constants import JUVE_ID
from livescore.core import leagues
from livescore.core.log import log_line

CACHE_DIR = Path("phase_layers_cache")
# Attesa massima della foto quando arriva la fase (None = senza limite, simulazione).
WAIT_SECONDS: float | None = 300
# Minuto dell'avviso per ogni slot: (stato ESPN, minuto).
PROMPT_AT = {"half": ("1H", 35), "end": ("2H", 80), "extra": ("ET", 110)}
SLOT_KIND = {"half": "half", "end": "full", "extra": "full"}
SLOT_TITLE = {
    "half": "HALF TIME",
    "end": "FINE PARTITA",
    "extra": "FINE PARTITA (dopo i supplementari)",
}
SLOT_NOTE = {
    "half": "",
    "end": "Vale per END OF 90' e FULL TIME.",
    "extra": "",
}
MAX_PHOTOS = 10
MAX_PHOTO_BYTES = 12 * 1024 * 1024
PHOTO_ID = re.compile(r"[0-9a-f]{16}")

# Orologio vero anche in simulazione (il replay sostituisce time.time/monotonic/sleep).
_clock = time.perf_counter


def _wait(seconds: float) -> None:
    threading.Event().wait(seconds)


def slot_for(kind: str, *, extra_time: bool = False, shootout=None) -> str | None:
    if kind == "half":
        return "half"
    if kind == "end_of_90":
        return "end"
    if kind == "full":
        return "extra" if (extra_time or shootout) else "end"
    return None


def _frame(value, min_zoom=1.0):
    if not isinstance(value, dict):
        raise ValueError("Posizione foto non valida.")
    try:
        frame = {k: float(value.get(k, d)) for k, d in (("x", 0), ("y", 0), ("zoom", 1))}
    except (TypeError, ValueError):
        raise ValueError("Posizione foto non valida.") from None
    if not all(math.isfinite(v) for v in frame.values()):
        raise ValueError("Posizione foto non valida.")
    frame["x"] = max(-3.0, min(3.0, frame["x"]))
    frame["y"] = max(-3.0, min(3.0, frame["y"]))
    frame["zoom"] = max(min_zoom, min(6.0, frame["zoom"]))
    return {k: round(v, 5) for k, v in frame.items()}


def parse_photo_request(envelope, session: str, *, ghost=False) -> dict:
    """Solo i campi delle foto: squadre, risultato e maglia li sa gia' il bot."""
    if not isinstance(envelope, dict) or str(envelope.get("session") or "") != session:
        raise ValueError("Sessione non valida.")
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise ValueError("Richiesta non valida.")
    photo_id = str(data.get("photo_id") or "")
    if not PHOTO_ID.fullmatch(photo_id):
        raise ValueError("Carica una foto.")
    # Sfondo sempre fermo e a pagina piena: la posizione che arriva dal client non conta.
    out = {"photo_id": photo_id, "frame": {"x": 0.0, "y": 0.0, "zoom": 1.0}}
    if ghost:
        return out
    person_id = data.get("person_id")
    if person_id and not PHOTO_ID.fullmatch(str(person_id)):
        raise ValueError("Foto della persona non valida.")
    out["person_id"] = str(person_id) if person_id else None
    person_frame = data.get("person_frame")
    out["person_frame"] = _frame(person_frame, min_zoom=0.2) if person_frame else None
    return out


class Desk:
    def __init__(self, *, token: str, chat_id: str, webapp_url: str, label: str = "",
                 direct_url: str = "", http=None) -> None:
        self.token = str(token or "").strip()
        self.chat_id = str(chat_id or "").strip()
        self.webapp_url = str(webapp_url or "").strip()
        self.label = label
        self.direct_url = str(direct_url or "").strip().rstrip("/")
        self.http = http or requests.Session()
        self.session = secrets.token_urlsafe(18)
        self.lock = threading.RLock()
        self.render_lock = threading.Lock()
        self.slots = {slot: {"prompt_id": None, "prompted": False, "messages": [],
                             "confirmed": None, "used": False,
                             "wait_started": None, "expired": False, "reminded": False}
                      for slot in PROMPT_AT}
        self.match: dict = {}
        self.data = None
        self.eligible = False
        self.photos: dict[str, bytes] = {}
        self.cutouts: dict[str, bytes] = {}
        self.previews: dict[str, bytes] = {}
        self.stage = "idle"
        self.server = None
        self.tunnel = None
        self.tunnel_url = ""
        self.start_lock = threading.Lock()
        self.prompting: set[str] = set()
        self.messages: list[int] = []
        self.warned = False

    # ------------------------------------------------------------------
    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id and self.webapp_url)

    @property
    def active(self) -> bool:
        return self.configured and self.eligible

    def update(self, ctx) -> None:
        """Dati della partita per l'editor (squadre, risultato, competizione)."""
        juve = JUVE_ID in (str(ctx.home_id), str(ctx.away_id))
        self.eligible = bool(
            settings.GOAL_GRAPHICS_ENABLED and juve
            and not leagues.is_friendly_competition(ctx.league_slug, ctx.league_name)
        )
        with self.lock:
            self.data = ctx.data
            self.match = {
                "home_name": ctx.home_name_raw, "away_name": ctx.away_name_raw,
                "home_id": ctx.home_id, "away_id": ctx.away_id,
                "home_goals": int(ctx.g_home or 0), "away_goals": int(ctx.g_away or 0),
                "league_slug": ctx.league_slug, "league_name": ctx.league_name,
            }

    def wanted_slots(self, ctx) -> list[str]:
        status, minute = ctx.status, int(ctx.elapsed or 0)
        sent = (ctx.state or {}).get("sent_periods", [])
        wanted = []
        if (status == "1H" and minute >= PROMPT_AT["half"][1]) or (status == "HT" and "HT" not in sent):
            wanted.append("half")
        if ((status == "2H" and minute >= PROMPT_AT["end"][1])
                or (status == "BREAK_ET" and "2H_END" not in sent)):
            wanted.append("end")
        if ((status == "ET" and minute >= PROMPT_AT["extra"][1])
                or (status in ("BREAK_PEN", "PEN") and "FT" not in sent)):
            wanted.append("extra")
        return wanted

    def tick(self, ctx) -> None:
        self.update(ctx)
        if not self.eligible:
            return
        if not self.configured:
            if not self.warned:
                self.warned = True
                log_line("WARN", "PHOTO", "Chat privata o Mini App non configurate: "
                         "HALF/END/FULL TIME senza grafica")
            return
        for slot in self.wanted_slots(ctx):
            self.prompt_async(slot)

    # ------------------------------------------------------------------
    # Avviso, attesa e livelli
    # ------------------------------------------------------------------
    def prompt_async(self, slot: str) -> None:
        with self.lock:
            if self.slots[slot]["prompted"] or slot in self.prompting:
                return
            self.prompting.add(slot)
        threading.Thread(target=self._prompt, args=(slot,), name=f"photo-{slot}", daemon=True).start()

    def _prompt(self, slot: str) -> None:
        try:
            self.start()
            message_id = self._send(self._prompt_text(slot), self._keyboard(slot), slot=slot)
            with self.lock:
                self.slots[slot]["prompt_id"] = message_id
                self.slots[slot]["prompted"] = True
            log_line("INFO", "PHOTO", f"{SLOT_TITLE[slot]}: avviso inviato, aspetto la foto")
        except Exception as exc:
            log_line("WARN", "PHOTO", f"Avviso {slot} non inviato: {type(exc).__name__}: {exc}")
        finally:
            with self.lock:
                self.prompting.discard(slot)

    def ready(self, kind: str, *, extra_time=False, shootout=None) -> bool:
        """Si puo' pubblicare la fase? No finche' si aspetta la foto."""
        slot = slot_for(kind, extra_time=extra_time, shootout=shootout)
        if slot is None or not self.active:
            return True
        with self.lock:
            state = self.slots[slot]
            if state["confirmed"] or state["expired"]:
                return True
            first = state["wait_started"] is None
            if first:
                state["wait_started"] = _clock()
            started = state["wait_started"]
            prompted = state["prompted"]
        if first:
            limit = "senza limite" if WAIT_SECONDS is None else f"max {int(WAIT_SECONDS // 60)} min"
            log_line("WAIT", "PHOTO", f"{kind.upper()}: aspetto la foto confermata ({limit})")
            if prompted:
                threading.Thread(target=self._remind, args=(slot,), daemon=True).start()
            else:
                self.prompt_async(slot)
        if WAIT_SECONDS is not None and _clock() - started >= WAIT_SECONDS:
            with self.lock:
                state["expired"] = True
            log_line("WARN", "PHOTO", f"{kind.upper()}: nessuna foto confermata in tempo")
            return True
        return False

    def holding(self) -> bool:
        """True mentre una fase aspetta la foto (la simulazione ferma l'orologio)."""
        if not self.active:
            return False
        with self.lock:
            return any(s["wait_started"] is not None and not s["confirmed"] and not s["expired"]
                       for s in self.slots.values())

    def layers_for(self, kind: str, *, extra_time=False, shootout=None) -> Path | None:
        slot = slot_for(kind, extra_time=extra_time, shootout=shootout)
        if slot is None:
            return None
        with self.lock:
            confirmed = self.slots[slot]["confirmed"]
            if not confirmed and slot == "extra":
                # Nessuna foto nuova dopo i supplementari: vale l'ultima confermata.
                confirmed = self.slots["end"]["confirmed"]
            if not confirmed:
                return None
            self.slots[slot]["used"] = True
        return Path(confirmed["layers"])

    # ------------------------------------------------------------------
    # Server locale + tunnel
    # ------------------------------------------------------------------
    def start(self) -> None:
        with self.start_lock:
            if self.server is None:
                port = int(os.getenv("PHASE_PHOTO_PORT", "0") or 0)
                server = _Server(("127.0.0.1", port), _Handler)
                server.desk = self
                threading.Thread(target=server.serve_forever, name="photo-http", daemon=True).start()
                self.server = server
                threading.Thread(target=_warm_up_cutout, name="photo-cutout", daemon=True).start()
                log_line("DEBUG", "PHOTO", f"Server foto pronto | port={server.server_address[1]}")
            if not self.direct_url and not self.tunnel_url:
                self.tunnel_url = self._open_tunnel()

    def _open_tunnel(self) -> str:
        exe = os.getenv("CLOUDFLARED") or shutil.which("cloudflared")
        if not exe:
            raise RuntimeError("cloudflared non disponibile")
        port = self.server.server_address[1]
        proc = subprocess.Popen(
            [exe, "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
        )
        self.tunnel = proc
        found = {}
        ready = threading.Event()

        def read():
            for line in proc.stdout:
                match = re.search(r"https://[A-Za-z0-9-]+\.trycloudflare\.com", line)
                if match and not found:
                    found["url"] = match.group(0)
                    ready.set()

        threading.Thread(target=read, name="photo-tunnel", daemon=True).start()
        if not ready.wait(45):
            raise RuntimeError("tunnel cloudflared non avviato")
        log_line("DEBUG", "PHOTO", "Tunnel Mini App pronto")
        return found["url"]

    @property
    def base_url(self) -> str:
        return self.direct_url or self.tunnel_url

    def launch_url(self, slot: str) -> str:
        parts = urlsplit(self.webapp_url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query.update({"mode": "live", "slot": slot, "phase": SLOT_KIND[slot],
                      "session": self.session, "direct": f"{self.base_url}/submit"})
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    def finish(self) -> None:
        """Fine partita: via pulsanti, avvisi, tunnel e foto."""
        with self.lock:
            messages, self.messages = list(self.messages), []
        for message_id in messages:
            try:
                self._call("deleteMessage", {"chat_id": self.chat_id, "message_id": message_id})
            except Exception:
                pass
        if self.tunnel is not None:
            try:
                self.tunnel.terminate()
            except Exception:
                pass
            self.tunnel = None
        if self.server is not None:
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            self.server = None
        self.photos.clear()
        self.cutouts.clear()
        self.previews.clear()
        shutil.rmtree(CACHE_DIR, ignore_errors=True)

    # ------------------------------------------------------------------
    # Telegram (chat privata, sessione propria: mai sul canale)
    # ------------------------------------------------------------------
    def _prefix(self) -> str:
        return f"🧪 <b>{self.label}</b> · " if self.label else ""

    def _score_line(self) -> str:
        from livescore.core import team_names
        from livescore.core.text import esc
        m = self.match
        home = esc(team_names.translate_team(m.get("home_name", "")))
        away = esc(team_names.translate_team(m.get("away_name", "")))
        return f"{home} {m.get('home_goals', 0)}-{m.get('away_goals', 0)} {away}"

    def _prompt_text(self, slot: str) -> str:
        note = f"\n{SLOT_NOTE[slot]}" if SLOT_NOTE[slot] else ""
        return (f"{self._prefix()}📸 <b>{SLOT_TITLE[slot]}</b> tra poco\n{self._score_line()}\n\n"
                "Carica la foto per la grafica: sfondo e persona si sistemano separatamente "
                f"e puoi cambiarla quante volte vuoi prima di confermare.{note}")

    def _keyboard(self, slot: str, label: str = "📸 Prepara la grafica") -> dict:
        return {"inline_keyboard": [[{"text": label, "web_app": {"url": self.launch_url(slot)}}]]}

    def _remind(self, slot: str) -> None:
        with self.lock:
            if self.slots[slot]["reminded"]:
                return
            self.slots[slot]["reminded"] = True
        limit = ("" if WAIT_SECONDS is None
                 else f" Se non arriva entro {int(WAIT_SECONDS // 60)} minuti esce solo il testo.")
        try:
            self._send(f"{self._prefix()}⏰ <b>{SLOT_TITLE[slot]}</b>: è il momento, "
                       f"la grafica aspetta la tua foto.{limit}", self._keyboard(slot), slot=slot)
        except Exception as exc:
            log_line("WARN", "PHOTO", f"Promemoria non inviato: {exc}")

    def _call(self, method: str, payload: dict):
        response = self.http.post(f"https://api.telegram.org/bot{self.token}/{method}",
                                  json=payload, timeout=20)
        body = response.json()
        if not body.get("ok"):
            raise RuntimeError(body.get("description") or f"HTTP {response.status_code}")
        return body.get("result")

    def _send(self, text: str, keyboard: dict | None = None, slot: str | None = None) -> int:
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML",
                   "disable_web_page_preview": True}
        if keyboard:
            payload["reply_markup"] = keyboard
        result = self._call("sendMessage", payload)
        message_id = int(result["message_id"])
        with self.lock:
            self.messages.append(message_id)
            if slot:
                self.slots[slot]["messages"].append(message_id)
        return message_id

    def _delete(self, message_ids) -> None:
        for message_id in message_ids:
            try:
                self._call("deleteMessage", {"chat_id": self.chat_id, "message_id": message_id})
            except Exception as exc:
                log_line("DEBUG", "PHOTO", f"Avviso non cancellato: {exc}")
            with self.lock:
                if message_id in self.messages:
                    self.messages.remove(message_id)

    # ------------------------------------------------------------------
    # Foto e grafica (chiamati dal server)
    # ------------------------------------------------------------------
    def store_photo(self, raw: bytes) -> dict:
        from livescore.graphics import phase_layers
        image = phase_layers.open_photo(raw)
        photo_id = hashlib.sha256(raw).hexdigest()[:16]
        with self.lock:
            self.photos[photo_id] = raw
            # Troppe foto: via le piu' vecchie, mai quelle confermate.
            keep = self._confirmed_ids() | {photo_id}
            for old in [k for k in self.photos if k not in keep][:max(0, len(self.photos) - MAX_PHOTOS)]:
                self.photos.pop(old)
                self.cutouts.pop(old, None)
        log_line("DEBUG", "PHOTO", f"Foto caricata | id={photo_id} | {image.width}x{image.height}")
        return {"photo_id": photo_id, "width": image.width, "height": image.height}

    def _confirmed_ids(self) -> set[str]:
        return {i for s in self.slots.values() if s["confirmed"] for i in s["confirmed"]["ids"]}

    def cutout(self, photo_id: str) -> bytes:
        """Persona scontornata (PNG), una volta sola per foto; i PNG trasparenti restano come sono."""
        from livescore.graphics import phase_layers
        with self.render_lock:
            if photo_id not in self.cutouts:
                raw = self.photos.get(photo_id)
                if not raw:
                    raise ValueError("Foto non trovata: ricaricala.")
                image = phase_layers.open_photo(raw)
                if phase_layers.has_transparency(image):
                    self.cutouts[photo_id] = raw
                else:
                    out = io.BytesIO()
                    phase_layers.cutout(image).save(out, "PNG")
                    self.cutouts[photo_id] = out.getvalue()
            return self.cutouts[photo_id]

    def clean_image(self, photo_id: str) -> bytes:
        """Sfondo senza la persona (ricostruito), per l'editor quando la persona si sposta."""
        from livescore.graphics import phase_layers
        raw = self.photos.get(photo_id)
        if not raw:
            raise ValueError("Foto non trovata.")
        person = self.cutout(photo_id)
        with self.render_lock:
            return phase_layers.clean_background_jpeg(raw, person)

    def preview_image(self, photo_id: str, *, person: bool) -> bytes:
        from PIL import Image
        key = f"{'p' if person else 'b'}{photo_id}"
        if key not in self.previews:
            raw = self.cutout(photo_id) if person else self.photos.get(photo_id)
            if not raw:
                raise ValueError("Foto non trovata.")
            with Image.open(io.BytesIO(raw)) as image:
                image = image.convert("RGBA" if person else "RGB")
                image.thumbnail((1400, 1400), Image.Resampling.LANCZOS)
                out = io.BytesIO()
                image.save(out, "PNG" if person else "JPEG", quality=88)
            self.previews[key] = out.getvalue()
        return self.previews[key]

    def _render_args(self, slot: str) -> dict:
        from livescore.kits import detect as kit_detect
        with self.lock:
            m = dict(self.match)
            data = self.data
        try:
            kit = kit_detect.rileva_kit_juve(data, m["home_id"], m["away_id"], m["home_name"],
                                             m["away_name"], m["league_slug"], m["league_name"])
        except Exception:
            kit = "home" if str(m.get("home_id")) == JUVE_ID else "away"
        return {
            "kind": SLOT_KIND[slot], "home_name": m["home_name"], "away_name": m["away_name"],
            "home_id": m["home_id"], "away_id": m["away_id"],
            "home_goals": m["home_goals"], "away_goals": m["away_goals"],
            "kit": kit if kit in ("home", "away", "third") else "home",
            "competition": m["league_slug"], "shootout": None, "extra_time": slot == "extra",
        }

    def _draw(self, slot: str, layers) -> bytes:
        from livescore.graphics import portrait
        return portrait.phase(layers=layers, **self._render_args(slot))

    def ghost(self, slot: str) -> bytes:
        from livescore.graphics import phase_layers
        with self.render_lock:
            return phase_layers.ghost(lambda layers: self._draw(slot, layers))

    def _build(self, request: dict) -> Path:
        from livescore.graphics import phase_layers
        self.stage = "cutout"
        same_photo = not request["person_id"] or request["person_id"] == request["photo_id"]
        person = self.cutout(request["person_id"] or request["photo_id"])
        background = self.photos.get(request["photo_id"])
        if not background:
            raise ValueError("Foto non trovata: ricaricala.")
        self.stage = "compose"
        key = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()[:20]
        folder = CACHE_DIR / key
        if not (folder / "player.png").is_file():
            self.stage = "erase" if same_photo and phase_layers.moved(request["person_frame"]) else "compose"
            phase_layers.build_layers(folder, background=background, person=person,
                                      background_frame=request["frame"],
                                      person_frame=request["person_frame"],
                                      remove_person=same_photo)
        return folder

    def preview(self, slot: str, request: dict) -> bytes:
        try:
            layers = self._build(request)
            with self.render_lock:
                return self._draw(slot, layers)
        finally:
            self.stage = "idle"

    def confirm(self, slot: str, request: dict) -> None:
        try:
            layers = self._build(request)
        finally:
            self.stage = "idle"
        ids = [request["photo_id"]] + ([request["person_id"]] if request["person_id"] else [])
        with self.lock:
            state = self.slots[slot]
            state["confirmed"] = {"layers": str(layers), "request": request, "ids": ids}
            # Foto confermata: avviso e promemoria di questa fase spariscono dalla chat.
            messages, state["messages"] = list(state["messages"]), []
            state["prompt_id"] = None
        log_line("OK", "PHOTO", f"{SLOT_TITLE[slot]}: foto confermata")
        self._delete(messages)

    def restore_state(self, slot: str) -> dict | None:
        """Ultima foto confermata, per riaprire l'editor da dove eri rimasto."""
        from livescore.graphics import phase_layers
        with self.lock:
            confirmed = self.slots[slot]["confirmed"]
        if not confirmed:
            return None
        request = confirmed["request"]
        try:
            bg = phase_layers.open_photo(self.photos[request["photo_id"]])
            person_id = request["person_id"] or request["photo_id"]
            person = phase_layers.open_photo(self.cutout(person_id))
        except (KeyError, ValueError):
            return None
        follow = request["person_frame"] is None
        frame = request["frame"] if follow else request["person_frame"]
        return {
            "bg": {"id": request["photo_id"], "w": bg.width, "h": bg.height, **request["frame"]},
            "person": {"id": person_id, "w": person.width, "h": person.height, "follow": follow, **frame},
        }


def _warm_up_cutout() -> None:
    try:
        from PIL import Image
        from livescore.graphics import phase_layers
        phase_layers.cutout(Image.new("RGB", (64, 64)))
        log_line("DEBUG", "PHOTO", "Scontorno pronto")
    except Exception as exc:
        log_line("WARN", "PHOTO", f"Scontorno non disponibile: {type(exc).__name__}: {exc}")


# ----------------------------------------------------------------------
# Server HTTP per la Mini App (stesse chiamate dell'endpoint di ImageGEN)
# ----------------------------------------------------------------------
class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _Handler(BaseHTTPRequestHandler):
    server_version = "LiveScoreJR/1.0"

    def log_message(self, *_):
        return

    @property
    def desk(self) -> Desk:
        return self.server.desk

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-ImageGEN-Session")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Cache-Control", "no-store")

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _bytes(self, payload, content_type="image/png"):
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _query(self):
        parts = urlsplit(self.path)
        return parts.path.rstrip("/"), dict(parse_qsl(parts.query))

    def _slot(self, query) -> str:
        slot = query.get("slot", "")
        if slot not in PROMPT_AT:
            raise ValueError("Fase non valida.")
        return slot

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path, query = self._query()
        if query.get("session", "") != self.desk.session:
            self._json(403, {"ok": False, "error": "Sessione non valida."})
            return
        try:
            if path == "/phase":
                slot = self._slot(query)
                desk = self.desk
                self._json(200, {"ok": True, "slot": slot, "kind": SLOT_KIND[slot],
                                 "title": SLOT_TITLE[slot], "score": desk._score_line(),
                                 "label": desk.label, "state": desk.restore_state(slot)})
            elif path == "/progress":
                self._json(200, {"ok": True, "stage": self.desk.stage})
            elif path == "/cutout":
                self._bytes(self.desk.preview_image(query.get("id", ""), person=True))
            elif path == "/clean":
                self._bytes(self.desk.clean_image(query.get("id", "")), "image/jpeg")
            elif path == "/photo":
                self._bytes(self.desk.preview_image(query.get("id", ""), person=False), "image/jpeg")
            else:
                self._json(404, {"ok": False, "error": "Endpoint non valido."})
        except ValueError as exc:
            self._json(404, {"ok": False, "error": str(exc)})
        except Exception as exc:
            log_line("WARN", "PHOTO", f"{path}: {type(exc).__name__}: {exc}")
            self._json(500, {"ok": False, "error": "Errore interno."})

    def do_POST(self):
        path, query = self._query()
        if self.headers.get("X-ImageGEN-Session", "") != self.desk.session:
            self._json(403, {"ok": False, "error": "Sessione non valida."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        try:
            if path == "/upload":
                if length <= 0 or length > MAX_PHOTO_BYTES:
                    self._json(413, {"ok": False, "error": "Foto troppo grande (max 12 MB)."})
                    return
                self._json(200, {"ok": True, **self.desk.store_photo(self.rfile.read(length))})
                return
            if path not in ("/ghost", "/preview", "/submit") or not 0 < length <= 16384:
                self._json(404, {"ok": False, "error": "Richiesta non valida."})
                return
            envelope = json.loads(self.rfile.read(length).decode("utf-8"))
            slot = self._slot(envelope.get("data") or {})
            desk = self.desk
            if path == "/ghost":
                parse_photo_request(envelope, desk.session, ghost=True)
                self._bytes(desk.ghost(slot))
            elif path == "/preview":
                self._bytes(desk.preview(slot, parse_photo_request(envelope, desk.session)))
            else:
                desk.confirm(slot, parse_photo_request(envelope, desk.session))
                self._json(200, {"ok": True})
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"ok": False, "error": str(exc) or "Richiesta non valida."})
        except Exception as exc:
            log_line("WARN", "PHOTO", f"{path}: {type(exc).__name__}: {exc}")
            self._json(500, {"ok": False, "error": "Errore interno."})


# ----------------------------------------------------------------------
# Punto d'accesso del bot
# ----------------------------------------------------------------------
DESK: Desk | None = None
LABEL = ""


def desk() -> Desk:
    global DESK
    if DESK is None:
        DESK = Desk(token=settings.BOT_TOKEN, chat_id=settings.PHOTO_CHAT_ID,
                    webapp_url=settings.PHOTO_WEBAPP_URL, label=LABEL,
                    direct_url=os.getenv("PHASE_PHOTO_DIRECT_URL", ""))
        atexit.register(DESK.finish)
    return DESK


def tick(ctx) -> None:
    try:
        desk().tick(ctx)
    except Exception as exc:
        log_line("WARN", "PHOTO", f"Foto di fase: {type(exc).__name__}: {exc}")


def ready(kind: str, **kwargs) -> bool:
    try:
        return desk().ready(kind, **kwargs)
    except Exception as exc:
        log_line("WARN", "PHOTO", f"Attesa foto saltata: {type(exc).__name__}: {exc}")
        return True


def holding() -> bool:
    return DESK is not None and DESK.holding()


def layers_for(kind: str, **kwargs) -> Path | None:
    return desk().layers_for(kind, **kwargs)


def finish() -> None:
    if DESK is not None:
        DESK.finish()
