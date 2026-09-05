import os
import re
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import juve_bot_espn as bot


ROOT = Path(__file__).resolve().parents[1]


class StartupTests(unittest.TestCase):
    def setUp(self):
        for target, kwargs in (
            ("GOAL_GRAPHICS_ENABLED", {"new": True}),
            ("avvia_ciclo_partita", {}),
            ("get_valid_token", {}),
        ):
            patcher = patch.object(bot, target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(bot.fclogo_sync, "sync_current_season",
                               return_value=Mock(errors=[]))
        self.sync = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.dict(os.environ, {"ONLY_REFRESH_TOKEN": "false"})
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch("builtins.print")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_successful_workflow_sync_is_not_repeated(self):
        with patch.dict(os.environ, {"FCLOGO_SYNC_DONE": "true"}):
            bot.main()
        self.sync.assert_not_called()
        bot.avvia_ciclo_partita.assert_called_once_with()

    def test_failed_or_skipped_workflow_sync_is_retried(self):
        with patch.dict(os.environ, {"FCLOGO_SYNC_DONE": "false"}):
            bot.main()
        self.sync.assert_called_once_with()
        bot.avvia_ciclo_partita.assert_called_once_with()

    def test_direct_start_still_syncs(self):
        with patch.dict(os.environ):
            os.environ.pop("FCLOGO_SYNC_DONE", None)
            bot.main()
        self.sync.assert_called_once_with()
        bot.avvia_ciclo_partita.assert_called_once_with()

    def test_sync_error_does_not_block_live(self):
        self.sync.side_effect = RuntimeError("FCLogo offline")
        with patch.dict(os.environ, {"FCLOGO_SYNC_DONE": "false"}):
            bot.main()
        bot.avvia_ciclo_partita.assert_called_once_with()

    def test_disabled_graphics_do_not_sync(self):
        with patch.object(bot, "GOAL_GRAPHICS_ENABLED", False), \
             patch.dict(os.environ, {"FCLOGO_SYNC_DONE": "false"}):
            bot.main()
        self.sync.assert_not_called()
        bot.avvia_ciclo_partita.assert_called_once_with()

    def test_keepalive_only_reaches_mocked_refresh(self):
        with patch.dict(os.environ, {"ONLY_REFRESH_TOKEN": "true",
                                     "FCLOGO_SYNC_DONE": "false"}):
            bot.main()
        bot.get_valid_token.assert_called_once_with()
        self.sync.assert_not_called()
        bot.avvia_ciclo_partita.assert_not_called()


class WorkflowConfigurationTests(unittest.TestCase):
    def test_keepalive_installs_required_pillow_version(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        pillow = re.search(r"(?im)^pillow==\S+", requirements).group(0)
        workflow = (ROOT / ".github/workflows/canva_keep_alive.yml").read_text(encoding="utf-8")
        install = next(line for line in workflow.splitlines()
                       if "pip install requests==" in line)
        self.assertIn(pillow, install)

    def test_publication_failure_is_non_blocking_and_sync_flag_uses_outcome(self):
        workflow = (ROOT / ".github/workflows/main_espn.yml").read_text(encoding="utf-8")
        publication = workflow.split("- name: Publish seasonal FCLogo team logos", 1)[1].split("- name:", 1)[0]
        self.assertIn("continue-on-error: true", publication)
        self.assertIn("::warning::", publication)
        self.assertNotIn("--force", publication)
        live = workflow.split("- name: Run Live Score Bot", 1)[1].split("- name:", 1)[0]
        self.assertIn("FCLOGO_SYNC_DONE: ${{ steps.fclogo_sync.outcome == 'success' && 'true' || 'false' }}", live)


if __name__ == "__main__":
    unittest.main()
