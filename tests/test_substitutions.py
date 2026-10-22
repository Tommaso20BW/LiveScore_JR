"""Cambi: minuto corretto, giocatore corretto, cambi raggruppati, stati salvati da versioni precedenti."""

import unittest

from livescore.hooks import bot
from livescore.match.substitutions import SubEvent, SubstitutionBook, group_fresh
from tests.sim_scenarios import (AWAY_ID, BARELLA, CONCEICAO, HOME_ID, LAUTARO, LOCATELLI,
                                 MCKENNIE, THURAM, VLAHOVIC, YILDIZ, goal, sub)
from tests.sim_support import Sim, payload


def second_half(*events, t=0, clock="60'", home=0, away=0):
    return (t, payload(clock=clock, period=2, home=home, away=away, key_events=list(events)))


def run(frames, end=700, **kw):
    sim = Sim(bot, frames, end, **kw)
    result = sim.run()
    return sim, result


def cambi(sim):
    """(secondo, metodo, id messaggio, testo) dei messaggi CAMBIO."""
    return [(e["t"], e["method"], e.get("message_id"), e["body"]["text"])
            for e in sim.telegram if e["ok"] and "CAMBIO" in e["body"].get("text", "")]


def first_line(text):
    return text.splitlines()[0]


class MinuteCorrectionTests(unittest.TestCase):
    def test_minute_corrected_after_sending_edits_same_message(self):
        s1 = sub("s1", "60'", 2, HOME_ID, THURAM, LOCATELLI)
        s1_fixed = sub("s1", "62'", 2, HOME_ID, THURAM, LOCATELLI)    # stesso id, minuto cambiato
        sim, _ = run([second_half(s1, t=0), second_half(s1_fixed, t=120, clock="63'")])
        rows = cambi(sim)
        self.assertEqual([r[1] for r in rows], ["sendMessage", "editMessageText"])
        self.assertIn("60'", first_line(rows[0][3]))
        self.assertIn("62'", first_line(rows[1][3]))
        self.assertEqual(rows[0][2], rows[1][2], "la correzione deve modificare il messaggio gia' inviato")
        self.assertNotIn("60'", rows[1][3])

    def test_minute_corrected_during_grouping_wait_sends_single_corrected_message(self):
        s1 = sub("s1", "60'", 2, HOME_ID, THURAM, LOCATELLI)
        s1_fixed = sub("s1", "61'", 2, HOME_ID, THURAM, LOCATELLI)
        sim, _ = run([second_half(s1, t=0), second_half(s1_fixed, t=4)])
        rows = cambi(sim)
        self.assertEqual(len(rows), 1)
        self.assertIn("61'", first_line(rows[0][3]))

    def test_other_source_reports_same_substitution_with_other_id_and_minute(self):
        a = sub("from-commentary", "62'", 2, HOME_ID, THURAM, LOCATELLI)
        b = sub("from-keyevents", "60'", 2, HOME_ID, THURAM, LOCATELLI)
        sim, _ = run([second_half(b, t=0), second_half(a, t=100), second_half(b, t=200), second_half(a, t=300)],
                     end=800)
        rows = cambi(sim)
        # una correzione 60' -> 62' e poi niente va-e-vieni anche se le due fonti si alternano
        self.assertEqual([r[1] for r in rows], ["sendMessage", "editMessageText"])
        self.assertIn("62'", first_line(rows[-1][3]))

    def test_minute_correction_edit_failure_is_retried(self):
        s1 = sub("s1", "60'", 2, HOME_ID, THURAM, LOCATELLI)
        s1_fixed = sub("s1", "62'", 2, HOME_ID, THURAM, LOCATELLI)
        attempts = []

        def fail_first_edit(n, method, body):
            if method == "editMessageText":
                attempts.append(n)
                return len(attempts) == 1
            return False

        sim, _ = run([second_half(s1, t=0), second_half(s1_fixed, t=100)], tg_fail=fail_first_edit)
        edits = [e for e in sim.telegram if e["method"] == "editMessageText"]
        self.assertEqual([e["ok"] for e in edits], [False, True])

    def test_absurd_minute_jump_is_not_treated_as_correction(self):
        s1 = sub("s1", "20'", 2, HOME_ID, THURAM, LOCATELLI)
        s1_weird = sub("s1", "80'", 2, HOME_ID, THURAM, LOCATELLI)
        sim, _ = run([second_half(s1, t=0), second_half(s1_weird, t=100)])
        self.assertEqual(len(cambi(sim)), 1)


