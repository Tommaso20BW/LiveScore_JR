"""Simulazione di una partita ESPN con il codice vero del LiveScore.

Il bot gira esattamente come in diretta (stesse regole: grafiche solo per la
Juventus e mai nelle amichevoli). Cambia solo cio' che sta intorno.

Due modalita', scelte da sole guardando lo stato della partita su ESPN:

- **replay** (partita gia' finita): il summary finale viene "riavvolto" e
  servito minuto per minuto, con un orologio che avanza da solo: la partita
  dura pochi minuti reali; un messaggio ogni 20 secondi.
- **live** (partita in corso o non ancora iniziata): ESPN e orologio sono
  quelli veri, il bot segue la partita in tempo reale fino al fischio finale.
  I click sui kit non arrivano (``getUpdates`` resta al LiveScore vero, che
  puo' girare in contemporanea con lo stesso bot Telegram).

In entrambe:

- Telegram: i messaggi vanno solo sul canale di test (Bot JR) e a fine
  partita, dopo 5 minuti, vengono cancellati tutti;
  con ``--dry-run`` non parte nulla e i messaggi restano solo nel report;
- Gist e snapshot delle foto: disattivati, nessuno stato reale toccato;
- foto di HALF TIME / END OF 90' / FULL TIME: l'avviso arriva nella tua chat
  privata (etichetta SIMULAZIONE) e la fase aspetta SENZA LIMITE la foto
  confermata. Nel replay intanto l'orologio della partita resta fermo.

Uso:  python -m livescore simulate <event_id | url ESPN> [--dry-run] [--mode auto|replay|live]
"""

from __future__ import annotations

import copy
import html
import json
import os
import re
import signal
import sys
import time as _time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import requests

REAL_SLEEP = _time.sleep
REAL_TIME = _time.time
REAL_MONOTONIC = _time.monotonic

ESPN_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/summary"
SEND_METHODS = ("sendMessage", "sendPhoto", "sendMediaGroup", "sendDocument", "sendAnimation")

# Durata simulata (secondi di orologio finto) delle pause tra i tempi.
PRE_SECONDS = 120
BREAKS = {"HT": 900, "BREAK_ET": 300, "HT_ET": 120, "BREAK_PEN": 120}
# Inizio e fine nominale (in secondi di gioco) di ogni tempo.
PERIODS = {1: (0, 45), 2: (2700, 90), 3: (5400, 105), 4: (6300, 120)}
STATUS_NAMES = {
    1: ("STATUS_FIRST_HALF", "First Half"),
    2: ("STATUS_SECOND_HALF", "Second Half"),
    3: ("STATUS_FIRST_HALF_EXTRA_TIME", "Extra Time"),
    4: ("STATUS_SECOND_HALF_EXTRA_TIME", "Extra Time"),
}
BREAK_STATUS = {
    "HT": ("STATUS_HALFTIME", "Halftime", 1),
    "BREAK_ET": ("STATUS_END_OF_REGULATION", "End of Regular Time", 2),
    "HT_ET": ("STATUS_HALFTIME_ET", "Extra Time Halftime", 3),
    "BREAK_PEN": ("STATUS_END_OF_EXTRATIME", "End of Extra Time", 4),
}
# Oltre questo margine dopo il fischio finale la simulazione si ferma comunque.
POST_TIMEOUT_SECONDS = 3 * 3600
# Secondi tra due messaggi: nel replay per leggerli con calma, nel live solo
# per non superare i limiti di Telegram (gli eventi arrivano gia' distanziati).
DEFAULT_INTERVAL = {"replay": 20.0, "live": 3.0}


class SimulationTimeout(SystemExit):
    pass


