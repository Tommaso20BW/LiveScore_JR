"""Operazioni rimandate: statistiche programmate e messaggi da ritentare."""

from __future__ import annotations

from livescore import settings
from livescore.core.log import log_line
from livescore.espn import client as espn_client
from livescore.match import stats_job
from livescore.match.context import MatchContext
from livescore.state import gist
from livescore.telegram import api as tg


def send_due_stats(ctx: MatchContext) -> None:
    """Invia le statistiche programmate la cui attesa e' scaduta."""
    # --- Invio stats programmato (5 min dopo il cambio di stato) ---
    # Coda non bloccante: durante l'attesa il bot continua a rilevare
    # gol, cambi e cartellini. Persistita nel Gist → sopravvive ai crash.
    for _ps in list(ctx.state.get("pending_stats", [])):
        if ctx._now_ts < int(_ps.get("due", 0)):
            continue
        _momento = _ps.get("momento")
        ctx.state["pending_stats"].remove(_ps)
        ctx.state_changed = True
        if (not stats_job.stats_eligible(ctx.home_id, ctx.away_id, ctx.league_slug, ctx.league_name)
                or not _momento or _momento in ctx.state.get("sent_stats", [])):
            continue
        data_fresh = espn_client.fetch_evento(ctx.event_id, ctx.league_slug) or ctx.data
        png_path = stats_job.recupera_e_genera_stats_html(data_fresh, ctx.home_id, ctx.away_id,
                                                 ctx.home_name_raw, ctx.away_name_raw, ctx.g_home, ctx.g_away,
                                                 _momento, ctx.league_name, league_slug=ctx.league_slug,
                                                 event_id=ctx.event_id)
        if tg.send_telegram_stats_photo(png_path, _momento, f"{ctx.e_comp} {ctx.hashtag}"):
            log_line("OK", "STATS", f"{_momento} | foto Telegram inviata")
            ctx.state["sent_stats"].append(_momento)
            gist.salva_stato_su_gist(ctx.state)
        else:
            # Invio non riuscito: rimetto in coda per un nuovo tentativo
            # a breve, invece di segnare le stats come inviate e perderle.
            log_line("RETRY", "STATS", f"{_momento} non inviata; nuovo tentativo tra 30s")
            ctx.state.setdefault("pending_stats", []).append({
                "momento": _momento,
                "due": ctx._now_ts + 30,
            })
            gist.salva_stato_su_gist(ctx.state)


def retry_cancel_message(ctx: MatchContext) -> None:
    """Ritenta il messaggio GOAL ANNULLATO rimasto in sospeso."""
    if ctx.status == "PEN":
        ctx.sleep_time = settings.POLL_SECONDS

    # --- Retry GOAL ANNULLATO non riuscito in un ciclo precedente ---
    # Lo stato del punteggio è già stato aggiornato quando l'annullamento è
    # stato rilevato, quindi qui NON possiamo contare su una ri-rilevazione
    # naturale: il testo del messaggio resta in coda finché l'invio non va a buon fine.
    if ctx.state.get("pending_goal_annullato"):
        _retry_cancel_id = tg.send_telegram_get_id(ctx.state["pending_goal_annullato"])
        if _retry_cancel_id:
            log_line("OK", "TELEGRAM", "GOAL ANNULLATO inviato | retry riuscito")
            ctx.state["cancel_msg_id"] = _retry_cancel_id
            ctx.state["pending_goal_annullato"] = None
            ctx.state_changed = True
        else:
            log_line("RETRY", "TELEGRAM", "GOAL ANNULLATO non inviato; nuovo tentativo al prossimo ciclo")
