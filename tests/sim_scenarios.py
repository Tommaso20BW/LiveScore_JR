"""Partite finte per il simulatore. Ogni scenario restituisce (frames, end, opzioni)."""

from __future__ import annotations

from tests.sim_support import AWAY_ID, HOME_ID, key_event, payload

VLAHOVIC = ("Dusan Vlahovic", "D. Vlahovic")
YILDIZ = ("Kenan Yildiz", "K. Yildiz")
THURAM = ("Khephren Thuram", "K. Thuram")
LOCATELLI = ("Manuel Locatelli", "M. Locatelli")
MCKENNIE = ("Weston McKennie", "W. McKennie")
CONCEICAO = ("Francisco Conceicao", "F. Conceicao")
LAUTARO = ("Lautaro Martinez", "L. Martinez")
BARELLA = ("Nicolo Barella", "N. Barella")


def sub(uid, clock, period, team, entra, esce):
    return key_event(uid, "Substitution", clock, period, team, entra, esce)


def goal(uid, clock, period, team, scorer, assist=None):
    parts = [scorer] + ([assist] if assist else [])
    return key_event(uid, "Goal", clock, period, team, *parts)


def red(uid, clock, period, team, player):
    return key_event(uid, "Red Card", clock, period, team, player)


# ───────────────────────────── 1. partita regolare ─────────────────────────────
def regular_match():
    g1 = goal("g1", "12'", 1, HOME_ID, VLAHOVIC, YILDIZ)
    r1 = red("r1", "38'", 1, AWAY_ID, BARELLA)
    s1 = sub("s1", "60'", 2, HOME_ID, THURAM, LOCATELLI)
    s2 = sub("s2", "60'", 2, HOME_ID, CONCEICAO, MCKENNIE)
    g2 = goal("g2", "75'", 2, AWAY_ID, LAUTARO)
    frames = [
        (0, payload(clock="1'", period=1)),
        (60, payload(clock="12'", period=1, home=1, key_events=[g1])),
        (300, payload(clock="38'", period=1, home=1, key_events=[g1, r1])),
        (420, payload(state="in", name="STATUS_HALFTIME", clock="45'", period=1, home=1, key_events=[g1, r1])),
        (900, payload(clock="46'", period=2, home=1, key_events=[g1, r1])),
        (1000, payload(clock="60'", period=2, home=1, key_events=[g1, r1, s1])),
        (1010, payload(clock="60'", period=2, home=1, key_events=[g1, r1, s1, s2])),
        (1300, payload(clock="75'", period=2, home=1, away=1, key_events=[g1, r1, s1, s2, g2])),
        (1700, payload(state="post", name="STATUS_FULL_TIME", clock="90'", period=2, home=1, away=1,
                       key_events=[g1, r1, s1, s2, g2])),
    ]
    return frames, 3600, {}


# ───────────────────── 2. supplementari e rigori ─────────────────────
def extra_time_and_shootout():
    def shots(*results):
        return [{"id": f"k{i}", "didScore": r, "player": f"P{i}"} for i, r in enumerate(results)]

    def so(home, away):
        return [{"id": HOME_ID, "shots": shots(*home)}, {"id": AWAY_ID, "shots": shots(*away)}]

    frames = [
        (0, payload(clock="1'", period=1)),
        (200, payload(name="STATUS_HALFTIME", clock="45'", period=1)),
        (600, payload(clock="46'", period=2)),
        (1100, payload(name="STATUS_END_OF_REGULATION", clock="90'", period=2)),
        (1200, payload(name="STATUS_EXTRA_TIME", clock="91'", period=3)),
        (1500, payload(name="STATUS_END_PERIOD", clock="105'", period=3)),
        (1600, payload(name="STATUS_EXTRA_TIME", clock="106'", period=4)),
        (1900, payload(name="STATUS_END_OF_EXTRATIME", clock="120'", period=4)),
        (2000, payload(name="STATUS_SHOOTOUT", clock="120'", period=5, shootout=so([True], [False]))),
        (2060, payload(name="STATUS_SHOOTOUT", clock="120'", period=5, shootout=so([True, True], [False, True]))),
        (2120, payload(name="STATUS_SHOOTOUT", clock="120'", period=5,
                       shootout=so([True, True, True, True], [False, True, False, False]))),
        (2400, payload(state="post", name="STATUS_FINAL_PEN", clock="120'", period=5,
                       shootout=so([True, True, True, True], [False, True, False, False]))),
    ]
    return frames, 5000, {}


