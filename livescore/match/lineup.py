"""STARTING XI dell'Italia: invio automatico della formazione ufficiale sul canale.

- Appena ESPN pubblica gli 11 titolari dell'Italia (di solito un'ora prima del via)
  parte la grafica con il campo e i nomi.
- A ogni giro si ricontrolla la maglia: se cambia (home <-> away) la grafica si rifà e
  si sostituisce la foto dello stesso messaggio (editMessageMedia), senza nuovi invii.
- Prima del fischio d'inizio vale lo stesso se ESPN corregge formazione o modulo.

Usa solo il riepilogo ESPN già letto dal ciclo: nessuna richiesta in più.
Stato nel Gist, chiave 'lineup': message_id, maglia, firma della formazione.
"""

from __future__ import annotations

import time

from livescore import settings
from livescore.constants import ITALY_ID
from livescore.core.log import log_line
from livescore.match import teams
from livescore.match.context import MatchContext
from livescore.state import gist
from livescore.telegram import api as tg

FINISHED = ("FT", "AET", "PEN", "POST")
CAPTION_TITLE = "✅📋 𝐗𝐈 𝐔𝐅𝐅𝐈𝐂𝐈𝐀𝐋𝐄 𝐈𝐓𝐀𝐋𝐈𝐀"
RETRY_SECONDS = 60           # dopo un invio/modifica fallito si riprova fra un minuto

_next_try = 0.0


def extract_lineup(data: dict | None, team_id: str = ITALY_ID) -> dict | None:
    """Modulo e 11 titolari della squadra da ESPN (rosters[]), None se non ancora pubblicati."""
    for roster in (data or {}).get("rosters") or []:
        if str((roster.get("team") or {}).get("id", "")) != str(team_id):
            continue
        players = []
        for entry in roster.get("roster") or []:
            if not entry.get("starter"):
                continue
            athlete = entry.get("athlete") or {}
            display = str(athlete.get("displayName") or athlete.get("fullName") or "").strip()
            last = str(athlete.get("lastName") or "").strip() or (display.split()[-1] if display else "")
            first = str(athlete.get("firstName") or "").strip() or (display.split()[0] if display else "")
            try:
                place = int(entry.get("formationPlace"))
            except (TypeError, ValueError):
                place = None
            if not last:
                return None
            players.append({
                "id": str(athlete.get("id") or display),
                "place": place,
                "pos": str((entry.get("position") or {}).get("abbreviation") or ""),
                "last": last,
                "first": first,
            })
        if len(players) != 11:
            return None
        return {"formation": str(roster.get("formation") or "").strip(), "players": players}
    return None


def signature(lineup: dict) -> str:
    """Firma della formazione: cambia se cambia un titolare, un posto o il modulo."""
    places = sorted((pl["place"] or 0, pl["id"]) for pl in lineup["players"])
    return lineup["formation"] + "|" + ",".join(f"{p}:{i}" for p, i in places)


def caption(ctx: MatchContext) -> str:
    return f"{CAPTION_TITLE}\n\n{ctx.e_comp} {ctx.hashtag}"


def render(ctx: MatchContext, lineup: dict, kit: str) -> bytes | None:
    try:
        from livescore.graphics import lineup as lineup_graphic
        return lineup_graphic.render_png(kit=kit, formation=lineup["formation"], players=lineup["players"],
                                         home_name=ctx.home_name_raw, away_name=ctx.away_name_raw)
    except Exception as exc:
        log_line("WARN", "GRAPHICS", f"STARTING XI non disponibile: {type(exc).__name__}: {exc}")
        return None


def announce_lineup(ctx: MatchContext) -> None:
    """Invia la STARTING XI dell'Italia o aggiorna la foto se cambia la maglia."""
    global _next_try
    if not settings.GOAL_GRAPHICS_ENABLED or not teams.is_italy(ctx.home_id, ctx.away_id):
        return
    if ctx.status in FINISHED or time.monotonic() < _next_try:
        return
    sent = ctx.state.get("lineup") if isinstance(ctx.state.get("lineup"), dict) else None
    lineup = extract_lineup(ctx.data)
    kit = teams.italy_kit(ctx.data, ctx.home_id)

    if sent is None:
        if lineup is None:
            return
        photo = render(ctx, lineup, kit)
        if not photo:
            _next_try = time.monotonic() + RETRY_SECONDS
            return
        msg_id, is_photo = tg._send_telegram_event_photo_get_id(
            caption(ctx), photo, filename="starting_xi.png", label="STARTING XI",
            retry_factory=lambda: render(ctx, lineup, kit))
        if not msg_id:
            log_line("RETRY", "TELEGRAM", "STARTING XI non inviata; nuovo tentativo fra un minuto")
            _next_try = time.monotonic() + RETRY_SECONDS
            return
        ctx.state["lineup"] = {"message_id": msg_id, "kit": kit if is_photo else None,
                               "signature": signature(lineup), "lineup": lineup}
        log_line("EVENT", "MATCH", f"STARTING XI | {lineup['formation']} | {kit} | Telegram inviato")
        gist.salva_stato_su_gist(ctx.state)
        ctx.state_changed = True
        return

    # Già inviata: si rifà solo se cambia la maglia (sempre) o la formazione (prima del via).
    current = sent.get("lineup")
    reasons = []
    if lineup is not None and ctx.status == "NS" and signature(lineup) != sent.get("signature"):
        current = lineup
        reasons.append("formazione")
    if kit != sent.get("kit"):
        reasons.append(f"maglia {sent.get('kit') or '-'} -> {kit}")
    if not reasons or not isinstance(current, dict) or not sent.get("message_id"):
        return
    photo = render(ctx, current, kit)
    if not photo or not tg.edit_telegram_goal_photo(sent["message_id"], caption(ctx), photo):
        log_line("RETRY", "TELEGRAM", "STARTING XI non aggiornata; nuovo tentativo fra un minuto")
        _next_try = time.monotonic() + RETRY_SECONDS
        return
    sent.update({"kit": kit, "signature": signature(current), "lineup": current})
    log_line("EVENT", "MATCH", f"STARTING XI aggiornata ({', '.join(reasons)}) | stesso messaggio")
    gist.salva_stato_su_gist(ctx.state)
    ctx.state_changed = True
