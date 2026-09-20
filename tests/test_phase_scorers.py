import unittest
import juve_bot_espn as bot


def goal(name, minute, period=0, team='111', kind='goal'):
    return dict(type=kind, player_name=name, minute=int(minute.split('+')[0]),
                minute_disp=minute, period=period, team_id=team)


class PhaseScorersTests(unittest.TestCase):
    def test_half_includes_recovery_not_second_half(self):
        events = [goal('Kenan Yildiz', '25', 1), goal('Kenan Yildiz', '45+12', 1),
                  goal('Later Player', '49', 2)]
        result = bot.phase_scorers_line(events, '111', '2', 'half')
        self.assertIn("25', 45+12'", result)
        self.assertNotIn('Later', result)

    def test_end_of_90_excludes_extra_time_even_on_late_recovery(self):
        events = [goal('Normal Player', '90+8'), goal('Extra Player', '96', 3)]
        result = bot.phase_scorers_line(events, '111', '2', 'end_of_90')
        self.assertIn("90+8'", result)
        self.assertNotIn('Extra', result)

    def test_extra_time_messages_have_no_list(self):
        for phase in ('1ET_START', '1ET_END', '2ET_START', 'ET_END_PENS'):
            self.assertEqual(bot.phase_scorers_line([goal('Kenan Yildiz', '25')], '111', '2', phase), '')

    def test_scoreless_has_no_empty_marker(self):
        self.assertEqual(bot.phase_scorers_line([], '111', '2', 'half'), '')

    def test_own_goal_and_opponent_use_ft_format(self):
        events = [goal('Own Player', '15', 1, kind='own goal'),
                  goal('Away Player', '30', 1, team='2', kind='penalty goal')]
        result = bot.phase_scorers_line(events, '111', '2', 'half')
        self.assertIn('(Autogol)', result)
        self.assertIn("30'", result)
