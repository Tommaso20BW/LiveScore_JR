"""Preparazione di ogni ciclo: lettura di ESPN e valori derivati."""

from __future__ import annotations

import sys
import time

from livescore.core import leagues, team_names
from livescore.core import text as txt
from livescore.core.log import log_line
from livescore.espn import client as espn_client
from livescore.espn import parser as espn_parser
from livescore.match import formatting as fmt
from livescore.match.context import MatchContext, Flow
from livescore.state import gist


def prepare_cycle(ctx: MatchContext) -> Flow | None:
    """Legge ESPN e prepara i valori del ciclo (stato, punteggio, nomi, eventi)."""
    if ctx.state.get("_gist_dirty"):
        if not gist.salva_stato_su_gist(ctx.state):
            log_line(
                "WAIT",
                "STATE",
                "Gist non sincronizzato; sospendo nuovi invii "
                "per evitare duplicati",
            )
            time.sleep(ctx.sleep_time)
            return Flow.CONTINUE

    ctx.data = espn_client.fetch_evento(ctx.event_id, ctx.league_slug)
    if not ctx.data:
        time.sleep(10)
        return Flow.CONTINUE

    ctx.status, ctx.elapsed = espn_parser.parse_status(ctx.data)

    try:
        ctx.competitors = ctx.data["header"]["competitions"][0]["competitors"]
    except Exception:
        ctx.competitors = ctx.partita["competitors"]

    ctx.home_id, ctx.away_id, ctx.home_name_raw, ctx.away_name_raw, ctx.g_home, ctx.g_away = espn_parser.parse_score(ctx.competitors)
    ctx.home_name = txt.esc(team_names.translate_team(ctx.home_name_raw))
    ctx.away_name = txt.esc(team_names.translate_team(ctx.away_name_raw))
    ctx.score_str = fmt.build_score_str(ctx.home_name, ctx.away_name, ctx.g_home, ctx.g_away)
    ctx.hashtag   = team_names.build_hashtag(ctx.home_name_raw, ctx.away_name_raw)
    ctx.e_comp    = leagues.get_league_emoji(ctx.league_slug)

    # --- Partita GIÀ conclusa all'avvio → spegni subito, non fare nulla ---
    comp_state_espn = (
        ctx.data.get("header", {}).get("competitions", [{}])[0]
            .get("status", {}).get("type", {}).get("state", "")
    )
    match_finished  = comp_state_espn == "post" or ctx.status in ("FT", "AET")
    never_processed = (
        not ctx.state.get("sent_periods")
        and not ctx.state.get("goal_messages")
        and ctx.state.get("goals_detected", 0) == 0
    )
    if match_finished and never_processed:
        log_line(
            "STOP",
            "MATCH",
            f"Partita già conclusa | {ctx.home_name} {ctx.g_home}-{ctx.g_away} {ctx.away_name}; nessun invio",
        )
        sys.exit(0)

    ctx.events = espn_parser.parse_events(ctx.data, ctx.home_name_raw, ctx.away_name_raw, ctx.home_id, ctx.away_id)

    if "_intro_logged" not in ctx.state:
        log_line(
            "EVENT",
            "MATCH",
            f"Partita trovata | {ctx.league_name} | {ctx.home_name} vs {ctx.away_name} | event_id={ctx.event_id}",
        )
        for raw, translated in ((ctx.home_name_raw, ctx.home_name), (ctx.away_name_raw, ctx.away_name)):
            t = team_names.translate_team(raw)
            in_map = bool(team_names.TEAM_MAP.get(raw) or any(k.lower() == raw.lower() for k in team_names.TEAM_MAP))
            if raw != t:
                log_line("DEBUG", "TEAMS", f"Traduzione | {raw} -> {txt.esc(t)}")
            elif not in_map:
                log_line("DEBUG", "TEAMS", f"Nome ESPN non mappato | {raw}")
        ctx.state["_intro_logged"] = True


    ctx._now_ts = int(time.time())
    if ctx.status != "NS" and ctx.progress_log.should_emit(
        ctx.status, ctx.elapsed, ctx.g_home, ctx.g_away, ctx._now_ts
    ):
        log_line(
            "LIVE",
            "MATCH",
            f"{ctx.status} {ctx.elapsed}' | {ctx.home_name} {ctx.g_home}-{ctx.g_away} {ctx.away_name}",
        )
