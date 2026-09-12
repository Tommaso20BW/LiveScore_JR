import unittest
from PIL import Image
import goal_graphics as g


class KeeperKitsTests(unittest.TestCase):
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