# ───────────────────── 3. gol annullato dal VAR ─────────────────────
def var_cancelled_goal():
    g1 = goal("g1", "20'", 1, HOME_ID, VLAHOVIC)
    frames = [
        (0, payload(clock="1'", period=1)),
        (60, payload(clock="20'", period=1, home=1, key_events=[g1])),
        (300, payload(clock="23'", period=1, home=0, key_events=[])),       # punteggio scende
        (460, payload(clock="26'", period=1, home=0, key_events=[])),        # conferma dopo 120s
        (800, payload(clock="40'", period=1, home=0)),
        (900, payload(state="post", name="STATUS_FULL_TIME", clock="90'", period=2, home=0)),
    ]
    return frames, 3600, {}


# ───────────────────── 4. correzione del marcatore ─────────────────────
def scorer_correction():
    g_wrong = goal("g1", "30'", 1, HOME_ID, YILDIZ)
    g_fixed = goal("g1", "30'", 1, HOME_ID, VLAHOVIC, YILDIZ)
    frames = [
        (0, payload(clock="1'", period=1)),
        (60, payload(clock="30'", period=1, home=1, key_events=[g_wrong])),
        (200, payload(clock="33'", period=1, home=1, key_events=[g_fixed])),
        (400, payload(state="post", name="STATUS_FULL_TIME", clock="90'", period=2, home=1, key_events=[g_fixed])),
    ]
    return frames, 3600, {}


# ───────────────────── 5. avvio a partita gia' in corso ─────────────────────
def late_start_catchup():
    g1 = goal("g1", "10'", 1, HOME_ID, VLAHOVIC, YILDIZ)
    g2 = goal("g2", "33'", 1, AWAY_ID, LAUTARO)
    g3 = goal("g3", "55'", 2, HOME_ID, YILDIZ)
    frames = [
        (0, payload(clock="60'", period=2, home=2, away=1, key_events=[g1, g2, g3])),
        (500, payload(state="post", name="STATUS_FULL_TIME", clock="90'", period=2, home=2, away=1,
                      key_events=[g1, g2, g3])),
    ]
    return frames, 3600, {}


# ───────────────────── 6. rigore sbagliato in gioco ─────────────────────
def missed_penalty():
    miss = key_event("p1", "Penalty - Missed", "41'", 1, HOME_ID, VLAHOVIC)
    frames = [
        (0, payload(clock="1'", period=1)),
        (100, payload(clock="41'", period=1, key_events=[miss])),
        (400, payload(state="post", name="STATUS_FULL_TIME", clock="90'", period=2, key_events=[miss])),
    ]
    return frames, 3600, {}


# ───────────────────── 7. Telegram instabile ─────────────────────
def flaky_telegram():
    g1 = goal("g1", "12'", 1, HOME_ID, VLAHOVIC)
    s1 = sub("s1", "60'", 2, HOME_ID, THURAM, LOCATELLI)

    def fail_first_two_of_each(n, method, body):
        text = body.get("text", "")
        return ("INIZIO PARTITA" in text or "GOAL" in text or "CAMBIO" in text) and n % 3 != 0

    frames = [
        (0, payload(clock="1'", period=1)),
        (60, payload(clock="12'", period=1, home=1, key_events=[g1])),
        (900, payload(clock="60'", period=2, home=1, key_events=[g1, s1])),
        (1500, payload(state="post", name="STATUS_FULL_TIME", clock="90'", period=2, home=1, key_events=[g1, s1])),
    ]
    return frames, 3600, {"tg_fail": fail_first_two_of_each}


SCENARIOS = {
    "regular_match": regular_match,
    "extra_time_and_shootout": extra_time_and_shootout,
    "var_cancelled_goal": var_cancelled_goal,
    "scorer_correction": scorer_correction,
    "late_start_catchup": late_start_catchup,
    "missed_penalty": missed_penalty,
    "flaky_telegram": flaky_telegram,
}