# ==============================================================================
# OROLOGIO FINTO
# ==============================================================================
class FakeClock:
    """time.time/monotonic che avanzano con le sleep del bot, senza aspettare.

    Mentre una fase aspetta la foto (hold), l'orologio si ferma: la partita
    riprende solo dopo la conferma nella Mini App.
    """

    def __init__(self) -> None:
        self.offset = 0.0
        self.hold = lambda: False

    def time(self) -> float:
        return REAL_TIME() + self.offset

    def monotonic(self) -> float:
        return REAL_MONOTONIC() + self.offset

    def sleep(self, seconds: float) -> None:
        if self.hold():
            # Attesa vera, ma il tempo di partita non avanza.
            before = REAL_MONOTONIC()
            REAL_SLEEP(1.0)
            self.offset -= REAL_MONOTONIC() - before
            return
        self.offset += max(0.0, float(seconds or 0))


# ==============================================================================
# PARTITA "RIAVVOLTA"
# ==============================================================================
def _clock_value(item: dict) -> float:
    for key in ("clock", "time"):
        value = (item.get(key) or {}).get("value")
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    return 0.0


def _period(item: dict) -> int | None:
    for source in (item, item.get("play") or {}):
        number = (source.get("period") or {}).get("number")
        if number:
            return int(number)
    return None


