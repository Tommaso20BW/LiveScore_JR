"""Piu' gol letti insieme, minuti di recupero e Gist non raggiungibile."""
import re
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from livescore.hooks import bot
from livescore.match import cycle
from livescore.match.context import Flow
from livescore.state import gist
from tests.sim_scenarios import AWAY_ID, HOME_ID, LAUTARO, VLAHOVIC, YILDIZ, goal
from tests.sim_support import Sim, payload


def goal_texts(sim):
    return [e["body"].get("text") or e["body"].get("caption") or "" for e in sim.telegram
            if e["ok"] and e["method"] in ("sendMessage", "sendPhoto")
            and "GOAL" in (e["body"].get("text") or e["body"].get("caption") or "")]


def scores(texts):
    found = []
    for text in texts:
        plain = re.sub(r"<[^>]+>", "", text)
        found.append(re.search(r"(\d+)-(\d+)", plain).group(0))
    return found


class TwoGoalsTests(unittest.TestCase):
    def frames(self):
        g1 = goal("g1", "10'", 1, HOME_ID, VLAHOVIC)
        g2 = goal("g2", "20'", 1, AWAY_ID, LAUTARO)
        g3 = goal("g3", "21'", 1, HOME_ID, YILDIZ)
        return [
            (0, payload(clock="9'", home=0, away=0)),
            (60, payload(clock="10'", home=1, away=0, key_events=[g1])),
            (200, payload(clock="21'", home=2, away=1, key_events=[g1, g2, g3])),
            (400, payload(state="post", name="STATUS_FULL_TIME", clock="90'", period=2, home=2, away=1,
                          key_events=[g1, g2, g3])),
        ]

    def test_each_goal_has_its_message_in_order(self):
        sim = Sim(bot, self.frames(), 1200)
        sim.run()
        texts = goal_texts(sim)
        self.assertEqual(scores(texts), ["1-0", "1-1", "2-1"])
        self.assertIn("20'", texts[1])
        self.assertIn("21'", texts[2])

    def test_failed_send_is_retried_without_duplicates(self):
        failed = []

        def fail_once(_call, _method, body):
            text = body.get("text") or body.get("caption") or ""
            if "GOAL" in text and "20'" in text and not failed:
                failed.append(True)
                return True
            return False

        sim = Sim(bot, self.frames(), 1200, tg_fail=fail_once)
        sim.run()
        self.assertTrue(failed)
        self.assertEqual(scores(goal_texts(sim)), ["1-0", "1-1", "2-1"])


class StoppageMinuteTests(unittest.TestCase):
    def test_first_goal_in_stoppage_keeps_format(self):
        g1 = goal("g1", "45'+2'", 1, HOME_ID, VLAHOVIC)
        frames = [
            (0, payload(clock="45'", home=0, away=0)),
            (60, payload(clock="45'+2'", home=1, away=0, key_events=[g1])),
            (300, payload(state="post", name="STATUS_FULL_TIME", clock="90'", period=2, home=1, away=0,
                          key_events=[g1])),
        ]
        sim = Sim(bot, frames, 900)
        sim.run()
        self.assertIn("45+2'", goal_texts(sim)[0])


class GistDownTests(unittest.TestCase):
    def test_live_keeps_reading_espn(self):
        ctx = SimpleNamespace(state={"_gist_dirty": True}, sleep_time=0, event_id="1", league_slug="ita.1")
        with patch.object(gist, "salva_stato_su_gist", return_value=True) as save, \
                patch.object(cycle.espn_client, "fetch_evento", return_value=None) as fetch, \
                patch.object(cycle.time, "sleep"):
            self.assertIs(cycle.prepare_cycle(ctx), Flow.CONTINUE)
        save.assert_called_once()
        fetch.assert_called_once()
        self.assertNotIn("_gist_dirty", ctx.state)


if __name__ == "__main__":
    unittest.main()
