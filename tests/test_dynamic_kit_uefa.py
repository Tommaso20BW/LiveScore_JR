import unittest
from unittest.mock import Mock, patch

import dynamic_kit_live_test as base
import dynamic_kit_uefa_live_test as uefa


class UefaDynamicKitTests(unittest.TestCase):
    def test_ucl_theme_is_independent_from_kit(self):
        try:
            import portrait_graphics
        except ImportError:
            self.skipTest("portrait_graphics disponibile nel repository completo")
        self.assertEqual(portrait_graphics.theme("home", "uefa.champions"), "ucl")
        self.assertEqual(portrait_graphics.theme("away", "uefa.champions"), "ucl")
        self.assertEqual(portrait_graphics.theme("third", "uefa.champions"), "ucl")

    def test_europa_theme_is_independent_from_kit(self):
        try:
            import portrait_graphics
        except ImportError:
            self.skipTest("portrait_graphics disponibile nel repository completo")
        self.assertEqual(portrait_graphics.theme("home", "uefa.europa"), "uel")
        self.assertEqual(portrait_graphics.theme("third", "uefa.europa"), "uel")

    def test_conference_theme_is_independent_from_kit(self):
        try:
            import portrait_graphics
        except ImportError:
            self.skipTest("portrait_graphics disponibile nel repository completo")
        self.assertEqual(portrait_graphics.theme("home", "uefa.europa.conf"), "conference")
        self.assertEqual(portrait_graphics.theme("away", "uefa.europa.conf"), "conference")

    def test_manual_still_overrides_espn_in_uefa(self):
        state = base.KitState(event_id="UEFA_SIM", fallback_kit="away", active_kit="away")
        state.ensure_compat()
        base.set_espn_kit(state, "third")
        base.set_manual_kit(state, "home")
        base.set_espn_kit(state, "away")
        self.assertEqual(state.espn_kit, "away")
        self.assertEqual(state.active_kit, "home")

    def test_unchanged_render_does_not_edit_telegram(self):
        state = base.KitState(event_id="UEFA_SIM", fallback_kit="away", active_kit="third")
        state.kit_media = {
            "kickoff": {
                "message_id": 10,
                "type": "kick",
                "caption": "kick",
                "kit": "away",
                "render_hash": uefa.sha(b"same"),
            }
        }
        tg = Mock()

        with patch.object(uefa, "render_entry", return_value=b"same"):
            edited, unchanged = uefa.refresh_all(tg, state, None)

        self.assertEqual(edited, 0)
        self.assertEqual(unchanged, 1)
        tg.edit_photo.assert_not_called()
        self.assertEqual(state.kit_media["kickoff"]["kit"], "third")

    def test_changed_render_uses_edit_message_media_path(self):
        state = base.KitState(event_id="UEFA_SIM", fallback_kit="away", active_kit="third")
        state.kit_media = {
            "goal": {
                "message_id": 11,
                "type": "goal",
                "caption": "goal",
                "kit": "away",
                "render_hash": uefa.sha(b"old"),
            }
        }
        tg = Mock()
        tg.edit_photo.return_value = True

        with patch.object(uefa, "render_entry", return_value=b"new"):
            edited, unchanged = uefa.refresh_all(tg, state, None)

        self.assertEqual((edited, unchanged), (1, 0))
        tg.edit_photo.assert_called_once_with(11, "goal", b"new")
        self.assertEqual(state.kit_media["goal"]["kit"], "third")


if __name__ == "__main__":
    unittest.main()
