"""Ciclo principale di una partita: legge ESPN a ogni giro e chiama i gestori, in ordine."""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime

from livescore import settings
from livescore.canva import auth as canva_auth
from livescore.constants import ESPN_BASE, ESPN_TZ
from livescore.core import http as net
from livescore.core.log import MatchProgressLog, log_line
from livescore.espn import client as espn_client
from livescore.graphics import logos as fclogo_sync
from livescore.match import cycle, deferred, finish, goals, incidents, phases, substitutions
from livescore.match.context import Flow, MatchContext
from livescore.state import gist


def avvia_ciclo_partita():
    ctx = MatchContext()
    team_id = str(settings.TEAM_ID).strip()
    ctx.progress_log = MatchProgressLog(
        heartbeat_minutes=settings.LIVE_LOG_HEARTBEAT_MINUTES,
        heartbeat_seconds=settings.LIVE_LOG_HEARTBEAT_MINUTES * 60,
    )

    try:
        test_r = net.SESSION.get(f"{ESPN_BASE}/ita.1/scoreboard",
                              params={"dates": datetime.now(ESPN_TZ).strftime("%Y%m%d")}, timeout=10)
    except Exception as e:
        log_line("WARN", "ESPN", f"Test connettività fallito: {e}")

    ctx.partita = espn_client.trova_partita_oggi(team_id)
    if not ctx.partita:
        log_line("INFO", "MATCH", f"Nessuna partita trovata | team_id={team_id}")
        return

    ctx.event_id    = ctx.partita["event_id"]
    ctx.league_slug = ctx.partita["league_slug"]
    ctx.league_name = ctx.partita["league_name"]

    gist_ok, ctx.state = gist.leggi_stato_da_gist()
    if not gist_ok:
        # Stato illeggibile per errore di rete/API: partire con uno stato
        # vergine rimanderebbe tutti i messaggi già pubblicati. Meglio uscire.
        log_line("ERROR", "STATE", "Gist illeggibile dopo i retry; arresto anti-duplicati")
        sys.exit(1)
    if ctx.state is None or ctx.state.get("event_id") != ctx.event_id:
        ctx.state = {
            "event_id":               ctx.event_id,
            "league_slug":            ctx.league_slug,
            "league_name":            ctx.league_name,
            "sent_periods":           [],
            "goals_detected":         0,
            "prev_home_goals":        0,
            "prev_away_goals":        0,
            "sent_subs":              {},
            "sent_cards":             [],
            "penalties_count":        0,
            "sent_stats":             [],
            "sent_failed_penalties":  [],
            "shootout_message_id":    None,
            "goal_messages":          {},
            "cancel_msg_id":          None,
            "pending_stats":          [],
            "pending_goal_cancellation": None,
        }
    if isinstance(ctx.state.get("sent_subs"), list):
        ctx.state["sent_subs"] = {}
    # La lega va sempre tenuta aggiornata nel Gist (anche su stati ripresi da
    # versioni precedenti): serve ai bot esterni che leggono la partita dal Gist.
    ctx.state["league_slug"] = ctx.league_slug
    ctx.state["league_name"] = ctx.league_name
    # Retrocompatibilità con stati salvati da versioni precedenti
    ctx.state.setdefault("cancel_msg_id", None)
    ctx.state.setdefault("pending_stats", [])
    ctx.state.setdefault("sent_stats", [])
    ctx.state.setdefault("sent_failed_penalties", [])
    ctx.state.setdefault("pending_goal_cancellation", None)

    while True:
        cycle_started = time.monotonic()
        ctx.sleep_time = settings.POLL_SECONDS
        if gist.take_async_failure() and isinstance(ctx.state, dict):
            ctx.state["_gist_dirty"] = True      # il salvataggio in background e' fallito: si riprova subito
        ctx.state_changed = False
        try:
            flow = cycle.prepare_cycle(ctx)
            if flow is Flow.CONTINUE:
                continue
            if flow is Flow.STOP:
                return
            deferred.send_due_stats(ctx)
            flow = phases.wait_for_kickoff(ctx)
            if flow is Flow.CONTINUE:
                continue
            if flow is Flow.STOP:
                return
            deferred.retry_cancel_message(ctx)
            phases.announce_kickoff(ctx)
            goals.catch_up_goals(ctx)
            phases.announce_halftime(ctx)
            phases.announce_second_half(ctx)
            phases.announce_extra_time(ctx)
            phases.announce_shootout(ctx)
            flow = goals.handle_goals(ctx)
            if flow is Flow.CONTINUE:
                continue
            if flow is Flow.STOP:
                return
            flow = finish.handle_finish(ctx)
            if flow is Flow.CONTINUE:
                continue
            if flow is Flow.STOP:
                return
            goals.fix_scorers(ctx)
            substitutions.handle_substitutions(ctx)
            incidents.announce_red_cards(ctx)
            incidents.announce_failed_penalties(ctx)

        except Exception as e:
            log_line("ERROR", "SYSTEM", f"Ciclo live fallito: {e}")
            ctx.sleep_time = settings.POLL_SECONDS

        finally:
            if (
                isinstance(ctx.state, dict)
                and not ctx.state.get("_reset_done")
                and (ctx.state_changed or ctx.state.get("_gist_dirty"))
            ):
                with gist.background():          # il polling non aspetta GitHub
                    gist.salva_stato_su_gist(ctx.state)

        # il tempo gia' speso nel ciclo (ESPN, Telegram, Gist) conta come attesa: cadenza fissa
        spent = time.monotonic() - cycle_started
        time.sleep(max(1.0, ctx.sleep_time - spent))


# ==============================================================================
# MAIN
# ==============================================================================
def main():
    channel = os.getenv("LIVE_SCORE_CHANNEL_NAME", "Juventus Reborn")
    graphics = "on" if settings.GOAL_GRAPHICS_ENABLED else "off"
    log_line(
        "START",
        "SYSTEM",
        f"Live Score avviato | team_id={settings.TEAM_ID} | canale={channel} | grafiche={graphics}",
    )

    if str(os.getenv('ONLY_REFRESH_TOKEN', '')).strip().lower() == "true":
        canva_auth.get_valid_token()
        return

    # Il workflow può aver già sincronizzato i loghi prima di pubblicarli.
    # Il sync gira in background e non ritarda mai la ricerca della partita: a
    # stagione completa controlla solo i loghi senza mono, il catalogo intero solo
    # quando manca ancora qualche pack della stagione (vedi logos.sync_logos).
    if settings.GOAL_GRAPHICS_ENABLED and os.getenv('FCLOGO_SYNC_DONE', '').strip().lower() != 'true':
        threading.Thread(target=_sync_logos_background, name="fclogo-sync", daemon=True).start()

    avvia_ciclo_partita()


def _sync_logos_background():
    try:
        report = fclogo_sync.sync_logos()
        log_line("DEBUG", "GRAPHICS", report.summary())
        for warning in report.errors:
            log_line("WARN", "GRAPHICS", f"FCLogo: {warning}")
    except Exception as exc:
        # Un problema del catalogo grafico non deve mai bloccare il live.
        log_line("WARN", "GRAPHICS", f"FCLogo non sincronizzato: {exc}")
