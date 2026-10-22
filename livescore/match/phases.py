"""Fasi della partita: inizio, intervalli, supplementari e rigori."""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone

from livescore.constants import E_BOLT, E_FLAG, E_KICK
from livescore.core.log import log_line
from livescore.espn import parser as espn_parser
from livescore.match import formatting as fmt
from livescore.match import media, stats_job
from livescore.match.context import MatchContext, Flow
from livescore.state import gist
from livescore.telegram import api as tg


def wait_for_kickoff(ctx: MatchContext) -> Flow | None:
    """Prima del fischio d'inizio: attende senza inviare nulla."""
    # --- Non ancora iniziata ---
    if ctx.status == "NS":
        try:
            comp       = ctx.data["header"]["competitions"][0]
            start_str  = comp.get("date", "")
            if start_str:
                start_time         = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                now_utc            = datetime.now(timezone.utc)
                minutes_to_kickoff = (start_time - now_utc).total_seconds() / 60
                if minutes_to_kickoff > 60:
                    log_line("STOP", "MATCH", f"Kickoff tra {minutes_to_kickoff:.0f} min; avvio troppo anticipato")
                    sys.exit(0)
                if "_ns_logged" not in ctx.state:
                    log_line("WAIT", "MATCH", f"Calcio d'inizio tra {minutes_to_kickoff:.0f} min")
                    ctx.state["_ns_logged"] = True
        except Exception as e:
            log_line("WARN", "MATCH", f"Orario partita non leggibile: {e}")
        time.sleep(6)
        return Flow.CONTINUE


def announce_kickoff(ctx: MatchContext) -> None:
    """Messaggio INIZIO PARTITA."""
    # --- Inizio primo tempo ---
    if ctx.status == "1H" and "1H" not in ctx.state["sent_periods"]:
        msg_id = media.send_phase_message(f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{ctx.home_name} - {ctx.away_name}\n\n{ctx.e_comp} {ctx.hashtag}",
            kind='kick', data_espn=ctx.data, home_id=ctx.home_id, away_id=ctx.away_id,
            home_name=ctx.home_name_raw, away_name=ctx.away_name_raw, league_slug=ctx.league_slug, league_name=ctx.league_name)
        if msg_id:
            log_line("EVENT", "MATCH", "INIZIO PARTITA | Telegram inviato")
            ctx.state["sent_periods"].append("1H")
            gist.salva_stato_su_gist(ctx.state)
            ctx.state_changed = True
        else:
            log_line("RETRY", "TELEGRAM", "INIZIO PARTITA non inviato; nuovo tentativo al prossimo ciclo")


def announce_halftime(ctx: MatchContext) -> None:
    """Messaggio FINE PRIMO TEMPO e programmazione delle statistiche."""
    # --- Fine primo tempo ---
    if ctx.status == "HT":
        if "HT" not in ctx.state["sent_periods"]:
            scorers_line = fmt.phase_scorers_line(ctx.events, ctx.home_id, ctx.away_id, 'half')
            msg_id = media.send_phase_message(f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{ctx.score_str}\n{scorers_line}\n{ctx.e_comp} {ctx.hashtag}",
                kind='half', data_espn=ctx.data, home_id=ctx.home_id, away_id=ctx.away_id,
                home_name=ctx.home_name_raw, away_name=ctx.away_name_raw, league_slug=ctx.league_slug, league_name=ctx.league_name,
                home_goals=ctx.g_home, away_goals=ctx.g_away)
            if msg_id:
                log_line("EVENT", "MATCH", f"FINE 1° TEMPO | {ctx.home_name} {ctx.g_home}-{ctx.g_away} {ctx.away_name} | Telegram inviato")
                ctx.state["sent_periods"].append("HT")
                stats_job._schedule_stats(ctx.state, "HT")
                gist.salva_stato_su_gist(ctx.state)
                ctx.state_changed = True
            else:
                log_line("RETRY", "TELEGRAM", "FINE 1° TEMPO non inviato; nuovo tentativo al prossimo ciclo")
        elif "HT" not in ctx.state["sent_stats"]:
            # Recovery: messaggio HT già inviato in un run precedente ma
            # stats mai partite (es. crash) → riprogramma
            if stats_job._schedule_stats(ctx.state, "HT"):
                ctx.state_changed = True


