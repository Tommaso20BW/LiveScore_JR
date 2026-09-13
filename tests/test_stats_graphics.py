import unittest
from unittest.mock import patch, call
from PIL import Image
import stats_graphics as stats
import juve_bot_espn as bot
import portrait_graphics as portrait


class StatsGraphicsTests(unittest.TestCase):
    def test_logos_use_shared_card_renderer_in_home_away_order(self):
        mark = Image.new('RGBA', (20, 30), 'white')
        with patch.object(portrait, 'logo', return_value=mark) as logo:
            stats.build_html(rows=[], kit='home', competition='ita.1', league_name='Serie A',
                momento='FT', home_id='110', away_id='111', home_name='Inter', away_name='Juventus')
        self.assertEqual(logo.call_args_list, [
            call('Inter', '110', 'home', stats.g.DEFAULT_ASSET_DIR, 128),
            call('Juventus', '111', 'home', stats.g.DEFAULT_ASSET_DIR, 128)])

    def test_zero_track_and_missing_values(self):
        html = stats.rows_html([('FUORIGIOCO', '0', '0'), ('xG', None, '0')])
        self.assertIn('track empty', html)
        self.assertNotIn('<i', html)
        self.assertNotIn('xG', html)

    def test_single_sided_bar_has_no_gap_or_fake_zero_segment(self):
        self.assertIn('<b style="flex:1"></b>', stats.rows_html([('ESPULSI', 0, 1)]))
        self.assertNotIn('<i', stats.rows_html([('ESPULSI', 0, 1)]))

    def test_only_juventus_competitive_matches(self):
        self.assertFalse(bot.stats_eligible('110', '103', 'ita.1'))
        self.assertFalse(bot.stats_eligible('111', '110', 'friendly.club'))
        for league in ('ita.1', 'ita.coppa_italia', 'ita.super_cup', 'uefa.champions'):
            self.assertTrue(bot.stats_eligible('110', '111', league))

    def test_phases_and_required_order(self):
        self.assertEqual(stats.PHASES, {'HT': 'half', '2H_END': 'end_of_90', 'FT': 'full'})
        self.assertEqual(stats.ORDER[:2], ('POSSESSO', 'xG'))
        self.assertIn('ESPULSI', stats.ORDER)
        self.assertIn('PARATE', stats.ORDER)

    def test_real_data_pipeline_missing_and_zero_xg(self):
        data = {'boxscore': {'teams': [
            {'homeAway': 'home', 'statistics': [{'name': 'redCards', 'displayValue': '1'}]},
            {'homeAway': 'away', 'statistics': [{'name': 'saves', 'displayValue': '5'}]}]}}
        for xg in (None, ('0.00', '0.00')):
            with patch.object(bot, 'rileva_kit_juve', return_value='away'), \
                 patch.object(bot, 'recupera_xg_espn', return_value=xg), \
                 patch.object(stats, 'build_html', return_value='html') as build, \
                 patch.object(stats, 'render', return_value='stats.png'):
                self.assertEqual(bot.recupera_e_genera_stats_html(data, '110', '111', 'Inter',
                    'Juventus', 0, 0, 'HT', league_slug='ita.1'), 'stats.png')
                rows = build.call_args.kwargs['rows']
                self.assertEqual('xG' in [row[0] for row in rows], xg is not None)
                self.assertIn(('ESPULSI', '1', '0'), rows)
                self.assertIn(('PARATE', '0', '5'), rows)

    def test_home_brand_changes_only_logo_pixels_no_shadow(self):
        background = Image.new('RGBA', (portrait.W, portrait.H), '#eeeeee')
        result = portrait.brand(background.copy(), 'home', __import__('goal_graphics').DEFAULT_ASSET_DIR)
        self.assertEqual(result.getpixel((1000, 100)), background.getpixel((1000, 100)))

    def test_away_theme_juventus_is_right_and_layout_is_approved(self):
        html = stats.build_html(rows=[('POSSESSO', '43%', '57%')], kit='home', competition='ita.1',
            league_name='Serie A', momento='2H_END', home_id='110', away_id='111',
            home_name='Inter', away_name='Juventus')
        self.assertIn('.home{color:#fff}', html)
        self.assertIn('.away{color:#FACA02}', html)
        self.assertIn('height:88px', html)
        self.assertIn('background:#39434d', html)
        self.assertIn('JR STATS • SERIE A', html)
        self.assertNotIn('{{', html)


if __name__ == '__main__':
    unittest.main()
