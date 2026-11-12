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
