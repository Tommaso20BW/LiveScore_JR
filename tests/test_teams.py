import unittest

from livescore.match import teams


class GraphicsTeamTests(unittest.TestCase):
    def test_juventus_except_friendlies(self):
        self.assertEqual(teams.graphics_team('111', '114', 'ita.1', 'Serie A'), '111')
        self.assertEqual(teams.graphics_team('111', '999', 'club.friendly', 'Club Friendly'), '')

    def test_italy_always_even_friendlies(self):
        self.assertEqual(teams.graphics_team('162', '164', 'fifa.world', 'FIFA World Cup'), '162')
        self.assertEqual(teams.graphics_team('164', '162', 'fifa.friendly', 'International Friendly'), '162')

    def test_other_matches_have_no_graphics(self):
        self.assertEqual(teams.graphics_team('114', '110', 'ita.1', 'Serie A'), '')

    def test_italy_theme_follows_the_shirt_colour(self):
        def data(colour):
            return {"boxscore": {"teams": [{"team": {"id": "162", "uniform": {"type": "home", "color": colour}}}]}}
        # Moldova-Italia: fuori casa ma in azzurro -> tema azzurro.
        self.assertEqual(teams.graphics_kit(data("0000FF"), '999', '162', 'Moldova', 'Italy'), 'ita_home')
        # Israele-Italia: in bianco -> tema bianco; anche in casa, se ESPN dice bianco.
        self.assertEqual(teams.graphics_kit(data("FFFFFF"), '461', '162', 'Israel', 'Italy'), 'ita_away')
        self.assertEqual(teams.graphics_kit(data("FFFFFF"), '162', '461', 'Italy', 'Israel'), 'ita_away')

    def test_italy_theme_follows_home_and_away(self):
        self.assertEqual(teams.graphics_kit({}, '162', '164', 'Italy', 'Spain'), 'ita_home')
        self.assertEqual(teams.graphics_kit({}, '164', '162', 'Spain', 'Italy'), 'ita_away')


if __name__ == '__main__':
    unittest.main()
