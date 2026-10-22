"""Gol: rilevamento, annullamenti VAR, recupero e correzioni."""

from __future__ import annotations

import time

from livescore import settings
from livescore.constants import E_CANCEL, E_MIC, JUVE_ID
from livescore.core import leagues, team_names
from livescore.core import text as txt
from livescore.core.log import log_line
from livescore.espn import client as espn_client
from livescore.espn import parser as espn_parser
from livescore.match import formatting as fmt
from livescore.match import media
from livescore.match.context import MatchContext, Flow
from livescore.telegram import api as tg

# Attesa prima di annunciare un gol annullato (VAR), in secondi.
CANCEL_CONFIRM_SECONDS = 15


def catch_up_goals(ctx: MatchContext) -> None:
    """Partita gia' in corso con stato vuoto: annuncia i gol mancanti."""
    # --- Catchup: partita già in corso con gist vuoto ---
    if ctx.state["goals_detected"] == 0 and (ctx.g_home + ctx.g_away) > 0 and not ctx.state.get("goal_messages"):
        _seen_uids = set()
        _seen_min_player = set()
        _deduped = []
        for e in ctx.events:
            if e["type"] in ("goal", "own goal", "penalty goal"):
                uid = e.get("uid", f"{e['minute']}_{e.get('player_name','')}")
                min_player_key = f"{e['minute']}_{e.get('player_name','').strip().lower()}"
                if uid not in _seen_uids and min_player_key not in _seen_min_player:
                    _seen_uids.add(uid)
                    _seen_min_player.add(min_player_key)
                    _deduped.append(e)
        goal_events_all = sorted(_deduped, key=lambda x: x["minute"])
        ch, ca = 0, 0
        for ge in goal_events_all:
            if ch + ca >= ctx.g_home + ctx.g_away:
                break
            actual_tid = fmt.goal_scoring_team_id(ge, ctx.home_id, ctx.away_id)
            if actual_tid == ctx.home_id:
                ch += 1
            else:
                ca += 1

            p_name = ge.get("player_name", "")
            a_name = ge.get("assist_name", "")
            scorer_line, assist_line = fmt.goal_player_lines(
                p_name, a_name, ge["type"], actual_tid
            )

            if actual_tid == ctx.home_id:
                goal_score = f"<b>{ctx.home_name} {ch}</b>-{ca} {ctx.away_name}"
            else:
                goal_score = f"{ctx.home_name} {ch}-<b>{ca} {ctx.away_name}</b>"

            goal_text = f"<b>GOAL · {ge['minute']}\' {E_MIC}</b>\n\n{goal_score}\n{scorer_line}{assist_line}\n{ctx.e_comp} {ctx.hashtag}"
            goal_key  = f"{ch}_{ca}"

            rendered_goal_retry = (lambda: media.prepara_grafica_goal(
                data_espn=ctx.data,
                scorer_name=p_name,
                goal_type=ge["type"],
                scoring_team_id=actual_tid,
                minute=ge["minute"],
                home_name=ctx.home_name_raw,
                away_name=ctx.away_name_raw,
                home_id=ctx.home_id,
                away_id=ctx.away_id,
                home_goals=ch,
                away_goals=ca,
                league_slug=ctx.league_slug,
                league_name=ctx.league_name,
                event_key=f"{ctx.event_id}|{goal_key}",
            )) if (settings.GOAL_GRAPHICS_ENABLED and not leagues.is_friendly_competition(ctx.league_slug, ctx.league_name) and str(actual_tid) == JUVE_ID and bool(p_name) and ge["type"] in ('goal', 'own goal', 'penalty goal')) else None
            rendered_goal = rendered_goal_retry() if rendered_goal_retry else None
            msg_id, sent_as_photo = tg.send_telegram_goal_get_id(
                goal_text,
                rendered_goal.png if rendered_goal else None,
                retry_factory=rendered_goal_retry,
            )
            if not msg_id:
                # Invio non riuscito: interrompo il recupero. Annullo
                # l'incremento di questo gol (non annunciato) e lascio che sia
                # il rilevamento live a riprovare i gol rimanenti.
                log_line("RETRY", "TELEGRAM", f"GOAL {ge['minute']}' non inviato | {ctx.home_name} {ch}-{ca} {ctx.away_name}")
                if actual_tid == ctx.home_id:
                    ch -= 1
                else:
                    ca -= 1
                break
            log_line("EVENT", "MATCH", f"GOAL {ge['minute']}' | {ctx.home_name} {ch}-{ca} {ctx.away_name} | Telegram inviato")
            ctx.state.setdefault("goal_messages", {})[goal_key] = {
                "msg_id":    msg_id,
                "scorer":    p_name,
                "assist":    a_name,
                "minute":    ge["minute"],
                "type":      ge["type"],
                "home_n":    ctx.home_name,
                "away_n":    ctx.away_name,
                "g_home":    ch,
                "g_away":    ca,
                "home_id":   ctx.home_id,
                "away_id":   ctx.away_id,
                "score_tid": actual_tid,
                "is_photo":  sent_as_photo,
                "graphic_kit": rendered_goal.kit if rendered_goal and sent_as_photo else None,
            }
            time.sleep(2)

        # Avanza solo fino ai gol realmente annunciati (ch/ca): se un invio
        # è fallito, i gol mancanti li recupera il rilevamento live.
        ctx.state["goals_detected"]  = ch + ca
        ctx.state["prev_home_goals"] = ch
        ctx.state["prev_away_goals"] = ca
        ctx.state_changed = True


