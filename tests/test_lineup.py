import unittest
from types import SimpleNamespace
from unittest import mock

from livescore.graphics import lineup as graphic
from livescore.match import lineup


def _roster(formation, places, team_id='162'):
    """Riepilogo ESPN minimo: 11 titolari con posto e ruolo, più una riserva."""
    roster = [{'starter': True, 'formationPlace': str(place), 'position': {'abbreviation': pos},
               'athlete': {'id': str(place), 'lastName': f'Cognome{place}', 'firstName': 'Nome',
                           'displayName': f'Nome Cognome{place}'}} for place, pos in places]
    roster.append({'starter': False, 'formationPlace': '0', 'position': {'abbreviation': 'SUB'},
                   'athlete': {'id': '99', 'lastName': 'Riserva'}})
    return {'rosters': [{'team': {'id': team_id}, 'formation': formation, 'roster': roster}]}


# Posti ESPN reali (partite di ottobre 2026).
F4231 = [(1, 'G'), (2, 'RB'), (3, 'LB'), (4, 'LM'), (5, 'CD-R'), (6, 'CD-L'), (7, 'AM-R'),
         (8, 'RM'), (9, 'F'), (10, 'AM'), (11, 'AM-L')]
F3421 = [(1, 'G'), (2, 'RM'), (3, 'LM'), (4, 'CD-L'), (5, 'CD'), (6, 'CD-R'), (7, 'CM-R'),
         (8, 'CM-L'), (9, 'F'), (10, 'CF-R'), (11, 'CF-L')]


def _places(lines):
    return [[pl['place'] for pl in line] for line in lines]


class ArrangeTest(unittest.TestCase):
    def test_table_formation(self):
        lu = lineup.extract_lineup(_roster('4-2-3-1', F4231))
        self.assertEqual(_places(graphic.arrange(lu['formation'], lu['players'])),
                         [[1], [3, 6, 5, 2], [4, 8], [11, 10, 7], [9]])

    def test_unknown_formation_uses_roles(self):
        # stesso 3-4-2-1 ma con un nome di modulo non in tabella
        lu = lineup.extract_lineup(_roster('3-4-2-1x', F3421))
        lines = graphic.arrange('3-4-2-1x', lu['players'])
        self.assertEqual(_places(lines), [[1], [4, 5, 6], [3, 8, 7, 2], [11, 10], [9]])

    def test_incomplete_lineup_is_ignored(self):
        data = _roster('4-2-3-1', F4231[:10])
        self.assertIsNone(lineup.extract_lineup(data))
        self.assertIsNone(lineup.extract_lineup(_roster('4-2-3-1', F4231, team_id='478')))

    def test_same_surname_gets_initial(self):
        players = [{'last': 'Esposito', 'first': 'Pio'}, {'last': 'Esposito', 'first': 'Sebastiano'},
                   {'last': 'Kean', 'first': 'Moise'}]
        names = graphic.display_names(players)
        self.assertEqual([names[id(p)] for p in players], ['P. ESPOSITO', 'S. ESPOSITO', 'KEAN'])


class AnnounceTest(unittest.TestCase):
    def setUp(self):
        lineup._next_try = 0.0
        patches = [
            mock.patch.object(lineup.settings, 'GOAL_GRAPHICS_ENABLED', True),
            mock.patch.object(lineup, 'render', return_value=b'png'),
            mock.patch.object(lineup.gist, 'salva_stato_su_gist'),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _ctx(self, uniform_color, status='NS', state=None):
        data = _roster('3-4-2-1', F3421)
        data['boxscore'] = {'teams': [{'team': {'id': '162', 'uniform': {'color': uniform_color}}}]}
        return SimpleNamespace(home_id='162', away_id='465', home_name='Italia', away_name='Turchia',
                               home_name_raw='Italy', away_name_raw='Türkiye', e_comp='🏆', hashtag='#ITATUR',
                               status=status, data=data, state=state if state is not None else {},
                               state_changed=False)

    def test_sent_once_then_photo_edited_on_kit_change(self):
        ctx = self._ctx('0000ff')
        with mock.patch.object(lineup.tg, '_send_telegram_event_photo_get_id', return_value=(77, True)) as send, \
                mock.patch.object(lineup.tg, 'edit_telegram_goal_photo', return_value=True) as edit:
            lineup.announce_lineup(ctx)
            lineup.announce_lineup(ctx)              # stesso giro dopo: nessun nuovo invio
            self.assertEqual(send.call_count, 1)
            self.assertEqual(ctx.state['lineup']['kit'], 'ita_home')
            edit.assert_not_called()

            ctx = self._ctx('ffffff', status='1H', state=ctx.state)   # maglia bianca
            lineup.announce_lineup(ctx)
            self.assertEqual(send.call_count, 1)
            edit.assert_called_once()
            self.assertEqual(edit.call_args[0][0], 77)
            self.assertEqual(ctx.state['lineup']['kit'], 'ita_away')

    def test_failed_edit_is_retried_later(self):
        state = {}
        with mock.patch.object(lineup.tg, '_send_telegram_event_photo_get_id', return_value=(5, True)):
            lineup.announce_lineup(self._ctx('0000ff', state=state))
        with mock.patch.object(lineup.tg, 'edit_telegram_goal_photo', return_value=False):
            lineup.announce_lineup(self._ctx('ffffff', state=state))
        self.assertEqual(state['lineup']['kit'], 'ita_home')     # non segnata come aggiornata
        self.assertGreater(lineup._next_try, 0)

    def test_not_for_juventus(self):
        ctx = self._ctx('0000ff')
        ctx.home_id = '111'
        with mock.patch.object(lineup.tg, '_send_telegram_event_photo_get_id') as send:
            lineup.announce_lineup(ctx)
        send.assert_not_called()


if __name__ == '__main__':
    unittest.main()
