import io
import unittest
from unittest.mock import Mock, patch

from PIL import Image

import dynamic_kit_live_test as base
import dynamic_kit_uefa_official_test as uefa


def png(pixel):
    im = Image.new("RGBA", (2, 2), pixel)
    s = io.BytesIO()
    im.save(s, "PNG")
    return s.getvalue()


class OfficialUefaKitTests(unittest.TestCase):
    def test_visual_hash_ignores_nonvisual_png_metadata(self):
        a = png((10, 20, 30, 255))
        b = png((10, 20, 30, 255))
        self.assertEqual(uefa.visual_hash(a), uefa.visual_hash(b))

    def test_identical_visual_does_not_edit(self):
        state = base.KitState(
            event_id="X",
            fallback_kit="away",
            active_kit="third",
        )
        old = png((1, 2, 3, 255))
        state.kit_media = {
            "kickoff": {
                "message_id": 10,
                "type": "kick",
                "caption": "kick",
                "kit": "away",
                "visual_hash": uefa.visual_hash(old),
            }
        }
        tg = Mock()
        with patch.object(uefa, "render_official", return_value=old):
            edited, same = uefa.refresh_all(tg, state, None)
        self.assertEqual((edited, same), (0, 1))
        tg.edit_photo.assert_not_called()

    def test_changed_visual_edits_same_message(self):
        state = base.KitState(
            event_id="X",
            fallback_kit="away",
            active_kit="third",
        )
        old = png((1, 2, 3, 255))
        new = png((4, 5, 6, 255))
        state.kit_media = {
            "goal": {
                "message_id": 22,
                "type": "goal",
                "caption": "goal",
                "kit": "away",
                "visual_hash": uefa.visual_hash(old),
            }
        }
        tg = Mock()
        tg.edit_photo.return_value = True
        with patch.object(uefa, "render_official", return_value=new):
            edited, same = uefa.refresh_all(tg, state, None)
        self.assertEqual((edited, same), (1, 0))
        tg.edit_photo.assert_called_once_with(22, "goal", new)

    def test_manual_ignores_later_espn_uniform(self):
        state = base.KitState(
            event_id="X",
            fallback_kit="away",
            active_kit="away",
        )
        base.set_manual_kit(state, "home")
        base.set_espn_kit(state, "third")
        self.assertEqual(state.espn_kit, "third")
        self.assertEqual(state.active_kit, "home")

    def test_production_theme_is_fixed_in_ucl(self):
        try:
            import portrait_graphics
        except ImportError:
            self.skipTest("Eseguito nel repository completo")
        self.assertEqual(portrait_graphics.theme("home", "uefa.champions"), "ucl")
        self.assertEqual(portrait_graphics.theme("away", "uefa.champions"), "ucl")
        self.assertEqual(portrait_graphics.theme("third", "uefa.champions"), "ucl")

    def test_production_theme_is_fixed_in_uel(self):
        try:
            import portrait_graphics
        except ImportError:
            self.skipTest("Eseguito nel repository completo")
        self.assertEqual(portrait_graphics.theme("home", "uefa.europa"), "uel")
        self.assertEqual(portrait_graphics.theme("third", "uefa.europa"), "uel")

    def test_production_theme_is_fixed_in_conference(self):
        try:
            import portrait_graphics
        except ImportError:
            self.skipTest("Eseguito nel repository completo")
        self.assertEqual(
            portrait_graphics.theme("home", "uefa.europa.conf"),
            "conference",
        )
        self.assertEqual(
            portrait_graphics.theme("away", "uefa.europa.conf"),
            "conference",
        )


if __name__ == "__main__":
    unittest.main()
