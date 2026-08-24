import unittest
from unittest.mock import patch

import juve_bot_espn as bot


class StatsDelayTests(unittest.TestCase):
    def test_default_stats_delay_is_five_minutes(self):
        self.assertEqual(bot.STATS_DELAY_SECONDS, 300)

        state = {"sent_stats": [], "pending_stats": []}
        with patch.object(bot.time, "time", return_value=1_000):
            self.assertTrue(bot._schedule_stats(state, "HT"))

        self.assertEqual(
            state["pending_stats"],
            [{"momento": "HT", "due": 1_300}],
        )

    def test_explicit_retry_delay_is_unchanged(self):
        state = {"sent_stats": [], "pending_stats": []}
        with patch.object(bot.time, "time", return_value=1_000):
            self.assertTrue(bot._schedule_stats(state, "HT", delay=30))

        self.assertEqual(state["pending_stats"][0]["due"], 1_030)


if __name__ == "__main__":
    unittest.main()