class GroupedSubstitutionTests(unittest.TestCase):
    def test_two_close_substitutions_share_one_message(self):
        s1 = sub("s1", "60'", 2, HOME_ID, THURAM, LOCATELLI)
        s2 = sub("s2", "61'", 2, HOME_ID, CONCEICAO, MCKENNIE)
        sim, _ = run([second_half(s1, t=0), second_half(s1, s2, t=5)])
        rows = cambi(sim)
        self.assertEqual(len(rows), 1)
        self.assertIn("K. Thuram, F. Conceicao", rows[0][3])
        self.assertIn("M. Locatelli, W. McKennie", rows[0][3])

    def test_late_substitution_in_same_window_is_added_to_existing_message(self):
        s1 = sub("s1", "60'", 2, HOME_ID, THURAM, LOCATELLI)
        s2 = sub("s2", "61'", 2, HOME_ID, CONCEICAO, MCKENNIE)
        sim, _ = run([second_half(s1, t=0), second_half(s1, s2, t=100)])
        rows = cambi(sim)
        self.assertEqual([r[1] for r in rows], ["sendMessage", "editMessageText"])
        self.assertIn("K. Thuram, F. Conceicao", rows[1][3])

    def test_one_of_a_group_moved_far_away_leaves_the_message_and_gets_its_own(self):
        s1 = sub("s1", "60'", 2, HOME_ID, THURAM, LOCATELLI)
        s2 = sub("s2", "61'", 2, HOME_ID, CONCEICAO, MCKENNIE)
        s2_fixed = sub("s2", "70'", 2, HOME_ID, CONCEICAO, MCKENNIE)
        sim, _ = run([second_half(s1, s2, t=0), second_half(s1, s2_fixed, t=100, clock="71'")], end=900)
        rows = cambi(sim)
        methods = [r[1] for r in rows]
        self.assertEqual(methods, ["sendMessage", "editMessageText", "sendMessage"])
        self.assertNotIn("Conceicao", rows[1][3])          # il primo messaggio resta solo con Thuram
        self.assertIn("70'", first_line(rows[2][3]))        # il cambio spostato ha il suo messaggio
        self.assertIn("F. Conceicao", rows[2][3])

    def test_different_teams_and_periods_never_share_a_message(self):
        home = sub("h1", "44'", 1, HOME_ID, THURAM, LOCATELLI)
        away = sub("a1", "44'", 1, AWAY_ID, LAUTARO, BARELLA)
        later = sub("h2", "46'", 2, HOME_ID, CONCEICAO, MCKENNIE)
        sim, _ = run([(0, payload(clock="44'", period=1, key_events=[home, away])),
                      (60, payload(clock="46'", period=2, key_events=[home, away, later]))], end=600)
        self.assertEqual(len([r for r in cambi(sim) if r[1] == "sendMessage"]), 3)


class PlayerCorrectionTests(unittest.TestCase):
    def test_espn_corrects_who_comes_off(self):
        wrong = sub("s1", "60'", 2, HOME_ID, THURAM, LOCATELLI)
        fixed = sub("s1b", "60'", 2, HOME_ID, THURAM, MCKENNIE)      # nuovo id, esce un altro
        sim, _ = run([second_half(wrong, t=0), second_half(wrong, fixed, t=100)])
        rows = cambi(sim)
        self.assertEqual([r[1] for r in rows], ["sendMessage", "editMessageText"])
        self.assertIn("W. McKennie", rows[1][3])
        self.assertNotIn("M. Locatelli", rows[1][3])

    def test_old_id_still_in_feed_does_not_flip_back(self):
        wrong = sub("s1", "60'", 2, HOME_ID, THURAM, LOCATELLI)
        fixed = sub("s1b", "60'", 2, HOME_ID, THURAM, MCKENNIE)
        sim, _ = run([second_half(wrong, t=0), second_half(wrong, fixed, t=100),
                      second_half(wrong, fixed, t=200), second_half(wrong, fixed, t=300)])
        self.assertEqual(len(cambi(sim)), 2)       # invio + una sola correzione


