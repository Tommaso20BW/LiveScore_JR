import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

import livescore_runner as runner


class MatchFoundNotificationTests(unittest.TestCase):
    def setUp(self):
        self.competitors = [
            {"homeAway": "home", "team": {"id": "111", "displayName": "Juventus"}, "score": "0"},
            {"homeAway": "away", "team": {"id": "147", "displayName": "NEC Nijmegen"}, "score": "0"},
        ]
        self.match = {"event_id": "123456", "league_slug": "uefa.europa",
                      "league_name": "Europa League", "competitors": self.competitors,
                      "competition": {"date": "2026-09-05T19:00Z",
                                      "venue": {"fullName": "Allianz Stadium"},
                                      "competitors": self.competitors}}
        for target, kwargs in (
            ("rileva_kit_juve", {"return_value": "home"}),
            ("GOAL_GRAPHICS_ENABLED", {"new": True}),
            ("translate_team", {"side_effect": lambda name: name}),
        ):
            p = patch.object(runner.bot, target, **kwargs)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(runner.bot.goal_graphics, "resolve_team_logo_source",
                         return_value=(None, "FCLogo"))
        self.source = p.start()
        self.addCleanup(p.stop)
        p = patch.object(runner, "_asset_status", return_value="disponibili")
        p.start()
        self.addCleanup(p.stop)

    def test_approved_format_and_italian_time(self):
        text = runner.messaggio_partita_trovata(self.match)
        self.assertIn("05/09/2026 · 21:00", text)
        self.assertIn("Kit Juventus: Home", text)
        self.assertIn("NEC Nijmegen: FCLogo", text)
        self.assertEqual(re.findall(r"<b>(.*?)</b>", text),
                         ["PARTITA TROVATA", "GRAFICHE", "LOGHI", "LIVE SCORE", "ESPN"])
        for excluded in ("non ancora", "fallback", "locale"):
            self.assertNotIn(excluded, text.lower())
        self.assertLess(len(text), 4096)

    def test_kit_labels(self):
        for kit in ("home", "away", "third"):
            runner.bot.rileva_kit_juve.return_value = kit
            self.assertIn(f"Kit Juventus: {kit.title()}", runner.messaggio_partita_trovata(self.match))

    def test_sources_short_labels_and_original_espn_names(self):
        runner.bot.translate_team.side_effect = lambda name: "NEC tradotto" if name.startswith("NEC") else name
        self.source.side_effect = [(None, "FCLogo"), (None, "ESPN")]
        text = runner.messaggio_partita_trovata(self.match)
        self.assertIn("NEC tradotto: ESPN", text)
        self.assertEqual(self.source.call_args_list[1].args[:2], ("NEC Nijmegen", "147"))

    def test_unavailable_logo_and_friendly_are_truthful(self):
        self.match["league_slug"] = "club.friendly"
        self.source.return_value = (None, "Non disponibile")
        text = runner.messaggio_partita_trovata(self.match)
        self.assertIn("GOAL / SAVED: disabilitate (amichevole)", text)
        self.assertIn("Background e scritte: non verificati", text)
        self.assertIn("NEC Nijmegen: Non disponibile", text)

    def test_missing_details_and_html_escaping(self):
        self.match["competition"] = {}
        self.match["league_name"] = "Cup <A&B>"
        text = runner.messaggio_partita_trovata(self.match)
        self.assertIn("Cup &lt;A&amp;B&gt;", text)
        self.assertIn("Orario non disponibile", text)
        self.assertIn("Stadio non disponibile", text)

    def test_notification_only_to_bot_jr_even_if_summary_fails(self):
        response = Mock()
        with patch.dict(os.environ, {"TELEGRAM_TO_BOT": "test-chat", "LIVE_SCORE_CHANNEL_NAME": "Bot JR"}), \
             patch.object(runner.bot, "BOT_TOKEN", "test-token"), \
             patch.object(runner.bot, "fetch_evento", side_effect=RuntimeError("offline")) as fetch, \
             patch.object(runner.bot, "_tg_post", return_value=response) as post:
            runner._notifica_partita_trovata_bot(self.match)
        fetch.assert_called_once_with("123456", "uefa.europa")
        payload = post.call_args.kwargs["payload"]
        self.assertEqual(payload["chat_id"], "test-chat")
        self.assertIn("Canale: Bot JR", payload["text"])

    def test_telegram_failure_does_not_stop_discovery(self):
        with patch.object(runner, "_ORIGINAL_TROVA_PARTITA", return_value=self.match), \
             patch.dict(os.environ, {"TELEGRAM_TO_BOT": "test-chat"}), \
             patch.object(runner.bot, "BOT_TOKEN", "test-token"), \
             patch.object(runner.bot, "fetch_evento", return_value=None), \
             patch.object(runner.bot, "_tg_post", side_effect=RuntimeError("offline")):
            self.assertIs(runner.trova_partita_con_notifica("111"), self.match)


class LogoSourceTests(unittest.TestCase):
    def test_corrupt_or_transparent_local_png_uses_espn(self):
        graphics = runner.bot.goal_graphics
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "logo.png"
            for corrupt in (True, False):
                if corrupt:
                    path.write_bytes(b"invalid")
                else:
                    Image.new("RGBA", (5, 5)).save(path)
                with patch.object(graphics, "_local_team_logo_path", return_value=path), \
                     patch.object(graphics, "_remote_espn_team_logo", return_value=Image.new("RGBA", (5, 5), "red")):
                    image, source = graphics.resolve_team_logo_source("Test", "1", Path(tmp))
                self.assertEqual(source, "ESPN")
                self.assertIsNotNone(image)
