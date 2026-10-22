"""Simulatore di partita: ESPN, Telegram e Gist finti, orologio finto.

Serve a far girare il ciclo vero (`avvia_ciclo_partita`) in un istante e a registrare
tutto cio' che il bot farebbe: messaggi Telegram, salvataggi di stato, righe di log.

Non importa `livescore`: riceve il "backend" (un oggetto su cui leggere/scrivere i nomi
del bot, es. `livescore.hooks.bot`). Cosi' lo stesso identico codice puo' essere usato
sia sul progetto nuovo sia sul vecchio `juve_bot_espn.py` per confrontare i risultati.
"""

from __future__ import annotations

import contextlib
import copy
import io
import re
import time as _time
from unittest.mock import Mock, patch

HOME_ID, HOME_NAME = "111", "Juventus"
AWAY_ID, AWAY_NAME = "110", "Inter"

_TS = re.compile(r"^\[\d\d:\d\d:\d\d\] ")


class StopSim(BaseException):
    """Fine della simulazione (BaseException: il ciclo del bot non la cattura)."""


class Clock:
    """Orologio finto: sleep() fa avanzare il tempo senza aspettare."""

    def __init__(self, start: float = 1_800_000_000.0):
        self.start = start
        self.now = start

    def time(self) -> float:
        return self.now

    def monotonic(self) -> float:
        return self.now - self.start

    def sleep(self, seconds) -> None:
        self.now += max(0.0, float(seconds))

    @property
    def elapsed(self) -> float:
        return self.now - self.start


# ─────────────────────────────── costruzione dei feed ESPN ───────────────────────────────
def athlete(name: str, short: str | None = None) -> dict:
    return {"athlete": {"displayName": name, "shortName": short or name}}


def key_event(uid, text, clock, period, team_id, *participants, raw_type="") -> dict:
    """Evento strutturato (keyEvents). Nei cambi: participants = [entra, esce]."""
    return {
        "id": str(uid),
        "type": {"text": text, "type": raw_type},
        "clock": {"displayValue": clock},
        "period": {"number": period},
        "team": {"id": str(team_id)},
        "participants": [athlete(*p) if isinstance(p, tuple) else athlete(p) for p in participants],
    }


def payload(*, state="in", name="STATUS_IN_PROGRESS", clock="1'", period=1,
            home=0, away=0, key_events=(), commentary=(), shootout=(), date="2030-01-01T18:00Z") -> dict:
    return {
        "header": {"competitions": [{
            "date": date,
            "status": {"type": {"state": state, "name": name, "description": ""},
                       "displayClock": clock, "period": period},
            "competitors": [
                {"homeAway": "home", "score": str(home),
                 "team": {"id": HOME_ID, "displayName": HOME_NAME}},
                {"homeAway": "away", "score": str(away),
                 "team": {"id": AWAY_ID, "displayName": AWAY_NAME}},
            ],
        }]},
        "keyEvents": list(key_events),
        "commentary": list(commentary),
        "shootout": list(shootout),
        "boxscore": {"teams": []},
        "gameInfo": {"venue": {"fullName": "Allianz Stadium"}},
    }


def match_info() -> dict:
    p = payload(state="pre", name="STATUS_SCHEDULED")
    comp = p["header"]["competitions"][0]
    return {"event_id": "999001", "league_slug": "ita.1", "league_name": "Serie A",
            "competitors": comp["competitors"], "competition": comp, "date": comp["date"]}


# ─────────────────────────────── esecuzione ───────────────────────────────
class Result(dict):
    """Esito di una simulazione (serializzabile in JSON)."""


