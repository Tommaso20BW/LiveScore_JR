import unittest
from PIL import Image
from livescore.graphics import goal as g


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


class CelebrationPosesTests(unittest.TestCase):
    @unittest.skipUnless((g.DEFAULT_ASSET_DIR / 'players').is_dir(), 'asset privati non presenti')
    def test_scream_and_point_sky_exist_for_every_player_and_kit(self):
        for player in g.load_players():
            for kit in ('home', 'away', 'third'):
                for pose in ('scream', 'point_sky'):
                    with self.subTest(player=player.slug, kit=kit, pose=pose):
                        path = g.resolve_player_path(player, kit, pose)
                        self.assertTrue(path.exists(), path.name)

    def test_celebration_file_names(self):
        player = g.find_player('Kenan Yildiz')
        self.assertEqual(g.player_filename(player, 'third', 'kiss_crest'),
                         'kenan_yildiz_third_black_pose_05_kiss_crest.png')
        keeper = g.find_player('Guglielmo Vicario')
        self.assertEqual(g.player_filename(keeper, 'away', 'shush'),
                         'guglielmo_vicario_keeper_green_pose_06_shush.png')

    def test_automatic_choice_without_player_uses_base_poses(self):
        for i in range(50):
            self.assertIn(g.choose_pose(f'evento-{i}'), g.AUTO_POSES)

    def test_automatic_choice_includes_celebrations_when_present(self):
        avail = ('arms_crossed', 'pointing', 'scream', 'point_sky', 'shush')
        scelte = {g.choose_pose(f'evento-{i}', None, avail) for i in range(200)}
        self.assertEqual(scelte, set(avail))

    def test_requested_pose_missing_for_kit_falls_back(self):
        avail = ('arms_crossed', 'pointing', 'scream')
        self.assertIn(g.choose_pose('x', 'kiss_crest', avail), avail)
        self.assertEqual(g.choose_pose('x', 'scream', avail), 'scream')
        self.assertEqual(g.choose_pose('x', 'kiss_crest'), 'kiss_crest')

    @unittest.skipUnless((g.DEFAULT_ASSET_DIR / 'players').is_dir(), 'asset privati non presenti')
    def test_available_poses_reads_files(self):
        yildiz = g.find_player('Kenan Yildiz')
        self.assertIn('kiss_crest', g.available_poses(yildiz, 'home'))
        vicario = g.find_player('Guglielmo Vicario')
        self.assertNotIn('kiss_crest', g.available_poses(vicario, 'home'))


class RaisedHandsScaleTests(unittest.TestCase):
    def _figure(self, top):
        from PIL import Image, ImageDraw
        im = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle((40, top, 59, 99), fill=(255, 0, 0, 255))
        return im

    def test_scale_does_not_depend_on_hand_height(self):
        from livescore.graphics.portrait import anchored_player
        high, _, up_high = anchored_player(self._figure(5), 200, 20)
        low, _, up_low = anchored_player(self._figure(30), 200, 20)
        self.assertEqual(high.width, low.width)          # stessa misura del giocatore
        self.assertEqual(high.height - up_high, 200)     # fondo sempre allineato
        self.assertEqual(low.height - up_low, 200)
        self.assertGreater(up_high, 0)                   # mani più alte: sporgono sopra
        self.assertLess(up_low, 0)                       # più basse: ritratto abbassato

    def test_without_ref_top_keeps_old_behaviour(self):
        from livescore.graphics.portrait import anchored_player
        portrait, anchor = anchored_player(self._figure(20), 160)
        self.assertEqual(portrait.height, 160)
        self.assertAlmostEqual(anchor, 20)

    def test_zoom_enlarges_and_keeps_bottom(self):
        from livescore.graphics.portrait import anchored_player
        normal, _ = anchored_player(self._figure(20), 160)
        big, _, up = anchored_player(self._figure(20), 160, None, 1.5)
        self.assertEqual(big.height, 240)
        self.assertEqual(big.height - up, 160)           # il fondo resta dov'era
        self.assertGreater(big.width, normal.width)
