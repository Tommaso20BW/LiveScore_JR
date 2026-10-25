"""Fine partita: messaggio finale, statistiche e spegnimento."""

from __future__ import annotations

import sys
import time

from livescore import settings
from livescore.constants import E_BALL, E_FLAG, E_PEN_OK
from livescore.core import text as txt
from livescore.core.log import log_line
from livescore.espn import client as espn_client
from livescore.espn import parser as espn_parser
from livescore.match import formatting as fmt
from livescore.match import media, stats_job
from livescore.match.context import MatchContext, Flow
from livescore.state import gist
from livescore.telegram import api as tg


def handle_finish(ctx: MatchContext) -> Flow | None:
    """Fine partita: messaggio finale, statistiche e chiusura."""
    # --- Fine partita ---
    comp_state_espn = (
        ctx.data.get("header", {}).get("competitions", [{}])[0]
            .get("status", {}).get("type", {}).get("state", "")
    )
    _pen_deciso = False
    if ctx.status == "PEN" and comp_state_espn != "post":
        _hp_check, _ap_check = espn_parser._rigori_icone(ctx.data, ctx.events, ctx.home_id, ctx.away_id,
                                              ctx.home_name_raw, ctx.away_name_raw)
        _tot_check = len(_hp_check) + len(_ap_check)
        if (espn_parser._shootout_deciso(_hp_check, _ap_check)
                and ctx.state.get("penalties_count", 0) >= _tot_check):
            # Gate penalties_count: l'ultimo messaggio RIGORI deve essere
            # stato DAVVERO consegnato prima di chiudere (se l'invio è
            # fallito il contatore è indietro → si riprova al prossimo
            # ciclo, il messaggio non va perso con lo spegnimento).
            # Doppia conferma (~12s) contro dati ESPN transitoriamente
            # sballati: la chiusura anticipata è irreversibile.
            ctx.state["_pen_deciso_seen"] = ctx.state.get("_pen_deciso_seen", 0) + 1
            if ctx.state["_pen_deciso_seen"] >= 2:
                _pen_deciso = True
                log_line(
                    "EVENT",
                    "MATCH",
                    f"Rigori decisi | {_hp_check.count(E_PEN_OK)}-{_ap_check.count(E_PEN_OK)}; "
                    "non attendo lo stato post di ESPN",
                )
        else:
            ctx.state["_pen_deciso_seen"] = 0

    is_finished = (
        ctx.status in ("FT", "AET") or
        (ctx.status == "PEN" and comp_state_espn == "post") or
        (ctx.status == "PEN" and _pen_deciso)
    )
    if (
        is_finished
        and isinstance(
            ctx.state.get("pending_goal_cancellation"),
            dict,
        )
    ):
        if not ctx.state.get("_ft_wait_cancel_logged"):
            try:
                _cancel_left = max(
                    0,
                    int(
                        ctx.state[
                            "pending_goal_cancellation"
                        ].get("confirm_at", 0)
                    )
                    - int(time.time()),
                )
            except (TypeError, ValueError):
                _cancel_left = 0

            log_line(
                "WAIT",
                "MATCH",
                f"Fine partita con possibile GOAL ANNULLATO "
                f"in verifica | circa {_cancel_left}s",
            )
            ctx.state["_ft_wait_cancel_logged"] = True

        time.sleep(ctx.sleep_time)
        return Flow.CONTINUE

    if is_finished:
        # Se un gol è ancora in sospeso (invio fallito per timeout in
        # QUESTO ciclo, il blocco gol gira prima di qui) NON chiudere subito:
        # ritenta qualche ciclo così il messaggio del gol non si perde.
        # Cap di sicurezza per non restare appesi se Telegram è giù a lungo.
        _goal_pending = (
            "FT" not in ctx.state["sent_periods"]
            and ctx.state.get("goals_detected", 0) < (ctx.g_home + ctx.g_away)
        )
        if _goal_pending:
            _retries = ctx.state.get("ft_pending_goal_retries", 0)
            if _retries < 5:
                ctx.state["ft_pending_goal_retries"] = _retries + 1
                ctx.state_changed = True
                log_line(
                    "RETRY",
                    "MATCH",
                    f"Partita finita con GOAL in sospeso | "
                    f"{ctx.state.get('goals_detected', 0)}/{ctx.g_home + ctx.g_away} | tentativo {_retries + 1}/5",
                )
                time.sleep(ctx.sleep_time)
                return Flow.CONTINUE
            log_line("ERROR", "MATCH", "GOAL in sospeso non inviato dopo 5 tentativi; chiusura forzata")

        if "FT" not in ctx.state["sent_periods"]:
            # Raggruppa i gol per squadra e per giocatore (con suffisso tipo)
            # Struttura: { team_id: { "chiave_giocatore": {"label": str, "minutes": [int]} } }
            from collections import OrderedDict
            def _build_scorers_list(team_id):
                """Restituisce lista di stringhe tipo '25', 43' B. Varga' per una squadra."""
                grouped = OrderedDict()  # chiave: (player_name, suffix)
                for e in ctx.events:
                    if e["type"] not in ("goal", "own goal", "penalty goal"):
                        continue
                    if fmt.goal_scoring_team_id(e, ctx.home_id, ctx.away_id) != team_id:
                        continue
                    ps = txt.fmt_player(e["player_name"])
                    if e["type"] == "own goal":
                        suffix = " (Autogol)"
                    else:
                        suffix = ""          # i rigori contano come gol normali
                    key = (ps, suffix)
                    if key not in grouped:
                        grouped[key] = []
                    # Usa minute_disp per preservare il formato recupero
                    # (es. "90+6" invece di 96). Fallback all'intero.
                    grouped[key].append(e.get("minute_disp") or str(e["minute"]))
                result = []
                for (ps, suffix), minutes in grouped.items():
                    mins_str = ", ".join(f"{m}'" for m in minutes)
                    result.append(f"{mins_str} {ps}{suffix}")
                return result

            home_scorers = _build_scorers_list(ctx.home_id)
            away_scorers = _build_scorers_list(ctx.away_id)

            if home_scorers or away_scorers:
                parts = []
                if home_scorers:
                    parts.append(", ".join(home_scorers))
                if away_scorers:
                    parts.append(", ".join(away_scorers))
                scorers_line = f"{E_BALL} <i>{' // '.join(parts)}</i>\n"
            else:
                scorers_line = ""

            has_shootout = (
                "ET_END_PENS" in ctx.state["sent_periods"] or
                ctx.status == "PEN" or
                len(ctx.data.get("shootout", [])) > 0
            )
            if has_shootout:
                _hp_icons, _ap_icons = espn_parser._rigori_icone(ctx.data, ctx.events, ctx.home_id, ctx.away_id,
                                                     ctx.home_name_raw, ctx.away_name_raw)
                home_pen_goals = _hp_icons.count(E_PEN_OK)
                away_pen_goals = _ap_icons.count(E_PEN_OK)
                if home_pen_goals > 0 or away_pen_goals > 0:
                    if home_pen_goals > away_pen_goals:
                        pen_score_str = (
                            f"<b>{ctx.home_name} {ctx.g_home} ({home_pen_goals})</b>-({away_pen_goals}) {ctx.g_away} {ctx.away_name}"
                        )
                    elif away_pen_goals > home_pen_goals:
                        pen_score_str = (
                            f"{ctx.home_name} {ctx.g_home} ({home_pen_goals})-<b>({away_pen_goals}) {ctx.g_away} {ctx.away_name}</b>"
                        )
                    else:
                        pen_score_str = (
                            f"{ctx.home_name} {ctx.g_home} ({home_pen_goals})-({away_pen_goals}) {ctx.g_away} {ctx.away_name}"
                        )
                    ctx.score_str = pen_score_str

            msg_finale = f"<b>FINE PARTITA {E_FLAG}</b>\n\n{ctx.score_str}\n{scorers_line}\n{ctx.e_comp} {ctx.hashtag}"

            # Supplementari giocati: FINE REGOLAMENTARI inviato solo quando si va ai supplementari.
            went_extra_time = "2H_END" in ctx.state["sent_periods"] or ctx.status in ("ET", "AET")

            ft_sent = media.send_phase_message(msg_finale, kind='full', data_espn=ctx.data,
                home_id=ctx.home_id, away_id=ctx.away_id, home_name=ctx.home_name_raw, away_name=ctx.away_name_raw,
                league_slug=ctx.league_slug, league_name=ctx.league_name,
                home_goals=ctx.g_home, away_goals=ctx.g_away,
                shootout=(home_pen_goals, away_pen_goals) if has_shootout else None,
                extra_time=went_extra_time and not has_shootout) is not None

            if not ft_sent:
                log_line("RETRY", "TELEGRAM", "FINE PARTITA non inviata; nuovo tentativo al prossimo ciclo")
                time.sleep(ctx.sleep_time)
                return Flow.CONTINUE

            log_line("EVENT", "MATCH", f"FINE PARTITA | {ctx.home_name} {ctx.g_home}-{ctx.g_away} {ctx.away_name} | Telegram inviato")
            # Persisti SUBITO: se il bot muore durante l'attesa delle stats,
            # al riavvio il messaggio finale non verrà reinviato.
            ctx.state["sent_periods"].append("FT")
            gist.salva_stato_su_gist(ctx.state)
            ctx.state_changed = True

        # --- Stats fine partita: 5 minuti dopo il messaggio finale ---
        # (attesa "a fette": la partita è finita, non c'è altro da monitorare)
        if stats_job.stats_eligible(ctx.home_id, ctx.away_id, ctx.league_slug, ctx.league_name) and "FT" not in ctx.state["sent_stats"]:
            log_line("WAIT", "STATS", f"FINE PARTITA | generazione tra {settings.STATS_DELAY_SECONDS}s")
            for _ in range(settings.STATS_DELAY_SECONDS // 5):
                time.sleep(5)
            data_fresh = espn_client.fetch_evento(ctx.event_id, ctx.league_slug) or ctx.data
            _ftp_h, _ftp_a = espn_parser._rigori_icone(data_fresh, ctx.events, ctx.home_id, ctx.away_id,
                                           ctx.home_name_raw, ctx.away_name_raw)
            ft_pen_home = _ftp_h.count(E_PEN_OK)
            ft_pen_away = _ftp_a.count(E_PEN_OK)
            png_path = stats_job.recupera_e_genera_stats_html(data_fresh, ctx.home_id, ctx.away_id,
                                                     ctx.home_name_raw, ctx.away_name_raw, ctx.g_home, ctx.g_away,
                                                     "FT", ctx.league_name, league_slug=ctx.league_slug,
                                                     pen_home=ft_pen_home, pen_away=ft_pen_away,
                                                     event_id=ctx.event_id)
            # Il bot sta per spegnersi: niente "prossimo ciclo" che possa
            # ritentare da solo, quindi ritento qui sul posto prima di
            # rinunciare, invece di segnare le stats come inviate a prescindere.
            ft_stats_ok = False
            for _attempt in range(5):
                if tg.send_telegram_stats_photo(png_path, "FT", f"{ctx.e_comp} {ctx.hashtag}"):
                    ft_stats_ok = True
                    break
                log_line("RETRY", "STATS", f"FINE PARTITA non inviate | tentativo {_attempt + 1}/5 | attesa 10s")
                time.sleep(10)
            if ft_stats_ok:
                log_line("OK", "STATS", "FINE PARTITA | foto Telegram inviata")
                ctx.state["sent_stats"].append("FT")
            else:
                log_line("ERROR", "STATS", "FINE PARTITA non inviate dopo 5 tentativi; proseguo con lo spegnimento")
            gist.salva_stato_su_gist(ctx.state)
            ctx.state_changed = True

        ctx.state["_reset_done"] = True
        gist.resetta_gist()
        log_line("STOP", "SYSTEM", f"Live Score terminato | {ctx.home_name} {ctx.g_home}-{ctx.g_away} {ctx.away_name}")
        sys.exit(0)