def announce_second_half(ctx: MatchContext) -> None:
    """Messaggio INIZIO SECONDO TEMPO."""
    # --- Inizio secondo tempo ---
    if ctx.status == "2H" and "2H" not in ctx.state["sent_periods"]:
        msg_id = tg.send_telegram_get_id(f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n{ctx.score_str}\n\n{ctx.e_comp} {ctx.hashtag}")
        if msg_id:
            log_line("EVENT", "MATCH", "INIZIO 2° TEMPO | Telegram inviato")
            ctx.state["sent_periods"].append("2H")
            gist.salva_stato_su_gist(ctx.state)
            ctx.state_changed = True
        else:
            log_line("RETRY", "TELEGRAM", "INIZIO 2° TEMPO non inviato; nuovo tentativo al prossimo ciclo")


def announce_extra_time(ctx: MatchContext) -> None:
    """Fine regolamentari, supplementari e pausa pre-rigori."""
    # --- Fine regolamentari → supplementari ---
    # Fotografie dello stato PRIMA che i blocchi qui sotto lo modifichino:
    # servono a garantire che due messaggi consecutivi (es. FINE
    # REGOLAMENTARI e INIZIO 1T SUPPLEMENTARE) non partano mai nello
    # stesso ciclo di polling, ma ad almeno un ciclo (~6s) di distanza.
    _2h_end_gia_inviato  = "2H_END"  in ctx.state["sent_periods"]
    _1et_end_gia_inviato = "1ET_END" in ctx.state["sent_periods"]

    # Caso normale: ESPN espone la pausa (END_OF_REGULATION / END_PERIOD
    # con period=2) → il messaggio parte DURANTE l'intervallo, come in TV.
    # Richiede 2 avvistamenti consecutivi (~12s) per non scattare su un
    # eventuale END_PERIOD transitorio prima del fischio finale di una
    # partita senza supplementari.
    if ctx.status == "BREAK_ET" and "2H_END" not in ctx.state["sent_periods"] and "FT" not in ctx.state["sent_periods"]:
        ctx.state["_break_et_seen"] = ctx.state.get("_break_et_seen", 0) + 1
        if ctx.state["_break_et_seen"] >= 2:
            scorers_line = fmt.phase_scorers_line(ctx.events, ctx.home_id, ctx.away_id, 'end_of_90')
            msg_id = media.send_phase_message(f"<b>FINE REGOLAMENTARI {E_FLAG}</b>\n\n{ctx.score_str}\n{scorers_line}\n{ctx.e_comp} {ctx.hashtag}", kind="end_of_90", data_espn=ctx.data, home_id=ctx.home_id, away_id=ctx.away_id, home_name=ctx.home_name_raw, away_name=ctx.away_name_raw, league_slug=ctx.league_slug, league_name=ctx.league_name, home_goals=ctx.g_home, away_goals=ctx.g_away)
            if msg_id:
                log_line("EVENT", "MATCH", f"FINE REGOLAMENTARI | {ctx.home_name} {ctx.g_home}-{ctx.g_away} {ctx.away_name} | Telegram inviato")
                ctx.state["sent_periods"].append("2H_END")
                stats_job._schedule_stats(ctx.state, "2H_END")
                gist.salva_stato_su_gist(ctx.state)
                ctx.state_changed = True
            else:
                log_line("RETRY", "TELEGRAM", "FINE REGOLAMENTARI non inviato; nuovo tentativo al prossimo ciclo")
    elif ctx.status != "BREAK_ET":
        ctx.state["_break_et_seen"] = 0

    # Recovery: ESPN non ha mai esposto la pausa (o il bot era giù) e lo
    # status è già ET/PEN/AET → invia ora. L'INIZIO 1T SUPPLEMENTARE
    # partirà comunque al ciclo successivo grazie a _2h_end_gia_inviato.
    if ctx.status in ("ET", "PEN", "AET") and "2H_END" not in ctx.state["sent_periods"] and "FT" not in ctx.state["sent_periods"]:
        scorers_line = fmt.phase_scorers_line(ctx.events, ctx.home_id, ctx.away_id, 'end_of_90')
        msg_id = media.send_phase_message(f"<b>FINE REGOLAMENTARI {E_FLAG}</b>\n\n{ctx.score_str}\n{scorers_line}\n{ctx.e_comp} {ctx.hashtag}", kind="end_of_90", data_espn=ctx.data, home_id=ctx.home_id, away_id=ctx.away_id, home_name=ctx.home_name_raw, away_name=ctx.away_name_raw, league_slug=ctx.league_slug, league_name=ctx.league_name, home_goals=ctx.g_home, away_goals=ctx.g_away)
        if msg_id:
            log_line("EVENT", "MATCH", f"FINE REGOLAMENTARI | {ctx.home_name} {ctx.g_home}-{ctx.g_away} {ctx.away_name} | Telegram inviato")
            ctx.state["sent_periods"].append("2H_END")
            if ctx.status == "ET":
                stats_job._schedule_stats(ctx.state, "2H_END")
            gist.salva_stato_su_gist(ctx.state)
            ctx.state_changed = True
        else:
            log_line("RETRY", "TELEGRAM", "FINE REGOLAMENTARI non inviato; nuovo tentativo al prossimo ciclo")
    elif ctx.status == "ET" and "2H_END" in ctx.state["sent_periods"] and "2H_END" not in ctx.state["sent_stats"]:
        # Recovery: stats di fine regolamentari mai partite dopo un crash
        if stats_job._schedule_stats(ctx.state, "2H_END"):
            ctx.state_changed = True

    # --- Supplementari ---
    if ctx.status == "ET":
        try:
            comp_status = ctx.data["header"]["competitions"][0].get("status", {})
            stype_name  = comp_status.get("type", {}).get("name", "").upper()
            et_period   = comp_status.get("period", 1)
        except Exception:
            stype_name = ""
            et_period  = 1

        is_et_halftime = any(kw in stype_name for kw in
                             ("HALFTIME", "HALF_TIME", "HT_ET", "EXTRA_TIME_HALF", "END_PERIOD"))
        is_second_et = (et_period >= 4 or (ctx.elapsed >= 106 and et_period >= 3))

        # Gate _2h_end_gia_inviato: se FINE REGOLAMENTARI è partito in
        # QUESTO ciclo, l'inizio supplementari aspetta il prossimo (~6s).
        if (_2h_end_gia_inviato and "1ET_START" not in ctx.state["sent_periods"]
                and not is_et_halftime and not is_second_et):
            if tg.send_telegram_get_id(f"<b>INIZIO 1T SUPPLEMENTARE {E_BOLT}</b>\n\n{ctx.score_str}\n\n{ctx.e_comp} {ctx.hashtag}"):
                ctx.state["sent_periods"].append("1ET_START")
                gist.salva_stato_su_gist(ctx.state)
                ctx.state_changed = True

        if (is_et_halftime or is_second_et) and "1ET_END" not in ctx.state["sent_periods"]:
            if tg.send_telegram_get_id(f"<b>FINE 1T SUPPLEMENTARE {E_FLAG}</b>\n\n{ctx.score_str}\n\n{ctx.e_comp} {ctx.hashtag}"):
                ctx.state["sent_periods"].append("1ET_END")
                gist.salva_stato_su_gist(ctx.state)
                ctx.state_changed = True

        # Gate _1et_end_gia_inviato: stessa logica, FINE 1T SUPPLEMENTARE
        # e INIZIO 2T SUPPLEMENTARE non partono mai nello stesso ciclo.
        if is_second_et and _1et_end_gia_inviato and "2ET_START" not in ctx.state["sent_periods"]:
            if tg.send_telegram_get_id(f"<b>INIZIO 2T SUPPLEMENTARE {E_BOLT}</b>\n\n{ctx.score_str}\n\n{ctx.e_comp} {ctx.hashtag}"):
                ctx.state["sent_periods"].append("2ET_START")
                gist.salva_stato_su_gist(ctx.state)
                ctx.state_changed = True

    # --- Intervallo supplementari ---
    if ctx.status == "HT_ET":
        if "1ET_START" not in ctx.state["sent_periods"]:
            ctx.state["sent_periods"].append("1ET_START")
            ctx.state_changed = True
        if "1ET_END" not in ctx.state["sent_periods"]:
            if tg.send_telegram_get_id(f"<b>FINE 1T SUPPLEMENTARE {E_FLAG}</b>\n\n{ctx.score_str}\n\n{ctx.e_comp} {ctx.hashtag}"):
                ctx.state["sent_periods"].append("1ET_END")
                gist.salva_stato_su_gist(ctx.state)
                ctx.state_changed = True

    # --- Pausa fine supplementari → rigori ---
    # ESPN espone la pausa pre-rigori (END_OF_EXTRATIME / END_PERIOD con
    # period=4): FINE 2T SUPPLEMENTARE parte QUI, durante l'intervallo,
    # invece che insieme al primo aggiornamento della lotteria.
    if ctx.status == "BREAK_PEN":
        if "1ET_END" not in ctx.state["sent_periods"]:
            # Backfill silenzioso: se il bot non ha mai visto l'intervallo
            # dei supplementari, non ha senso annunciarlo ora in ritardo.
            ctx.state["sent_periods"].append("1ET_END")
            ctx.state_changed = True
        if "ET_END_PENS" not in ctx.state["sent_periods"]:
            _pens_intro_ok = True
            if "2ET_START" in ctx.state["sent_periods"] or "1ET_START" in ctx.state["sent_periods"]:
                _pens_intro_ok = tg.send_telegram_get_id(f"<b>FINE 2T SUPPLEMENTARE {E_FLAG}</b>\n\n{ctx.score_str}\n\n{ctx.e_comp} {ctx.hashtag}") is not None
            if _pens_intro_ok:
                ctx.state["sent_periods"].append("ET_END_PENS")
                gist.salva_stato_su_gist(ctx.state)
                ctx.state_changed = True


def announce_shootout(ctx: MatchContext) -> None:
    """Lotteria dei rigori: aggiorna il messaggio RIGORI."""
    # --- Rigori ---
    if ctx.status == "PEN":
        if "ET_END_PENS" not in ctx.state["sent_periods"]:
            _pens_intro_ok = True
            if "2ET_START" in ctx.state["sent_periods"] or "1ET_START" in ctx.state["sent_periods"]:
                _pens_intro_ok = tg.send_telegram_get_id(f"<b>FINE 2T SUPPLEMENTARE {E_FLAG}</b>\n\n{ctx.score_str}\n\n{ctx.e_comp} {ctx.hashtag}") is not None
            if _pens_intro_ok:
                ctx.state["sent_periods"].append("ET_END_PENS")
                gist.salva_stato_su_gist(ctx.state)
                ctx.state_changed = True

        home_pen_icons, away_pen_icons = espn_parser._rigori_icone(ctx.data, ctx.events, ctx.home_id, ctx.away_id,
                                                       ctx.home_name_raw, ctx.away_name_raw)

        total_kicks = len(home_pen_icons) + len(away_pen_icons)
        if total_kicks > ctx.state["penalties_count"]:
            _pen_msg_ok = tg.send_telegram_get_id(
                f"<b>RIGORI {E_KICK}</b>\n\n"
                f"{ctx.home_name}: " + ("".join(home_pen_icons) if home_pen_icons else "—") + "\n"
                f"{ctx.away_name}: " + ("".join(away_pen_icons) if away_pen_icons else "—") + f"\n\n{ctx.e_comp} {ctx.hashtag}"
            )
            if _pen_msg_ok:
                ctx.state["penalties_count"] = total_kicks
                ctx.state_changed = True
