import unittest
from PIL import Image, ImageFont
import goal_graphics as g
import portrait_graphics as p


class KeeperKitsTests(unittest.TestCase):
    def test_saved_minutes_have_four_pixel_clearance_in_upper_s(self):
        heading = p.saved_heading(g.DEFAULT_ASSET_DIR)
        font = ImageFont.truetype(str(g.DEFAULT_ASSET_DIR/'fonts/DharmaGothicEBold.otf'), 24)
        mask = heading.getchannel('A').point(lambda a: 255 if a > 100 else 0)
        for minute in ("1'", "56'", "90+2'", "90+12'", "120+12'"):
            with self.subTest(minute=minute):
                x, y = p.saved_minute_position(heading, minute, font)
                x, y = x-p.M, y-p.M
                box = font.getbbox(minute)
                self.assertLess(y, 51)
                self.assertIsNone(mask.crop((x-4,y-4,x+box[2]-box[0]+4,y+box[3]-box[1]+4)).getbbox())

    def test_all_keepers_have_both_poses_in_every_kit(self):
        for name in ('Kamil Grabara', 'Carlo Pinsoglio', 'Guglielmo Vicario'):
            player = g.find_player(name)
            for kit, color in (('home', 'blue'), ('away', 'green'), ('third', 'orange')):
                for pose in ('arms_crossed', 'pointing'):
                    with self.subTest(name=name, kit=kit, pose=pose):
                        path = g.resolve_player_path(player, kit, pose)
                        self.assertIn('keeper_' + color, path.name)
                        with Image.open(path) as source:
                            self.assertTrue(g._has_real_transparency(source))
