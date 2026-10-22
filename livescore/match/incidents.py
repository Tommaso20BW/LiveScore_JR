"""Cartellini e rigori sbagliati."""

from __future__ import annotations

from livescore import settings
from livescore.constants import E_EXIT, E_KICK, E_PEN_KO, E_RED, JUVE_ID
from livescore.core import leagues
from livescore.core import text as txt
from livescore.core.log import log_line
from livescore.match import media
from livescore.match.context import MatchContext
from livescore.telegram import api as tg


def _failpen_gia_inviato(state: dict, e: dict) -> bool:
    """Dedup rigori sbagliati tollerante alla correzione del minuto da parte
    di ESPN (es. 44' → 45'+1): stesso giocatore + stesso esito entro ±3'."""
    for rec in state.get("sent_failed_penalties", []):
        if isinstance(rec, str):
            # Retrocompatibilità con il vecchio formato stringa
            if rec == f"failpen_{e['minute']}_{e['player_name']}".replace(" ", "_"):
                return True
            continue
        if rec.get("uid") and e.get("uid"):
            if rec["uid"] == e["uid"]:
                return True
            continue
        if (rec.get("player") == e["player_name"]
                and rec.get("type") == e["type"]
                and abs(int(rec.get("minute", 0)) - e["minute"]) <= 3):
            return True
    return False


def announce_red_cards(ctx: MatchContext) -> None:
    """Cartellini rossi e doppie ammonizioni."""
    # --- Cartellini rossi / doppio giallo ---
    for e in ctx.events:
        if e["type"] in ("red card", "second yellow card"):
            p_name  = txt.fmt_player(e["player_name"])
            card_id = f"card_{e['player_name']}".replace(" ", "_")
            if card_id not in ctx.state["sent_cards"]:
                is_second_yellow = e["type"] == "second yellow card"
                team_name = ctx.home_name if e["team_id"] == ctx.home_id else ctx.away_name
                label = f"ROSSO {team_name.upper()}" if is_second_yellow else f"ROSSO {team_name.upper()}"
                msg_id = tg.send_telegram_get_id(
                    f"<b>{label} · {e['minute']}' {E_RED}</b>\n\n"
                    f"{E_EXIT} <i>{p_name}</i>\n\n{ctx.e_comp} {ctx.hashtag}"
                )
                if msg_id:
                    log_line("EVENT", "MATCH", f"{label} {e['minute']}' | {p_name} | Telegram inviato")
                    ctx.state["sent_cards"].append(card_id)
                    ctx.state_changed = True


def announce_failed_penalties(ctx: MatchContext) -> None:
    """Rigori sbagliati o parati durante il gioco."""
    # --- Rigori sbagliati (solo durante il gioco: nella lotteria dei
    # rigori l'esito di ogni calcio lo annuncia già il blocco RIGORI) ---
    for e in ctx.events:
        regular_penalty = (
            ctx.status not in ("PEN", "BREAK_PEN")
            and e["type"] in ("penalty missed", "penalty saved")
        )
        shootout_save = e["type"] == "shootout saved"
        if regular_penalty or shootout_save:
            if _failpen_gia_inviato(ctx.state, e):
                continue
            team_name = ctx.home_name if e["team_id"] == ctx.home_id else ctx.away_name
            opponent_id = ctx.away_id if str(ctx.home_id) == JUVE_ID else (
                ctx.home_id if str(ctx.away_id) == JUVE_ID else ""
            )
            is_juve_save = (
                e["type"] in ("penalty saved", "shootout saved")
                and bool(opponent_id)
                and str(e["team_id"]) == str(opponent_id)
            )
            goalkeeper_name = (
                media.trova_portiere_juve(ctx.data, e.get("assist_name", ""))
                if is_juve_save else ""
            )
            rendered_saved = None
            if goalkeeper_name:
                rendered_saved_retry = (lambda: media.prepara_grafica_parata_rigore(
                    data_espn=ctx.data,
                    penalty_event=e,
                    goalkeeper_name=goalkeeper_name,
                    minute=e.get("minute_disp", e["minute"]),
                    home_name=ctx.home_name_raw,
                    away_name=ctx.away_name_raw,
                    home_id=ctx.home_id,
                    away_id=ctx.away_id,
                    home_goals=ctx.g_home,
                    away_goals=ctx.g_away,
                    event_key=f"{ctx.event_id}|saved|{e.get('uid', '')}",
                    league_slug=ctx.league_slug,
                    league_name=ctx.league_name,
                )) if (settings.GOAL_GRAPHICS_ENABLED and not leagues.is_friendly_competition(ctx.league_slug, ctx.league_name)) else None
                rendered_saved = rendered_saved_retry() if rendered_saved_retry else None
                penalty_text = (
                    f"<b>RIGORE PARATO · {e['minute']}' {E_KICK}</b>\n\n"
                    f"🧤 <i>{txt.fmt_player(goalkeeper_name)}</i>\n"
                    f"{E_PEN_KO} <i>{txt.fmt_player(e['player_name'])}</i>\n\n"
                    f"{ctx.e_comp} {ctx.hashtag}"
                )
                msg_id, _ = tg.send_telegram_saved_get_id(
                    penalty_text,
                    rendered_saved.png if rendered_saved else None,
                    retry_factory=rendered_saved_retry,
                )
            else:
                # Nella lotteria il mancato riconoscimento del portiere
                # non crea un doppione: resta il messaggio RIGORI aggregato.
                if shootout_save:
                    continue
                msg_id = tg.send_telegram_get_id(
                    f"<b>RIGORE SBAGLIATO {team_name.upper()} · {e['minute']}' {E_KICK}</b>\n\n"
                    f"{E_PEN_KO} <i>{txt.fmt_player(e['player_name'])}</i>\n\n"
                    f"{ctx.e_comp} {ctx.hashtag}"
                )
            if msg_id:
                label = "RIGORE PARATO" if goalkeeper_name else "RIGORE SBAGLIATO"
                log_line("EVENT", "MATCH", f"{label} {team_name.upper()} {e['minute']}' | {txt.fmt_player(e['player_name'])} | Telegram inviato")
                ctx.state["sent_failed_penalties"].append({
                    "player": e["player_name"],
                    "type":   e["type"],
                    "minute": e["minute"],
                    "uid":    e.get("uid", ""),
                })
                ctx.state_changed = True
