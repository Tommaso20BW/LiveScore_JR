"""Statistiche di fine tempo: programmazione, generazione e invio."""

import time

from livescore import settings
from livescore.constants import JUVE_ID
from livescore.core import leagues
from livescore.core.log import log_line
from livescore.espn import stats as espn_stats
from livescore.kits import detect as kit_detect


def stats_eligible(home_id, away_id, league_slug, league_name=""):
    return (JUVE_ID in (str(home_id), str(away_id))
            and not leagues.is_friendly_competition(league_slug, league_name))


def recupera_e_genera_stats_html(data_espn: dict, home_id: str, away_id: str,
                                  home_name: str, away_name: str,
                                  home_goals: int, away_goals: int,
                                  momento: str, league_name: str = "SERIE A",
                                  league_slug: str = "",
                                  pen_home: int = 0, pen_away: int = 0,
                                  event_id: str = "",
                                  hd_output: bool = True):
    if not stats_eligible(home_id, away_id, league_slug, league_name):
        return None
    from livescore.graphics import stats as stats_graphics
    kit = kit_detect.rileva_kit_juve(data_espn, home_id, away_id, home_name, away_name,
                         league_slug, league_name)
    raw         = espn_stats._estrai_stats_espn(data_espn)

    def g(side, *keys, fallback="0"):
        for key in keys:
            val = raw[side].get(key.lower())
            if val is not None and str(val) not in ("0", "", "0.0", "0%", "0.0%"):
                return val
        for key in keys:
            val = raw[side].get(key.lower())
            if val is not None:
                return val
        return fallback

    def perc(h_val, a_val):
        try:
            h = float(str(h_val).replace("%", "").strip())
            a = float(str(a_val).replace("%", "").strip())
            total = h + a
            return None if total == 0 else int(h / total * 100)
        except Exception:
            return None

    def fmt_pct(val):
        try:
            v = float(str(val).replace("%", "").strip())
            if v <= 1.0:
                return f"{int(round(v*100))}%"
            return f"{int(round(v))}%"
        except Exception:
            return str(val)

    pos_h_raw = g("home", "possessionPct", "possessionpct", "possession", fallback="50")
    pos_a_raw = g("away", "possessionPct", "possessionpct", "possession", fallback="50")
    pos_h     = fmt_pct(pos_h_raw)
    pos_a     = fmt_pct(pos_a_raw)
    try:
        bp_perc = float(str(pos_h_raw).replace("%", ""))
        if bp_perc <= 1:
            bp_perc *= 100
        bp_perc = max(0.0, min(100.0, bp_perc))
    except Exception:
        bp_perc = 50.0
    pos_right_pct = f"{100.0 - bp_perc:.2f}%"
    pos_ring_class = " has-split" if 0.0 < bp_perc < 100.0 else ""

    sot_h    = g("home", "shotsOnTarget",   "shotsontarget",   fallback="0")
    sot_a    = g("away", "shotsOnTarget",   "shotsontarget",   fallback="0")
    shots_h  = g("home", "totalShots",      "totalshots",      fallback="0")
    shots_a  = g("away", "totalShots",      "totalshots",      fallback="0")
    falli_h  = g("home", "foulsCommitted",  "foulscommitted",  "fouls", fallback="0")
    falli_a  = g("away", "foulsCommitted",  "foulscommitted",  "fouls", fallback="0")
    gialli_h = g("home", "yellowCards",     "yellowcards",     fallback="0")
    gialli_a = g("away", "yellowCards",     "yellowcards",     fallback="0")
    rossi_h  = g("home", "redCards",        "redcards",        fallback="0")
    rossi_a  = g("away", "redCards",        "redcards",        fallback="0")
    corner_h = g("home", "wonCorners",      "woncorners",
                          "cornerKicks",    "cornerkicks",
                          "corners",        "corner",          fallback="0")
    corner_a = g("away", "wonCorners",      "woncorners",
                          "cornerKicks",    "cornerkicks",
                          "corners",        "corner",          fallback="0")
    saves_h  = g("home", "saves",           fallback="0")
    saves_a  = g("away", "saves",           fallback="0")
    offside_h = g("home", "offsides",       fallback="0")
    offside_a = g("away", "offsides",       fallback="0")
    pass_h   = g("home", "totalPasses",     "totalpasses",     fallback="0")
    pass_a   = g("away", "totalPasses",     "totalpasses",     fallback="0")
    passpct_h = fmt_pct(g("home", "passPct", "passpct",        fallback="0"))
    passpct_a = fmt_pct(g("away", "passPct", "passpct",        fallback="0"))

    stats_mappate = []
    xg = espn_stats.recupera_xg_espn(event_id, home_id, away_id)
    if xg is not None:
        xg_h, xg_a = xg
        stats_mappate.append(
            ("Expected Goals (xG)", xg_h, xg_a, perc(xg_h, xg_a))
        )

    stats_mappate.extend([
        ("Tiri in porta",       sot_h,      sot_a,      perc(sot_h,      sot_a)),
        ("Tiri",                shots_h,    shots_a,    perc(shots_h,    shots_a)),
        ("Corner",              corner_h,   corner_a,   perc(corner_h,   corner_a)),
        ("Fuorigioco",          offside_h,  offside_a,  perc(offside_h,  offside_a)),
        ("Falli",               falli_h,    falli_a,    perc(falli_h,    falli_a)),
        ("Ammoniti",            gialli_h,   gialli_a,   perc(gialli_h,   gialli_a)),
        ("Espulsi",             rossi_h,    rossi_a,    perc(rossi_h,    rossi_a)),
        ("Parate",              saves_h,    saves_a,    perc(saves_h,    saves_a)),
        ("Passaggi totali",     pass_h,     pass_a,     perc(pass_h,     pass_a)),
        ("Precisione passaggi", passpct_h,  passpct_a,  perc(
            str(passpct_h).replace("%",""), str(passpct_a).replace("%",""))),
    ])

    aliases = {"Expected Goals (xG)": "xG", "Passaggi totali": "PASSAGGI"}
    mapped = {aliases.get(label, label.upper()): (h, a) for label, h, a, _ in stats_mappate}
    mapped["POSSESSO"] = (pos_h, pos_a)
    rows = [(label, *mapped[label]) for label in stats_graphics.ORDER if label in mapped]
    html = stats_graphics.build_html(rows=rows, kit=kit, competition=league_slug,
        league_name=league_name, momento=momento, home_id=home_id, away_id=away_id,
        home_name=home_name, away_name=away_name)
    return stats_graphics.render(html, hd_output=hd_output)


# ==============================================================================
# CICLO PRINCIPALE
# ==============================================================================
def _schedule_stats(state: dict, momento: str, delay: int = settings.STATS_DELAY_SECONDS) -> bool:
    """Programma l'invio della grafica stats `delay` secondi dopo il cambio di
    stato (HT / 2H_END / FT), senza bloccare il ciclo live. Ritorna True se è
    stata aggiunta una nuova programmazione."""
    if momento in state.get("sent_stats", []):
        return False
    pend = state.setdefault("pending_stats", [])
    if any(p.get("momento") == momento for p in pend):
        return False
    pend.append({"momento": momento, "due": int(time.time()) + delay})
    log_line("WAIT", "STATS", f"{momento} programmate tra {delay}s")
    return True