def handle_goals(ctx: MatchContext) -> Flow | None:
    """Rileva nuovi gol, annullamenti VAR e punteggi instabili."""
    # --- Rilevamento goal ---
    # IMPORTANTE: questo blocco sta PRIMA di is_finished (fix applicato).
    # Se un gol arriva nello stesso ciclo in cui la partita passa a FT,
    # va annunciato qui prima che il blocco is_finished chiami sys.exit(0)
    # e spenga il bot — altrimenti il gol (es. 4-1 al 90') non parte mai.
    total_goals_now = ctx.g_home + ctx.g_away
    prev_home = ctx.state.get("prev_home_goals", 0)
    prev_away = ctx.state.get("prev_away_goals", 0)

    if total_goals_now > ctx.state["goals_detected"]:
        time.sleep(settings.GOAL_CONFIRM_SECONDS)
        data_confirm = espn_client.fetch_evento(ctx.event_id, ctx.league_slug) or ctx.data
        try:
            competitors_confirm = data_confirm["header"]["competitions"][0]["competitors"]
        except Exception:
            competitors_confirm = ctx.competitors
        _, _, _, _, g_home_c, g_away_c = espn_parser.parse_score(competitors_confirm)
        if g_home_c + g_away_c != total_goals_now:
            log_line("WAIT", "MATCH", f"Punteggio instabile | {ctx.g_home}-{ctx.g_away} -> {g_home_c}-{g_away_c}; attendo conferma")
            time.sleep(ctx.sleep_time)
            return Flow.CONTINUE
        ctx.data   = data_confirm
        ctx.g_home = g_home_c
        ctx.g_away = g_away_c
        ctx.events = espn_parser.parse_events(ctx.data, ctx.home_name_raw, ctx.away_name_raw, ctx.home_id, ctx.away_id)
        ctx.score_str = fmt.build_score_str(ctx.home_name, ctx.away_name, ctx.g_home, ctx.g_away)

        goal_events = [e for e in ctx.events
                       if e["type"] in ("goal", "own goal", "penalty goal")]

        # Quale squadra ha segnato.
        # Di norma lo si capisce dall'aumento rispetto all'ultimo punteggio
        # annunciato (prev_*). Se però lo stato salvato è incoerente
        # (prev_* gia avanti, p.es. dopo un riavvio del job), questi confronti
        # fallirebbero e il gol verrebbe perso in silenzio: in quel caso si
        # ricava il marcatore dall'ultimo evento del feed ESPN.
        if ctx.g_home > prev_home:
            scoring_tid = ctx.home_id
        elif ctx.g_away > prev_away:
            scoring_tid = ctx.away_id
        else:
            _gevs = sorted(goal_events, key=lambda x: x["minute"])
            if _gevs:
                _last_ev = _gevs[-1]
                scoring_tid = fmt.goal_scoring_team_id(
                    _last_ev, ctx.home_id, ctx.away_id
                )
            else:
                scoring_tid = ctx.home_id if ctx.g_home >= ctx.g_away else ctx.away_id
            log_line("WARN", "MATCH", f"Punteggio incoerente | prima={prev_home}-{prev_away} | ora={ctx.g_home}-{ctx.g_away}; marcatore dedotto dal feed")

        # Flag: True solo se il gol è stato realmente annunciato (ora o in passato).
        # Il contatore avanzerà SOLO in quel caso.
        goal_announced = False

        if scoring_tid:
            candidates = sorted(
                [
                    e for e in goal_events
                    if fmt.goal_scoring_team_id(e, ctx.home_id, ctx.away_id) == scoring_tid
                ],
                key=lambda x: (x["minute"], x.get("seq", 0)),
            )

            expected_count = ctx.g_home if scoring_tid == ctx.home_id else ctx.g_away

            last = candidates[expected_count - 1] if len(candidates) >= expected_count else (candidates[-1] if candidates else None)

            if last:
                player_name = last.get("player_name", "")
                assist_name = last.get("assist_name", "")
                goal_minute = last.get("minute_disp", str(last.get("minute", ctx.elapsed)))
                goal_type   = last.get("type", "goal")
            else:
                # Feed ESPN incompleto: gol rilevato dal punteggio ma nessun
                # evento marcatore associato. Annuncio comunque per non bloccare
                # il ciclo (altrimenti goals_detected non avanza mai).
                log_line("WARN", "ESPN", "GOAL rilevato senza marcatore; invio provvisorio")
                player_name = ""
                assist_name = ""
                goal_minute = ctx.elapsed
                goal_type   = "goal"

            actual_scoring_tid = scoring_tid
            scorer_line, assist_line = fmt.goal_player_lines(
                player_name,
                assist_name,
                goal_type,
                actual_scoring_tid,
            )

            if actual_scoring_tid == ctx.home_id:
                goal_score = f"<b>{ctx.home_name} {ctx.g_home}</b>-{ctx.g_away} {ctx.away_name}"
            else:
                goal_score = f"{ctx.home_name} {ctx.g_home}-<b>{ctx.g_away} {ctx.away_name}</b>"

            goal_text = f"<b>GOAL · {goal_minute}' {E_MIC}</b>\n\n{goal_score}\n{scorer_line}{assist_line}\n{ctx.e_comp} {ctx.hashtag}"
            goal_key = f"{ctx.g_home}_{ctx.g_away}"

            if ctx.state.get("goal_messages", {}).get(goal_key, {}).get("msg_id"):
                # Gol già annunciato davvero in passato: duplicato corretto,
                # il contatore può avanzare.
                goal_announced = True
            else:
                _scorer_log = f" {txt.fmt_player(player_name)}" if player_name else " (marcatore in attesa)"
                _assist_log = f" | assist: {txt.fmt_player(assist_name)}" if assist_name and assist_name != player_name else ""
                rendered_goal_retry = (lambda: media.prepara_grafica_goal(
                    data_espn=ctx.data,
                    scorer_name=player_name,
                    goal_type=goal_type,
                    scoring_team_id=actual_scoring_tid,
                    minute=goal_minute,
                    home_name=ctx.home_name_raw,
                    away_name=ctx.away_name_raw,
                    home_id=ctx.home_id,
                    away_id=ctx.away_id,
                    home_goals=ctx.g_home,
                    away_goals=ctx.g_away,
                    league_slug=ctx.league_slug,
                    league_name=ctx.league_name,
                    event_key=f"{ctx.event_id}|{goal_key}",
                )) if (settings.GOAL_GRAPHICS_ENABLED and not leagues.is_friendly_competition(ctx.league_slug, ctx.league_name) and str(actual_scoring_tid) == JUVE_ID and bool(player_name) and goal_type in ('goal', 'own goal', 'penalty goal')) else None
                rendered_goal = rendered_goal_retry() if rendered_goal_retry else None
                msg_id, sent_as_photo = tg.send_telegram_goal_get_id(
                    goal_text,
                    rendered_goal.png if rendered_goal else None,
                    retry_factory=rendered_goal_retry,
                )
                if msg_id:
                    ctx.state.setdefault("goal_messages", {})[goal_key] = {
                        "msg_id":    msg_id,
                        "scorer":    player_name,
                        "assist":    assist_name,
                        "minute":    goal_minute,
                        "type":      goal_type,
                        "home_n":    ctx.home_name,
                        "away_n":    ctx.away_name,
                        "g_home":    ctx.g_home,
                        "g_away":    ctx.g_away,
                        "home_id":   ctx.home_id,
                        "away_id":   ctx.away_id,
                        "score_tid": actual_scoring_tid,
                        "is_photo":  sent_as_photo,
                        "graphic_kit": rendered_goal.kit if rendered_goal and sent_as_photo else None,
                    }
                    ctx.state_changed = True
                    goal_announced = True
                    log_line("EVENT", "MATCH", f"GOAL{_scorer_log}{_assist_log} | {ctx.home_name} {ctx.g_home}-{ctx.g_away} {ctx.away_name} | Telegram inviato")
                else:
                    # Invio NON riuscito: non avanzo il contatore così al ciclo
                    # successivo il bot rientra qui e riprova (il gol non si perde).
                    log_line("RETRY", "TELEGRAM", f"GOAL non inviato | {ctx.home_name} {ctx.g_home}-{ctx.g_away} {ctx.away_name}; nuovo tentativo al prossimo ciclo")

        # Il contatore avanza SOLO se il gol è stato davvero annunciato.
        # Se l'invio è fallito (o scoring_tid assente), lo stato resta indietro
        # e il gol verrà ritentato, invece di sparire.
        if goal_announced:
            ctx.state["goals_detected"]  = total_goals_now
            ctx.state["prev_home_goals"] = ctx.g_home
            ctx.state["prev_away_goals"] = ctx.g_away
            ctx.state_changed = True

    elif total_goals_now < ctx.state["goals_detected"]:
        # ======================================================
        # GOAL ANNULLATO — conferma non bloccante
        # ======================================================
        # La diminuzione del punteggio viene osservata per CANCEL_CONFIRM_SECONDS secondi,
        # ma il normale polling continua: ESPN, eventi, kit e callback
        # restano attivi. Il timer è persistito nel Gist e sopravvive
        # quindi anche a un riavvio del workflow.
        _cancel_now = int(time.time())
        pending_cancel = ctx.state.get("pending_goal_cancellation")
        _baseline_total = int(ctx.state.get("goals_detected", 0))

        if not isinstance(pending_cancel, dict):
            pending_cancel = {
                "baseline_total": _baseline_total,
                "baseline_home": int(ctx.state.get("prev_home_goals", 0)),
                "baseline_away": int(ctx.state.get("prev_away_goals", 0)),
                "candidate_home": int(ctx.g_home),
                "candidate_away": int(ctx.g_away),
                "confirm_at": _cancel_now + CANCEL_CONFIRM_SECONDS,
            }
            ctx.state["pending_goal_cancellation"] = pending_cancel
            ctx.state_changed = True
            log_line(
                "WAIT",
                "MATCH",
                f"Possibile GOAL ANNULLATO | {ctx.g_home}-{ctx.g_away}; "
                f"conferma non bloccante tra {CANCEL_CONFIRM_SECONDS}s",
            )
        else:
            try:
                _baseline_total = int(
                    pending_cancel.get(
                        "baseline_total",
                        ctx.state.get("goals_detected", 0),
                    )
                )
            except (TypeError, ValueError):
                _baseline_total = int(ctx.state.get("goals_detected", 0))

            try:
                _candidate_home = int(
                    pending_cancel.get("candidate_home", ctx.g_home)
                )
                _candidate_away = int(
                    pending_cancel.get("candidate_away", ctx.g_away)
                )
            except (TypeError, ValueError):
                _candidate_home = int(ctx.g_home)
                _candidate_away = int(ctx.g_away)

            if (
                int(ctx.g_home),
                int(ctx.g_away),
            ) != (
                _candidate_home,
                _candidate_away,
            ):
                pending_cancel["candidate_home"] = int(ctx.g_home)
                pending_cancel["candidate_away"] = int(ctx.g_away)
                pending_cancel["confirm_at"] = _cancel_now + CANCEL_CONFIRM_SECONDS
                ctx.state_changed = True
                log_line(
                    "WAIT",
                    "MATCH",
                    f"GOAL ANNULLATO: candidato cambiato in "
                    f"{ctx.g_home}-{ctx.g_away}; nuova conferma tra {CANCEL_CONFIRM_SECONDS}s",
                )

            try:
                _confirm_at = int(pending_cancel.get("confirm_at", 0))
            except (TypeError, ValueError):
                _confirm_at = 0

            if _cancel_now >= _confirm_at:
                data_cancel = espn_client.fetch_evento(ctx.event_id, ctx.league_slug) or ctx.data
                try:
                    competitors_cancel = data_cancel[
                        "header"
                    ]["competitions"][0]["competitors"]
                except Exception:
                    competitors_cancel = ctx.competitors

                (
                    _,
                    _,
                    _,
                    _,
                    g_home_c,
                    g_away_c,
                ) = espn_parser.parse_score(competitors_cancel)

                try:
                    _candidate_home = int(
                        pending_cancel.get("candidate_home", ctx.g_home)
                    )
                    _candidate_away = int(
                        pending_cancel.get("candidate_away", ctx.g_away)
                    )
                except (TypeError, ValueError):
                    _candidate_home = int(ctx.g_home)
                    _candidate_away = int(ctx.g_away)

                _confirmed_pair = (int(g_home_c), int(g_away_c))
                _candidate_pair = (_candidate_home, _candidate_away)

                if (
                    g_home_c + g_away_c < _baseline_total
                    and _confirmed_pair != _candidate_pair
                ):
                    pending_cancel["candidate_home"] = int(g_home_c)
                    pending_cancel["candidate_away"] = int(g_away_c)
                    pending_cancel["confirm_at"] = _cancel_now + CANCEL_CONFIRM_SECONDS
                    ctx.state_changed = True
                    log_line(
                        "WAIT",
                        "MATCH",
                        f"GOAL ANNULLATO: ESPN ora mostra "
                        f"{g_home_c}-{g_away_c}; nuova conferma tra {CANCEL_CONFIRM_SECONDS}s",
                    )

                elif g_home_c + g_away_c < _baseline_total:
                    ctx.data = data_cancel
                    ctx.g_home = g_home_c
                    ctx.g_away = g_away_c
                    ctx.events = espn_parser.parse_events(
                        ctx.data,
                        ctx.home_name_raw,
                        ctx.away_name_raw,
                        ctx.home_id,
                        ctx.away_id,
                    )
                    ctx.score_str = fmt.build_score_str(
                        ctx.home_name,
                        ctx.away_name,
                        ctx.g_home,
                        ctx.g_away,
                    )
                    cancel_text = (
                        f"<b>GOAL ANNULLATO {E_CANCEL}</b>\n\n"
                        f"{ctx.score_str}\n\n"
                        f"{ctx.e_comp} {ctx.hashtag}"
                    )
                    cancel_msg_id = tg.send_telegram_get_id(cancel_text)

                    if cancel_msg_id:
                        log_line(
                            "EVENT",
                            "MATCH",
                            "GOAL ANNULLATO | Telegram inviato",
                        )
                        ctx.state["cancel_msg_id"] = cancel_msg_id
                    else:
                        log_line(
                            "RETRY",
                            "TELEGRAM",
                            "GOAL ANNULLATO non inviato; "
                            "nuovo tentativo al prossimo ciclo",
                        )
                        ctx.state["pending_goal_annullato"] = cancel_text

                    keys_to_remove = [
                        key
                        for key in ctx.state.get("goal_messages", {})
                        if (
                            int(key.split("_")[0])
                            + int(key.split("_")[1])
                            > g_home_c + g_away_c
                        )
                    ]
                    for key in keys_to_remove:
                        ctx.state["goal_messages"].pop(key, None)

                    ctx.state["goals_detected"] = g_home_c + g_away_c
                    ctx.state["prev_home_goals"] = g_home_c
                    ctx.state["prev_away_goals"] = g_away_c
                    ctx.state["pending_goal_cancellation"] = None
                    ctx.state.pop("_ft_wait_cancel_logged", None)
                    ctx.state_changed = True

                else:
                    log_line(
                        "INFO",
                        "MATCH",
                        f"Punteggio ripristinato | "
                        f"{g_home_c}-{g_away_c}; "
                        "possibile annullamento scartato",
                    )
                    ctx.data = data_cancel
                    ctx.events = espn_parser.parse_events(
                        ctx.data,
                        ctx.home_name_raw,
                        ctx.away_name_raw,
                        ctx.home_id,
                        ctx.away_id,
                    )
                    ctx.g_home = g_home_c
                    ctx.g_away = g_away_c
                    ctx.score_str = fmt.build_score_str(
                        ctx.home_name,
                        ctx.away_name,
                        ctx.g_home,
                        ctx.g_away,
                    )
                    ctx.state["pending_goal_cancellation"] = None
                    ctx.state.pop("_ft_wait_cancel_logged", None)
                    ctx.state_changed = True

    else:
        # Se ESPN ripristina il totale precedente prima dei 120s,
        # il possibile annullamento viene scartato immediatamente.
        pending_cancel = ctx.state.get("pending_goal_cancellation")
        if isinstance(pending_cancel, dict):
            try:
                _baseline_total = int(
                    pending_cancel.get(
                        "baseline_total",
                        ctx.state.get("goals_detected", 0),
                    )
                )
            except (TypeError, ValueError):
                _baseline_total = int(ctx.state.get("goals_detected", 0))

            if total_goals_now >= _baseline_total:
                log_line(
                    "INFO",
                    "MATCH",
                    f"Punteggio ripristinato/cambiato | "
                    f"{ctx.g_home}-{ctx.g_away}; "
                    "possibile annullamento scartato",
                )
                ctx.state["pending_goal_cancellation"] = None
                ctx.state.pop("_ft_wait_cancel_logged", None)
                ctx.state_changed = True