class LoopStaysResponsiveTests(unittest.TestCase):
    def test_goal_during_substitution_grouping_is_not_delayed(self):
        s1 = sub("s1", "60'", 2, HOME_ID, THURAM, LOCATELLI)
        g = goal("g1", "60'", 2, AWAY_ID, LAUTARO)
        frames = [second_half(s1, t=0), (2, payload(clock="60'", period=2, away=1, key_events=[s1, g]))]
        sim, _ = run(frames, end=200)
        goal_t = next(e["t"] for e in sim.telegram if "GOAL" in e["body"].get("text", ""))
        sub_t = next(e["t"] for e in sim.telegram if "CAMBIO" in e["body"].get("text", ""))
        self.assertLess(goal_t, sub_t)


class SavedStateCompatibilityTests(unittest.TestCase):
    def legacy_state(self):
        return {
            "event_id": "999001", "league_slug": "ita.1", "league_name": "Serie A",
            "sent_periods": ["1H", "HT", "2H"], "goals_detected": 0, "prev_home_goals": 0,
            "prev_away_goals": 0, "sent_cards": [], "penalties_count": 0, "sent_stats": ["HT"],
            "sent_failed_penalties": [], "shootout_message_id": None, "goal_messages": {},
            "cancel_msg_id": None, "pending_stats": [], "pending_goal_cancellation": None,
            "sent_subs": {"111:2:60": {"msg_id": 555, "minute": 60, "period": 2,
                                       "ins": ["K. Thuram"], "outs": ["M. Locatelli"], "sub_ids": ["s1"]}},
        }

    def test_substitution_already_in_old_format_state_is_not_resent(self):
        s1 = sub("s1", "60'", 2, HOME_ID, THURAM, LOCATELLI)
        sim, _ = run([second_half(s1, t=0)], initial_state=self.legacy_state(), end=300)
        self.assertEqual(cambi(sim), [])

    def test_old_format_state_gets_minute_correction_too(self):
        s1 = sub("s1", "62'", 2, HOME_ID, THURAM, LOCATELLI)
        sim, _ = run([second_half(s1, t=0)], initial_state=self.legacy_state(), end=300)
        rows = cambi(sim)
        # lo stato vecchio non conosceva l'id come "proprietario": stessa coppia -> correzione del minuto
        self.assertEqual([r[1] for r in rows], ["editMessageText"])
        self.assertEqual(rows[0][2], 555)
        self.assertIn("62'", first_line(rows[0][3]))

    def test_saved_state_stays_readable_by_old_fields(self):
        s1 = sub("s1", "60'", 2, HOME_ID, THURAM, LOCATELLI)
        _, result = run([second_half(s1, t=0)], end=300)
        slot = next(iter(result["final_state"]["sent_subs"].values()))
        for field in ("msg_id", "minute", "period", "ins", "outs", "sub_ids"):
            self.assertIn(field, slot)
        self.assertEqual((slot["ins"], slot["outs"], slot["minute"]), (["K. Thuram"], ["M. Locatelli"], 60))


class PureLogicTests(unittest.TestCase):
    def ev(self, uid, minute, player_in, player_out, team="111", period=2):
        return SubEvent(uid, team, period, minute, player_in, player_out)

    def test_group_fresh_orders_chronologically_and_uses_earliest_minute(self):
        groups = group_fresh([self.ev("b", 61, "C", "D"), self.ev("a", 60, "A", "B")])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0][0].minute, 60)

    def test_plan_is_pure_until_committed(self):
        slots = {}
        book = SubstitutionBook(slots)
        plan = book.plan([self.ev("a", 60, "A", "B")])
        self.assertEqual(len(plan.fresh), 1)
        self.assertEqual(slots, {})
        book.add_slot("111", 2, 7, plan.fresh)
        self.assertEqual(len(slots), 1)
        again = SubstitutionBook(slots).plan([self.ev("a", 60, "A", "B")])
        self.assertEqual((again.fresh, again.edits), ([], {}))

    def test_edit_not_committed_is_proposed_again(self):
        slots = {}
        book = SubstitutionBook(slots)
        book.add_slot("111", 2, 7, [self.ev("a", 60, "A", "B")])
        first = book.plan([self.ev("a", 62, "A", "B")])
        self.assertEqual(len(first.edits), 1)
        # Telegram non ha confermato -> nessun commit -> stesso piano al ciclo dopo
        second = SubstitutionBook(slots).plan([self.ev("a", 62, "A", "B")])
        self.assertEqual(len(second.edits), 1)


if __name__ == "__main__":
    unittest.main()
