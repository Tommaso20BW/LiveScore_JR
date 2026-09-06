import os
import unittest
from unittest.mock import patch

import stats_preview


EVENT = {
    "header": {
        "league": {"name": "Italian Serie A"},
        "competitions": [{
            "competitors": [
                {
                    "homeAway": "home",
                    "score": "3",
                    "team": {"id": "110", "displayName": "Internazionale"},
                },
                {
                    "homeAway": "away",
                    "score": "2",
                    "team": {"id": "114", "displayName": "Napoli"},
                },
            ]
        }],
    }
}


class StatsPreviewTests(unittest.TestCase):
    def test_preview_is_forced_to_bot_jr(self):
        with patch.dict(os.environ, {"TELEGRAM_TO_BOT": "bot-jr"}), \
             patch.object(stats_preview.bot, "BOT_TOKEN", "token"), \
             patch.object(stats_preview.bot, "CHAT_ID", "main-channel"), \
             patch.object(stats_preview, "fetch_event", return_value=EVENT), \
             patch.object(
                 stats_preview.bot,
                 "recupera_e_genera_stats_html",
                 return_value="/tmp/stats.png",
             ) as render, \
             patch.object(
                 stats_preview.bot,
                 "send_telegram_stats_photo",
                 return_value=True,
             ) as send:
            self.assertTrue(stats_preview.send_preview("401874937", "ita.1", "FT"))
            self.assertEqual(stats_preview.bot.CHAT_ID, "bot-jr")

        self.assertEqual(render.call_args.args[1:7], ("110", "114", "Inter", "Napoli", 3, 2))
        self.assertTrue(render.call_args.kwargs["hd_output"])
        send.assert_called_once_with(
            "/tmp/stats.png",
            "FT",
            "🇮🇹 #InterNapoli",
            min_long_side=2000,
        )


if __name__ == "__main__":
    unittest.main()