class Sim:
    """Una partita simulata.

    frames   : [(secondi, payload)] il feed ESPN cambia al raggiungimento di ciascun istante
    end      : secondi dopo i quali la simulazione si interrompe (se il bot non ha gia' finito)
    initial_state : stato Gist di partenza (per simulare un riavvio a partita in corso)
    tg_fail  : funzione (n_chiamata, metodo, payload) -> True per far fallire quell'invio
    """

    def __init__(self, backend, frames, end, *, initial_state=None, tg_fail=None, graphics=False):
        self.B = backend
        self.frames = sorted(frames, key=lambda f: f[0])
        self.end = end
        self.initial_state = initial_state
        self.tg_fail = tg_fail
        self.graphics = graphics
        self.clock = Clock()
        self.telegram: list[dict] = []
        self.saves: list[dict] = []
        self.resets = 0
        self._msg_id = 1000
        self._tg_calls = 0

    # -- finti --
    def _current(self):
        now = self.clock.elapsed
        if now > self.end:
            raise StopSim()
        current = self.frames[0][1]
        for t, p in self.frames:
            if t <= now:
                current = p
        return copy.deepcopy(current)

    def _fetch(self, event_id, league_slug):
        return self._current()

    def _tg_post(self, method, payload=None, data=None, files=None, timeout=10):
        self._tg_calls += 1
        body = dict(payload or data or {})
        failed = bool(self.tg_fail and self.tg_fail(self._tg_calls, method, body))
        entry = {"t": round(self.clock.elapsed), "method": method, "body": body,
                 "files": sorted(files) if files else None, "ok": not failed}
        self.telegram.append(entry)
        response = Mock()
        if failed:
            response.status_code = 500
            response.json.return_value = {"ok": False}
            response.raise_for_status.side_effect = RuntimeError("telegram 500")
            return response
        message_id = body.get("message_id")
        if message_id is None:
            self._msg_id += 1
            message_id = self._msg_id
        entry["message_id"] = message_id
        response.status_code = 200
        response.json.return_value = {"ok": True, "result": {"message_id": message_id}}
        return response

    def _load(self):
        return True, copy.deepcopy(self.initial_state)

    def _save(self, state):
        self.saves.append(copy.deepcopy(state))
        return True

    def _reset(self):
        self.resets += 1
        return True

    def _stats_photo(self, png_path, momento, hashtag, *a, **k):
        self.telegram.append({"t": round(self.clock.elapsed), "method": "STATS_PHOTO",
                              "body": {"momento": momento, "caption": hashtag}, "files": None, "ok": True})
        return True

    # -- esecuzione --
    def run(self) -> Result:
        B = self.B
        out = io.StringIO()
        outcome = "ended"
        patches = [
            patch.object(B, "trova_partita_oggi", lambda team_id: match_info()),
            patch.object(B, "fetch_evento", self._fetch),
            patch.object(B, "_tg_post", self._tg_post),
            patch.object(B, "leggi_stato_da_gist", self._load),
            patch.object(B, "salva_stato_su_gist", self._save),
            patch.object(B, "resetta_gist", self._reset),
            patch.object(B, "recupera_xg_espn", lambda *a, **k: None),
            patch.object(B, "recupera_e_genera_stats_html", lambda *a, **k: "stats.png"),
            patch.object(B, "send_telegram_stats_photo", self._stats_photo),
            patch.object(B, "GOAL_GRAPHICS_ENABLED", self.graphics),
            patch.object(B, "BOT_TOKEN", "TOKEN"),
            patch.object(B, "CHAT_ID", "-100"),
            patch.object(B, "BOT_JR_CHAT_ID", "-200"),
            patch.object(B.SESSION, "get", Mock(return_value=Mock(status_code=200))),
            patch.object(_time, "sleep", self.clock.sleep),
            patch.object(_time, "time", self.clock.time),
            patch.object(_time, "monotonic", self.clock.monotonic),
        ]
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            with contextlib.redirect_stdout(out):
                try:
                    B.avvia_ciclo_partita()
                except StopSim:
                    outcome = "timeout"
                except SystemExit as exc:
                    outcome = f"exit({exc.code})"
        log = [_TS.sub("", line) for line in out.getvalue().splitlines() if line.strip()]
        return Result(
            outcome=outcome,
            seconds=round(self.clock.elapsed),
            telegram=self.telegram,
            log=log,
            saves=len(self.saves),
            final_state=self.saves[-1] if self.saves else None,
            resets=self.resets,
        )

    # comodo nei test
    def messages(self, method="sendMessage"):
        return [e for e in self.telegram if e["method"] == method and e["ok"]]

    def texts(self):
        return [e["body"].get("text", "") for e in self.messages()]
