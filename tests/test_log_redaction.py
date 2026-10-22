import os
import unittest
from unittest.mock import patch

from livescore.core.log import redact


class RedactionTests(unittest.TestCase):
    def test_bot_token_in_url_is_hidden(self):
        text = "POST https://api.telegram.org/bot123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw/sendMessage"
        self.assertNotIn("AAHdqTcv", redact(text))
        self.assertIn("sendMessage", redact(text))

    def test_secret_from_environment_is_hidden(self):
        with patch.dict(os.environ, {"GH_PAT": "ghp_supersecretvalue"}):
            self.assertEqual(redact("token=ghp_supersecretvalue ok"), "token=*** ok")

    def test_normal_text_is_untouched(self):
        self.assertEqual(redact("CAMBIO JUVENTUS 60' | Telegram inviato"), "CAMBIO JUVENTUS 60' | Telegram inviato")


if __name__ == "__main__":
    unittest.main()
