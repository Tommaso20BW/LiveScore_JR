import io
import unittest
from unittest.mock import patch
from PIL import Image
import goal_graphics as g
import portrait_graphics as p

class PortraitTests(unittest.TestCase):
    def test_domestic_saved_matches_goal_kit(self):
        for kit in ('home', 'away', 'third'):
            for comp in ('ita.1', 'ita.coppa_italia', 'ita.super_cup'):
                self.assertEqual(p.theme(kit, comp, True), p.theme(kit, comp, False))

    def test_competition_priority_and_conference_slug(self):
        for comp,expected in [('uefa.champions','ucl'),('uefa.europa','uel'),('uefa.europa.conf','conference')]:
            self.assertEqual(p.theme('away',comp,True),expected)

    def test_goal_and_missing_player_are_portrait(self):
        with patch.object(g,'_remote_espn_team_logo',return_value=None):
            for kind in ('goal','own goal','penalty goal'):
                r=g.render_goal_card(scorer_name='Test Missing',minute='90+12',home_name='Juventus',away_name='Inter',home_goals=1,away_goals=0,kit='home',goal_type=kind)
                self.assertEqual(Image.open(io.BytesIO(r.png)).size,(1086,1448))
                self.assertIsNone(r.player)

    def test_espn_logo_keeps_rgb(self):
        source=Image.new('RGBA',(40,40),'red')
        with patch.object(g,'resolve_team_logo_source',return_value=(source,'ESPN')):
            self.assertEqual(p.logo('Test','1','ucl',g.DEFAULT_ASSET_DIR,40).getpixel((20,20)),(255,0,0,255))

    def test_fclogo_is_textured(self):
        source=Image.new('RGBA',(40,40),'red')
        with patch.object(g,'resolve_team_logo_source',return_value=(source,'FCLogo')):
            self.assertNotEqual(p.logo('Test','1','ucl',g.DEFAULT_ASSET_DIR,40).getpixel((20,20)),(255,0,0,255))

    def test_phase_rejects_extra_time(self):
        with self.assertRaises(ValueError):
            p.phase(kind='extra_time',home_name='Juventus',away_name='Inter',home_id='111',away_id='110')
