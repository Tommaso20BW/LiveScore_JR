import unittest
from unittest.mock import patch
from PIL import Image
import portrait_graphics as p
import goal_graphics as g

class LogoAlignmentTests(unittest.TestCase):
    def test_unequal_widths_and_reversed_order(self):
        for widths in [(40,64), (64,40), (40,41)]:
            marks = [Image.new('RGBA',(w,64),'white') for w in widths]
            positions = list(p.centered_logo_positions(marks,p.W/2))
            left = positions[0][1]
            right = positions[-1][1]+positions[-1][0].width
            self.assertLessEqual(abs((left+right)/2-p.W/2),.5)
            self.assertEqual(positions[1][1]-(left+widths[0]),20)

    def test_transparent_padding_does_not_affect_logo(self):
        source = Image.new('RGBA',(200,200))
        source.paste('white',(70,10,110,90))
        with patch.object(g,'resolve_team_logo_source',return_value=(source,'ESPN')):
            self.assertEqual(p.logo('test','1','home',g.DEFAULT_ASSET_DIR,64).size,(32,64))

    def test_missing_logo_centers_remaining(self):
        mark = Image.new('RGBA',(40,64),'white')
        self.assertEqual(list(p.centered_logo_positions([None,mark],543))[0][1],523)