class Timeline:
    """Ricostruisce dal summary finale lo stato ESPN a ogni secondo di partita."""

    def __init__(self, final: dict) -> None:
        self.final = final
        self.comp = final["header"]["competitions"][0]
        self.home = next(c for c in self.comp["competitors"] if c.get("homeAway") == "home")
        self.away = next(c for c in self.comp["competitors"] if c.get("homeAway") == "away")

        self.key_events = [(self._kp(e), e) for e in final.get("keyEvents", [])]
        self.scoring = [(self._kp(e), e) for e in final.get("scoringPlays", [])]
        # Il commento non ha sempre il tempo di gioco: lo eredita dalla riga precedente.
        self.commentary = []
        period = 1
        for item in sorted(final.get("commentary", []), key=lambda i: i.get("sequence", 0)):
            period = _period(item) or period
            self.commentary.append(((period, _clock_value(item)), item))

        played = {p for (p, _), _ in self.key_events + self.commentary if p in PERIODS}
        played |= {1, 2}
        status_name = str(self.comp.get("status", {}).get("type", {}).get("name", "")).upper()
        self.shootout = bool(final.get("shootout")) or "PEN" in status_name
        if self.shootout or "AET" in status_name or "EXTRA" in status_name:
            played |= {3, 4}

        # Segmenti: (inizio simulato, fine simulata, tipo, periodo, orologio di partenza)
        self.segments: list[tuple[float, float, str, int, float]] = []
        t = 0.0

        def add(duration: float, kind: str, period: int = 0, clock_start: float = 0.0) -> None:
            nonlocal t
            self.segments.append((t, t + duration, kind, period, clock_start))
            t += duration

        add(PRE_SECONDS, "PRE")
        for period in sorted(played):
            start, nominal = PERIODS[period]
            last = max([v for (p, v), _ in self.key_events + self.commentary if p == period] or [0])
            end = max(nominal * 60, last + 30)
            add(end - start, "LIVE", period, start)
            pause = {1: "HT", 2: "BREAK_ET", 3: "HT_ET", 4: "BREAK_PEN"}[period]
            if period == 2 and 3 not in played:
                break
            if period == 4 and not self.shootout:
                break
            add(BREAKS[pause], pause, period)
        if self.shootout:
            kicks = sum(len(team.get("shots", []) or []) for team in final.get("shootout", []) or [])
            add(max(120, 40 * kicks), "PEN", 5)
        self.end = t

    @staticmethod
    def _kp(item: dict) -> tuple[int, float]:
        return (_period(item) or 1, _clock_value(item))

    def _cut(self, period: int, clock: float, *, whole_period: bool = False):
        def keep(key: tuple[int, float]) -> bool:
            p, v = key
            if p < period:
                return True
            return p == period and (whole_period or v <= clock)
        return keep

    def _score(self, keep) -> tuple[int, int]:
        home = away = 0
        for key, event in self.key_events:
            if not keep(key) or not event.get("scoringPlay") or event.get("shootout"):
                continue
            team = str((event.get("team") or {}).get("id", ""))
            own = "own" in str((event.get("type") or {}).get("text", "")).lower()
            if (team == str(self.home["team"]["id"])) != own:
                home += 1
            else:
                away += 1
        return home, away

    def snapshot(self, elapsed: float) -> dict:
        data = copy.deepcopy(self.final)
        if elapsed >= self.end:
            return data                       # fischio finale: summary vero, intero
        segment = next(s for s in self.segments if s[0] <= elapsed < s[1])
        start, _, kind, period, clock_start = segment
        comp = data["header"]["competitions"][0]

        if kind == "PRE":
            keep = lambda key: False  # noqa: E731
            # La data resta quella vera (nei messaggi deve vedersi quella): un
            # calcio d'inizio gia' passato al bot va bene, aspetta solo il fischio.
            comp["status"] = {"clock": 0, "displayClock": "0'", "period": 0,
                              "type": {"name": "STATUS_SCHEDULED", "state": "pre",
                                       "description": "Scheduled", "completed": False}}
        elif kind == "LIVE":
            clock = clock_start + (elapsed - start)
            keep = self._cut(period, clock)
            nominal = PERIODS[period][1]
            minute = int(clock // 60) + 1
            display = f"{nominal}'+{minute - nominal}'" if minute > nominal else f"{minute}'"
            name, desc = STATUS_NAMES[period]
            comp["status"] = {"clock": clock, "displayClock": display, "period": period,
                              "type": {"name": name, "state": "in", "description": desc,
                                       "completed": False}}
        else:
            if kind == "PEN":
                keep = lambda key: True  # noqa: E731
                name, desc, status_period = "STATUS_SHOOTOUT", "Penalties", 5
            else:
                name, desc, status_period = BREAK_STATUS[kind]
                keep = self._cut(period, 0, whole_period=True)
            comp["status"] = {"clock": 0, "displayClock": "", "period": status_period,
                              "type": {"name": name, "state": "in", "description": desc,
                                       "completed": False}}

        data["keyEvents"] = [e for key, e in self.key_events if keep(key)]
        data["commentary"] = [e for key, e in self.commentary if keep(key)]
        if "scoringPlays" in data:
            data["scoringPlays"] = [e for key, e in self.scoring if keep(key)]
        if kind != "PEN":
            data.pop("shootout", None)
        home_goals, away_goals = self._score(keep)
        for competitor in comp["competitors"]:
            is_home = competitor.get("homeAway") == "home"
            competitor["score"] = str(home_goals if is_home else away_goals)
            competitor.pop("winner", None)
        return data

    def label(self, elapsed: float) -> str:
        if elapsed >= self.end:
            return "FT"
        start, _, kind, period, clock_start = next(
            s for s in self.segments if s[0] <= elapsed < s[1]
        )
        if kind == "LIVE":
            clock = clock_start + (elapsed - start)
            nominal = PERIODS[period][1]
            minute = int(clock // 60) + 1
            return f"{nominal}'+{minute - nominal}" if minute > nominal else f"{minute}'"
        return {"PRE": "pre", "PEN": "rigori"}.get(kind, kind)


# ==============================================================================
# RETE E TELEGRAM
# ==============================================================================
class FakeResponse:
    def __init__(self, payload: Any = None, status: int = 200) -> None:
        self._payload = {} if payload is None else payload
        self.status_code = status
        self.ok = status < 400
        self.headers: dict[str, str] = {"Content-Type": "application/json"}
        self.text = json.dumps(self._payload, ensure_ascii=False)
        self.content = self.text.encode("utf-8")

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            response = requests.Response()
            response.status_code = self.status_code
            raise requests.HTTPError(f"{self.status_code} (simulazione)", response=response)


def _file_bytes(value: Any) -> bytes | None:
    if isinstance(value, (tuple, list)):
        value = value[1] if len(value) > 1 else value[0]
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if hasattr(value, "read"):
        try:
            position = value.tell()
        except Exception:
            position = None
        data = value.read()
        if position is not None:
            try:
                value.seek(position)
            except Exception:
                pass
        return data if isinstance(data, bytes) else None
    return None


def match_state(summary: dict) -> str:
    """Stato ESPN della partita: "pre", "in" o "post"."""
    comp = (summary.get("header", {}).get("competitions") or [{}])[0]
    return str(comp.get("status", {}).get("type", {}).get("state", "")).lower()


def resolve_mode(summary: dict, mode: str = "auto") -> str:
    """auto: replay se la partita e' finita, altrimenti live."""
    if mode in ("replay", "live"):
        return mode
    return "replay" if match_state(summary) == "post" else "live"


class Simulation:
    def __init__(self, final: dict, *, team_id: str, chat_id: str, dry_run: bool,
                 interval: float, output: Path,
                 live: bool = False, espn_session: Any = None) -> None:
        self.live = live
        self.timeline = Timeline(final)
        self.final = final
        # Nel live: ultimo summary vero letto dal bot (minuto nei log, risultato nel report).
        self.latest = final
        self.espn = espn_session or requests.Session()
        self.team_id = team_id
        self.chat_id = chat_id
        self.dry_run = dry_run
        self.interval = interval
        self.output = output
        self.clock = FakeClock()
        self.started = None
        self.real = requests.Session()
        self.last_send = 0.0
        self.last_updates = 0.0
        self.sending = False
        self.interrupted = False
        self.next_id = 1000
        self.sent: list[tuple[str, int]] = []
        self.log: list[dict] = []
        self.images = 0

    # --- tempo ---
    def elapsed(self) -> float:
        if self.started is None:
            self.started = self.clock.monotonic()
        value = self.clock.monotonic() - self.started
        # Nel live la durata la decide la partita vera (e il timeout del workflow).
        if not self.live and value > self.timeline.end + POST_TIMEOUT_SECONDS:
            raise SimulationTimeout("Simulazione: il bot non ha chiuso la partita, mi fermo")
        return value

    def minute(self) -> str:
        """Minuto di gioco da mostrare nei log e nel report."""
        if not self.live:
            return self.timeline.label(self.elapsed())
        comp = (self.latest.get("header", {}).get("competitions") or [{}])[0]
        status = comp.get("status", {})
        state = match_state(self.latest)
        if state == "post":
            return "FT"
        if state == "pre":
            return "pre"
        return str(status.get("displayClock") or status.get("type", {}).get("shortDetail") or "live")

    # --- ESPN ---
    def summary(self) -> dict:
        return self.timeline.snapshot(self.elapsed())

    def espn_get(self, url: str, params=None, **kwargs):
        """Live: ESPN vero (con i retry del bot); il summary letto resta per log e report."""
        response = self.espn.get(url, params=params, **kwargs)
        if url.rstrip("/").endswith("/summary") and response.status_code == 200:
            try:
                data = response.json()
                if data.get("header", {}).get("competitions"):
                    self.latest = data
            except ValueError:
                pass
        return response

    def partita(self) -> dict:
        comp = self.final["header"]["competitions"][0]
        league = self.final["header"].get("league", {})
        competitors = copy.deepcopy(comp["competitors"])
        for competitor in competitors:
            if not self.live:          # nel replay la partita riparte da 0-0
                competitor["score"] = "0"
        return {
            "event_id": str(self.final["header"].get("id") or comp.get("id")),
            "league_slug": league.get("slug") or "",
            "league_name": league.get("name") or league.get("slug") or "",
            "competitors": competitors,
            "competition": comp,
            "date": comp.get("date", ""),
        }

    # --- Telegram ---
    def telegram(self, url: str, payload: dict | None, data: dict | None,
                 files: dict | None, timeout: int):
        method = url.rsplit("/", 1)[-1]
        if method == "getUpdates":
            # Click sui pulsanti kit del messaggio "partita trovata": su Bot JR
            # arrivano dal Telegram vero, come nel live (live e simulazione non
            # girano mai insieme). Con l'orologio accelerato il ciclo e' rapidissimo:
            # al massimo una lettura vera ogni 2 secondi. In prova non c'e' niente da leggere.
            # Nel live il LiveScore vero puo' girare insieme con lo stesso bot: i click
            # restano a lui, altrimenti la simulazione glieli ruberebbe.
            if self.dry_run or self.live or REAL_TIME() - self.last_updates < 2:
                return FakeResponse({"ok": True, "result": []})
            self.last_updates = REAL_TIME()
            return self.real.post(url, json=payload, data=data, timeout=timeout)
        body = dict(payload or data or {})
        if "chat_id" in body:
            body["chat_id"] = self.chat_id         # sempre e solo sul canale di test
        if method in SEND_METHODS:
            wait = self.last_send + self.interval - REAL_TIME()
            if wait > 0 and not self.dry_run:
                REAL_SLEEP(wait)
            self.last_send = REAL_TIME()
        image = self._record(method, body, files)

        if self.dry_run:
            if method in SEND_METHODS:
                self.next_id += 1
                result = {"message_id": self.next_id, "chat": {"id": self.chat_id}}
                if image:
                    # Come Telegram: le dimensioni della foto, che il bot controlla.
                    try:
                        from PIL import Image
                        with Image.open(self.output / image) as picture:
                            width, height = picture.size
                        result["photo"] = [{"width": width, "height": height}]
                    except Exception:
                        pass
                return FakeResponse({"ok": True, "result": result})
            return FakeResponse({"ok": True, "result": True})

        sending = method in SEND_METHODS
        if sending:
            # Annullamento durante un invio: il messaggio parte comunque, quindi
            # ci si ferma solo dopo averne salvato l'ID (vedi _on_signal).
            self.sending = True
        try:
            response = self.real.post(
                url,
                json=body if payload is not None else None,
                data=body if data is not None else None,
                files=files,
                timeout=timeout,
            )
            if sending:
                try:
                    result = response.json().get("result")
                    for message in result if isinstance(result, list) else [result]:
                        self.sent.append((str(self.chat_id), int(message["message_id"])))
                except Exception:
                    pass
                save_pending(self.output, self.sent)
        finally:
            if sending:
                self.sending = False
        if sending and self.interrupted:
            raise KeyboardInterrupt
        return response

    def _on_signal(self, signum, frame) -> None:
        """Annullamento del run (SIGINT/SIGTERM da GitHub o Ctrl+C)."""
        self.interrupted = True
        if not self.sending:
            raise KeyboardInterrupt

    def _record(self, method: str, body: dict, files: dict | None) -> str | None:
        image = None
        for value in (files or {}).values():
            content = _file_bytes(value)
            if content:
                self.images += 1
                image = f"{self.images:02d}_{method}.png"
                (self.output / image).write_bytes(content)
                break
        text = body.get("text") or body.get("caption") or ""
        if not text and isinstance(body.get("media"), str):
            try:
                text = json.loads(body["media"]).get("caption", "")
            except Exception:
                text = ""
        self.log.append({
            "minuto": self.minute(),
            "metodo": method,
            "testo": str(text),
            "immagine": image,
            "message_id": body.get("message_id"),
        })
        preview = re.sub(r"<[^>]+>", "", html.unescape(str(text))).replace("\n", " ")[:90]
        print(f"[SIM {self.log[-1]['minuto']:>7}] {method}{' + immagine' if image else ''} | {preview}",
              flush=True)
        return image

    def cleanup(self, delete_after: float) -> None:
        if self.dry_run or not self.sent:
            return
        print(f"[SIM] Fine simulazione: cancello {len(self.sent)} messaggi tra "
              f"{int(delete_after // 60)} minuti", flush=True)
        REAL_SLEEP(delete_after)
        delete_pending(self.output)

    def write_report(self) -> Path:
        comp = self.latest["header"]["competitions"][0]
        home_c = next(c for c in comp["competitors"] if c.get("homeAway") == "home")
        away_c = next(c for c in comp["competitors"] if c.get("homeAway") == "away")
        home = home_c["team"]["displayName"]
        away = away_c["team"]["displayName"]
        lines = [
            f"# Simulazione {home} {home_c.get('score')}-{away_c.get('score')} {away}",
            "",
            f"Event ID {self.partita()['event_id']} · {self.partita()['league_name']} · "
            f"{'live vero' if self.live else 'replay'} · "
            f"{'prova senza invii' if self.dry_run else 'inviata su Bot JR'}",
            "",
        ]
        for entry in self.log:
            text = re.sub(r"<[^>]+>", "", html.unescape(entry["testo"])).strip()
            head = f"**{entry['minuto']}** · `{entry['metodo']}`"
            if entry["immagine"]:
                head += f" · immagine `{entry['immagine']}`"
            lines += [head, "", "> " + text.replace("\n", "\n> ") if text else "", ""]
        report = self.output / "report.md"
        report.write_text("\n".join(lines), encoding="utf-8")
        summary = os.getenv("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as handle:
                handle.write("\n".join(lines) + "\n")
        return report


class SimSession:
    """Al posto di net.SESSION: ESPN simulato, Telegram sul canale di test, resto bloccato."""

    def __init__(self, sim: Simulation) -> None:
        self.sim = sim
        self.real = sim.real
        self.headers = self.real.headers

    def mount(self, *args, **kwargs) -> None:
        pass

    def get(self, url, params=None, **kwargs):
        if self.sim.live and "espn.com" in url:
            return self.sim.espn_get(url, params=params, **kwargs)
        if "site.api.espn.com" in url and url.rstrip("/").endswith("/summary"):
            return FakeResponse(self.sim.summary())
        if "site.api.espn.com" in url and url.rstrip("/").endswith("/scoreboard"):
            return FakeResponse({"leagues": [], "events": []})
        if "api.github.com" in url:
            return FakeResponse({"message": "bloccato dalla simulazione"}, 404)
        return self.real.get(url, params=params, **kwargs)

    def post(self, url, json=None, data=None, files=None, timeout=10, **kwargs):
        if "api.telegram.org" in url:
            return self.sim.telegram(url, json, data, files, timeout)
        return FakeResponse({"message": "bloccato dalla simulazione"}, 403)

    def put(self, url, **kwargs):
        return FakeResponse({"message": "bloccato dalla simulazione"}, 403)

    def patch(self, url, **kwargs):
        return FakeResponse({"message": "bloccato dalla simulazione"}, 403)

    def request(self, method, url, **kwargs):
        # Stesse regole dei metodi singoli, per chi usa session.request(...).
        handler = getattr(self, str(method).lower(), None)
        if handler is None:
            return FakeResponse({"message": "bloccato dalla simulazione"}, 403)
        return handler(url, **kwargs)

    def delete(self, url, **kwargs):
        return FakeResponse({"message": "bloccato dalla simulazione"}, 403)


# ==============================================================================
# PULIZIA (anche se il run viene annullato)
# ==============================================================================
PENDING_FILE = "messaggi_da_cancellare.json"


def save_pending(output: Path, sent: list[tuple[str, int]]) -> None:
    """Elenco dei messaggi ancora su Bot JR, riscritto a ogni invio: se il run
    viene annullato, lo step di pulizia del workflow li cancella da qui."""
    path = Path(output) / PENDING_FILE
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps([list(item) for item in sent]), encoding="utf-8")
    temporary.replace(path)


def delete_pending(output: Path | str) -> int:
    """Cancella da Telegram i messaggi rimasti nell'elenco; tiene solo quelli falliti."""
    path = Path(output) / PENDING_FILE
    try:
        pending = [(str(chat), int(message)) for chat, message in json.loads(path.read_text("utf-8"))]
    except (OSError, ValueError, TypeError):
        print("[SIM] Nessun messaggio da cancellare", flush=True)
        return 0
    if not pending:
        print("[SIM] Nessun messaggio da cancellare", flush=True)
        return 0
    token = os.getenv("TELEGRAM_TOKEN", "")
    session = requests.Session()
    failed: list[tuple[str, int]] = []
    for chat_id, message_id in pending:
        try:
            response = session.post(
                f"https://api.telegram.org/bot{token}/deleteMessage",
                json={"chat_id": chat_id, "message_id": message_id}, timeout=10)
            # 400 = gia' cancellato (per esempio dal bot stesso): va bene cosi'.
            if not (response.ok or response.status_code == 400):
                failed.append((chat_id, message_id))
        except requests.RequestException:
            failed.append((chat_id, message_id))
        REAL_SLEEP(0.2)
    save_pending(path.parent, failed)
    print(f"[SIM] Cancellati {len(pending) - len(failed)}/{len(pending)} messaggi", flush=True)
    return len(pending) - len(failed)


@contextmanager
def _nothing():
    yield


class LocalSnapshots:
    """Al posto dello snapshot store su GitHub: il runtime pubblica una foto di
    fase solo dopo averne salvato lo snapshot della foto. In simulazione resta nella
    cartella locale del run, e il branch runtime-snapshots del live non si tocca."""

    def enabled(self) -> bool:
        return True

    def persist_snapshot(self, *, event_id: str, kind: str, snapshot_dir: Path) -> dict:
        return {"path": str(snapshot_dir), "event_id": str(event_id), "kind": kind,
                "simulated": True}

    def restore_snapshot(self, metadata: dict, *, destination_root: Path) -> Path:
        return Path(str(metadata.get("path") or ""))

    def cleanup_event(self, event_id: str) -> int:
        return 0


# ==============================================================================
# AVVIO
# ==============================================================================
def parse_event_id(value: str) -> str:
    """Accetta l'ID ESPN oppure l'URL della partita (es. .../gameId/401874772, ?gameId=..., ?event=...)."""
    text = str(value).strip()
    if text.isdigit():
        return text
    match = re.search(r"(?:gameId|event|matchId)(?:/|=)(\d+)", text, re.IGNORECASE)
    if not match:
        raise ValueError(f"Non trovo l'ID della partita in: {text!r} (serve l'ID ESPN o l'URL della partita)")
    return match.group(1)


def load_summary(event_id: str, league: str = "eng.1") -> dict:
    """ESPN restituisce il summary con qualsiasi slug valido: la lega vera e' nell'header."""
    response = requests.get(ESPN_SUMMARY.format(slug=league), params={"event": event_id}, timeout=30)
    response.raise_for_status()
    data = response.json()
    if not data.get("header", {}).get("competitions"):
        raise ValueError(f"Partita {event_id} non trovata su ESPN")
    return data


def run(event_id: str, *, team_id: str = "", league: str = "eng.1", dry_run: bool = False,
        interval: float | None = None, delete_after: float = 300.0,
        output: Path | str = "sim_output", mode: str = "auto") -> int:
    event_id = parse_event_id(event_id)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    final = load_summary(event_id, league)
    mode = resolve_mode(final, mode)
    live = mode == "live"
    if interval is None:
        interval = DEFAULT_INTERVAL[mode]
    comp = final["header"]["competitions"][0]
    # Al bot la squadra serve solo per trovare la partita del giorno: qui la
    # partita e' gia' data, e le regole guardano solo se in campo c'e' la Juve.
    ids = [str(c["team"]["id"]) for c in comp["competitors"]]
    team_id = str(team_id or ("111" if "111" in ids else ids[0]))

    chat_id = os.getenv("TELEGRAM_TO_BOT") or os.getenv("TELEGRAM_TO") or "simulazione"
    if not dry_run and (not os.getenv("TELEGRAM_TOKEN") or chat_id == "simulazione"):
        print("[SIM] TELEGRAM_TOKEN o TELEGRAM_TO_BOT mancanti: passo alla prova senza invii")
        dry_run = True

    # Configurazione del bot prima di importarne i moduli.
    os.environ.update({
        "TEAM_ID": team_id,
        "TELEGRAM_TO": chat_id,
        "TELEGRAM_TO_BOT": chat_id,
        "GOAL_GRAPHICS_ENABLED": "true",
        "FCLOGO_SYNC_DONE": "true",
        "LIVE_SCORE_CHANNEL_NAME": "Bot JR",
        "SNAPSHOT_GH_TOKEN": "",
        "STEP_SUMMARY_DISABLED": "1",   # il riepilogo lo scrive write_report
    })
    os.environ.setdefault("TELEGRAM_TOKEN", "simulazione")

    from livescore import settings
    from livescore.core import http as net

    sim = Simulation(final, team_id=team_id, chat_id=chat_id, dry_run=dry_run,
                     interval=interval, output=output,
                     live=live, espn_session=net.SESSION)

    settings.TEAM_ID = team_id
    settings.CHAT_ID = chat_id
    settings.BOT_JR_CHAT_ID = chat_id
    settings.GOAL_GRAPHICS_ENABLED = True
    settings.BOT_TOKEN = os.environ["TELEGRAM_TOKEN"]
    settings.GH_PAT = None
    settings.GIST_ID = None
    net.SESSION = SimSession(sim)

    from livescore.state import gist
    gist.leggi_stato_da_gist = lambda: (True, None)
    gist.salva_stato_su_gist = lambda state: True
    gist.resetta_gist = lambda: True
    gist.background = _nothing
    gist.take_async_failure = lambda: False
    gist.flush = lambda timeout=45.0: True

    from livescore.espn import client as espn_client
    espn_client.trova_partita_oggi = lambda _team_id: sim.partita()

    # Foto delle fasi: stesso limite di attesa del live (phase_photo.WAIT_SECONDS).
    # Senza invii (dry run) l'avviso non parte e le fasi restano solo testo.
    from livescore.match import phase_photo
    phase_photo.LABEL = "SIMULAZIONE"
    if dry_run:
        settings.PHOTO_CHAT_ID = None
    sim.clock.hold = phase_photo.holding

    if not live:   # nel live l'orologio resta quello vero
        _time.time = sim.clock.time
        _time.monotonic = sim.clock.monotonic
        _time.sleep = sim.clock.sleep

    partita = sim.partita()
    print(f"[SIM] {sim.timeline.home['team']['displayName']} - "
          f"{sim.timeline.away['team']['displayName']} | {partita['league_name']} | "
          f"{'live vero' if live else 'replay'} (stato ESPN: {match_state(final) or '?'}) | "
          f"{'prova senza invii' if dry_run else 'invio su Bot JR'}",
          flush=True)
    for name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), sim._on_signal)

    code = 0
    try:
        from livescore import runner
        # Gli snapshot delle foto del live (branch runtime-snapshots) restano intatti.
        runner.KIT_RUNTIME.snapshot_store = LocalSnapshots()
        runner.main()
    except SimulationTimeout as exc:
        print(f"[SIM] {exc}", flush=True)
        code = 1
    except KeyboardInterrupt:
        sim.interrupted = True
        print("[SIM] Simulazione annullata", flush=True)
        code = 130
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 0
    finally:
        for name in ("SIGINT", "SIGTERM"):
            if hasattr(signal, name):
                signal.signal(getattr(signal, name), signal.SIG_IGN)   # la pulizia non va interrotta
        _time.time, _time.monotonic, _time.sleep = REAL_TIME, REAL_MONOTONIC, REAL_SLEEP
        report = sim.write_report()
        print(f"[SIM] {len(sim.log)} chiamate Telegram, {sim.images} immagini | report: {report}",
              flush=True)
        if sim.interrupted:
            if not sim.dry_run:
                delete_pending(output)          # annullata: niente attesa, si pulisce subito
        else:
            sim.cleanup(delete_after)
    return code