def fix_scorers(ctx: MatchContext) -> None:
    """Corregge marcatori e assist dei gol gia' annunciati."""
    # --- Correzione marcatori ---
    for goal_key, saved in list(ctx.state.get("goal_messages", {}).items()):
        msg_id = saved.get("msg_id")
        if not msg_id:
            continue

        try:
            gh, ga = map(int, goal_key.split("_"))
        except ValueError:
            continue

        s_home_id = saved.get("home_id", ctx.home_id)
        s_away_id = saved.get("away_id", ctx.away_id)
        s_home_n  = saved.get("home_n", ctx.home_name)
        s_away_n  = saved.get("away_n", ctx.away_name)
        s_tid     = saved.get("score_tid")

        goal_events_all = [e for e in ctx.events if e["type"] in ("goal", "own goal", "penalty goal")]

        if s_tid == s_home_id:
            idx = gh - 1
        else:
            idx = ga - 1

        candidates = sorted(
            [
                e for e in goal_events_all
                if fmt.goal_scoring_team_id(e, s_home_id, s_away_id) == s_tid
            ],
            key=lambda x: (x["minute"], x.get("seq", 0)),
        )

        if idx < 0 or idx >= len(candidates):
            continue

        current = candidates[idx]
        current_scorer = current.get("player_name", "")
        current_assist = current.get("assist_name", "")
        current_type = current.get("type", saved.get("type", "goal"))

        if (txt._norm_name(current_scorer) != txt._norm_name(saved.get("scorer", ""))) or \
           (txt._norm_name(current_assist) != txt._norm_name(saved.get("assist", ""))) or \
           (current_type != saved.get("type", "goal")):

            actual_tid = s_tid
            scorer_line_new, assist_line_new = fmt.goal_player_lines(
                current_scorer,
                current_assist,
                current_type,
                actual_tid,
            )

            if actual_tid == s_home_id:
                goal_score_new = f"<b>{s_home_n} {gh}</b>-{ga} {s_away_n}"
            else:
                goal_score_new = f"{s_home_n} {gh}-<b>{ga} {s_away_n}</b>"

            e_comp_saved = leagues.get_league_emoji(ctx.league_slug)
            hashtag_saved = team_names.build_hashtag(s_home_n, s_away_n)
            _min_disp_new = current.get("minute_disp", str(current["minute"]))
            goal_text_new = f"<b>GOAL · {_min_disp_new}' {E_MIC}</b>\n\n{goal_score_new}\n{scorer_line_new}{assist_line_new}\n{e_comp_saved} {hashtag_saved}"

            changes = []
            if txt._norm_name(current_scorer) != txt._norm_name(saved.get("scorer", "")):
                changes.append(f"marcatore: {saved.get('scorer')} → {current_scorer}")
            if txt._norm_name(current_assist) != txt._norm_name(saved.get("assist", "")):
                old_a = saved.get("assist", "—") or "—"
                new_a = current_assist or "—"
                changes.append(f"assist: {old_a} → {new_a}")
            if current_type != saved.get("type", "goal"):
                changes.append(f"tipo: {saved.get('type', 'goal')} → {current_type}")

            rendered_correction = media.prepara_grafica_goal(
                data_espn=ctx.data,
                scorer_name=current_scorer,
                goal_type=current_type,
                scoring_team_id=actual_tid,
                minute=_min_disp_new,
                home_name=ctx.home_name_raw,
                away_name=ctx.away_name_raw,
                home_id=s_home_id,
                away_id=s_away_id,
                home_goals=gh,
                away_goals=ga,
                league_slug=ctx.league_slug,
                league_name=ctx.league_name,
                event_key=f"{ctx.event_id}|{goal_key}",
            )
            was_photo = bool(saved.get("is_photo"))
            edit_ok, new_msg_id, new_is_photo = tg.replace_corrected_goal_message(
                msg_id,
                was_photo,
                goal_text_new,
                rendered_correction,
            )

            if edit_ok:
                log_line("EDIT", "MATCH", f"GOAL {goal_key} corretto | {', '.join(changes)}")
                ctx.state["goal_messages"][goal_key]["msg_id"]     = new_msg_id
                ctx.state["goal_messages"][goal_key]["scorer"]    = current_scorer
                ctx.state["goal_messages"][goal_key]["assist"]    = current_assist
                ctx.state["goal_messages"][goal_key]["type"]      = current_type
                ctx.state["goal_messages"][goal_key]["score_tid"] = actual_tid
                ctx.state["goal_messages"][goal_key]["is_photo"]  = new_is_photo
                ctx.state["goal_messages"][goal_key]["graphic_kit"] = (
                    rendered_correction.kit
                    if rendered_correction and new_is_photo else None
                )
                ctx.state_changed = True
            else:
                log_line("RETRY", "TELEGRAM", f"Correzione GOAL {goal_key} fallita | {', '.join(changes)}")
