import json
import unittest
from unittest.mock import Mock
from manual_graphics.webapp_payload import parse_webapp_update


class WebAppPayloadTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Mock()
        self.catalog.teams.return_value = [{'name': 'Atalanta', 'id': '105'}]
        self.catalog.players.return_value = ['Kenan Yildiz']

    def update(self, data):
        return {'message': {'web_app_data': {'data': json.dumps({
            'v': 1, 'action': 'render', 'session': 'run-1', 'data': data
        })}}}

    def test_goal_becomes_ready_render_request(self):
        state, effects = parse_webapp_update({}, self.update({
            'kind': 'goal', 'competition': 'ita.1', 'kit': 'home', 'side': 'home',
            'opponent': {'name': 'Atalanta'}, 'player': 'Kenan Yildiz',
            'minute': '90+4', 'pose': 'arms_crossed', 'score': [2, 1]
        }), self.catalog, 100, expected_session='run-1')
        self.assertEqual(effects, [])
        self.assertEqual(state['status'], 'ready')
        self.assertEqual(state['source'], 'webapp')
        self.assertEqual(state['data']['minute'], '90+4')
        self.assertEqual(state['data']['score'], (2, 1))

    def test_busy_session_rejects_second_request(self):
        state = {'status': 'rendering'}
        new_state, effects = parse_webapp_update(state, self.update({}), self.catalog, 100, expected_session='run-1')
        self.assertIs(new_state, state)
        self.assertTrue(effects)

    def test_saved_requires_goalkeeper_catalog_match(self):
        self.catalog.players.return_value = []
        state, effects = parse_webapp_update({}, self.update({
            'kind': 'saved', 'competition': 'ita.1', 'kit': 'home', 'side': 'home',
            'opponent': {'name': 'Atalanta'}, 'player': 'Kenan Yildiz',
            'minute': '10', 'pose': 'pointing', 'score': [0, 0]
        }), self.catalog, 100, expected_session='run-1')
        self.assertNotEqual(state.get('status'), 'ready')
        self.assertTrue(effects)
        self.catalog.players.assert_called_with('Kenan Yildiz', goalkeeper=True)

    def test_stale_session_is_silently_ignored(self):
        state = {'status': 'completed'}
        new_state, effects = parse_webapp_update(
            state, self.update({}), self.catalog, 100, expected_session='run-2')
        self.assertIs(new_state, state)
        self.assertEqual(effects, [])
