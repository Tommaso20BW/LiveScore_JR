import unittest
from PIL import Image
from portrait_graphics import phase_group_positions, visible_logo_bbox


class PhaseScoreCenterTests(unittest.TestCase):
    def test_score_center_is_independent_of_logo_width_padding_and_presence(self):
        narrow = Image.new('RGBA', (180, 120))
        narrow.paste('white', (41, 10, 91, 110))
        wide = Image.new('RGBA', (200, 120))
        wide.paste('white', (8, 10, 158, 110))
        for home, away in [(narrow, wide), (wide, narrow), (None, wide),
                           (narrow, None), (None, None)]:
            for width in [120, 121, 240]:
                with self.subTest(home=home, away=away, width=width):
                    sx, hx, ax = phase_group_positions(home, away, width)
                    self.assertLessEqual(abs(sx + width / 2 - 543), .5)
                    if home is not None:
                        self.assertEqual(sx - (hx + visible_logo_bbox(home)[2]), 28)
                    else:
                        self.assertIsNone(hx)
                    if away is not None:
                        self.assertEqual(ax + visible_logo_bbox(away)[0] - (sx + width), 28)
                    else:
                        self.assertIsNone(ax)
