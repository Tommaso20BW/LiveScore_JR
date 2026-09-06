import os
import unittest
from unittest.mock import patch

from live_logging import MatchProgressLog, _elapsed_minute, log_line


class LiveLoggingTests(unittest.TestCase):
    def test_log_line_uses_fixed_columns(self):
        with patch("builtins.print") as output:
            log_line("warn", "telegram", "timeout", timestamp="15:02:20")
        output.assert_called_once_with(
            "[15:02:20] WARN   TELEGRAM   | timeout",
            flush=True,
        )

    def test_debug_is_hidden_by_default_and_can_be_enabled(self):
        with patch.dict(os.environ, {}, clear=True), patch("builtins.print") as output:
            log_line("debug", "espn", "dettaglio", timestamp="15:02:20")
            output.assert_not_called()

        with patch.dict(os.environ, {"LIVE_LOG_DEBUG": "1"}), patch("builtins.print") as output:
            log_line("debug", "espn", "dettaglio", timestamp="15:02:20")
            output.assert_called_once_with(
                "[15:02:20] DEBUG  ESPN       | dettaglio",
                flush=True,
            )

    def test_recovery_minutes_are_supported(self):
        self.assertEqual(_elapsed_minute(0), 0)
        self.assertEqual(_elapsed_minute("90+3"), 93)
        self.assertEqual(_elapsed_minute("45'"), 45)
        self.assertIsNone(_elapsed_minute("HT"))

    def test_progress_is_throttled_but_changes_are_immediate(self):
        progress = MatchProgressLog(heartbeat_minutes=5, heartbeat_seconds=300)

        self.assertTrue(progress.should_emit("1H", "2", 0, 0, 100))
        self.assertFalse(progress.should_emit("1H", "3", 0, 0, 150))
        self.assertFalse(progress.should_emit("1H", "4", 0, 0, 200))
        self.assertTrue(progress.should_emit("1H", "5", 0, 0, 210))
        self.assertTrue(progress.should_emit("1H", "6", 1, 0, 220))
        self.assertTrue(progress.should_emit("HT", "45", 1, 0, 230))

    def test_stalled_feed_still_emits_a_health_line(self):
        progress = MatchProgressLog(heartbeat_minutes=5, heartbeat_seconds=300)
        self.assertTrue(progress.should_emit("1H", "12", 0, 0, 100))
        self.assertFalse(progress.should_emit("1H", "12", 0, 0, 399))
        self.assertTrue(progress.should_emit("1H", "12", 0, 0, 400))


if __name__ == "__main__":
    unittest.main()
