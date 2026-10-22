"""Cambi: un messaggio per squadra e minuto, corretto da solo quando ESPN corregge.

Come funziona
-------------
Ogni cambio e' un *record* ``{uid, in, out, minute, ...}``. I record annunciati insieme
stanno nello stesso *slot* (= un messaggio Telegram) dentro ``state["sent_subs"]``, che
resta salvato nel Gist nel formato di sempre (``ins`` / ``outs`` / ``sub_ids`` / ``minute``)
piu' una lista ``subs`` con i record, che serve a riconoscere le correzioni.

A ogni ciclo si confronta il feed ESPN con i record gia' annunciati:

* stesso cambio con **minuto diverso**  -> si corregge il minuto del messaggio
* stesso id con **giocatori diversi**   -> si corregge il giocatore
* altro id ma stessa coppia di giocatori -> e' lo stesso cambio visto da un'altra fonte ESPN
* cambio nuovo vicino a un messaggio gia' inviato (±2', stesso tempo) -> si aggiunge al messaggio
* cambio nuovo e isolato -> si attende ``SUB_GROUP_SECONDS`` (senza bloccare il ciclo) per
  raggrupparlo con quelli che arrivano subito dopo, poi parte un messaggio nuovo

La logica di decisione (`SubstitutionBook.plan`) non fa nulla da sola: restituisce cosa
cambiare e il gestore (`handle_substitutions`) lo applica a Telegram. Lo stato si aggiorna solo
dopo che Telegram ha confermato, cosi' un invio fallito viene ritentato al ciclo dopo.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field

from livescore import settings
from livescore.constants import E_DOWN, E_SUB, E_UP
from livescore.core import text as txt
from livescore.core.log import log_line
from livescore.match.context import MatchContext
from livescore.telegram import api as tg

WINDOW_MINUTES = 2          # cambi entro ±2' (stesso tempo) finiscono nello stesso messaggio
MAX_CORRECTION_MINUTES = 15  # una correzione di minuto oltre questo scarto e' considerata un'altra cosa


# ───────────────────────────────── dati ─────────────────────────────────
@dataclass
class SubEvent:
    """Un cambio letto dal feed ESPN (nomi gia' nel formato dei messaggi)."""

    uid: str
    team_id: str
    period: int
    minute: int
    player_in: str
    player_out: str
    seq: int = 0

    @classmethod
    def from_feed(cls, event: dict) -> "SubEvent":
        # nel feed: player_name = chi ESCE, assist_name = chi ENTRA
        return cls(
            uid=str(event["uid"]),
            team_id=str(event["team_id"]),
            period=event.get("period", 1),
            minute=event["minute"],
            player_in=txt.fmt_player(event["assist_name"]),
            player_out=txt.fmt_player(event["player_name"]),
            seq=event.get("seq", 0),
        )

    @property
    def pair(self) -> frozenset:
        return frozenset((self.player_in, self.player_out))


@dataclass
class Plan:
    """Cosa fare in questo ciclo."""

    edits: dict = field(default_factory=dict)       # slot_key -> nuovo slot (da inviare a Telegram)
    reasons: dict = field(default_factory=dict)     # slot_key -> descrizioni delle modifiche
    fresh: list = field(default_factory=list)       # cambi nuovi, ancora senza messaggio
    bookkeeping: bool = False                       # True se sono cambiati solo id interni (da salvare)


def render_text(team_title: str, minute, ins, outs, e_comp: str, hashtag: str) -> str:
    """Testo del messaggio: identico per invio, aggiunte e correzioni."""
    return (
        f"<b>CAMBIO {team_title} · {minute}' {E_SUB}</b>\n\n"
        f"{E_UP} {', '.join(ins)}\n"
        f"{E_DOWN} {', '.join(outs)}\n\n"
        f"{e_comp} {hashtag}"
    )


# ───────────────────────────────── logica ─────────────────────────────────
class SubstitutionBook:
    """Registro dei cambi gia' annunciati (una vista su ``state["sent_subs"]``)."""

    def __init__(self, sent_subs: dict):
        self.slots = sent_subs
        for slot in self.slots.values():
            self._ensure_records(slot)

    # -- compatibilita' con gli stati salvati dalle versioni precedenti --
    @staticmethod
    def _ensure_records(slot: dict) -> None:
        if "subs" in slot:
            return
        ins, outs, uids = slot.get("ins", []), slot.get("outs", []), slot.get("sub_ids", [])
        aligned = len(uids) == len(ins)
        slot["subs"] = [
            {"uid": uids[i] if aligned else None, "uids": [uids[i]] if aligned else [],
             "in": ins[i], "out": outs[i] if i < len(outs) else "",
             "minute": slot.get("minute", 0), "seen": []}
            for i in range(len(ins))
        ]

    @staticmethod
    def _sync(slot: dict) -> None:
        """Riallinea i campi 'storici' dello slot ai suoi record."""
        subs = slot["subs"]
        slot["ins"] = [r["in"] for r in subs]
        slot["outs"] = [r["out"] for r in subs]
        if subs:
            slot["minute"] = min(r["minute"] for r in subs)
        known = list(slot.get("sub_ids", []))
        for r in subs:
            for u in r.get("uids", []):
                if u and u not in known:
                    known.append(u)
        slot["sub_ids"] = known

    # -- ricerche --
    def _known_uid(self, uid: str) -> bool:
        return any(uid in slot.get("sub_ids", []) for slot in self.slots.values())

    def _owner(self, uid: str):
        for key, slot in self.slots.items():
            for i, r in enumerate(slot["subs"]):
                if r.get("uid") == uid:
                    return key, i
        return None

    def _by_pair(self, ev: SubEvent):
        for key, slot in self.slots.items():
            if key.split(":")[0] != ev.team_id:
                continue
            for i, r in enumerate(slot["subs"]):
                if frozenset((r["in"], r["out"])) == ev.pair:
                    return key, i
        return None

    def _slot_for(self, ev: SubEvent):
        for key, slot in self.slots.items():
            if (key.split(":")[0] == ev.team_id
                    and slot.get("period", 1) == ev.period
                    and abs(slot["minute"] - ev.minute) <= WINDOW_MINUTES):
                return key
        return None

    # -- decisione --
    def plan(self, events: list[SubEvent]) -> Plan:
        plan = Plan()
        work: dict[str, dict] = {}

        def editable(key: str) -> dict:
            if key not in work:
                work[key] = copy.deepcopy(self.slots[key])
            return work[key]

        def note(key: str, text: str) -> None:
            plan.reasons.setdefault(key, []).append(text)

        def apply_state(key: str, index: int, ev: SubEvent, *, new_uid: bool) -> None:
            """Aggiorna un record con i dati dell'evento (una sola volta per ogni stato mai visto)."""
            slot = editable(key)
            rec = slot["subs"][index]
            current = [rec["in"], rec["out"], rec["minute"]]
            wanted = [ev.player_in, ev.player_out, ev.minute]
            if wanted == current or wanted in rec.get("seen", []):
                return                                    # gia' applicato o gia' scartato: niente va-e-vieni
            if abs(ev.minute - rec["minute"]) > MAX_CORRECTION_MINUTES:
                return                                    # scarto implausibile: non e' una correzione
            rec.setdefault("seen", []).append(current)
            changes = []
            if ev.minute != rec["minute"]:
                changes.append(f"{rec['minute']}' → {ev.minute}'")
            if ev.player_in != rec["in"]:
                changes.append(f"↑ {rec['in']} → {ev.player_in}")
            if ev.player_out != rec["out"]:
                changes.append(f"↓ {rec['out']} → {ev.player_out}")
            rec["in"], rec["out"], rec["minute"] = ev.player_in, ev.player_out, ev.minute
            if new_uid:
                rec["uid"] = ev.uid
            if ev.uid not in rec["uids"]:
                rec["uids"].append(ev.uid)
            note(key, ", ".join(changes))

        for ev in events:
            owner = self._owner(ev.uid)
            if owner:                                     # stesso id: ESPN ha modificato il cambio
                apply_state(owner[0], owner[1], ev, new_uid=False)
                continue
            if self._known_uid(ev.uid):                   # id vecchio / alias / stato di versioni precedenti
                continue

            by_pair = self._by_pair(ev)
            if by_pair:                                   # stessa coppia, altro id: stesso cambio
                key, index = by_pair
                rec = self.slots[key]["subs"][index]
                if ev.uid not in rec["uids"]:
                    rec["uids"].append(ev.uid)
                    self._sync(self.slots[key])
                    plan.bookkeeping = True
                if ev.minute != rec["minute"]:
                    apply_state(key, index, ev, new_uid=True)
                continue

            key = self._slot_for(ev)
            if key is None:
                plan.fresh.append(ev)                     # nuovo e isolato
                continue

            slot = editable(key)
            in_present = any(r["in"] == ev.player_in for r in slot["subs"])
            out_present = any(r["out"] == ev.player_out for r in slot["subs"])
            if in_present and out_present:
                continue                                  # doppione gia' coperto
            if in_present or out_present:                 # ESPN ha corretto UNO dei due giocatori
                index = next(i for i, r in enumerate(slot["subs"])
                             if (r["in"] == ev.player_in if in_present else r["out"] == ev.player_out))
                rec = slot["subs"][index]
                if in_present:
                    note(key, f"↓ {rec['out']} → {ev.player_out}")
                    rec["out"] = ev.player_out
                else:
                    note(key, f"↑ {rec['in']} → {ev.player_in}")
                    rec["in"] = ev.player_in
                rec["uid"] = ev.uid
                if ev.uid not in rec["uids"]:
                    rec["uids"].append(ev.uid)
                continue
            slot["subs"].append({"uid": ev.uid, "uids": [ev.uid], "in": ev.player_in,
                                 "out": ev.player_out, "minute": ev.minute, "seen": []})
            note(key, "aggiunto")

        # un cambio il cui minuto e' stato spostato lontano dagli altri esce dal messaggio
        # e ne riceve uno suo (non va perso)
        for key, slot in list(work.items()):
            subs = slot["subs"]
            evicted: list[str] = []
            if len(subs) > 1:
                steady = [r for r in subs if not r.get("seen")] or subs
                minutes = sorted(r["minute"] for r in steady)
                anchor = minutes[(len(minutes) - 1) // 2]
                far = [r for r in subs if abs(r["minute"] - anchor) > WINDOW_MINUTES]
                if len(far) < len(subs):
                    for r in far:
                        evicted.extend(r.get("uids", []) or [r["uid"]])
                        subs.remove(r)
                        note(key, f"{r['in']} spostato a {r['minute']}'")
                        plan.fresh.append(SubEvent(r["uid"], key.split(":")[0], slot.get("period", 1),
                                                   r["minute"], r["in"], r["out"]))
            self._sync(slot)
            if evicted:
                slot["sub_ids"] = [u for u in slot["sub_ids"] if u not in evicted]

        for key, slot in work.items():
            before = self.slots[key]
            if (slot["ins"], slot["outs"], slot["minute"]) != (before["ins"], before["outs"], before["minute"]):
                plan.edits[key] = slot
        plan.fresh = _dedup_by_pair(plan.fresh)
        return plan

    # -- applicazione (dopo conferma di Telegram) --
    def commit(self, key: str, slot: dict) -> None:
        self.slots[key] = slot

    def add_slot(self, team_id: str, period: int, msg_id, group: list[SubEvent]) -> str:
        minute = min(s.minute for s in group)
        key = f"{team_id}:{period}:{minute}"
        slot = {
            "msg_id": msg_id, "minute": minute, "period": period,
            "ins": [], "outs": [], "sub_ids": [],
            "subs": [{"uid": s.uid, "uids": [s.uid], "in": s.player_in, "out": s.player_out,
                      "minute": s.minute, "seen": []} for s in group],
        }
        self._sync(slot)
        self.slots[key] = slot
        return key


def _dedup_by_pair(events: list[SubEvent]) -> list[SubEvent]:
    """La stessa sostituzione puo' arrivare da piu' fonti con id diversi: ne tengo una."""
    seen, out = set(), []
    for ev in events:
        key = (ev.team_id, ev.pair)
        if key not in seen:
            seen.add(key)
            out.append(ev)
    return out


def group_fresh(events: list[SubEvent]) -> list[list[SubEvent]]:
    """Cambi della stessa squadra e dello stesso tempo, entro ±2', nello stesso messaggio."""
    groups: list[list[SubEvent]] = []
    for ev in sorted(events, key=lambda e: (e.minute, e.seq)):
        for g in groups:
            first = g[0]
            if (first.team_id == ev.team_id and first.period == ev.period
                    and abs(first.minute - ev.minute) <= WINDOW_MINUTES):
                g.append(ev)
                break
        else:
            groups.append([ev])
    return groups


# ───────────────────────────────── gestore del ciclo ─────────────────────────────────
def _team_title(ctx: MatchContext, team_id: str) -> str:
    return ctx.home_name.upper() if team_id == ctx.home_id else ctx.away_name.upper()


def handle_substitutions(ctx: MatchContext) -> None:
    """Cambi: nuovi messaggi, raggruppamento e correzioni di ESPN."""
    feed = [SubEvent.from_feed(e) for e in ctx.events if e["type"] == "substitution"]
    book = SubstitutionBook(ctx.state["sent_subs"])
    plan = book.plan(feed)
    if plan.bookkeeping:
        ctx.state_changed = True

    for key, new_slot in plan.edits.items():
        team_id = key.split(":")[0]
        title = _team_title(ctx, team_id)
        text = render_text(title, new_slot["minute"], new_slot["ins"], new_slot["outs"], ctx.e_comp, ctx.hashtag)
        what = "; ".join(r for r in plan.reasons.get(key, []) if r)
        if tg.send_telegram_edit(new_slot["msg_id"], text):
            book.commit(key, new_slot)
            ctx.state_changed = True
            log_line("EDIT", "MATCH", f"CAMBIO {title} {new_slot['minute']}' aggiornato | {what}"
                                      f" | entra: {', '.join(new_slot['ins'])} | esce: {', '.join(new_slot['outs'])}")
        else:
            log_line("RETRY", "TELEGRAM", f"Edit CAMBIO {title} {new_slot['minute']}' fallito | {what}")

    _send_new_substitutions(ctx, book, plan.fresh)


def _send_new_substitutions(ctx: MatchContext, book: SubstitutionBook, fresh: list[SubEvent]) -> None:
    if not fresh:
        ctx.sub_hold_since = None
        return
    now = time.time()
    if ctx.sub_hold_since is None:
        ctx.sub_hold_since = now
        if settings.SUB_GROUP_SECONDS > 0:
            log_line("WAIT", "MATCH", f"CAMBIO rilevato; raggruppamento per {settings.SUB_GROUP_SECONDS}s")
    if now - ctx.sub_hold_since < settings.SUB_GROUP_SECONDS:
        return                                  # il ciclo continua: gol e cartellini non aspettano

    sent_all = True
    for group in group_fresh(fresh):
        team_id, period = group[0].team_id, group[0].period
        title = _team_title(ctx, team_id)
        minute = min(s.minute for s in group)
        ins = [s.player_in for s in group]
        outs = [s.player_out for s in group]
        msg_id = tg.send_telegram_get_id(render_text(title, minute, ins, outs, ctx.e_comp, ctx.hashtag))
        if msg_id:
            log_line("EVENT", "MATCH", f"CAMBIO {title} {minute}' | entra: {', '.join(ins)} | esce: {', '.join(outs)} | Telegram inviato")
            book.add_slot(team_id, period, msg_id, group)
            ctx.state_changed = True
        else:
            # invio non riuscito: nessuno stato salvato, al ciclo dopo il cambio risulta ancora nuovo e si riprova
            sent_all = False
            log_line("RETRY", "TELEGRAM", f"CAMBIO {title} {minute}' non inviato | entra: {', '.join(ins)} | esce: {', '.join(outs)}")
    if sent_all:
        ctx.sub_hold_since = None
